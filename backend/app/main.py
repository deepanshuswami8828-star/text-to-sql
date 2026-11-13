"""FastAPI application: JSON API under /api, plus the built React frontend at /."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import Settings, get_settings
from .database import DatabaseNotFound, DatabaseRegistry, QueryError
from .history import HistoryStore
from .importer import UploadError
from .llm import LLMError, SQLGenerator, make_generator
from .schemas import (
    DatabaseOut,
    ExecuteRequest,
    ExecuteResponse,
    GenerateRequest,
    GenerateResponse,
    HealthOut,
    HistoryItem,
    HistoryUpdate,
    SchemaOut,
)
from .seed import SAMPLES_BY_ID, ensure_sample_databases
from .service import answer_question
from .sql_guard import UnsafeSQLError

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, generator: SQLGenerator | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        ensure_sample_databases(settings.sample_dir)
        registry = DatabaseRegistry(settings)
        registry.refresh()
        app.state.registry = registry
        app.state.history = HistoryStore(settings.app_db_path)
        app.state.generator = generator or make_generator(settings)
        if generator is None:
            if settings.llm_enabled:
                log.info("AI provider: %s (model %s)", settings.provider, settings.active_model)
            else:
                log.warning("No AI API key set (ANTHROPIC_API_KEY or GROQ_API_KEY): "
                            "natural-language questions are disabled.")
        yield

    app = FastAPI(title="Text-to-SQL", version=__version__, lifespan=lifespan)
    app.state.settings = settings

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # ---------- error handling ----------

    @app.exception_handler(DatabaseNotFound)
    async def _db_not_found(_: Request, exc: DatabaseNotFound):
        return JSONResponse(status_code=404, content={"detail": f"Database '{exc.args[0]}' not found."})

    @app.exception_handler(UploadError)
    async def _upload_error(_: Request, exc: UploadError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(LLMError)
    async def _llm_error(_: Request, exc: LLMError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    def registry(request: Request) -> DatabaseRegistry:
        return request.app.state.registry

    def history(request: Request) -> HistoryStore:
        return request.app.state.history

    # ---------- meta ----------

    @app.get("/api/health", response_model=HealthOut)
    def health(request: Request):
        llm_enabled = settings.llm_enabled or generator is not None
        return HealthOut(
            llm_enabled=llm_enabled,
            provider=settings.provider,
            model=settings.active_model,
            max_rows=settings.max_rows,
            version=__version__,
        )

    # ---------- databases ----------

    @app.get("/api/databases", response_model=list[DatabaseOut])
    def list_databases(request: Request):
        return [d.to_out() for d in registry(request).list()]

    @app.get("/api/databases/{database_id}/schema", response_model=SchemaOut)
    def get_schema(database_id: str, request: Request):
        return registry(request).schema(database_id)

    @app.get("/api/databases/{database_id}/examples", response_model=list[str])
    def get_examples(database_id: str, request: Request):
        reg = registry(request)
        info = reg.get(database_id)
        if info.kind == "sample" and info.id in SAMPLES_BY_ID:
            return SAMPLES_BY_ID[info.id].questions
        return example_questions(reg.schema(database_id))

    @app.post("/api/databases/upload", response_model=DatabaseOut, status_code=201)
    def upload_database(
        request: Request,
        file: UploadFile = File(...),
        database_id: str | None = Form(default=None),
    ):
        info = registry(request).add_upload(file.filename or "upload.csv", file.file, database_id or None)
        return info.to_out()

    @app.delete("/api/databases/{database_id}", status_code=204)
    def delete_database(database_id: str, request: Request):
        registry(request).delete_upload(database_id)
        history(request).clear(database_id=database_id, keep_starred=False)

    # ---------- queries ----------

    @app.post("/api/generate", response_model=GenerateResponse)
    def generate(req: GenerateRequest, request: Request):
        if not (settings.llm_enabled or generator is not None):
            raise HTTPException(
                status_code=503,
                detail="Add an API key to the .env file to ask questions in plain English: "
                       "ANTHROPIC_API_KEY for Claude, or GROQ_API_KEY for Groq's free tier. "
                       "You can still write and run SQL yourself.",
            )
        reg = registry(request)
        response = answer_question(req, reg, request.app.state.generator, settings)
        if response.answerable and response.sql:
            response.history_id = history(request).add(
                database_id=response.database_id,
                question=req.question,
                sql=response.sql,
                explanation=response.explanation,
                row_count=response.result.row_count if response.result else None,
                error=response.error,
                source="ai",
            )
        return response

    @app.post("/api/execute", response_model=ExecuteResponse)
    def execute(req: ExecuteRequest, request: Request):
        reg = registry(request)
        reg.get(req.database_id)
        try:
            sql, result = reg.execute(req.database_id, req.sql)
            response = ExecuteResponse(sql=sql, result=result)
        except (UnsafeSQLError, QueryError) as e:
            response = ExecuteResponse(sql=req.sql.strip(), error=str(e))
        if req.save_to_history:
            response.history_id = history(request).add(
                database_id=req.database_id,
                question=req.question,
                sql=response.sql,
                row_count=response.result.row_count if response.result else None,
                error=response.error,
                source="manual",
            )
        return response

    # ---------- history ----------

    @app.get("/api/history", response_model=list[HistoryItem])
    def list_history(
        request: Request,
        database_id: str | None = None,
        starred: bool = False,
        limit: int = Query(default=100, ge=1, le=500),
    ):
        return history(request).list(database_id=database_id, starred_only=starred, limit=limit)

    @app.patch("/api/history/{item_id}", response_model=HistoryItem)
    def update_history(item_id: int, body: HistoryUpdate, request: Request):
        item = history(request).set_starred(item_id, body.starred)
        if item is None:
            raise HTTPException(status_code=404, detail="History item not found.")
        return item

    @app.delete("/api/history/{item_id}", status_code=204)
    def delete_history(item_id: int, request: Request):
        if not history(request).delete(item_id):
            raise HTTPException(status_code=404, detail="History item not found.")

    @app.delete("/api/history", status_code=204)
    def clear_history(request: Request, database_id: str | None = None):
        history(request).clear(database_id=database_id, keep_starred=True)

    # ---------- frontend ----------

    dist: Path = settings.frontend_dist
    if (dist / "index.html").exists():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


def example_questions(schema: SchemaOut, limit: int = 6) -> list[str]:
    """Simple starter questions for an uploaded database, built from its schema (no LLM call)."""
    questions: list[str] = []
    for t in schema.tables:
        if t.kind != "table":
            continue
        numeric = [c.name for c in t.columns
                   if any(k in c.type.upper() for k in ("INT", "REAL", "NUM", "DEC", "FLOAT", "DOUBLE"))
                   and not c.primary_key and not c.foreign_key and not c.name.lower().endswith("id")]
        categorical = [c.name for c in t.columns if c.values]
        if numeric and categorical:
            questions.append(f"What is the average {numeric[0]} for each {categorical[0]} in {t.name}?")
        elif categorical:
            questions.append(f"How many {t.name} rows are there for each {categorical[0]}?")
        if numeric:
            questions.append(f"Show the 10 {t.name} rows with the highest {numeric[0]}")
        questions.append(f"How many rows are in {t.name}?")
    seen: set[str] = set()
    unique = [q for q in questions if not (q in seen or seen.add(q))]
    return unique[:limit]


app = create_app()
