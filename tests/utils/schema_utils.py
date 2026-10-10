# Check Primary Keys
from sqlalchemy import Engine, MetaData, Table

def check_primary_key(
    db_engine: Engine,
    table_name: str,
    expected_primary_key: list[str]
):
    metadata = MetaData()

    table = Table(
        table_name,
        metadata,
        autoload_with=db_engine
    )

    primary_key = [
        column.name
        for column in table.primary_key.columns
    ]

    assert primary_key == expected_primary_key


def check_foreign_keys(
    db_engine: Engine,
    table_name: str,
    expected_foreign_keys: dict[str, tuple[str, str]],
):
    metadata = MetaData()

    table = Table(
        table_name,
        metadata,
        autoload_with=db_engine
    )

    actual_foreign_keys = {
        fk.parent.name: (
            fk.column.table.name,
            fk.column.name
        )
        for fk in table.foreign_keys
    }

    assert actual_foreign_keys == expected_foreign_keys