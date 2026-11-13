"""Checks the request we send to the Claude API and how responses are parsed.

No network: the SDK is given a mock HTTP transport that records requests and returns canned replies.
"""

import json
from datetime import date

import anthropic
import httpx2
import pytest

from app.config import Settings
from app.llm import (
    OUTPUT_SCHEMA,
    ClaudeSQLGenerator,
    Failure,
    LLMError,
    build_system_prompt,
    build_user_message,
)
from app.schemas import HistoryTurn


def _message(text: str | None, stop_reason: str = "end_turn") -> dict:
    content = [{"type": "text", "text": text}] if text is not None else []
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 0},
    }


class Recorder:
    def __init__(self, replies: list[httpx2.Response]):
        self.replies = replies
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self.replies[min(len(self.requests), len(self.replies)) - 1]

    def body(self, i: int = -1) -> dict:
        return json.loads(self.requests[i].content)


def _generator(recorder: Recorder, **overrides) -> ClaudeSQLGenerator:
    settings = Settings(_env_file=None, anthropic_api_key="test-key", **overrides)
    client = anthropic.Anthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(recorder)),
    )
    return ClaudeSQLGenerator(settings, client=client)


def _ok(answer: dict) -> httpx2.Response:
    return httpx2.Response(200, json=_message(json.dumps(answer)))


def test_request_shape_and_parsing():
    rec = Recorder([_ok({"answerable": True, "sql": "SELECT 1", "explanation": "One."})])
    gen = _generator(rec).generate(
        dialect="sqlite", schema="CREATE TABLE t (a INT);", question="What is one?",
        history=[HistoryTurn(question="earlier q", sql="SELECT 2")], failures=[],
    )
    assert (gen.answerable, gen.sql, gen.explanation) == (True, "SELECT 1", "One.")

    req = rec.requests[0]
    body = rec.body()
    assert req.url.path == "/v1/messages"
    assert "server-side-fallback-2026-07-01" in req.headers.get("anthropic-beta", "")
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert body["output_config"] == {
        "effort": "medium",
        "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
    }
    assert "thinking" not in body and "temperature" not in body
    system = body["system"][0]
    assert system["cache_control"] == {"type": "ephemeral"}
    assert "CREATE TABLE t (a INT);" in system["text"] and "SQLite" in system["text"]
    user = body["messages"][0]["content"]
    assert "Question: What is one?" in user and "earlier q" in user and "SELECT 2" in user


def test_no_fallback_param_for_models_without_it():
    rec = Recorder([_ok({"answerable": True, "sql": "SELECT 1", "explanation": ""})])
    _generator(rec, claude_model="claude-haiku-5-5").generate(
        dialect="sqlite", schema="", question="q", history=[], failures=[])
    assert "fallbacks" not in rec.body()
    assert "anthropic-beta" not in rec.requests[0].headers


def test_repair_turn_includes_previous_answer_and_error():
    rec = Recorder([
        _ok({"answerable": True, "sql": "SELECT bad", "explanation": ""}),
        _ok({"answerable": True, "sql": "SELECT good", "explanation": ""}),
    ])
    g = _generator(rec)
    first = g.generate(dialect="sqlite", schema="", question="q", history=[], failures=[])
    second = g.generate(dialect="sqlite", schema="", question="q", history=[],
                        failures=[Failure(generation=first, error="no such column: bad")])
    assert second.sql == "SELECT good"
    msgs = rec.body(1)["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert "SELECT bad" in json.dumps(msgs[1]["content"])
    assert "no such column: bad" in msgs[2]["content"]


def test_refusal_becomes_friendly_error():
    rec = Recorder([httpx2.Response(200, json=_message(None, stop_reason="refusal"))])
    with pytest.raises(LLMError) as exc:
        _generator(rec).generate(dialect="sqlite", schema="", question="q", history=[], failures=[])
    assert exc.value.status_code == 422


@pytest.mark.parametrize("status,expected_status,needle", [
    (401, 502, "API key"),
    (429, 429, "rate limiting"),
    (500, 502, "Claude API error"),
])
def test_api_errors_are_mapped(status, expected_status, needle):
    rec = Recorder([httpx2.Response(status, json={"type": "error", "error": {"type": "x", "message": "boom"}})])
    with pytest.raises(LLMError) as exc:
        _generator(rec).generate(dialect="sqlite", schema="", question="q", history=[], failures=[])
    assert exc.value.status_code == expected_status
    assert needle in exc.value.message


def test_prompt_builders():
    assert "PostgreSQL" in build_system_prompt("postgresql", "x")
    msg = build_user_message("How many?", [], today=date(2026, 1, 2))
    assert msg == "Today's date: 2026-01-02\nQuestion: How many?"
