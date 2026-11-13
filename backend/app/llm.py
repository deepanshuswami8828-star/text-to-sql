"""Natural language -> SQL with Claude (Anthropic) or Groq.

Claude uses structured outputs so every response is JSON matching OUTPUT_SCHEMA,
and prompt caching on the system prompt (instructions + database schema), which
is identical for every question about the same database. Groq uses JSON mode
with the same prompt.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

import anthropic
import groq

from .config import Settings
from .schemas import HistoryTurn

log = logging.getLogger(__name__)

DIALECT_LABELS = {
    "sqlite": "SQLite",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mariadb": "MariaDB",
    "mssql": "SQL Server (T-SQL)",
    "oracle": "Oracle",
    "duckdb": "DuckDB",
}

DIALECT_TIPS = {
    "sqlite": (
        "SQLite tips: dates are stored as ISO-8601 TEXT, so use strftime('%Y', col), "
        "strftime('%Y-%m', col), date(col, '-30 day') and date('now'). "
        "Use || for string concatenation and CAST(x AS REAL) to avoid integer division. "
        "There is no ILIKE (LIKE is already case-insensitive for ASCII)."
    ),
    "postgresql": (
        "PostgreSQL tips: use date_trunc('month', col), EXTRACT(YEAR FROM col), "
        "ILIKE for case-insensitive matching, and ::numeric before ROUND(x, 2)."
    ),
    "mysql": "MySQL tips: use DATE_FORMAT(col, '%Y-%m'), YEAR(col), CONCAT(a, b) and backtick-quoted identifiers.",
}

SYSTEM_TEMPLATE = """\
You are an expert data analyst. You turn questions about a {dialect} database into one correct, \
efficient SQL query, and you explain the result in plain language.

<schema>
{schema}
</schema>

How to write the query:
- Write exactly one read-only query: SELECT, or WITH ... SELECT. Never write statements that change data or schema; they are blocked anyway.
- Use only the tables and columns in the schema above. Quote identifiers that contain spaces, capitals or reserved words.
- Use {dialect} syntax and functions. {tips}
- Join tables on their foreign keys. Give every computed column a short, readable alias (e.g. total_revenue).
- Round money and averages to 2 decimal places. Use the known column values listed in the schema for filters (match their exact spelling and case).
- For "top N", "most", "highest" or "lowest" questions, sort the results and add a LIMIT. Otherwise return all matching rows; the app limits how many rows it displays.
- Questions about trends over time should return one row per period, ordered by period.
- If a question is ambiguous (e.g. what counts as revenue, whether cancelled orders count), choose the most sensible business interpretation and mention it in the explanation.

When the question can't be answered:
- If the schema doesn't contain the data needed, or the message isn't a question about this data, set answerable to false, leave sql empty, and use the explanation to say briefly what the database does contain.

The explanation:
- One to three short sentences for a non-technical reader: what the query returns and any assumptions you made. Don't restate the SQL.
- Write it in the same language the user wrote the question in.
"""

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answerable": {
            "type": "boolean",
            "description": "False if the question can't be answered from this database.",
        },
        "sql": {
            "type": "string",
            "description": "A single read-only SQL query, or an empty string if not answerable.",
        },
        "explanation": {
            "type": "string",
            "description": "Plain-language summary of what the query returns and any assumptions.",
        },
    },
    "required": ["answerable", "sql", "explanation"],
    "additionalProperties": False,
}

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    """Claude could not produce SQL. `status_code` is what the API route should return."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class Generation:
    answerable: bool
    sql: str
    explanation: str
    # Full assistant content blocks, passed back unchanged when asking Claude to repair a query.
    raw_content: Any = field(default=None, repr=False)


@dataclass
class Failure:
    generation: Generation
    error: str


class SQLGenerator(Protocol):
    def generate(
        self,
        *,
        dialect: str,
        schema: str,
        question: str,
        history: list[HistoryTurn],
        failures: list[Failure],
    ) -> Generation: ...


def _error_detail(e: Exception) -> str:
    """The human-readable message inside an API error body, without the SDK's wrapper text."""
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        if isinstance(err.get("message"), str):
            return err["message"]
    return str(getattr(e, "message", e))


def parse_answer(text: str) -> dict[str, Any]:
    """Parse the model's JSON answer, tolerating code fences or reasoning text around it."""
    cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("The AI returned a malformed answer. Try again.", 502) from None
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            raise LLMError("The AI returned a malformed answer. Try again.", 502) from None
    if not isinstance(data, dict):
        raise LLMError("The AI returned a malformed answer. Try again.", 502)
    return data


def _to_generation(data: dict[str, Any], raw_content: Any) -> Generation:
    return Generation(
        answerable=bool(data.get("answerable")),
        sql=str(data.get("sql") or "").strip(),
        explanation=str(data.get("explanation") or "").strip(),
        raw_content=raw_content,
    )


def build_system_prompt(dialect: str, schema: str) -> str:
    label = DIALECT_LABELS.get(dialect, dialect)
    return SYSTEM_TEMPLATE.format(dialect=label, schema=schema, tips=DIALECT_TIPS.get(dialect, ""))


def build_user_message(question: str, history: list[HistoryTurn], today: date | None = None) -> str:
    parts = []
    if history:
        parts.append("Earlier in this conversation (the new question may refer to these):")
        for i, turn in enumerate(history, start=1):
            parts.append(f"{i}. Question: {turn.question}")
            if turn.sql:
                parts.append(f"   SQL: {turn.sql}")
        parts.append("")
    parts.append(f"Today's date: {(today or date.today()).isoformat()}")
    parts.append(f"Question: {question}")
    return "\n".join(parts)


def repair_message(error: str) -> str:
    return (
        "Running that query against the database failed with this error:\n"
        f"{error}\n\n"
        "Write a corrected query that answers the same question."
    )


class ClaudeSQLGenerator:
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None):
        self.settings = settings
        self._client = client

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            kwargs: dict[str, Any] = {"timeout": 180.0, "max_retries": 2}
            if self.settings.anthropic_api_key:
                kwargs["api_key"] = self.settings.anthropic_api_key
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def generate(
        self,
        *,
        dialect: str,
        schema: str,
        question: str,
        history: list[HistoryTurn],
        failures: list[Failure],
    ) -> Generation:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": build_user_message(question, history)}
        ]
        for failure in failures:
            messages.append({"role": "assistant", "content": failure.generation.raw_content})
            messages.append({"role": "user", "content": repair_message(failure.error)})

        params: dict[str, Any] = {
            "model": self.settings.claude_model,
            "max_tokens": 16000,
            "system": [
                {
                    "type": "text",
                    "text": build_system_prompt(dialect, schema),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": messages,
            "output_config": {
                "effort": self.settings.claude_effort,
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
        }
        if self.settings.use_fallbacks:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"

        try:
            response = self.client.beta.messages.create(**params)
        except anthropic.AuthenticationError as e:
            raise LLMError("The Claude API key was rejected. Check ANTHROPIC_API_KEY in your .env file.", 502) from e
        except anthropic.PermissionDeniedError as e:
            raise LLMError(f"The Claude API key doesn't have access to this model: {e.message}", 502) from e
        except anthropic.NotFoundError as e:
            raise LLMError(f"Model '{self.settings.claude_model}' was not found. Check CLAUDE_MODEL.", 502) from e
        except anthropic.RateLimitError as e:
            raise LLMError("Claude is rate limiting requests right now. Wait a moment and try again.", 429) from e
        except anthropic.BadRequestError as e:
            detail = _error_detail(e)
            if "credit balance" in detail.lower():
                raise LLMError(
                    "Your Anthropic account is out of credits. Add credits in the Anthropic Console "
                    "(Plans & Billing), then try again.",
                    402,
                ) from e
            raise LLMError(f"Claude rejected the request: {detail}", 502) from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error ({e.status_code}). Try again shortly.", 502) from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Couldn't reach the Claude API. Check your internet connection.", 502) from e

        if response.stop_reason == "refusal":
            raise LLMError("Claude declined to answer this question. Try rephrasing it.", 422)
        if response.stop_reason == "max_tokens":
            raise LLMError("Claude's answer was cut off. Try a simpler or more specific question.", 502)

        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LLMError("Claude returned no answer. Try again.", 502)
        data = parse_answer(text)

        usage = response.usage
        log.info(
            "claude model=%s input=%s cache_read=%s output=%s",
            response.model, usage.input_tokens, getattr(usage, "cache_read_input_tokens", None),
            usage.output_tokens,
        )
        return _to_generation(data, response.content)


JSON_INSTRUCTION = """
Reply with only a JSON object and no other text, in exactly this shape:
{"answerable": true, "sql": "SELECT ...", "explanation": "..."}
"""


class GroqSQLGenerator:
    """Uses Groq's API (free tier available) with open models such as gpt-oss or Llama."""

    def __init__(self, settings: Settings, client: groq.Groq | None = None):
        self.settings = settings
        self._client = client

    @property
    def client(self) -> groq.Groq:
        if self._client is None:
            self._client = groq.Groq(
                api_key=self.settings.groq_api_key or os.environ.get("GROQ_API_KEY"),
                timeout=120.0,
                max_retries=2,
            )
        return self._client

    def generate(
        self,
        *,
        dialect: str,
        schema: str,
        question: str,
        history: list[HistoryTurn],
        failures: list[Failure],
    ) -> Generation:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt(dialect, schema) + JSON_INSTRUCTION},
            {"role": "user", "content": build_user_message(question, history)},
        ]
        for failure in failures:
            messages.append({"role": "assistant", "content": failure.generation.raw_content})
            messages.append({"role": "user", "content": repair_message(failure.error)})

        try:
            response = self.client.chat.completions.create(
                model=self.settings.groq_model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_completion_tokens=8192,
            )
        except groq.AuthenticationError as e:
            raise LLMError("The Groq API key was rejected. Check GROQ_API_KEY in your .env file.", 502) from e
        except groq.NotFoundError as e:
            raise LLMError(f"Groq model '{self.settings.groq_model}' was not found. Check GROQ_MODEL.", 502) from e
        except groq.RateLimitError as e:
            raise LLMError(
                "Groq's free-tier limit was reached. Wait a minute and try again.", 429
            ) from e
        except groq.BadRequestError as e:
            detail = _error_detail(e)
            if "json" in detail.lower():
                raise LLMError("The AI returned a malformed answer. Try again or rephrase the question.", 502) from e
            raise LLMError(f"Groq rejected the request: {detail}", 502) from e
        except groq.APIStatusError as e:
            raise LLMError(f"Groq API error ({e.status_code}). Try again shortly.", 502) from e
        except groq.APIConnectionError as e:
            raise LLMError("Couldn't reach the Groq API. Check your internet connection.", 502) from e

        if not response.choices:
            raise LLMError("The AI returned no answer. Try again.", 502)
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise LLMError("The AI's answer was cut off. Try a simpler or more specific question.", 502)
        text = choice.message.content or ""
        data = parse_answer(text)
        if response.usage:
            log.info(
                "groq model=%s input=%s output=%s",
                response.model, response.usage.prompt_tokens, response.usage.completion_tokens,
            )
        return _to_generation(data, text)


def make_generator(settings: Settings) -> SQLGenerator:
    """Build the generator for the configured provider."""
    if settings.provider == "groq":
        return GroqSQLGenerator(settings)
    return ClaudeSQLGenerator(settings)
