from pathlib import Path
import logging

import pandas as pd
import yaml
from sqlalchemy import create_engine, text

LOGGER = logging.getLogger(__name__)

ETL_CONFIG_PATH = Path("config/etl.yaml")


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def build_db_url(config: dict) -> str:
    db = config["database"]

    return (
        f'{db["dialect"]}://'
        f'{db["user"]}:{db["password"]}@'
        f'{db["host"]}:{db["port"]}/{db["name"]}'
    )


def get_engine(config: dict):
    return create_engine(build_db_url(config))


def clear_target_tables(
    connection,
    config: dict,
) -> None:
    target_tables = [
        config["tables"][
            dataset_name
        ]["target_table"]
        for dataset_name in reversed(
            config["load_order"]
        )
    ]

    quoted = [
        f'"{table_name}"'
        for table_name in target_tables
    ]

    sql = (
        "TRUNCATE TABLE "
        + ", ".join(quoted)
        + " RESTART IDENTITY CASCADE;"
    )

    connection.execute(
        text(sql)
    )


def load_data(
    clean_data: dict[str, pd.DataFrame],
) -> dict:
    """
    Load reads only ETL runtime/table mapping config.
    It does not contain validation logic.
    """
    config = load_yaml(
        ETL_CONFIG_PATH
    )

    engine = get_engine(
        config
    )

    load_mode = config[
        "load"
    ].get(
        "mode",
        "full_refresh",
    )

    chunksize = config[
        "load"
    ].get(
        "chunksize",
        500,
    )

    db_schema = config[
        "database"
    ].get(
        "schema",
        "public",
    )

    report = {}

    try:
        with engine.begin() as connection:

            if load_mode == "full_refresh":
                LOGGER.info(
                    "[LOAD] mode=full_refresh "
                    "- clearing target tables"
                )

                clear_target_tables(
                    connection,
                    config,
                )

            elif load_mode != "append":
                raise ValueError(
                    f"Unsupported load mode: "
                    f"{load_mode}"
                )

            for dataset_name in config[
                "load_order"
            ]:
                df = clean_data[
                    dataset_name
                ]

                target_table = config[
                    "tables"
                ][dataset_name][
                    "target_table"
                ]

                LOGGER.info(
                    "[LOAD] START "
                    "dataset=%s target=%s rows=%d",
                    dataset_name,
                    target_table,
                    len(df),
                )

                df.to_sql(
                    name=target_table,
                    schema=db_schema,
                    con=connection,
                    if_exists="append",
                    index=False,
                    method="multi",
                    chunksize=chunksize,
                )

                report[
                    dataset_name
                ] = {
                    "target_table": target_table,
                    "rows": len(df),
                    "status": "SUCCESS",
                }

                LOGGER.info(
                    "[LOAD] SUCCESS "
                    "dataset=%s target=%s rows=%d",
                    dataset_name,
                    target_table,
                    len(df),
                )

        LOGGER.info(
            "[LOAD] Transaction COMMIT"
        )

        return report

    except Exception:
        LOGGER.exception(
            "[LOAD] FAILED "
            "- transaction rolled back"
        )
        raise
