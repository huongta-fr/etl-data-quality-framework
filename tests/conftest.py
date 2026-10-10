import pytest
import json
from pathlib import Path
from utils.db import get_engine

METADATA_PATH = Path("logs/etl_metadata.json")

@pytest.fixture(scope="session")
def db_engine():
    engine = get_engine()
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def etl_run():
    metadata = json.loads(
        METADATA_PATH.read_text(encoding="utf-8")
    )

    run_id = metadata["current_db"]["run_id"]

    run = next(
        (
            r for r in metadata["successful_runs"]
            if r["run_id"] == run_id
        ),
        None,
    )

    assert run is not None, (
        f"Missing ETL metadata for run_id={run_id}"
    )

    assert run["status"] == "SUCCESS"
    assert run["load_mode"] == "full_refresh"

    return run