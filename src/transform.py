from pathlib import Path
import logging

import pandas as pd
import yaml
from sqlalchemy import create_engine, inspect
from sqlalchemy.sql.sqltypes import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    Numeric,
    SmallInteger,
    String,
)

LOGGER = logging.getLogger(__name__)

ETL_CONFIG_PATH = Path("config/etl.yaml")
DQ_CONFIG_PATH = Path("config/data_quality.yaml")


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


def get_target_metadata(
    etl_config: dict,
) -> dict[str, dict]:
    """
    PostgreSQL is the source of truth for physical schema.

    Reads:
      - columns + datatypes + nullable
      - primary keys
      - unique constraints
      - foreign keys
      - VARCHAR length
    """
    engine = get_engine(etl_config)
    inspector = inspect(engine)
    db_schema = etl_config["database"].get("schema", "public")

    target_to_dataset = {
        cfg["target_table"]: dataset_name
        for dataset_name, cfg in etl_config["tables"].items()
    }

    metadata = {}

    for dataset_name, table_cfg in etl_config["tables"].items():
        table_name = table_cfg["target_table"]

        columns = inspector.get_columns(
            table_name,
            schema=db_schema,
        )

        pk = inspector.get_pk_constraint(
            table_name,
            schema=db_schema,
        ).get("constrained_columns") or []

        unique_constraints = inspector.get_unique_constraints(
            table_name,
            schema=db_schema,
        )

        unique_sets = [
            item.get("column_names", [])
            for item in unique_constraints
            if item.get("column_names")
        ]

        foreign_keys = []

        for fk in inspector.get_foreign_keys(
            table_name,
            schema=db_schema,
        ):
            referred_table = fk["referred_table"]

            foreign_keys.append({
                "columns": fk["constrained_columns"],
                "reference_table": referred_table,
                "reference_dataset": target_to_dataset.get(referred_table),
                "reference_columns": fk["referred_columns"],
            })

        metadata[dataset_name] = {
            "target_table": table_name,
            "columns": {
                col["name"]: {
                    "type": col["type"],
                    "nullable": col["nullable"],
                }
                for col in columns
            },
            "primary_key": pk,
            "unique_constraints": unique_sets,
            "foreign_keys": foreign_keys,
        }

    return metadata


def convert_series(
    series: pd.Series,
    sql_type,
) -> tuple[pd.Series, pd.Series]:
    """
    Returns:
      converted_series,
      invalid_cast_mask

    invalid_cast_mask identifies values that existed in raw data but
    could not be converted to the PostgreSQL target datatype.
    """
    original_not_null = series.notna()

    if isinstance(sql_type, (Integer, BigInteger, SmallInteger)):
        converted = pd.to_numeric(
            series,
            errors="coerce",
        ).astype("Int64")

    elif isinstance(sql_type, (Numeric, Float)):
        converted = pd.to_numeric(
            series,
            errors="coerce",
        )

    elif isinstance(sql_type, (DateTime, Date)):
        converted = pd.to_datetime(
            series,
            errors="coerce",
        )

    elif isinstance(sql_type, Boolean):
        mapping = {
            "true": True,
            "false": False,
            "1": True,
            "0": False,
        }

        converted = (
            series.astype("string")
            .str.lower()
            .map(mapping)
            .astype("boolean")
        )

    else:
        converted = series

    invalid_cast_mask = (
        original_not_null
        & converted.isna()
    )

    return converted, invalid_cast_mask


def add_reject_reason(
    df: pd.DataFrame,
    mask: pd.Series,
    reason: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rejected = df.loc[mask].copy()
    rejected["reject_reason"] = reason

    remaining = df.loc[~mask].copy()

    return remaining, rejected


def append_rejected(
    parts: list[pd.DataFrame],
    rejected: pd.DataFrame,
):
    if not rejected.empty:
        parts.append(rejected)


def validate_and_cast_datatypes(
    dataset_name: str,
    df: pd.DataFrame,
    table_metadata: dict,
) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    current = df.copy()
    rejected_parts = []

    for column_name, column_meta in table_metadata["columns"].items():

        if column_name not in current.columns:
            continue

        converted, invalid_mask = convert_series(
            current[column_name],
            column_meta["type"],
        )

        current[column_name] = converted

        current, rejected = add_reject_reason(
            current,
            invalid_mask.loc[current.index],
            f"INVALID_DATATYPE_{column_name.upper()}",
        )

        append_rejected(
            rejected_parts,
            rejected,
        )

    return current, rejected_parts


def validate_required_columns(
    df: pd.DataFrame,
    table_metadata: dict,
) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    current = df.copy()
    rejected_parts = []

    for column_name, column_meta in table_metadata["columns"].items():

        if column_name not in current.columns:
            # Missing source column is a pipeline/schema problem, not a row problem.
            if not column_meta["nullable"]:
                raise ValueError(
                    f"Required target column missing from raw data: {column_name}"
                )
            continue

        if column_meta["nullable"]:
            continue

        mask = current[column_name].isna()

        current, rejected = add_reject_reason(
            current,
            mask,
            f"NULL_{column_name.upper()}",
        )

        append_rejected(
            rejected_parts,
            rejected,
        )

    return current, rejected_parts


def validate_string_lengths(
    df: pd.DataFrame,
    table_metadata: dict,
) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    current = df.copy()
    rejected_parts = []

    for column_name, column_meta in table_metadata["columns"].items():

        if column_name not in current.columns:
            continue

        sql_type = column_meta["type"]

        if not isinstance(sql_type, String):
            continue

        max_length = getattr(
            sql_type,
            "length",
            None,
        )

        if not max_length:
            continue

        mask = (
            current[column_name].notna()
            & (
                current[column_name]
                .astype(str)
                .str.len()
                > max_length
            )
        )

        current, rejected = add_reject_reason(
            current,
            mask,
            f"MAX_LENGTH_{column_name.upper()}",
        )

        append_rejected(
            rejected_parts,
            rejected,
        )

    return current, rejected_parts


def validate_uniqueness(
    df: pd.DataFrame,
    table_metadata: dict,
) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    current = df.copy()
    rejected_parts = []

    constraints = []

    pk = table_metadata["primary_key"]
    if pk:
        constraints.append(pk)

    constraints.extend(
        table_metadata["unique_constraints"]
    )

    seen = set()

    for columns in constraints:
        key = tuple(columns)

        if not columns or key in seen:
            continue

        seen.add(key)

        mask = current.duplicated(
            subset=columns,
            keep="first",
        )

        current, rejected = add_reject_reason(
            current,
            mask,
            "DUPLICATE_" + "_".join(columns).upper(),
        )

        append_rejected(
            rejected_parts,
            rejected,
        )

    return current, rejected_parts


def validate_foreign_keys(
    df: pd.DataFrame,
    table_metadata: dict,
    clean_data: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    current = df.copy()
    rejected_parts = []

    for fk in table_metadata["foreign_keys"]:

        source_columns = fk["columns"]
        reference_columns = fk["reference_columns"]
        reference_dataset = fk["reference_dataset"]

        if reference_dataset is None:
            raise ValueError(
                "FK reference table is not mapped in etl.yaml: "
                f'{fk["reference_table"]}'
            )

        if len(source_columns) != 1 or len(reference_columns) != 1:
            raise NotImplementedError(
                "Composite foreign keys are not implemented in this demo."
            )

        source_column = source_columns[0]
        reference_column = reference_columns[0]

        if reference_dataset not in clean_data:
            raise ValueError(
                f"Referenced dataset '{reference_dataset}' must be transformed "
                "before the dependent dataset. Check load_order in etl.yaml."
            )

        reference_df = clean_data[
            reference_dataset
        ]

        valid_values = set(
            reference_df[
                reference_column
            ].dropna()
        )

        mask = (
            current[source_column].notna()
            & ~current[source_column].isin(valid_values)
        )

        current, rejected = add_reject_reason(
            current,
            mask,
            f"INVALID_FK_{source_column.upper()}",
        )

        append_rejected(
            rejected_parts,
            rejected,
        )

    return current, rejected_parts


# -------------------------
# Business rules
# -------------------------

def business_allowed_values(
    df: pd.DataFrame,
    rule: dict,
    clean_data: dict[str, pd.DataFrame],
) -> pd.Series:
    return (
        df[rule["column"]].notna()
        & ~df[rule["column"]].isin(rule["values"])
    )


def business_min_value(
    df: pd.DataFrame,
    rule: dict,
    clean_data: dict[str, pd.DataFrame],
) -> pd.Series:
    column = rule["column"]
    value = rule["value"]

    if rule.get("inclusive", True):
        return (
            df[column].notna()
            & (df[column] < value)
        )

    return (
        df[column].notna()
        & (df[column] <= value)
    )


def business_equals_reference(
    df: pd.DataFrame,
    rule: dict,
    clean_data: dict[str, pd.DataFrame],
) -> pd.Series:
    reference_df = clean_data[
        rule["reference_dataset"]
    ]

    reference = reference_df[
        [
            rule["join_on"],
            rule["reference_column"],
        ]
    ].rename(
        columns={
            rule["reference_column"]:
            "__reference_value"
        }
    )

    checked = df.merge(
        reference,
        on=rule["join_on"],
        how="left",
        sort=False,
    )

    checked.index = df.index

    tolerance = rule.get(
        "tolerance",
        0,
    )

    return (
        checked["__reference_value"].notna()
        & (
            (
                checked[rule["column"]]
                - checked["__reference_value"]
            ).abs()
            > tolerance
        )
    )


BUSINESS_RULE_HANDLERS = {
    "allowed_values": business_allowed_values,
    "min_value": business_min_value,
    "equals_reference": business_equals_reference,
}


def validate_business_rules(
    dataset_name: str,
    df: pd.DataFrame,
    rules: list[dict],
    clean_data: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    current = df.copy()
    rejected_parts = []

    for rule in rules:
        rule_type = rule["type"]

        if rule_type not in BUSINESS_RULE_HANDLERS:
            raise ValueError(
                f"Unsupported business rule type: {rule_type}"
            )

        mask = BUSINESS_RULE_HANDLERS[
            rule_type
        ](
            current,
            rule,
            clean_data,
        )

        current, rejected = add_reject_reason(
            current,
            mask,
            rule["reason"],
        )

        if not rejected.empty:
            LOGGER.info(
                "[TRANSFORM][BUSINESS_RULE] "
                "dataset=%s rule=%s reason=%s count=%d",
                dataset_name,
                rule["name"],
                rule["reason"],
                len(rejected),
            )

        append_rejected(
            rejected_parts,
            rejected,
        )

    return current, rejected_parts


def transform_dataset(
    dataset_name: str,
    raw_df: pd.DataFrame,
    table_metadata: dict,
    business_rules: list[dict],
    clean_data: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Structural validation comes from PostgreSQL metadata.
    Business validation comes from data_quality.yaml.
    """
    current = raw_df.copy()
    rejected_parts = []

    current, parts = validate_and_cast_datatypes(
        dataset_name,
        current,
        table_metadata,
    )
    rejected_parts.extend(parts)

    current, parts = validate_required_columns(
        current,
        table_metadata,
    )
    rejected_parts.extend(parts)

    current, parts = validate_string_lengths(
        current,
        table_metadata,
    )
    rejected_parts.extend(parts)

    current, parts = validate_uniqueness(
        current,
        table_metadata,
    )
    rejected_parts.extend(parts)

    current, parts = validate_foreign_keys(
        current,
        table_metadata,
        clean_data,
    )
    rejected_parts.extend(parts)

    current, parts = validate_business_rules(
        dataset_name,
        current,
        business_rules,
        clean_data,
    )
    rejected_parts.extend(parts)

    if rejected_parts:
        rejected_df = pd.concat(
            rejected_parts,
            ignore_index=True,
        )
    else:
        rejected_df = pd.DataFrame(
            columns=list(raw_df.columns)
            + ["reject_reason"]
        )

    return current, rejected_df


def build_transform_report(
    raw_data: dict[str, pd.DataFrame],
    clean_data: dict[str, pd.DataFrame],
    rejected_data: dict[str, pd.DataFrame],
) -> dict:
    report = {}

    for dataset_name in clean_data:
        rejected_df = rejected_data[
            dataset_name
        ]

        issues = {}

        if not rejected_df.empty:
            issues = (
                rejected_df["reject_reason"]
                .value_counts()
                .to_dict()
            )

        report[dataset_name] = {
            "input_rows": len(
                raw_data[dataset_name]
            ),
            "clean_rows": len(
                clean_data[dataset_name]
            ),
            "rejected_rows": len(
                rejected_df
            ),
            "issues": issues,
        }

    return report


def transform_data(
    raw_data: dict[str, pd.DataFrame],
) -> tuple[
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict,
]:
    etl_config = load_yaml(
        ETL_CONFIG_PATH
    )
    dq_config = load_yaml(
        DQ_CONFIG_PATH
    )

    target_metadata = get_target_metadata(
        etl_config
    )

    clean_data = {}
    rejected_data = {}

    for dataset_name in etl_config[
        "load_order"
    ]:
        rules = (
            dq_config
            .get("datasets", {})
            .get(dataset_name, {})
            .get("rules", [])
        )

        clean_df, rejected_df = (
            transform_dataset(
                dataset_name=dataset_name,
                raw_df=raw_data[
                    dataset_name
                ],
                table_metadata=target_metadata[
                    dataset_name
                ],
                business_rules=rules,
                clean_data=clean_data,
            )
        )

        clean_data[
            dataset_name
        ] = clean_df

        rejected_data[
            dataset_name
        ] = rejected_df

        LOGGER.info(
            "[TRANSFORM] dataset=%s "
            "input=%d clean=%d rejected=%d",
            dataset_name,
            len(raw_data[dataset_name]),
            len(clean_df),
            len(rejected_df),
        )

    report = build_transform_report(
        raw_data,
        clean_data,
        rejected_data,
    )

    return (
        clean_data,
        rejected_data,
        report,
    )
