"""Source -> PostgreSQL reconciliation for a successful full-refresh ETL run.

The authoritative run comes from the existing ``etl_run`` fixture. No seed is
silently selected. Rejected CSVs must preserve their original source columns.
"""
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from sqlalchemy import inspect, text
from sqlalchemy.sql.sqltypes import BigInteger, Integer, SmallInteger, Numeric, Float, Date, DateTime, Boolean


ROOT = Path(__file__).resolve().parents[2]
TABLES = {
    "customers": "customer",
    "products": "product",
    "orders": "order",
    "order_items": "order_item",
    "payments": "payment",
}


def _resolve_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _dataset_file(dataset, run, dataset_name, kind):
    """Use explicit run paths, or derive exact seed directory from run metadata."""
    path_fields = (
        ("raw_path", "source_path", "raw_file", "source_file")
        if kind == "raw" else
        ("rejected_path", "reject_path", "rejected_file", "reject_file")
    )
    for metadata in (dataset, run):
        for field in path_fields:
            value = metadata.get(field)
            if isinstance(value, str) and value:
                path = _resolve_path(value)
                if path.is_dir():
                    path = path / f"{dataset_name}.csv"
                assert path.is_file(), f"Missing {kind} CSV: {path}"
                return path

    seed = dataset.get("seed", run.get("seed"))
    assert seed is not None, (
        f"No {kind} path or seed in etl_run for {dataset_name}. "
        "Add a path to the ETL metadata; do not guess a seed."
    )
    folder = f"seed_{seed}" if not str(seed).startswith("seed_") else str(seed)
    path = ROOT / "data" / kind / folder / f"{dataset_name}.csv"
    assert path.is_file(), f"Missing {kind} CSV: {path}"
    return path


def _read_csv(path):
    # Keep text representations; avoid float rounding and NA coercion of IDs.
    return pd.read_csv(path, dtype="string", keep_default_na=False)


def _canonical(value, sql_type):
    if value is None or value is pd.NA:
        return None
    if isinstance(value, str) and value == "":
        return None
    if isinstance(sql_type, (Integer, BigInteger, SmallInteger)):
        try:
            val = Decimal(str(value))
            if val != val.to_integral_value():
                raise ValueError(f"Non-integral key: {value!r}")
            return str(int(val))
        except InvalidOperation as exc:
            raise AssertionError(f"Invalid integer key {value!r}") from exc
    # Values from PostgreSQL can be non-string native types.
    return str(value)


def _keys(rows, pk_columns, column_types):
    return Counter(
        tuple(_canonical(row[col], column_types[col]) for col in pk_columns)
        for row in rows
    )


def reconcile_primary_keys(engine, etl_run, dataset_name):
    """Check accepted source PK multiset equals target PK multiset.

    Unlike count-only checks, reports missing and unexpected PKs. Assumes
    full-refresh and keys unchanged by transformations.
    """
    assert etl_run["load_mode"] == "full_refresh"
    dataset = etl_run["datasets"][dataset_name]
    table_name = dataset.get("target_table", TABLES[dataset_name])
    schema = dataset.get("schema", "public")
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name, schema=schema)
    assert columns, f"Target table not found: {schema}.{table_name}"
    column_types = {c["name"]: c["type"] for c in columns}
    pk_columns = inspector.get_pk_constraint(table_name, schema=schema).get("constrained_columns") or []
    assert pk_columns, f"No PK defined: {schema}.{table_name}"

    raw = _read_csv(_dataset_file(dataset, etl_run, dataset_name, "raw"))
    rejected = _read_csv(_dataset_file(dataset, etl_run, dataset_name, "rejected"))
    for df, label in ((raw, "raw"), (rejected, "rejected")):
        missing = set(pk_columns) - set(df.columns)
        assert not missing, f"{label} missing PK columns: {sorted(missing)}"

    raw_keys = _keys(raw.to_dict("records"), pk_columns, column_types)
    rejected_keys = _keys(rejected.to_dict("records"), pk_columns, column_types)
    invalid_rejects = rejected_keys - raw_keys
    assert not invalid_rejects, (
        f"{dataset_name}: rejected PK occurrences not in raw: "
        f"{invalid_rejects.most_common(10)}"
    )
    expected = raw_keys - rejected_keys

    preparer = engine.dialect.identifier_preparer
    sql = (
        f"SELECT {', '.join(preparer.quote(c) for c in pk_columns)} "
        f"FROM {preparer.quote_schema(schema)}.{preparer.quote(table_name)}"
    )
    with engine.connect() as conn:
        target_rows = conn.execute(text(sql)).mappings().all()
    actual = _keys(target_rows, pk_columns, column_types)

    missing = expected - actual
    unexpected = actual - expected
    assert not missing and not unexpected, (
        f"{dataset_name}: PK reconciliation failed\n"
        f"expected={sum(expected.values())}, actual={sum(actual.values())}\n"
        f"missing={missing.most_common(10)}\n"
        f"unexpected={unexpected.most_common(10)}"
    )
