"""The question -> SQL -> result pipeline, with automatic query repair and database routing."""

from __future__ import annotations

import logging

from .config import Settings
from .database import DatabaseRegistry, QueryError
from .llm import Failure, LLMError, SQLGenerator
from .schemas import Attempt, GenerateRequest, GenerateResponse, HistoryTurn
from .sql_guard import UnsafeSQLError, to_sqlglot_dialect, validate_read_only

log = logging.getLogger(__name__)


def answer_question(
    req: GenerateRequest,
    registry: DatabaseRegistry,
    generator: SQLGenerator,
    settings: Settings,
) -> GenerateResponse:
    """Answer on the selected database. If it doesn't have the data, find another database that does."""
    response = _answer_on(req.database_id, req.question, req.history, req.execute, registry, generator, settings)
    if response.answerable or not (req.auto_route and settings.auto_route):
        return response

    target = _pick_other_database(req, registry, generator)
    if target is None:
        return response
    routed = _answer_on(target, req.question, [], req.execute, registry, generator, settings)
    if not routed.answerable:
        return response
    routed.routed_from = req.database_id
    return routed


def _pick_other_database(req: GenerateRequest, registry: DatabaseRegistry, generator: SQLGenerator) -> str | None:
    others = {d.id for d in registry.list() if d.id != req.database_id}
    if not others:
        return None
    catalog = registry.catalog_text(exclude=req.database_id)
    if not catalog:
        return None
    try:
        target = generator.route(question=req.question, catalog=catalog)
    except LLMError as e:
        log.info("Routing failed: %s", e.message)
        return None
    return target if target in others else None


def _answer_on(
    database_id: str,
    question: str,
    history: list[HistoryTurn],
    execute: bool,
    registry: DatabaseRegistry,
    generator: SQLGenerator,
    settings: Settings,
) -> GenerateResponse:
    """Ask for SQL on one database, run it, and if it fails let the AI fix it (up to max_fix_attempts times)."""
    info = registry.get(database_id)
    schema = registry.schema_prompt(info.id)
    failures: list[Failure] = []
    attempts: list[Attempt] = []

    for _ in range(settings.max_fix_attempts + 1):
        gen = generator.generate(
            dialect=info.dialect,
            schema=schema,
            question=question,
            history=history,
            failures=failures,
        )
        if not gen.answerable or not gen.sql:
            return GenerateResponse(
                question=question,
                database_id=info.id,
                answerable=False,
                sql="",
                explanation=gen.explanation or "This question can't be answered from this database.",
                attempts=attempts,
            )

        try:
            if execute:
                sql, result = registry.execute(info.id, gen.sql)
            else:
                sql, result = validate_read_only(gen.sql, to_sqlglot_dialect(info.dialect)), None
        except (UnsafeSQLError, QueryError) as e:
            attempts.append(Attempt(sql=gen.sql, error=str(e)))
            failures.append(Failure(generation=gen, error=str(e)))
            continue

        return GenerateResponse(
            question=question,
            database_id=info.id,
            answerable=True,
            sql=sql,
            explanation=gen.explanation,
            result=result,
            attempts=attempts,
        )

    last = attempts[-1]
    return GenerateResponse(
        question=question,
        database_id=info.id,
        answerable=True,
        sql=last.sql,
        explanation=gen.explanation,
        error=last.error,
        attempts=attempts[:-1],
    )
