from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


def check_record_completeness(
    db_engine: Engine,
    dataset: dict,
):
    source_path = Path(dataset["source_path"])
    rejected_path = dataset.get("rejected_path")

    assert source_path.is_file(), (
        f"Source file not found: {source_path}"
    )

    source_count = len(pd.read_csv(source_path))

    if rejected_path:
        rejected_path = Path(rejected_path)
        assert rejected_path.is_file(), (
            f"Rejected file not found: {rejected_path}"
        )
        rejected_count = len(pd.read_csv(rejected_path))
    else:
        rejected_count = 0

    # target_table must come from trusted ETL configuration.
    table = dataset["target_table"]

    with db_engine.connect() as conn:
        db_count = conn.execute(
            text(f'SELECT COUNT(*) FROM "{table}"')
        ).scalar_one()

    assert source_count == dataset["source_rows"]
    assert rejected_count == dataset["rejected_rows"]
    assert db_count == dataset["loaded_rows"]

    assert source_count == db_count + rejected_count, (
        f"Completeness FAILED for {table}: "
        f"source={source_count}, "
        f"db={db_count}, "
        f"rejected={rejected_count}"
    )