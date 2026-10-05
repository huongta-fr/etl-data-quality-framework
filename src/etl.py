from pathlib import Path
from datetime import datetime
import logging
import time

import yaml

from extract import extract_data
from transform import transform_data
from load import load_data

ETL_CONFIG_PATH = Path("config/etl.yaml")


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def setup_logging() -> Path:
    log_folder = Path("logs")
    log_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    log_file = (
        log_folder
        / f"etl_{timestamp}.log"
    )

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(message)s"
        ),
        handlers=[
            logging.FileHandler(
                log_file,
                encoding="utf-8",
            ),
            logging.StreamHandler(),
        ],
        force=True,
    )

    return log_file


def save_rejected_data(
    rejected_data,
    output_folder: Path,
):
    logger = logging.getLogger(__name__)

    output_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    for dataset_name, df in (
        rejected_data.items()
    ):
        if df.empty:
            continue

        path = (
            output_folder
            / f"{dataset_name}_rejected.csv"
        )

        df.to_csv(
            path,
            index=False,
        )

        logger.info(
            "[REJECT] dataset=%s "
            "rows=%d file=%s",
            dataset_name,
            len(df),
            path,
        )


def run_etl():
    log_file = setup_logging()
    logger = logging.getLogger(__name__)
    start = time.time()

    logger.info("=" * 70)
    logger.info("ETL START")
    logger.info("Log file: %s", log_file)

    try:
        config = load_yaml(
            ETL_CONFIG_PATH
        )

        raw_path = Path(
            config["data"]["raw_path"]
        )

        rejected_path = Path(
            config["data"][
                "rejected_path"
            ]
        )

        dataset_names = config[
            "load_order"
        ]

        logger.info(
            "----- EXTRACT START -----"
        )

        raw_data = extract_data(
            raw_path,
            dataset_names,
        )

        logger.info(
            "----- EXTRACT SUCCESS -----"
        )

        logger.info(
            "----- TRANSFORM START -----"
        )

        (
            clean_data,
            rejected_data,
            transform_report,
        ) = transform_data(
            raw_data
        )

        save_rejected_data(
            rejected_data,
            rejected_path,
        )

        logger.info(
            "----- TRANSFORM SUCCESS -----"
        )

        logger.info(
            "----- LOAD START -----"
        )

        load_report = load_data(
            clean_data
        )

        logger.info(
            "----- LOAD SUCCESS -----"
        )

        logger.info(
            "===== ETL SUMMARY ====="
        )

        for dataset_name, report in (
            transform_report.items()
        ):
            logger.info(
                "%s | input=%d "
                "| clean=%d "
                "| rejected=%d "
                "| issues=%s",
                dataset_name,
                report["input_rows"],
                report["clean_rows"],
                report["rejected_rows"],
                report["issues"],
            )

        for dataset_name, report in (
            load_report.items()
        ):
            logger.info(
                "%s -> %s "
                "| loaded=%d "
                "| status=%s",
                dataset_name,
                report["target_table"],
                report["rows"],
                report["status"],
            )

        logger.info(
            "ETL STATUS: SUCCESS"
        )

    except Exception:
        logger.exception(
            "ETL STATUS: FAILED"
        )
        raise

    finally:
        logger.info(
            "Duration: %.2f seconds",
            time.time() - start,
        )
        logger.info("=" * 70)


if __name__ == "__main__":
    run_etl()
