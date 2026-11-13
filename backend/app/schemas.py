"""Pydantic models for API requests and responses."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------- Databases & schema ----------


class DatabaseOut(BaseModel):
    id: str
    name: str
    kind: Literal["sample", "upload", "external"]
    dialect: str
    description: str = ""
    deletable: bool = False


class ColumnOut(BaseModel):
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
    foreign_key: str | None = None  # "other_table.column"
    values: list[str] | None = None  # distinct values for low-cardinality text columns


class TableOut(BaseModel):
    name: str
    kind: Literal["table", "view"] = "table"
    row_count: int | None = None
    columns: list[ColumnOut]
    ddl: str = ""
    sample_rows: list[list[Any]] = Field(default_factory=list)


class SchemaOut(BaseModel):
    database_id: str
    dialect: str
    tables: list[TableOut]


# ---------- Queries ----------


class QueryResult(BaseModel):
    columns: list[str]
    column_types: list[Literal["number", "text", "boolean", "empty"]]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: float


class HistoryTurn(BaseModel):
    """A previous question/SQL pair, sent back so follow-up questions have context."""

    question: str = Field(max_length=4000)
    sql: str = Field(default="", max_length=20000)


class GenerateRequest(BaseModel):
    database_id: str
    question: str = Field(min_length=1, max_length=4000)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=10)
    execute: bool = True
    # If the selected database can't answer, look for another database that can.
    auto_route: bool = True


class Attempt(BaseModel):
    sql: str
    error: str


class GenerateResponse(BaseModel):
    question: str
    database_id: str  # the database that was actually queried
    routed_from: str | None = None  # set when the selected database couldn't answer and another one did
    answerable: bool
    sql: str
    explanation: str
    result: QueryResult | None = None
    error: str | None = None
    attempts: list[Attempt] = Field(default_factory=list)  # failed attempts that Claude repaired
    history_id: int | None = None


class ExecuteRequest(BaseModel):
    database_id: str
    sql: str = Field(min_length=1, max_length=20000)
    question: str | None = Field(default=None, max_length=4000)
    save_to_history: bool = True


class ExecuteResponse(BaseModel):
    sql: str
    result: QueryResult | None = None
    error: str | None = None
    history_id: int | None = None


# ---------- History ----------


class HistoryItem(BaseModel):
    id: int
    database_id: str
    question: str | None
    sql: str
    explanation: str | None
    row_count: int | None
    error: str | None
    source: Literal["ai", "manual"]
    starred: bool
    created_at: str


class HistoryUpdate(BaseModel):
    starred: bool


# ---------- Misc ----------


class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"
    llm_enabled: bool
    provider: Literal["anthropic", "groq"] | None = None
    model: str
    max_rows: int
    version: str
