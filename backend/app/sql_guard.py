"""Static safety checks for SQL before it reaches a database.

Only single, read-only queries (SELECT / WITH ... SELECT / UNION ...) are allowed.
This is the first layer of defence; the database connection itself is also
opened read-only (see database.py), so a query that slips past this check
still cannot modify data.
"""

from __future__ import annotations

import logging

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

# sqlglot logs a warning whenever it falls back to a generic Command node; we
# reject those anyway, so keep the server log quiet.
logging.getLogger("sqlglot").setLevel(logging.ERROR)

_STATEMENT_KEYS = {
    "insert", "update", "delete", "drop", "create", "alter", "merge", "command",
    "pragma", "attach", "detach", "transaction", "commit", "rollback", "set", "use",
    "grant", "revoke", "copy", "describe", "show", "analyze", "truncatetable",
}

# SQLAlchemy dialect name -> sqlglot dialect name
DIALECT_MAP = {
    "sqlite": "sqlite",
    "postgresql": "postgres",
    "mysql": "mysql",
    "mariadb": "mysql",
    "mssql": "tsql",
    "oracle": "oracle",
    "duckdb": "duckdb",
    "snowflake": "snowflake",
    "bigquery": "bigquery",
}

_FORBIDDEN_NODE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Drop",
    "Create",
    "Alter",
    "AlterTable",
    "Merge",
    "TruncateTable",
    "Command",
    "Into",
    "Set",
    "Use",
    "Transaction",
    "Commit",
    "Rollback",
    "Grant",
    "Revoke",
    "Copy",
    "LoadData",
    "Lock",
    "Pragma",
    "Attach",
    "Detach",
)
FORBIDDEN_NODES = tuple(
    getattr(exp, name) for name in _FORBIDDEN_NODE_NAMES if hasattr(exp, name)
)

# Functions that read files, sleep, or reach outside the database.
FORBIDDEN_FUNCTIONS = {
    "load_extension",
    "readfile",
    "writefile",
    "edit",
    "fts3_tokenizer",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "pg_sleep",
    "pg_sleep_for",
    "pg_sleep_until",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_reload_conf",
    "lo_import",
    "lo_export",
    "dblink",
    "dblink_exec",
    "sleep",
    "benchmark",
    "load_file",
    "xp_cmdshell",
    "openrowset",
    "opendatasource",
}


class UnsafeSQLError(ValueError):
    """Raised when SQL is not a single read-only query."""


def to_sqlglot_dialect(sqlalchemy_dialect: str) -> str | None:
    return DIALECT_MAP.get(sqlalchemy_dialect)


def _function_name(node: exp.Expression) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.this).lower()
    return node.key.lower()


def validate_read_only(sql: str, dialect: str | None = None) -> str:
    """Return the cleaned SQL if it is a single read-only query, else raise UnsafeSQLError.

    `dialect` is a sqlglot dialect name (e.g. "sqlite", "postgres").
    """
    cleaned = (sql or "").strip()
    while cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    if not cleaned:
        raise UnsafeSQLError("The query is empty.")

    try:
        statements = [s for s in sqlglot.parse(cleaned, read=dialect) if s is not None]
    except (ParseError, TokenError) as e:
        first_line = str(e).splitlines()[0] if str(e) else "parse error"
        raise UnsafeSQLError(f"Could not parse the SQL: {first_line}") from e

    if not statements:
        raise UnsafeSQLError("The query is empty.")
    if len(statements) > 1:
        raise UnsafeSQLError("Only one SQL statement can be run at a time.")

    root = statements[0]
    if not isinstance(root, exp.Query):
        if isinstance(root, FORBIDDEN_NODES) or root.key in _STATEMENT_KEYS:
            kind = "REPLACE/other" if root.key == "command" else root.key.upper()
            raise UnsafeSQLError(
                f"Only read-only SELECT queries are allowed; {kind} statements are blocked."
            )
        raise UnsafeSQLError("This doesn't look like a valid SELECT query.")

    for node in root.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafeSQLError(
                f"Only read-only queries are allowed ({node.key.upper()} is not permitted)."
            )
        if isinstance(node, exp.Func) and _function_name(node) in FORBIDDEN_FUNCTIONS:
            raise UnsafeSQLError(f"The function {_function_name(node)}() is not allowed.")

    return cleaned
