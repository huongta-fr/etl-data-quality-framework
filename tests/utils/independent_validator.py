"""Independent DuckDB SQL validator for seed-scoped e-commerce raw CSV files.

Supported by ERD: five tables, their PKs and the four FK edges.
Assumptions requiring confirmation: PKs/FKs cannot be empty; for duplicate PKs
keep the first raw CSV occurrence; FK parents must be accepted rows; a rejected
CSV contains the original raw columns (additional reject metadata is allowed).
This is NOT a complete oracle until business rules match the agreed spec.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import duckdb

RULES = {
    "customers": {"pk": "customer_id", "fk": []},
    "products": {"pk": "product_id", "fk": []},
    "orders": {"pk": "order_id", "fk": [("customer_id", "customers", "customer_id")]},
    "order_items": {"pk": "order_item_id", "fk": [("order_id", "orders", "order_id"), ("product_id", "products", "product_id")]},
    "payments": {"pk": "payment_id", "fk": [("order_id", "orders", "order_id")]},
}
EVALUATION_ORDER = tuple(RULES)


def _ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _literal(value: Path) -> str:
    return "'" + str(value.resolve()).replace("'", "''") + "'"


def _csv_path(folder: Path, table: str, rejected: bool = False) -> Path:
    name = f"{table}_rejected.csv" if rejected else f"{table}.csv"
    path = folder / name
    if not path.is_file():
        raise FileNotFoundError(f"Expected CSV not found: {path}")
    return path


def _columns(con: duckdb.DuckDBPyConnection, view: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info('{view}')").fetchall()]


def _read(con: duckdb.DuckDBPyConnection, name: str, path: Path) -> None:
    con.execute(
        f"CREATE TEMP VIEW {_ident(name)} AS "
        f"SELECT * FROM read_csv({_literal(path)}, header=true, all_varchar=true)"
    )


def _row_key(values: tuple) -> tuple[str | None, ...]:
    # Ignore extra rejected-only columns; differentiate NULL from empty string.
    return tuple(None if v is None else str(v) for v in values)


def _expected_rows(con: duckdb.DuckDBPyConnection, raw_dir: Path) -> dict[str, Counter]:
    expected = {}
    for table, rule in RULES.items():
        _read(con, f"raw_{table}", _csv_path(raw_dir, table))
        source_cols = _columns(con, f"raw_{table}")
        needed = {rule['pk'], *(fk for fk, _, _ in rule['fk'])}
        missing = needed - set(source_cols)
        if missing:
            raise ValueError(f"{table}.csv missing columns: {sorted(missing)}")

        # _pos follows CSV scan order for the single-file CSV sources assumed here.
        con.execute(f'''
            CREATE TEMP VIEW ranked_{table} AS
            SELECT *, ROW_NUMBER() OVER () AS _pos,
                ROW_NUMBER() OVER (
                    PARTITION BY {_ident(rule['pk'])} ORDER BY _pos
                ) AS _duplicate_rank
            FROM (SELECT *, ROW_NUMBER() OVER () AS _pos
                  FROM {_ident(f'raw_{table}')}) s
        '''.replace('SELECT *, ROW_NUMBER() OVER () AS _pos,', 'SELECT * EXCLUDE (_pos), _pos,'))
        # Avoid duplicate _pos in output, preserving columns plus ranking.
        predicates = [
            f"NULLIF(TRIM(r.{_ident(rule['pk'])}), '') IS NULL",
            "r._duplicate_rank > 1",
        ]
        for col, parent, parent_key in rule['fk']:
            predicates.append(f"NULLIF(TRIM(r.{_ident(col)}), '') IS NULL")
            predicates.append(
                f"(r.{_ident(col)} IS NOT NULL AND TRIM(r.{_ident(col)}) <> '' "
                f"AND NOT EXISTS (SELECT 1 FROM valid_{parent} p "
                f"WHERE p.{_ident(parent_key)} = r.{_ident(col)}))"
            )
        con.execute(f'''
            CREATE TEMP VIEW invalid_{table} AS
            SELECT * FROM ranked_{table} r
            WHERE {' OR '.join(predicates)}
        ''')
        con.execute(f'''
            CREATE TEMP VIEW valid_{table} AS
            SELECT r.* FROM ranked_{table} r
            WHERE NOT EXISTS (SELECT 1 FROM invalid_{table} i WHERE i._pos = r._pos)
        ''')
        select_cols = ', '.join(_ident(c) for c in source_cols)
        rows = con.execute(f"SELECT {select_cols} FROM invalid_{table}").fetchall()
        expected[table] = Counter(_row_key(row) for row in rows)
    return expected


def compare_seed(raw_dir: str | Path, rejected_dir: str | Path) -> dict[str, dict]:
    """Return per-table discrepancies; no ETL code is imported or executed.

    Matches full raw rows, not only business PK, so duplicate PK cases can be
    compared. Identical repeated raw rows are compared by multiplicity.
    """
    raw_dir, rejected_dir = Path(raw_dir), Path(rejected_dir)
    con = duckdb.connect(':memory:')
    try:
        expected = _expected_rows(con, raw_dir)
        results = {}
        for table in EVALUATION_ORDER:
            reject_path = rejected_dir / f"{table}_rejected.csv"

            if reject_path.is_file():
                _read(con, f"rejected_{table}", reject_path)

                raw_cols = _columns(con, f"raw_{table}")
                reject_cols = set(_columns(con, f"rejected_{table}"))

                missing = set(raw_cols) - reject_cols
                if missing:
                    raise ValueError(
                        f"{table}: missing rejected columns: {sorted(missing)}"
                    )

                select_cols = ", ".join(_ident(c) for c in raw_cols)
                actual_rows = con.execute(
                    f"SELECT {select_cols} "
                    f"FROM {_ident(f'rejected_{table}')}"
                ).fetchall()

                actual = Counter(_row_key(row) for row in actual_rows)
            else:
                actual = Counter()

            results[table] = {
                "expected_count": expected[table].total(),
                "actual_count": actual.total(),
                "false_rejections": actual - expected[table],
                "missed_rejections": expected[table] - actual,
            }
        return results
    finally:
        con.close()


def discover_seeds(data_dir: str | Path) -> list[str]:
    root = Path(data_dir)
    raw, rejected = root / 'raw', root / 'rejected'
    raw_seeds = {p.name for p in raw.iterdir() if p.is_dir() and p.name.startswith('seed_')}
    rejected_seeds = {p.name for p in rejected.iterdir() if p.is_dir() and p.name.startswith('seed_')}
    if raw_seeds != rejected_seeds:
        raise ValueError(f'Seed folder mismatch: raw-only={raw_seeds-rejected_seeds}, rejected-only={rejected_seeds-raw_seeds}')
    if not raw_seeds:
        raise ValueError(f'No seed_* directories in {raw}')
    return sorted(raw_seeds)
