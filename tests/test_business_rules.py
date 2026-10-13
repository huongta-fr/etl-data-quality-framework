"""Business rules: target, rejected decisions, transformation decisions.

Run: pytest -v tests/test_business_rules.py

The target suite reads PostgreSQL. The other two suites run controlled input
through the actual business-rule validator, without modifying PostgreSQL.
They do NOT validate historical rejected CSVs/logs from an ETL run.
"""

from pathlib import Path
import sys

import pandas as pd
import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.config_loader import load_config
from utils.db import get_engine
from src.transform import validate_business_rules  # Adapt import if your module is elsewhere.


# Independent business specification / expected SQL checks.
# Do not derive expected behavior from transform's rule handlers.
RULES = [
    ("valid_customer_status", 'customer',
     "status IS NOT NULL AND status NOT IN ('ACTIVE', 'INACTIVE')"),
    ("valid_product_status", 'product',
     "status IS NOT NULL AND status NOT IN ('ACTIVE', 'INACTIVE')"),
    ("positive_product_price", 'product', "price IS NOT NULL AND price <= 0"),
    ("non_negative_stock", 'product', "stock_quantity IS NOT NULL AND stock_quantity < 0"),
    ("valid_order_status", '"order"',
     "status IS NOT NULL AND status NOT IN "
     "('PENDING', 'PAID', 'SHIPPED', 'COMPLETED', 'CANCELLED')"),
    ("positive_quantity", 'order_item', "quantity IS NOT NULL AND quantity <= 0"),
    ("positive_unit_price", 'order_item', "unit_price IS NOT NULL AND unit_price <= 0"),
    ("valid_payment_status", 'payment',
     "status IS NOT NULL AND status NOT IN ('SUCCESS', 'FAILED', 'PENDING')"),
    ("valid_payment_method", 'payment',
     "payment_method IS NOT NULL AND payment_method NOT IN "
     "('CARD', 'PAYPAL', 'BANK_TRANSFER')"),
    ("payment_amount_matches_order_total", 'payment AS p',
     'p.amount IS NOT NULL AND o.total_amount IS NOT NULL '
     'AND ABS(p.amount - o.total_amount) > 0.01'),
]

# Each row: rule_name, dataset_name, column, accepted value, rejected value.
# Boundary values are intentional (0 for strictly positive, -1 for nonnegative).
CASES = [
    ("valid_customer_status", "customers", "status", "ACTIVE", "UNKNOWN"),
    ("valid_product_status", "products", "status", "INACTIVE", "UNKNOWN"),
    ("positive_product_price", "products", "price", 0.01, 0),
    ("non_negative_stock", "products", "stock_quantity", 0, -1),
    ("valid_order_status", "orders", "status", "PAID", "INVALID"),
    ("positive_quantity", "order_items", "quantity", 1, 0),
    ("positive_unit_price", "order_items", "unit_price", 0.01, -1),
    ("valid_payment_status", "payments", "status", "SUCCESS", "UNKNOWN"),
    ("valid_payment_method", "payments", "payment_method", "CARD", "CASH"),
    ("payment_amount_matches_order_total", "payments", "amount", 100.0, 99.0),
]


@pytest.fixture(scope="module")
def config():
    return load_config("etl")


@pytest.fixture(scope="module")
def engine():
    db_engine = get_engine()  # utils.db.get_engine() takes no arguments.
    try:
        yield db_engine
    finally:
        db_engine.dispose()


def get_rule(config, dataset, name):
    rules = config["datasets"][dataset]["rules"]
    matches = [rule for rule in rules if rule["name"] == name]
    assert len(matches) == 1, f"Expected exactly one configured rule {name}"
    return matches[0]


def run_controlled_case(config, rule_name, dataset, column, good, bad):
    rule = get_rule(config, dataset, rule_name)
    # Same reference for both payments: order total = 100.
    references = {"orders": pd.DataFrame({"order_id": [42], "total_amount": [100.0]})}
    records = pd.DataFrame({
        "_test_id": ["valid", "invalid"],
        column: [good, bad],
    })
    if rule_name == "payment_amount_matches_order_total":
        records["order_id"] = 42
    clean, rejected_parts = validate_business_rules(
        dataset, records, [rule], references
    )
    rejected = (pd.concat(rejected_parts, ignore_index=True)
                if rejected_parts else pd.DataFrame(columns=[*records.columns, "reject_reason"]))
    return clean, rejected, rule


class TestTargetBusinessRules:
    """SQL validation of already-loaded records in PostgreSQL."""

    @pytest.mark.parametrize("rule_name,table,violation", RULES,
                             ids=[r[0] for r in RULES])
    def test_business_rule_target(self, engine, rule_name, table, violation):
        join = (' JOIN "order" AS o ON p.order_id = o.order_id'
                if rule_name == "payment_amount_matches_order_total" else "")
        with engine.connect() as connection:
            total = connection.execute(
                text(f"SELECT COUNT(*) FROM {table}{join}")
            ).scalar_one()
            invalid_count = connection.execute(
                text(f"SELECT COUNT(*) FROM {table}{join} WHERE {violation}")
            ).scalar_one()
        assert total > 0, f"{rule_name}: no rows available to validate"
        assert invalid_count == 0, (
            f"{rule_name}: {invalid_count} violating row(s) out of {total} checked"
        )


class TestRejectedBusinessRules:
    """Check actual reject decisions on controlled invalid data.

    Not an audit of ETL's previously persisted rejected records.
    """

    @pytest.mark.parametrize("rule_name,dataset,column,good,bad", CASES,
                             ids=[c[0] for c in CASES])
    def test_invalid_record_has_correct_reject_reason(
        self, config, rule_name, dataset, column, good, bad
    ):
        _, rejected, rule = run_controlled_case(
            config, rule_name, dataset, column, good, bad
        )
        actual = rejected.loc[rejected["_test_id"] == "invalid"]
        assert len(actual) == 1, f"{rule_name}: invalid input not rejected once"
        assert actual.iloc[0]["reject_reason"] == rule["reason"]
        # Independently assert that this fixture is indeed invalid.
        assert bad != good


class TestTransformationDecisions:
    """Check both acceptance and rejection against independent test fixtures."""

    @pytest.mark.parametrize("rule_name,dataset,column,good,bad", CASES,
                             ids=[c[0] for c in CASES])
    def test_accept_and_reject(self, config, rule_name, dataset, column, good, bad):
        clean, rejected, _ = run_controlled_case(
            config, rule_name, dataset, column, good, bad
        )
        assert clean["_test_id"].tolist() == ["valid"], (
            f"{rule_name}: valid input rejected or invalid input accepted"
        )
        assert rejected["_test_id"].tolist() == ["invalid"], (
            f"{rule_name}: expected exactly the invalid input to be rejected"
        )
