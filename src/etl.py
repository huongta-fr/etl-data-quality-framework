from pathlib import Path
from datetime import datetime, timezone
import json
import os
import uuid
import logging
import sys
import time
import argparse

from extract import extract_data
from transform import transform_data
from load import load_data

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config_loader import load_config


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


def project_relative_path(path: Path) -> str:
    """Return a portable path relative to the project working directory."""
    return path.resolve().relative_to(Path.cwd().resolve()).as_posix()


def save_rejected_data(
    rejected_data,
    output_folder: Path,
):
    logger = logging.getLogger(__name__)

    output_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    saved_paths = {}

    for dataset_name, df in (
        rejected_data.items()
    ):
        if df.empty:
            saved_paths[dataset_name] = None
            continue

        path = (
            output_folder
            / f"{dataset_name}_rejected.csv"
        )

        df.to_csv(
            path,
            index=False,
        )

        saved_paths[dataset_name] = project_relative_path(path)

        logger.info(
            "[REJECT] dataset=%s "
            "rows=%d file=%s",
            dataset_name,
            len(df),
            path,
        )

    return saved_paths


def write_json_atomic(path: Path, payload: dict) -> None:
    """Publish a complete JSON file using atomic replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def append_success_metadata(path: Path, manifest: dict) -> None:
    """Store successful run history and the current full-refresh DB state."""
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            history = json.load(handle)
        if not isinstance(history, dict) or not isinstance(history.get("successful_runs"), list):
            raise ValueError(f"Invalid metadata history: {path}")
    else:
        # Migrate the previous single-run manifest when available.
        previous_path = path.with_name("latest_success.json")
        if previous_path.exists():
            with previous_path.open("r", encoding="utf-8") as handle:
                previous = json.load(handle)
            if not isinstance(previous, dict) or previous.get("status") != "SUCCESS" or not previous.get("run_id"):
                raise ValueError(f"Invalid legacy manifest: {previous_path}")
            history = {"successful_runs": [previous]}
        else:
            history = {"successful_runs": []}

    if any(run.get("run_id") == manifest["run_id"] for run in history["successful_runs"]):
        raise ValueError(f"Duplicate run_id: {manifest['run_id']}")

    history["successful_runs"].append(manifest)
    # load_data currently performs a full_refresh: old seeds are NOT still in DB.
    history["current_db"] = {
        "run_id": manifest["run_id"],
        "seeds": [manifest["seed"]],
        "load_mode": manifest["load_mode"],
        "updated_at": manifest["finished_at"],
    }
    write_json_atomic(path, history)


def run_etl():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Run ETL pipeline with optional seed override"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Override the seed from config file"
    )
    args = parser.parse_args()
    
    log_file = setup_logging()
    logger = logging.getLogger(__name__)
    start = time.time()
    started_at = datetime.now(timezone.utc)
    run_id = f"{started_at:%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:12]}"

    logger.info("=" * 70)
    logger.info("ETL START run_id=%s", run_id)
    logger.info("Log file: %s", log_file)

    try:
        config = load_config("etl")
        
        # Override seed if provided via command line
        if args.seed is not None:
            config["seed"] = args.seed
        
        seed = config["seed"]

        root_folder = Path(
        config["data"]["root"]
        )

        data_folder = Path(
            config["data"]["raw_folder"]
        )

        input_path = (
            root_folder
            / data_folder
            / f"seed_{seed}"
        )

        rejected_folder= Path(
            config["data"]["rejected_folder"]
        )

        rejected_path = (
            root_folder
            / rejected_folder
            / f"seed_{seed}"
            / run_id
        )

        dataset_names = config[
            "load_order"
        ]

        logger.info(
            "----- EXTRACT START -----"
        )

        raw_data = extract_data(
            input_path,
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
        ) = transform_data(config,
            raw_data
        )

        rejected_files = save_rejected_data(
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
            config,
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

        # Only publish metadata when all expected datasets were loaded.
        datasets = {}
        for dataset_name in dataset_names:
            if dataset_name not in raw_data:
                raise RuntimeError(f"Missing extracted dataset: {dataset_name}")
            if dataset_name not in transform_report or dataset_name not in load_report:
                raise RuntimeError(f"Missing ETL report: {dataset_name}")

            transformed = transform_report[dataset_name]
            loaded = load_report[dataset_name]
            source_rows = len(raw_data[dataset_name])
            rejected_rows = len(rejected_data[dataset_name])
            clean_rows = len(clean_data[dataset_name])

            if (
                source_rows != clean_rows + rejected_rows
                or source_rows != transformed["input_rows"]
                or clean_rows != transformed["clean_rows"]
                or rejected_rows != transformed["rejected_rows"]
                or clean_rows != loaded["rows"]
                or loaded["status"] != "SUCCESS"
            ):
                raise RuntimeError(f"Inconsistent ETL counts/status for {dataset_name}")

            datasets[dataset_name] = {
                "source_path": project_relative_path(input_path / f"{dataset_name}.csv"),
                "rejected_path": rejected_files.get(dataset_name),
                "source_rows": source_rows,
                "clean_rows": clean_rows,
                "rejected_rows": rejected_rows,
                "loaded_rows": loaded["rows"],
                "target_table": loaded["target_table"],
            }

        manifest_path = Path("logs") / "etl_metadata.json"
        manifest = {
            "run_id": run_id,
            "seed": seed,
            "status": "SUCCESS",
            "load_mode": "full_refresh",
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "log_path": project_relative_path(log_file),
            "datasets": datasets,
        }
        # Append only successful runs; current_db describes the latest full refresh.
        # Run ETL jobs sequentially (no concurrent writers for this JSON file).
        append_success_metadata(manifest_path, manifest)
        logger.info("[METADATA] run_id=%s manifest=%s", run_id, manifest_path)
        logger.info("ETL STATUS: SUCCESS")

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
