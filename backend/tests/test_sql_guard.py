import pytest

from app.sql_guard import UnsafeSQLError, validate_read_only

ALLOWED = [
    ("SELECT 1", "sqlite"),
    ("select * from customers;", "sqlite"),
    ("SELECT 1;;  ", "sqlite"),
    ("WITH t AS (SELECT 1 AS a) SELECT * FROM t", "sqlite"),
    ("SELECT a FROM x UNION ALL SELECT b FROM y", "sqlite"),
    ("SELECT strftime('%Y-%m', order_date) AS m, COUNT(*) FROM orders GROUP BY 1", "sqlite"),
    ("SELECT * FROM t WHERE name LIKE '%drop table%'", "sqlite"),
    ('SELECT "weird col" FROM "my table"', "sqlite"),
    ("SELECT date_trunc('month', created_at) FROM orders", "postgres"),
    ("-- top customers\nSELECT 1", "sqlite"),
]

BLOCKED = [
    ("", "sqlite", "empty"),
    ("   ;  ", "sqlite", "empty"),
    ("-- only a comment", "sqlite", "empty"),
    ("DELETE FROM orders", "sqlite", "DELETE"),
    ("DROP TABLE orders", "sqlite", "DROP"),
    ("UPDATE orders SET status = 'x'", "sqlite", "UPDATE"),
    ("INSERT INTO orders VALUES (1)", "sqlite", "INSERT"),
    ("REPLACE INTO orders VALUES (1)", "sqlite", "blocked"),
    ("CREATE TABLE z (a INT)", "sqlite", "CREATE"),
    ("ALTER TABLE orders ADD COLUMN x INT", "sqlite", "ALTER"),
    ("PRAGMA table_info(orders)", "sqlite", "PRAGMA"),
    ("ATTACH DATABASE 'other.db' AS other", "sqlite", "ATTACH"),
    ("VACUUM", "sqlite", "blocked"),
    ("BEGIN", "sqlite", "TRANSACTION"),
    ("SELECT 1; DROP TABLE orders", "sqlite", "one SQL statement"),
    ("SELECT load_extension('evil')", "sqlite", "load_extension"),
    ("SELEC * FRM orders", "sqlite", "valid SELECT"),
    ("SELECT * INTO backup FROM orders", "postgres", "INTO"),
    ("SELECT * FROM orders FOR UPDATE", "postgres", "LOCK"),
    ("SELECT pg_sleep(100)", "postgres", "pg_sleep"),
    ("SELECT pg_read_file('/etc/passwd')", "postgres", "pg_read_file"),
    ("WITH d AS (DELETE FROM x RETURNING *) SELECT * FROM d", "postgres", "DELETE"),
]


@pytest.mark.parametrize("sql,dialect", ALLOWED)
def test_allows_read_only_queries(sql, dialect):
    cleaned = validate_read_only(sql, dialect)
    assert not cleaned.endswith(";")
    assert cleaned == cleaned.strip()


@pytest.mark.parametrize("sql,dialect,expected", BLOCKED)
def test_blocks_unsafe_or_invalid_sql(sql, dialect, expected):
    with pytest.raises(UnsafeSQLError) as exc:
        validate_read_only(sql, dialect)
    assert expected.lower() in str(exc.value).lower()
