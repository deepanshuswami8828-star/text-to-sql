"""Groq provider: request shape, parsing, errors, and provider selection. No network calls."""

import json

import groq
import httpx
import pytest

from app.config import Settings
from app.llm import (
    ClaudeSQLGenerator,
    Failure,
    GroqSQLGenerator,
    LLMError,
    make_generator,
    parse_answer,
)


def _completion(content: str, finish_reason: str = "stop") -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "openai/gpt-oss-120b",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
    }


class Recorder:
    def __init__(self, replies: list[httpx.Response]):
        self.replies = replies
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.replies[min(len(self.requests), len(self.replies)) - 1]

    def body(self, i: int = -1) -> dict:
        return json.loads(self.requests[i].content)


def _generator(rec: Recorder) -> GroqSQLGenerator:
    settings = Settings(_env_file=None, llm_provider="groq", groq_api_key="test-key")
    client = groq.Groq(api_key="test-key", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(rec)))
    return GroqSQLGenerator(settings, client=client)


def _ok(answer: dict) -> httpx.Response:
    return httpx.Response(200, json=_completion(json.dumps(answer)))


def test_groq_request_shape_and_parsing():
    rec = Recorder([_ok({"answerable": True, "sql": "SELECT 1", "explanation": "One."})])
    gen = _generator(rec).generate(dialect="sqlite", schema="CREATE TABLE t (a INT);", question="What is one?",
                                   history=[], failures=[])
    assert (gen.answerable, gen.sql, gen.explanation) == (True, "SELECT 1", "One.")
    assert rec.requests[0].url.path.endswith("/chat/completions")
    body = rec.body()
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["response_format"] == {"type": "json_object"}
    system, user = body["messages"]
    assert system["role"] == "system" and "CREATE TABLE t (a INT);" in system["content"] and "JSON" in system["content"]
    assert user["role"] == "user" and "Question: What is one?" in user["content"]


def test_groq_repair_turn_includes_previous_answer_and_error():
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
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert "SELECT bad" in msgs[2]["content"]
    assert "no such column: bad" in msgs[3]["content"]


@pytest.mark.parametrize("status,expected_status,needle", [
    (401, 502, "GROQ_API_KEY"),
    (429, 429, "free-tier limit"),
    (404, 502, "GROQ_MODEL"),
    (500, 502, "Groq API error"),
])
def test_groq_errors_are_mapped(status, expected_status, needle):
    rec = Recorder([httpx.Response(status, json={"error": {"message": "boom", "type": "x"}})])
    with pytest.raises(LLMError) as exc:
        _generator(rec).generate(dialect="sqlite", schema="", question="q", history=[], failures=[])
    assert exc.value.status_code == expected_status
    assert needle in exc.value.message


def test_groq_cut_off_answer():
    rec = Recorder([httpx.Response(200, json=_completion('{"answerable": true, "sql": "SEL', finish_reason="length"))])
    with pytest.raises(LLMError, match="cut off"):
        _generator(rec).generate(dialect="sqlite", schema="", question="q", history=[], failures=[])


def test_parse_answer_tolerates_wrapping():
    expected = {"answerable": True, "sql": "SELECT 1", "explanation": "x"}
    assert parse_answer(json.dumps(expected)) == expected
    assert parse_answer("```json\n" + json.dumps(expected) + "\n```") == expected
    assert parse_answer("<think>hmm {not json}</think>" + json.dumps(expected)) == expected
    with pytest.raises(LLMError, match="malformed"):
        parse_answer("no json here")


@pytest.fixture
def no_env_keys(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GROQ_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("provider,anthropic_key,groq_key,expected", [
    ("auto", None, None, None),
    ("auto", "a", None, "anthropic"),
    ("auto", None, "g", "groq"),
    ("auto", "a", "g", "anthropic"),
    ("groq", "a", "g", "groq"),
    ("groq", "a", None, None),
    ("anthropic", None, "g", None),
])
def test_provider_selection(no_env_keys, provider, anthropic_key, groq_key, expected):
    s = Settings(_env_file=None, llm_provider=provider, anthropic_api_key=anthropic_key, groq_api_key=groq_key)
    assert s.provider == expected
    assert s.llm_enabled is (expected is not None)


def test_make_generator_and_active_model(no_env_keys):
    s = Settings(_env_file=None, llm_provider="groq", groq_api_key="g", groq_model="llama-test")
    assert isinstance(make_generator(s), GroqSQLGenerator)
    assert s.active_model == "llama-test"
    s = Settings(_env_file=None, anthropic_api_key="a")
    assert isinstance(make_generator(s), ClaudeSQLGenerator)
    assert s.active_model == "claude-opus-5-5"
