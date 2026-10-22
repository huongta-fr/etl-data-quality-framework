"""Export authoritative PostgreSQL structural rules for Fabric Silver validation.
Run locally with DATABASE_URL set; never upload credentials to Fabric.
"""
import json
import os
from pathlib import Path
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError
import yaml

ETL_CONFIG_PATH = Path("config/etl.yaml")
BASE_CONFIG_PATH = Path("config/base.yaml")


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_url_from_base_config() -> str | None:
    if not BASE_CONFIG_PATH.exists():
        return None
    base_config = _load_yaml(BASE_CONFIG_PATH)
    db = base_config.get("database") or {}
    required_keys = ("dialect", "host", "port", "name", "user", "password")
    if not all(db.get(key) for key in required_keys):
        return None
    return (
        f"{db['dialect']}://{db['user']}:{db['password']}"
        f"@{db['host']}:{db['port']}/{db['name']}"
    )


def _get_database_url() -> str:
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    config_url = _build_url_from_base_config()
    if config_url:
        print("DATABASE_URL is not set; using database config from config/base.yaml")
        return config_url
    raise SystemExit(
        "Set DATABASE_URL or provide complete database settings in config/base.yaml"
    )


def _connection_help(url: str, namespace: str) -> str:
    return (
        "Could not connect to PostgreSQL.\n"
        f"- DATABASE_URL: {url}\n"
        f"- PG_SCHEMA: {namespace}\n"
        "\nTroubleshooting:\n"
        "1) Ensure Docker Desktop is running\n"
        "2) Start DB: docker compose up -d postgres\n"
        "3) Check health: docker compose ps\n"
        "4) Validate port binding to localhost:5432\n"
        "5) Verify user/password/db in DATABASE_URL or config/base.yaml"
    )


url = _get_database_url()
config = _load_yaml(ETL_CONFIG_PATH)
namespace = os.environ.get("PG_SCHEMA", "public")

try:
    engine = create_engine(url)
    inspector = inspect(engine)
    tables = config["tables"]
    target_lookup = {v["target_table"]: k for k, v in tables.items()}
    metadata = {}

    for name, cfg in tables.items():
        table = cfg["target_table"]
        columns = inspector.get_columns(table, schema=namespace)
        if not columns:
            raise RuntimeError(f"Missing PostgreSQL table: {namespace}.{table}")

        keys = inspector.get_pk_constraint(table, schema=namespace).get("constrained_columns") or []
        uniques = [
            v["column_names"]
            for v in inspector.get_unique_constraints(table, schema=namespace)
            if v.get("column_names")
        ]

        fks = []
        for fk in inspector.get_foreign_keys(table, schema=namespace):
            reference = target_lookup.get(fk["referred_table"])
            if reference is None:
                raise RuntimeError(f"Unknown referenced table: {fk['referred_table']}")
            fks.append(
                {
                    "columns": fk["constrained_columns"],
                    "reference_dataset": reference,
                    "reference_columns": fk["referred_columns"],
                }
            )

        metadata[name] = {
            "columns": {
                c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                for c in columns
            },
            "primary_key": keys,
            "unique_constraints": uniques,
            "foreign_keys": fks,
        }

    with open("schema_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print("Created schema_metadata.json; upload to lh_ecommerce/Files/config")
except OperationalError as exc:
    raise SystemExit(f"{_connection_help(url, namespace)}\n\nOriginal error: {exc}") from exc
