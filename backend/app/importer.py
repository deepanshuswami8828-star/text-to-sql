"""Turn an uploaded CSV file into a table inside a SQLite database."""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from pathlib import Path


class UploadError(ValueError):
    """Raised when an uploaded file can't be imported."""


def slugify(text: str, fallback: str = "data") -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()
    if not slug:
        slug = fallback
    if slug[0].isdigit():
        slug = f"{fallback}_{slug}"
    return slug[:60]


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UploadError("Could not decode the CSV file (expected UTF-8 text).")


def _clean_headers(header: list[str]) -> list[str]:
    names: list[str] = []
    seen: dict[str, int] = {}
    for i, h in enumerate(header, start=1):
        name = slugify(h, fallback="col") if h.strip() else f"col_{i}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        names.append(name)
    return names


def _has_leading_zero(v: str) -> bool:
    """True for identifiers like zip codes or phone numbers ("00123"), which must stay text."""
    s = v.lstrip("+-")
    return len(s) > 1 and s[0] == "0" and s[1].isdigit()


def _is_int(v: str) -> bool:
    try:
        int(v)
    except ValueError:
        return False
    return not _has_leading_zero(v)


def _is_float(v: str) -> bool:
    try:
        float(v)
    except ValueError:
        return False
    return not _has_leading_zero(v) and v.lower() not in {"nan", "inf", "-inf", "infinity", "-infinity"}


def _detect_delimiter(text: str) -> str:
    """Pick the candidate delimiter that appears most often in the header line."""
    header = text.split("\n", 1)[0]
    counts = {d: header.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def _infer_type(values: list[str]) -> str:
    non_empty = [v for v in values if v != ""]
    if not non_empty:
        return "TEXT"
    if all(_is_int(v) for v in non_empty):
        return "INTEGER"
    if all(_is_float(v) for v in non_empty):
        return "REAL"
    return "TEXT"


def _convert(value: str, sql_type: str):
    if value == "":
        return None
    if sql_type == "INTEGER":
        return int(value)
    if sql_type == "REAL":
        return float(value)
    return value


def unique_table_name(conn: sqlite3.Connection, base: str) -> str:
    existing = {r[0].lower() for r in conn.execute("SELECT name FROM sqlite_master")}
    name, n = base, 1
    while name.lower() in existing:
        n += 1
        name = f"{base}_{n}"
    return name


def import_csv(csv_path: Path, db_path: Path, table_base_name: str) -> str:
    """Load `csv_path` into a new table in the SQLite file `db_path`. Returns the table name."""
    text = _decode(csv_path.read_bytes())
    if not text.strip():
        raise UploadError("The CSV file is empty.")

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_detect_delimiter(text))
    try:
        header = next(reader)
    except StopIteration:
        raise UploadError("The CSV file has no header row.") from None
    columns = _clean_headers(header)
    width = len(columns)
    rows = []
    for row in reader:
        if not row or all(not cell.strip() for cell in row):
            continue
        row = [cell.strip() for cell in row[:width]]
        row += [""] * (width - len(row))
        rows.append(row)
    if not rows:
        raise UploadError("The CSV file has a header but no data rows.")

    types = [_infer_type([r[i] for r in rows]) for i in range(width)]

    conn = sqlite3.connect(db_path)
    try:
        table = unique_table_name(conn, table_base_name)
        cols_sql = ", ".join(f'"{c}" {t}' for c, t in zip(columns, types))
        conn.execute(f'CREATE TABLE "{table}" ({cols_sql})')
        placeholders = ", ".join("?" for _ in columns)
        conn.executemany(
            f'INSERT INTO "{table}" VALUES ({placeholders})',
            ([_convert(v, t) for v, t in zip(r, types)] for r in rows),
        )
        conn.commit()
    finally:
        conn.close()
    return table


SQLITE_HEADER = b"SQLite format 3\x00"


def check_sqlite_file(path: Path) -> None:
    """Raise UploadError unless `path` is a readable SQLite database with at least one table."""
    with path.open("rb") as f:
        if f.read(16) != SQLITE_HEADER:
            raise UploadError("This file is not a SQLite database.")
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        raise UploadError(f"Could not read the SQLite database: {e}") from e
    if n == 0:
        raise UploadError("The SQLite database has no tables.")
