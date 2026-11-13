import io
import sqlite3
from decimal import Decimal

import pytest

from app.database import DatabaseRegistry, QueryError, to_jsonable
from app.importer import UploadError
from app.sql_guard import UnsafeSQLError


def test_sample_database_is_registered(registry: DatabaseRegistry):
    ids = [d.id for d in registry.list()]
    assert ids == ["ecommerce"]
    assert registry.get("ecommerce").kind == "sample"


def test_schema_introspection(registry: DatabaseRegistry):
    schema = registry.schema("ecommerce")
    tables = {t.name: t for t in schema.tables}
    assert set(tables) == {"categories", "products", "customers", "employees", "orders", "order_items", "reviews"}
    orders = tables["orders"]
    assert orders.row_count == 2000
    cols = {c.name: c for c in orders.columns}
    assert cols["order_id"].primary_key
    assert cols["customer_id"].foreign_key == "customers.customer_id"
    assert cols["status"].values == ["cancelled", "delivered", "processing", "returned", "shipped"]
    assert len(orders.sample_rows) == 3
    # name-like columns are not listed as categorical values
    assert {c.name: c for c in tables["customers"].columns}["first_name"].values is None


def test_schema_prompt_has_ddl_values_and_samples(registry: DatabaseRegistry):
    prompt = registry.schema_prompt("ecommerce")
    assert "CREATE TABLE orders" in prompt
    assert "-- selling price in INR" in prompt  # original DDL comments are kept
    assert "orders.payment_method values:" in prompt
    assert "-- sample rows" in prompt


def test_execute_returns_rows_and_types(registry: DatabaseRegistry):
    sql, result = registry.execute(
        "ecommerce", "SELECT status, COUNT(*) AS n FROM orders GROUP BY status ORDER BY n DESC;"
    )
    assert sql.endswith("DESC")
    assert result.columns == ["status", "n"]
    assert result.column_types == ["text", "number"]
    assert result.rows[0][0] == "delivered"
    assert sum(r[1] for r in result.rows) == 2000
    assert not result.truncated


def test_execute_truncates_to_max_rows(registry: DatabaseRegistry):
    _, result = registry.execute("ecommerce", "SELECT * FROM orders")
    assert result.row_count == registry.settings.max_rows == 50
    assert result.truncated


def test_execute_blocks_writes(registry: DatabaseRegistry):
    with pytest.raises(UnsafeSQLError):
        registry.execute("ecommerce", "DELETE FROM orders")


def test_connection_is_read_only_even_if_guard_is_bypassed(registry: DatabaseRegistry):
    with registry.engine("ecommerce").connect() as conn:
        with pytest.raises(Exception, match="readonly|read-only|query_only"):
            conn.exec_driver_sql("DELETE FROM orders")


def test_execute_reports_sql_errors(registry: DatabaseRegistry):
    with pytest.raises(QueryError, match="no such table"):
        registry.execute("ecommerce", "SELECT * FROM missing_table")


def test_execute_times_out_long_queries(registry: DatabaseRegistry):
    registry.settings.query_timeout_seconds = 0.3
    endless = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT COUNT(*) FROM n"
    with pytest.raises(QueryError, match="longer than"):
        registry.execute("ecommerce", endless)


def test_to_jsonable():
    assert to_jsonable(Decimal("2.50")) == 2.5
    assert to_jsonable(Decimal("3")) == 3
    assert to_jsonable(b"\x00\x01") == "<2 bytes>"
    assert to_jsonable(float("nan")) == "nan"


def test_upload_sqlite_file_and_delete(registry: DatabaseRegistry, tmp_path):
    src = tmp_path / "shop.sqlite"
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO items VALUES (1, 'pen'), (2, 'book')")
    conn.commit()
    conn.close()

    info = registry.add_upload("My Shop.sqlite", io.BytesIO(src.read_bytes()))
    assert info.id == "my_shop" and info.kind == "upload"
    _, result = registry.execute("my_shop", "SELECT name FROM items ORDER BY id")
    assert result.rows == [["pen"], ["book"]]

    registry.delete_upload("my_shop")
    assert "my_shop" not in [d.id for d in registry.list()]
    assert not (registry.settings.uploads_dir / "my_shop.db").exists()


def test_upload_rejects_bad_files(registry: DatabaseRegistry):
    with pytest.raises(UploadError, match="not a SQLite database"):
        registry.add_upload("fake.db", io.BytesIO(b"hello world, definitely not sqlite"))
    with pytest.raises(UploadError, match="Upload a SQLite"):
        registry.add_upload("photo.png", io.BytesIO(b"\x89PNG"))
    with pytest.raises(UploadError, match="empty"):
        registry.add_upload("empty.csv", io.BytesIO(b""))
    # nothing half-written is left behind
    assert list(registry.settings.uploads_dir.glob("*")) == []


def test_upload_size_limit(registry: DatabaseRegistry):
    registry.settings.max_upload_mb = 1
    with pytest.raises(UploadError, match="larger than 1 MB"):
        registry.add_upload("big.csv", io.BytesIO(b"a\n" + b"1\n" * 600_000))


def test_cannot_delete_sample(registry: DatabaseRegistry):
    with pytest.raises(UploadError):
        registry.delete_upload("ecommerce")
