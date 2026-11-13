from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import DatabaseRegistry
from app.llm import Failure, Generation
from app.main import create_app
from app.schemas import HistoryTurn
from app.seed import ensure_sample_databases


@pytest.fixture(scope="session")
def built_samples(tmp_path_factory) -> Path:
    """Build the sample databases once per test session."""
    sample_dir = tmp_path_factory.mktemp("sample")
    ensure_sample_databases(sample_dir)
    return sample_dir


@pytest.fixture
def settings(tmp_path: Path, built_samples: Path) -> Settings:
    data = tmp_path / "data"
    (data / "sample").mkdir(parents=True)
    for db_file in built_samples.glob("*.db"):
        (data / "sample" / db_file.name).write_bytes(db_file.read_bytes())
    return Settings(
        _env_file=None,
        anthropic_api_key=None,
        data_dir=data,
        frontend_dist=tmp_path / "no-frontend",
        max_rows=50,
        query_timeout_seconds=2,
        max_fix_attempts=2,
    )


@pytest.fixture
def registry(settings: Settings) -> DatabaseRegistry:
    reg = DatabaseRegistry(settings)
    reg.refresh()
    return reg


class FakeGenerator:
    """Stands in for Claude: returns scripted answers and records what it was asked."""

    def __init__(self, script: list[Generation] | Callable[..., Generation] | None = None):
        self.script = script
        self.calls: list[dict] = []

    def generate(self, *, dialect: str, schema: str, question: str,
                 history: list[HistoryTurn], failures: list[Failure]) -> Generation:
        self.calls.append(dict(dialect=dialect, schema=schema, question=question,
                               history=history, failures=list(failures)))
        if callable(self.script):
            return self.script(question=question, failures=failures)
        if self.script:
            return self.script[min(len(self.calls), len(self.script)) - 1]
        return Generation(answerable=True, sql="SELECT COUNT(*) AS n FROM customers",
                          explanation="Counts customers.")


@pytest.fixture
def fake_generator() -> FakeGenerator:
    return FakeGenerator()


@pytest.fixture
def client(settings: Settings, fake_generator: FakeGenerator) -> Iterator[TestClient]:
    app = create_app(settings, generator=fake_generator)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_without_llm(settings: Settings, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
