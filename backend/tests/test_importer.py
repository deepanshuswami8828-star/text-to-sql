import sqlite3

import pytest

from app.importer import UploadError, import_csv, slugify


def _table(db, name):
    conn = sqlite3.connect(db)
    try:
        cols = [(r[1], r[2]) for r in conn.execute(f'PRAGMA table_info("{name}")')]
        rows = conn.execute(f'SELECT * FROM "{name}"').fetchall()
    finally:
        conn.close()
    return cols, rows


def test_slugify():
    assert slugify("Sales Report 2025.csv") == "sales_report_2025_csv"
    assert slugify("2025 data") == "data_2025_data"
    assert slugify("!!!") == "data"


def test_import_infers_types_and_cleans_headers(tmp_path):
    csv_file = tmp_path / "people.csv"
    csv_file.write_text(
        "Name,Age,Salary (INR),Zip,Name\n"
        "Asha,31,55000.5,00123,x\n"
        "Ravi,,62000,40001,y\n",
        encoding="utf-8",
    )
    db = tmp_path / "out.db"
    table = import_csv(csv_file, db, "people")
    assert table == "people"
    cols, rows = _table(db, "people")
    assert cols == [("name", "TEXT"), ("age", "INTEGER"), ("salary_inr", "REAL"), ("zip", "TEXT"), ("name_2", "TEXT")]
    assert rows == [("Asha", 31, 55000.5, "00123", "x"), ("Ravi", None, 62000.0, "40001", "y")]


def test_import_semicolon_csv_with_bom_and_ragged_rows(tmp_path):
    csv_file = tmp_path / "data.csv"
    csv_file.write_bytes("﻿city;sales\nPune;10\nDelhi;20;extra\nGoa\n".encode())
    db = tmp_path / "out.db"
    import_csv(csv_file, db, "data")
    cols, rows = _table(db, "data")
    assert [c[0] for c in cols] == ["city", "sales"]
    assert rows == [("Pune", 10), ("Delhi", 20), ("Goa", None)]


def test_import_adds_unique_table_name(tmp_path):
    csv_file = tmp_path / "t.csv"
    csv_file.write_text("a\n1\n")
    db = tmp_path / "out.db"
    assert import_csv(csv_file, db, "t") == "t"
    assert import_csv(csv_file, db, "t") == "t_2"


def test_import_rejects_header_only(tmp_path):
    csv_file = tmp_path / "t.csv"
    csv_file.write_text("a,b\n")
    with pytest.raises(UploadError, match="no data rows"):
        import_csv(csv_file, tmp_path / "out.db", "t")
