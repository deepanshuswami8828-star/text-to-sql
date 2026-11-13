"""Application settings, loaded from environment variables and the repo-root .env file."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> parents[2] is the repository root
ROOT_DIR = Path(__file__).resolve().parents[2]

# Models that accept the server-side refusal fallback parameter.
FALLBACK_CAPABLE_MODELS = {
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
    "claude-fable-5-1",
    "claude-fable-5-2",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Claude ---
    anthropic_api_key: str | None = None
    claude_model: str = "claude-opus-5-5"
    claude_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    claude_fallbacks: bool = True
    max_fix_attempts: int = 2  # how many times Claude may repair a failing query

    # --- Storage ---
    data_dir: Path = ROOT_DIR / "data"
    frontend_dist: Path = ROOT_DIR / "frontend" / "dist"

    # --- Query execution ---
    max_rows: int = 1000
    query_timeout_seconds: float = 15.0
    max_upload_mb: int = 50

    # Extra databases, as "name=sqlalchemy_url" pairs separated by ";"
    # e.g. "analytics=postgresql+psycopg://readonly:pw@localhost/analytics"
    databases: str = ""

    # Comma-separated list of origins allowed to call the API (dev server by default)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def llm_enabled(self) -> bool:
        return bool(
            self.anthropic_api_key
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        )

    @property
    def use_fallbacks(self) -> bool:
        return self.claude_fallbacks and self.claude_model in FALLBACK_CAPABLE_MODELS

    @property
    def sample_dir(self) -> Path:
        return self.data_dir / "sample"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def app_db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def external_databases(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for pair in self.databases.split(";"):
            if "=" not in pair:
                continue
            name, url = pair.split("=", 1)
            if name.strip() and url.strip():
                result[name.strip()] = url.strip()
        return result


@lru_cache
def get_settings() -> Settings:
    return Settings()
