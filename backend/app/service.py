"""The question -> SQL -> result pipeline, including automatic query repair."""

from __future__ import annotations

from .config import Settings
from .database import DatabaseRegistry, QueryError
from .llm import Failure, SQLGenerator
from .schemas import Attempt, GenerateRequest, GenerateResponse
from .sql_guard import UnsafeSQLError, to_sqlglot_dialect, validate_read_only


def answer_question(
    req: GenerateRequest,
    registry: DatabaseRegistry,
    generator: SQLGenerator,
    settings: Settings,
) -> GenerateResponse:
    """Ask Claude for SQL, run it, and if it fails let Claude fix it (up to max_fix_attempts times)."""
    info = registry.get(req.database_id)
    schema = registry.schema_prompt(info.id)
    failures: list[Failure] = []
    attempts: list[Attempt] = []

    for _ in range(settings.max_fix_attempts + 1):
        gen = generator.generate(
            dialect=info.dialect,
            schema=schema,
            question=req.question,
            history=req.history,
            failures=failures,
        )
        if not gen.answerable or not gen.sql:
            return GenerateResponse(
                question=req.question,
                answerable=False,
                sql="",
                explanation=gen.explanation or "This question can't be answered from this database.",
                attempts=attempts,
            )

        try:
            if req.execute:
                sql, result = registry.execute(info.id, gen.sql)
            else:
                sql, result = validate_read_only(gen.sql, to_sqlglot_dialect(info.dialect)), None
        except (UnsafeSQLError, QueryError) as e:
            attempts.append(Attempt(sql=gen.sql, error=str(e)))
            failures.append(Failure(generation=gen, error=str(e)))
            continue

        return GenerateResponse(
            question=req.question,
            answerable=True,
            sql=sql,
            explanation=gen.explanation,
            result=result,
            attempts=attempts,
        )

    last = attempts[-1]
    return GenerateResponse(
        question=req.question,
        answerable=True,
        sql=last.sql,
        explanation=gen.explanation,
        error=last.error,
        attempts=attempts[:-1],
    )
