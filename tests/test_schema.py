# tests/test_schema.py

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import Engine, inspect
from sqlalchemy import MetaData, Table
from tests.utils.schema_utils import check_primary_key, check_foreign_keys

# Define table names as constants
CUSTOMER = "customer"
ORDER = "order"
PRODUCT = "product"
PAYMENT = "payment"
ORDER_ITEM = "order_item"

# Test to check if the required tables exist in the database
def test_required_tables_exist(db_engine: Engine):
    inspector = inspect(db_engine)

    tables = inspector.get_table_names()

    expected_tables = [
        CUSTOMER,
        ORDER,
        PRODUCT,
        PAYMENT,
        ORDER_ITEM,
    ]

    for table in expected_tables:
        assert table in tables

''' 
Test to check if the required columns exist in each table.
This test checks for the presence of specific columns in the "customers", "orders", "products", and "payments" tables. 
It uses SQLAlchemy's inspector to retrieve the column names for each
'''
def test_customers_columns(db_engine: Engine):
    inspector = inspect(db_engine)

    columns = inspector.get_columns(CUSTOMER)
    actual_columns = {col["name"] for col in columns}

    expected_columns = {
        "customer_id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "status",
        "created_at",
    }

    assert expected_columns.issubset(actual_columns)

def test_orders_columns(db_engine: Engine):
    inspector = inspect(db_engine)

    columns = inspector.get_columns(ORDER)
    actual_columns = {col["name"] for col in columns}

    expected_columns = {
        "order_id",
        "customer_id",
        "order_date",
        "total_amount",
        "status",
    }

    assert expected_columns.issubset(actual_columns)

def test_products_columns(db_engine: Engine):
    inspector = inspect(db_engine)

    columns = inspector.get_columns(PRODUCT)
    actual_columns = {col["name"] for col in columns}

    expected_columns = {
        "product_id",
        "product_name",
        "category",
        "price",
        "stock_quantity",
        "status",
        "created_at",
    }

    assert expected_columns.issubset(actual_columns)

def test_payments_columns(db_engine: Engine):
    inspector = inspect(db_engine)

    columns = inspector.get_columns(PAYMENT)
    actual_columns = {col["name"] for col in columns}

    expected_columns = {
        "payment_id",
        "order_id",
        "amount",
        "payment_method",
        "payment_date",
        "status",
        "transaction_id",
    }

    assert expected_columns.issubset(actual_columns)

def test_order_items_columns(db_engine: Engine):
    inspector = inspect(db_engine)

    columns = inspector.get_columns("order_item")
    actual_columns = {col["name"] for col in columns}

    expected_columns = {
        "order_item_id",
        "order_id",
        "product_id",
        "quantity",
        "unit_price",
    }

    assert expected_columns.issubset(actual_columns)
    

# Check data types of columns in each table
def test_customers_column_types(db_engine: Engine):
    inspector = inspect(db_engine)

    columns = inspector.get_columns(CUSTOMER)
    column_types = {col["name"]: col["type"].__class__.__name__ for col in columns}

    expected_column_types = {
        "customer_id": "INTEGER",
        "first_name": "VARCHAR",
        "last_name": "VARCHAR",
        "email": "VARCHAR",
        "phone": "VARCHAR",
        "status": "VARCHAR",
        "created_at": "TIMESTAMP",
    }

    assert expected_column_types == column_types

# Check Primary Keys
def test_customers_primary_key(db_engine: Engine):
    check_primary_key(db_engine, table_name=CUSTOMER, expected_primary_key=["customer_id"])

def test_orders_primary_key(db_engine: Engine):
    check_primary_key(db_engine, table_name=ORDER, expected_primary_key=["order_id"])

def test_products_primary_key(db_engine: Engine):
    check_primary_key(db_engine, table_name=PRODUCT, expected_primary_key=["product_id"])

def test_payments_primary_key(db_engine: Engine):
    check_primary_key(db_engine, table_name=PAYMENT, expected_primary_key=["payment_id"])

def test_order_items_primary_key(db_engine: Engine):
    check_primary_key(db_engine, table_name=ORDER_ITEM, expected_primary_key=["order_item_id"])


# Check Foreign Keys


def test_orders_foreign_key(db_engine: Engine):
    check_foreign_keys(
        db_engine,
        table_name=ORDER,
        expected_foreign_keys={
            "customer_id": (CUSTOMER, "customer_id"),
        }
    )

def test_payments_foreign_key(db_engine: Engine):
    check_foreign_keys(
        db_engine,
        table_name=PAYMENT,
        expected_foreign_keys={
            "order_id": (ORDER, "order_id"),
        }
    )

def test_order_items_foreign_key(db_engine: Engine):
    check_foreign_keys(
        db_engine,
        table_name=ORDER_ITEM,
        expected_foreign_keys={
            "order_id": (ORDER, "order_id"),
            "product_id": (PRODUCT, "product_id"),
        }
    )