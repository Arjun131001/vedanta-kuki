"""SQLite is both the catalogue and durable work queue for this milestone."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager

from .config import Settings
from .qa_store import create_tables


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL, kind TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL UNIQUE,
                    storage_key TEXT NOT NULL, status TEXT NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    error TEXT, validation_json TEXT
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
                    kind TEXT NOT NULL DEFAULT 'validation', version INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    available_at REAL NOT NULL, lease_until REAL, lease_owner TEXT,
                    UNIQUE(document_id, kind, version)
                );
                CREATE INDEX IF NOT EXISTS jobs_available ON jobs(status, available_at);
                CREATE TABLE IF NOT EXISTS fact_jobs (
                    document_id TEXT PRIMARY KEY REFERENCES documents(id), status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, available_at REAL NOT NULL,
                    lease_until REAL, lease_owner TEXT, error TEXT, model TEXT NOT NULL,
                    result_json TEXT, updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fact_segments (
                    document_id TEXT NOT NULL REFERENCES documents(id), request_hash TEXT NOT NULL,
                    segment_id TEXT NOT NULL, ordinal INTEGER NOT NULL, payload_json TEXT NOT NULL,
                    status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, error TEXT, output_json TEXT,
                    PRIMARY KEY(document_id, request_hash, segment_id)
                );
                CREATE TABLE IF NOT EXISTS fact_runs (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
                    archived_at REAL NOT NULL, job_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS source_results (
                    document_id TEXT NOT NULL REFERENCES documents(id), version INTEGER NOT NULL,
                    kind TEXT NOT NULL, summary_json TEXT NOT NULL,
                    PRIMARY KEY(document_id, version)
                );
                CREATE TABLE IF NOT EXISTS source_units (
                    document_id TEXT NOT NULL, version INTEGER NOT NULL, unit_index INTEGER NOT NULL,
                    label TEXT NOT NULL, content_json TEXT NOT NULL,
                    PRIMARY KEY(document_id, version, unit_index),
                    FOREIGN KEY(document_id, version) REFERENCES source_results(document_id, version)
                );
            """)
            create_tables(db)
            document_columns = {row["name"] for row in db.execute("PRAGMA table_info(documents)")}
            if "auto_generate" not in document_columns:
                db.execute("ALTER TABLE documents ADD COLUMN auto_generate INTEGER NOT NULL DEFAULT 0")
            if "generation_error" not in document_columns:
                db.execute("ALTER TABLE documents ADD COLUMN generation_error TEXT")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(fact_jobs)")}
            for name in ("source_snapshot", "source_hash", "request_hash", "document_hash", "schema_hash", "prompt_version"):
                if name not in columns:
                    db.execute(f"ALTER TABLE fact_jobs ADD COLUMN {name} TEXT")
            if "provider" not in columns:
                db.execute("ALTER TABLE fact_jobs ADD COLUMN provider TEXT NOT NULL DEFAULT 'gemini'")
            # Existing validated documents are retained and requeued once for source extraction.
            db.execute("BEGIN IMMEDIATE")
            ready = db.execute("""SELECT d.id FROM documents d WHERE d.status='ready'
                AND NOT EXISTS (SELECT 1 FROM source_results s WHERE s.document_id=d.id AND s.version=1)""").fetchall()
            # Upgrade old PDF layouts once, without disturbing active fact jobs.
            legacy = db.execute("""SELECT d.id FROM documents d JOIN source_results s ON s.document_id=d.id AND s.version=1
                WHERE d.kind='pdf' AND d.status='ready' AND json_extract(s.summary_json,'$.layout_version') IS NULL
                AND NOT EXISTS (SELECT 1 FROM fact_jobs f WHERE f.document_id=d.id AND f.status IN ('queued','processing'))""").fetchall()
            ready = list(ready) + list(legacy)
            now = time.time()
            for row in ready:
                db.execute("UPDATE documents SET status='queued',error=NULL,updated_at=? WHERE id=?", (now, row["id"]))
                db.execute("""UPDATE jobs SET status='queued',attempts=0,available_at=?,lease_until=NULL,lease_owner=NULL
                    WHERE document_id=? AND kind='validation' AND version=1""", (now, row["id"]))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.settings.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def public(row):
        result = dict(row)
        fact_status = result.pop("fact_status", None)
        fact_error = result.pop("fact_error", None)
        segment_error = result.pop("fact_segment_error", None)
        automatic = bool(result.get("auto_generate"))
        result["auto_generate"] = automatic
        result["generation_error"] = result.get("generation_error") or (segment_error if fact_status == "failed" else None) or fact_error
        if result["status"] == "failed" or result["generation_error"] or fact_status == "failed":
            result["generation_status"] = "failed"
        elif fact_status == "ready":
            result["generation_status"] = "generated"
        elif automatic or fact_status in ("queued", "processing"):
            result["generation_status"] = "generating"
        else:
            result["generation_status"] = "not_requested"
        result.pop("storage_key", None)
        result["validation"] = json.loads(result.pop("validation_json") or "null")
        result["source_summary"] = json.loads(result.pop("source_summary_json") or "null")
        return result

    def get(self, document_id):
        with self.connect() as db:
            row = db.execute("""SELECT d.*, j.attempts, j.available_at AS next_attempt_at, f.status AS fact_status, f.error AS fact_error,
                (SELECT error FROM fact_segments fs WHERE fs.document_id=d.id AND fs.status='failed' ORDER BY fs.ordinal LIMIT 1) AS fact_segment_error,
                (SELECT summary_json FROM source_results s WHERE s.document_id=d.id AND s.version=1) AS source_summary_json
                FROM documents d JOIN jobs j ON j.document_id=d.id AND j.kind='validation' AND j.version=1 LEFT JOIN fact_jobs f ON f.document_id=d.id WHERE d.id=?""", (document_id,)).fetchone()
        return self.public(row) if row else None

    def list(self):
        with self.connect() as db:
            rows = db.execute("""SELECT d.*, j.attempts, j.available_at AS next_attempt_at, f.status AS fact_status, f.error AS fact_error,
                (SELECT error FROM fact_segments fs WHERE fs.document_id=d.id AND fs.status='failed' ORDER BY fs.ordinal LIMIT 1) AS fact_segment_error,
                (SELECT summary_json FROM source_results s WHERE s.document_id=d.id AND s.version=1) AS source_summary_json
                FROM documents d JOIN jobs j ON j.document_id=d.id AND j.kind='validation' AND j.version=1 LEFT JOIN fact_jobs f ON f.document_id=d.id ORDER BY d.created_at DESC""").fetchall()
        return [self.public(row) for row in rows]

    def sources(self, document_id, unit=None, offset=0, limit=100):
        with self.connect() as db:
            result = db.execute("SELECT * FROM source_results WHERE document_id=? AND version=1", (document_id,)).fetchone()
            if not result:
                return None
            rows = db.execute("SELECT unit_index,label FROM source_units WHERE document_id=? AND version=1 ORDER BY unit_index", (document_id,)).fetchall()
            response = {"document_id": document_id, "version": result["version"], "kind": result["kind"], "summary": json.loads(result["summary_json"]),
                        "units": [{"index": row["unit_index"], "label": row["label"]} for row in rows]}
            if unit is not None:
                row = db.execute("SELECT content_json FROM source_units WHERE document_id=? AND version=1 AND unit_index=?", (document_id, unit)).fetchone()
                if not row:
                    raise ValueError("Source unit not found.")
                content = json.loads(row["content_json"])
                if "cells" in content:
                    content["total_cells"] = len(content["cells"])
                    content["cells"] = content["cells"][offset:offset + limit]
                    content["offset"] = offset
                response["unit"] = content
            return response

    def ingest(self, temp_path, filename, kind, size, digest):
        """Serialize deduplication and registration. Client filenames never become paths."""
        destination = None
        committed = False
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT id FROM documents WHERE sha256=?", (digest,)).fetchone()
                if existing:
                    document_id, duplicate = existing["id"], True
                else:
                    document_id, duplicate = uuid.uuid4().hex, False
                    storage_key = document_id + "." + kind
                    destination = self.settings.uploads_dir / storage_key
                    temp_path.replace(destination)
                    now = time.time()
                    db.execute("""INSERT INTO documents
                        (id,filename,kind,size_bytes,sha256,storage_key,status,created_at,updated_at,auto_generate)
                        VALUES (?,?,?,?,?,?,'queued',?,?,1)""",
                        (document_id, filename, kind, size, digest, storage_key, now, now))
                    db.execute("INSERT INTO jobs(id,document_id,status,available_at) VALUES (?,?,'queued',?)",
                               (uuid.uuid4().hex, document_id, now))
            committed = True
            return self.get(document_id), duplicate
        except BaseException:
            if destination and not committed:
                destination.unlink(missing_ok=True)
            raise
        finally:
            temp_path.unlink(missing_ok=True)

    def retry(self, document_id):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM documents WHERE id=?", (document_id,)).fetchone()
            if not row:
                return "missing"
            if row["status"] != "failed":
                return "conflict"
            now = time.time()
            db.execute("UPDATE documents SET status='queued',error=NULL,updated_at=? WHERE id=?", (now, document_id))
            db.execute("""UPDATE jobs SET status='queued',attempts=0,available_at=?,
                lease_until=NULL,lease_owner=NULL WHERE document_id=? AND kind='validation' AND version=1""", (now, document_id))
        return "ok"

    def claim(self, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            expired = db.execute("SELECT * FROM jobs WHERE kind='validation' AND version=1 AND status='processing' AND lease_until<=?", (now,)).fetchall()
            for job in expired:
                status = "failed" if job["attempts"] >= self.settings.max_attempts else "queued"
                error = "Worker lease expired; retry limit reached." if status == "failed" else "Worker interrupted; validation will resume."
                db.execute("""UPDATE jobs SET status=?,available_at=?,lease_owner=NULL,lease_until=NULL
                    WHERE id=?""", (status, now, job["id"]))
                db.execute("UPDATE documents SET status=?,error=?,updated_at=? WHERE id=?",
                           (status, error, now, job["document_id"]))
            job = db.execute("""SELECT j.*,d.storage_key,d.kind AS document_kind FROM jobs j JOIN documents d ON d.id=j.document_id
                WHERE j.kind='validation' AND j.version=1 AND j.status='queued' AND j.available_at<=? ORDER BY j.available_at LIMIT 1""", (now,)).fetchone()
            if not job:
                return None
            owner = uuid.uuid4().hex
            db.execute("""UPDATE jobs SET status='processing',attempts=attempts+1,lease_owner=?,lease_until=? WHERE id=?""",
                       (owner, now + self.settings.lease_seconds, job["id"]))
            db.execute("UPDATE documents SET status='processing',error=NULL,updated_at=? WHERE id=?", (now, job["document_id"]))
            return {**dict(job), "attempts": job["attempts"] + 1, "lease_owner": owner}

    def heartbeat(self, job):
        with self.connect() as db:
            cursor = db.execute("""UPDATE jobs SET lease_until=? WHERE id=? AND status='processing' AND lease_owner=? AND lease_until>?""",
                                (time.time() + self.settings.lease_seconds, job["id"], job["lease_owner"], time.time()))
            return cursor.rowcount == 1

    def finish(self, job, validation=None, error=None, now=None, permanent=False, source=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            owned = db.execute("SELECT id FROM jobs WHERE id=? AND lease_owner=? AND status='processing' AND lease_until>?",
                               (job["id"], job["lease_owner"], now)).fetchone()
            if not owned:
                return False  # A stale worker must never overwrite the new lease holder.
            if error is None and source is None:
                raise ValueError("Successful completion requires source content.")
            if error is None:
                db.execute("INSERT INTO source_results(document_id,version,kind,summary_json) VALUES (?,?,?,?) ON CONFLICT(document_id,version) DO UPDATE SET kind=excluded.kind,summary_json=excluded.summary_json",
                           (job["document_id"], source["version"], source["kind"], json.dumps(source["summary"])))
                db.execute("DELETE FROM source_units WHERE document_id=? AND version=?", (job["document_id"], source["version"]))
                for unit in source["units"]:
                    db.execute("INSERT INTO source_units(document_id,version,unit_index,label,content_json) VALUES (?,?,?,?,?)",
                               (job["document_id"], source["version"], unit["index"], unit["label"], json.dumps(unit)))
            status = "ready" if error is None else ("failed" if permanent or job["attempts"] >= self.settings.max_attempts else "queued")
            delay = min(60, self.settings.retry_base_seconds * 2 ** (job["attempts"] - 1)) if error else 0
            db.execute("""UPDATE jobs SET status=?,available_at=?,lease_owner=NULL,lease_until=NULL WHERE id=?""",
                       ("completed" if status == "ready" else status, now + delay, job["id"]))
            db.execute("UPDATE documents SET status=?,error=?,validation_json=COALESCE(?,validation_json),updated_at=? WHERE id=?",
                       (status, error, json.dumps(validation) if validation else None, now, job["document_id"]))
            return True
