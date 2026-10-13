
from sqlalchemy import Engine


# check orphan records in target
def test_orders_customer_fk(db_engine: Engine):
    query = """
        SELECT COUNT(*)
        FROM orders o
        LEFT JOIN customers c
          ON o.customer_id = c.customer_id
        WHERE c.customer_id IS NULL
    """

    with db_engine.cursor() as cursor:
        cursor.execute(query)
        orphan_count = cursor.fetchone()[0]

    assert orphan_count == 0, (
        f"Found {orphan_count} orphan orders"
    )

# Test payment -> order
def test_payments_order_fk(db_engine):
    query = """
        SELECT COUNT(*)
        FROM payments p
        LEFT JOIN orders o
          ON p.order_id = o.order_id
        WHERE o.order_id IS NULL
    """

    with db_engine.connect() as connection:
        result = connection.execute(query)
        orphan_count = result.fetchone()[0]

    assert orphan_count == 0, (
        f"Found {orphan_count} orphan payments"
    )
