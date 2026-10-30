import hashlib
import json
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from . import qa_store
from .calculations import fy_summary_from_records

from .config import Settings
from .store import Store
from . import fact_queue
from .segments import build_manifest


class QaSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_ids: list[str]


class QaMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    request_id: str


class FySummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    year: int
    document_ids: list[str]


def safe_filename(value):
    name = (value or "untitled").replace("\\", "/").split("/")[-1]
    return re.sub(r"[\x00-\x1f\x7f]", "", name).strip()[:180] or "untitled"


def create_app(settings=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(settings)
        yield

    app = FastAPI(title="Verdant document intake", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[settings.cors_origin], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.get("/api/health")
    def health():
        with app.state.store.connect() as db:
            db.execute("SELECT 1")
        return {"status": "ok", "service": "document-intake", "stage": "source-extraction"}

    @app.post("/api/fy/summary")
    def fy_summary(request: FySummaryRequest):
        if not 1990 <= request.year <= 2100:
            raise HTTPException(400, "Financial year start must be between 1990 and 2100.")
        try:
            snapshot = qa_store.load_records_for_documents(app.state.store, request.document_ids)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        summary = fy_summary_from_records(snapshot["records"], request.year, snapshot.get("documents"))
        summary["warnings"] = snapshot.get("warnings") or []
        return summary

    @app.get("/api/eval/comparison")
    def eval_comparison():
        root = Path(__file__).resolve().parents[2] / "docs" / "eval"
        baseline = root / "baseline" / "scorecard.json"
        improved = root / "improved" / "scorecard.json"
        if not baseline.exists() or not improved.exists():
            return {
                "available": False,
                "message": "Baseline and improved scorecards are not published yet.",
                "baseline": None,
                "improved": None,
            }
        return {
            "available": True,
            "baseline": json.loads(baseline.read_text(encoding="utf-8")),
            "improved": json.loads(improved.read_text(encoding="utf-8")),
        }

    @app.get("/api/qa/sessions")
    def qa_sessions():
        return {"sessions": qa_store.list_sessions(app.state.store)}

    @app.post("/api/qa/sessions", status_code=201)
    def qa_create_session(request: QaSessionRequest):
        try:
            return qa_store.create_session(app.state.store, request.document_ids)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/qa/sessions/{session_id}")
    def qa_get_session(session_id: str):
        result = qa_store.session(app.state.store, session_id)
        if not result:
            raise HTTPException(404, "Conversation not found.")
        return result

    @app.post("/api/qa/sessions/{session_id}/messages", status_code=202)
    def qa_message(session_id: str, request: QaMessageRequest):
        from .qa import requires_calculation
        if not settings.openai_api_key and not requires_calculation(request.question):
            raise HTTPException(503, "OpenAI is not configured. Add OPENAI_API_KEY to the project .env and restart the services.")
        try:
            result = qa_store.enqueue(app.state.store, session_id, request.question, request.request_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        if not result:
            raise HTTPException(404, "Conversation not found.")
        return result

    @app.get("/api/documents")
    def documents():
        return {"documents": app.state.store.list()}

    @app.get("/api/documents/{document_id}")
    def document(document_id: str):
        result = app.state.store.get(document_id)
        if not result:
            raise HTTPException(404, "Document not found.")
        return result

    @app.get("/api/documents/{document_id}/sources")
    def sources(document_id: str, unit: int | None = Query(None, ge=1), offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)):
        if not app.state.store.get(document_id):
            raise HTTPException(404, "Document not found.")
        try:
            result = app.state.store.sources(document_id, unit, offset, limit)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        if result is None:
            raise HTTPException(409, "Source extraction is not complete.")
        return result

    @app.get("/api/facts/config")
    def facts_config():
        return {"configured": bool(settings.openai_api_key), "provider": "openai", "model": settings.openai_model, "automatic_on_upload": True}

    @app.get("/api/documents/{document_id}/facts")
    def facts(document_id: str):
        if not app.state.store.get(document_id):
            raise HTTPException(404, "Document not found.")
        return fact_queue.get(app.state.store, document_id)

    @app.get("/api/documents/{document_id}/facts/history")
    def fact_history(document_id: str):
        if not app.state.store.get(document_id):
            raise HTTPException(404, "Document not found.")
        return {"runs": fact_queue.history(app.state.store, document_id)}

    @app.get("/api/documents/{document_id}/facts/plan")
    def fact_plan(document_id: str):
        if not app.state.store.get(document_id):
            raise HTTPException(404, "Document not found.")
        try:
            source = fact_queue.load_source(app.state.store, document_id)
            segments = build_manifest(source)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"segments": len(segments), "warnings": source["summary"].get("warnings", []), "provider_calls_before_retries": len(segments)}

    @app.post("/api/documents/{document_id}/facts", status_code=202)
    def request_facts(document_id: str):
        if not settings.openai_api_key:
            raise HTTPException(503, "OpenAI is not configured. Add OPENAI_API_KEY to the project .env and restart the services.")
        outcome = fact_queue.enqueue(app.state.store, document_id)
        if outcome == "missing":
            raise HTTPException(404, "Document not found.")
        if outcome == "provider_conflict":
            raise HTTPException(409, "A previous provider job is still active; wait for it to stop before requesting a new extraction.")
        if outcome == "no_segments":
            raise HTTPException(409, "No extractable source records are available.")
        if outcome == "too_large":
            raise HTTPException(413, "Source is too large for a single extraction request; no partial results were generated.")
        if outcome == "not_ready":
            raise HTTPException(409, "Source extraction must complete first.")
        return fact_queue.get(app.state.store, document_id)

    @app.post("/api/documents/{document_id}/facts/revalidate")
    def revalidate_facts(document_id: str):
        if not app.state.store.get(document_id):
            raise HTTPException(404, "Document not found.")
        if fact_queue.revalidate(app.state.store, document_id) != "ok":
            raise HTTPException(409, "Saved candidates are unavailable or the job changed. No provider call was made.")
        return fact_queue.get(app.state.store, document_id)

    @app.post("/api/documents", status_code=202)
    async def upload(files: list[UploadFile] = File(...)):
        if len(files) > settings.max_files:
            for item in files:
                await item.close()
            raise HTTPException(400, f"Upload up to {settings.max_files} files at once.")
        results = []
        for item in files:
            filename = safe_filename(item.filename)
            kind = Path(filename).suffix.lower().lstrip(".")
            temp_path = None
            try:
                if kind not in ("pdf", "xlsx"):
                    results.append({"filename": filename, "error": "Only PDF and XLSX files are supported."})
                    continue
                digest, size = hashlib.sha256(), 0
                with tempfile.NamedTemporaryFile(dir=settings.data_dir, prefix="incoming-", suffix=".tmp", delete=False) as temp:
                    temp_path = Path(temp.name)
                    while chunk := await item.read(1024 * 1024):
                        size += len(chunk)
                        if size > settings.max_upload_bytes:
                            raise ValueError(f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit.")
                        digest.update(chunk)
                        temp.write(chunk)
                if size == 0:
                    raise ValueError("The file is empty.")
                doc, duplicate = app.state.store.ingest(temp_path, filename, kind, size, digest.hexdigest())
                results.append({"filename": filename, "document": doc, "duplicate": duplicate})
            except ValueError as exc:
                results.append({"filename": filename, "error": str(exc)})
            finally:
                if temp_path:
                    temp_path.unlink(missing_ok=True)
                await item.close()
        return {"results": results}

    @app.post("/api/documents/{document_id}/retry")
    def retry(document_id: str):
        document = app.state.store.get(document_id)
        if document and document["status"] == "ready" and document["generation_status"] == "failed":
            if not settings.openai_api_key:
                raise HTTPException(503, "OpenAI is not configured. Add OPENAI_API_KEY and restart the services.")
            outcome = fact_queue.enqueue(app.state.store, document_id)
            if outcome not in ("queued", "existing"):
                raise HTTPException(409, "Generation could not be queued. Review the source or split the document.")
            return app.state.store.get(document_id)
        status = app.state.store.retry(document_id)
        if status == "missing":
            raise HTTPException(404, "Document not found.")
        if status == "conflict":
            raise HTTPException(409, "Only failed documents can be retried.")
        return app.state.store.get(document_id)

    return app


app = create_app()
