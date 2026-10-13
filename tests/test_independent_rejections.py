
"""Run with: python -m pytest tests/test_independent_rejections.py -v"""

import os
from pathlib import Path

import pytest

from tests.utils.independent_validator import (
    compare_seed,
    discover_seeds,
    EVALUATION_ORDER,
)

DATA_DIR = Path(
    os.environ.get(
        "ETL_DATA_DIR",
        Path(__file__).resolve().parents[1] / "data"
    )
)


@pytest.fixture(scope="module")
def validation_results():
    cache = {}

    def get_results(seed):
        if seed not in cache:
            cache[seed] = compare_seed(
                DATA_DIR / "raw" / seed,
                DATA_DIR / "rejected" / seed
            )
        return cache[seed]

    return get_results


@pytest.mark.parametrize("seed", discover_seeds(DATA_DIR))
@pytest.mark.parametrize("table", EVALUATION_ORDER)
def test_rejected_rows_match_independent_validator(
    seed, table, validation_results
):
    results = validation_results(seed)
    outcome = results[table]

    false_rows = outcome["false_rejections"]
    missed_rows = outcome["missed_rejections"]

    assert not false_rows and not missed_rows, (
        f'{seed}/{table}: actual={outcome["actual_count"]}, '
        f'expected={outcome["expected_count"]}, '
        f'false_rejections={list(false_rows.items())[:5]}, '
        f'missed_rejections={list(missed_rows.items())[:5]}'
    )
