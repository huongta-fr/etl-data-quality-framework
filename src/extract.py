from pathlib import Path
import logging

import pandas as pd

LOGGER = logging.getLogger(__name__)


def extract_data(
    input_folder: Path,
    dataset_names: list[str],
) -> dict[str, pd.DataFrame]:
    """
    Read raw CSV files only.

    Extract does not validate business rules and does not cast according
    to the target schema. That belongs to Transform.
    """
    datasets = {}

    for dataset_name in dataset_names:
        path = input_folder / f"{dataset_name}.csv"

        if not path.exists():
            raise FileNotFoundError(
                f"Raw dataset not found: {path}"
            )

        df = pd.read_csv(path)

        datasets[dataset_name] = df

        LOGGER.info(
            "[EXTRACT] dataset=%s file=%s rows=%d columns=%d",
            dataset_name,
            path,
            len(df),
            len(df.columns),
        )

    return datasets
