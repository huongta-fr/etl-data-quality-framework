"""Day 14: source-to-target PK reconciliation for the current full-refresh run."""
import pytest

from tests.utils.reconciliation_utils import reconcile_primary_keys


DATASETS = ["customers", "products", "orders", "order_items", "payments"]


@pytest.mark.parametrize("dataset_name", DATASETS)
def test_primary_key_reconciliation(db_engine, etl_run, dataset_name):
    reconcile_primary_keys(db_engine, etl_run, dataset_name)
