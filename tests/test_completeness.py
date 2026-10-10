import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.utils.completeness_utils import check_record_completeness


@pytest.mark.parametrize(
    "dataset_name",
    [
        "customers",
        "products",
        "orders",
        "order_items",
        "payments",
    ],
)
def test_record_completeness(
    db_engine,
    etl_run,
    dataset_name,
):
    dataset = etl_run["datasets"][dataset_name]

    check_record_completeness(
        db_engine,
        dataset,
    )