from sqlalchemy import text
import pandas as pd

def test_database_connection(db_engine):
    with db_engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


def test_read_database(db_engine):
    df = pd.read_sql("SELECT 1 AS value", db_engine)

    assert len(df) == 1
    assert df.iloc[0]["value"] == 1