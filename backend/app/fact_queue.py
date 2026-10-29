"""Separate durable queue for explicit, billable fact-extraction requests."""
import json
import hashlib
from .facts import MAX_SOURCE_CHARS, PROMPT_VERSION, SCHEMA_HASH
from .evidence_index import build_index, INDEX_VERSION
from .segments import build_manifest, SEGMENT_VERSION
import time
import uuid


def get(store, document_id):
    with store.connect() as db:
        row = db.execute("SELECT document_id,status,attempts,error,provider,model,result_json,updated_at FROM fact_jobs WHERE document_id=?", (document_id,)).fetchone()
    if not row:
        return {"status": "not_requested", "document_id": document_id}
    result = dict(row)
    result["output"] = json.loads(result.pop("result_json") or "null")
    with store.connect() as db:
        segments = db.execute("SELECT segment_id,status,attempts,error FROM fact_segments WHERE document_id=? ORDER BY ordinal", (document_id,)).fetchall()
    result["segments"] = [dict(item) for item in segments]
    return result


def enqueue_automatic(store):
    """Resume upload intent after source extraction, including a worker restart.

    Completed/failed fact jobs are never re-extracted on startup. Idempotent
    enqueueing and upload deduplication prevent duplicate provider requests.
    """
    with store.connect() as db:
        row = db.execute("""SELECT d.id FROM documents d WHERE d.auto_generate=1
            AND d.status='ready' AND d.generation_error IS NULL
            AND NOT EXISTS (SELECT 1 FROM fact_jobs f WHERE f.document_id=d.id)
            ORDER BY d.created_at LIMIT 1""").fetchone()
    if not row:
        return False
    error = None
    if not store.settings.openai_api_key:
        error = "OpenAI is not configured. Add OPENAI_API_KEY and restart the services, then retry generation."
    else:
        try:
            outcome = enqueue(store, row["id"])
            if outcome not in ("queued", "existing"):
                error = {"no_segments": "No extractable source records are available; OCR may be needed.",
                         "too_large": "The source exceeds safe generation limits; split the document and upload it again."}.get(outcome,
                         "Automatic generation could not be queued. Please retry generation.")
        except (ValueError, TypeError, KeyError):
            error = "Automatic generation could not prepare the source. Please review the document and retry."
    if error:
        with store.connect() as db:
            db.execute("UPDATE documents SET generation_error=? WHERE id=? AND NOT EXISTS (SELECT 1 FROM fact_jobs WHERE document_id=?)",
                       (error, row["id"], row["id"]))
    return True


def enqueue(store, document_id):
    now = time.time()
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        doc = db.execute("SELECT status,sha256 FROM documents WHERE id=?", (document_id,)).fetchone()
        if not doc:
            return "missing"
        source = db.execute("SELECT version,kind,summary_json FROM source_results WHERE document_id=? AND version=1", (document_id,)).fetchone()
        if doc["status"] != "ready" or not source:
            return "not_ready"
        rows = db.execute("SELECT content_json FROM source_units WHERE document_id=? AND version=1 ORDER BY unit_index", (document_id,)).fetchall()
        snapshot = {"version": source["version"], "kind": source["kind"], "summary": json.loads(source["summary_json"]), "units": [json.loads(row["content_json"]) for row in rows]}
        serialized = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        try:
            manifest = build_manifest(snapshot)
        except ValueError:
            return "too_large"
        if not manifest:
            return "no_segments"
        source_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        request_hash = hashlib.sha256(f"openai:{source_hash}:{store.settings.openai_model}:{PROMPT_VERSION}:{SCHEMA_HASH}:{INDEX_VERSION}:{SEGMENT_VERSION}".encode()).hexdigest()
        existing = db.execute("SELECT * FROM fact_jobs WHERE document_id=?", (document_id,)).fetchone()
        if existing and existing["status"] in ("queued", "processing"):
            return "existing" if existing["provider"] == "openai" else "provider_conflict"
        if existing and existing["request_hash"] == request_hash and existing["status"] == "failed":
            failed = db.execute("SELECT count(*) FROM fact_segments WHERE document_id=? AND request_hash=? AND status='failed'", (document_id, request_hash)).fetchone()[0]
            if failed:
                db.execute("UPDATE fact_segments SET status='queued',attempts=0,error=NULL WHERE document_id=? AND request_hash=? AND status='failed'", (document_id, request_hash))
                db.execute("UPDATE fact_jobs SET status='queued',available_at=?,error=NULL,updated_at=? WHERE document_id=?", (now, now, document_id))
                return "queued"
        if existing and existing["status"] == "ready" and existing["request_hash"] == request_hash:
            return "existing"
        if existing:
            archived = dict(existing)
            archived["segments"] = [dict(item) for item in db.execute(
                "SELECT * FROM fact_segments WHERE document_id=? AND request_hash=? ORDER BY ordinal",
                (document_id, existing["request_hash"])).fetchall()]
            db.execute("INSERT INTO fact_runs(id,document_id,archived_at,job_json) VALUES (?,?,?,?)",
                       (uuid.uuid4().hex, document_id, now, json.dumps(archived)))
        db.execute("""INSERT INTO fact_jobs(document_id,status,attempts,available_at,model,updated_at,source_snapshot,source_hash,request_hash,document_hash,schema_hash,prompt_version,provider)
            VALUES (?,'queued',0,?,?,?,?,?,?,?,?,?,'openai') ON CONFLICT(document_id) DO UPDATE SET status='queued',attempts=0,
            available_at=excluded.available_at,model=excluded.model,provider=excluded.provider,updated_at=excluded.updated_at,
            source_snapshot=excluded.source_snapshot,source_hash=excluded.source_hash,request_hash=excluded.request_hash,
            document_hash=excluded.document_hash,schema_hash=excluded.schema_hash,prompt_version=excluded.prompt_version,error=NULL,lease_owner=NULL,lease_until=NULL,result_json=NULL""",
            (document_id, now, store.settings.openai_model, now, serialized, source_hash, request_hash, doc["sha256"], SCHEMA_HASH, PROMPT_VERSION))
        db.execute("DELETE FROM fact_segments WHERE document_id=?", (document_id,))
        for ordinal, segment in enumerate(manifest):
            db.execute("INSERT INTO fact_segments(document_id,request_hash,segment_id,ordinal,payload_json,status) VALUES (?,?,?,?,?,'queued')",
                       (document_id, request_hash, segment["id"], ordinal, json.dumps(segment)))
        db.execute("UPDATE documents SET generation_error=NULL WHERE id=?", (document_id,))
    return "queued"


def claim(store, now=None):
    now = time.time() if now is None else now
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        # Never send an older provider's saved jobs to a different API.
        db.execute("""UPDATE fact_jobs SET status='failed',error='This queued job belongs to a previous provider. Request a new extraction explicitly.',
                      lease_owner=NULL,lease_until=NULL,updated_at=? WHERE provider!='openai' AND status='queued'""", (now,))
        db.execute("""UPDATE fact_jobs SET status='failed',error='This interrupted job belongs to a previous provider. Request a new extraction explicitly.',
                      lease_owner=NULL,lease_until=NULL,updated_at=? WHERE provider!='openai' AND status='processing' AND lease_until<=?""", (now,now))
        expired = db.execute("SELECT * FROM fact_jobs WHERE provider='openai' AND status='processing' AND lease_until<=?", (now,)).fetchall()
        for job in expired:
            segment = db.execute("SELECT * FROM fact_segments WHERE document_id=? AND request_hash=? AND status='processing'", (job["document_id"], job["request_hash"])).fetchone()
            if segment:
                status = "failed" if segment["attempts"] >= store.settings.max_attempts else "queued"
                db.execute("UPDATE fact_segments SET status=?,error=? WHERE document_id=? AND request_hash=? AND segment_id=?", (status, "Worker interrupted before confirmation.", job["document_id"], job["request_hash"], segment["segment_id"]))
            db.execute("UPDATE fact_jobs SET status='queued',available_at=?,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE document_id=?", (now, now, job["document_id"]))
        row = db.execute("SELECT * FROM fact_jobs WHERE provider='openai' AND status='queued' AND available_at<=? ORDER BY available_at LIMIT 1", (now,)).fetchone()
        if not row:
            return None
        segment = db.execute("SELECT * FROM fact_segments WHERE document_id=? AND request_hash=? AND status='queued' ORDER BY ordinal LIMIT 1", (row["document_id"],row["request_hash"])).fetchone()
        if not segment:
            _finalize(db, row["document_id"], row["request_hash"], now)
            return None
        owner = uuid.uuid4().hex
        db.execute("UPDATE fact_jobs SET status='processing',attempts=attempts+1,lease_owner=?,lease_until=?,error=NULL,updated_at=? WHERE document_id=?", (owner, now + store.settings.lease_seconds, now, row["document_id"]))
        db.execute("UPDATE fact_segments SET status='processing',attempts=attempts+1 WHERE document_id=? AND request_hash=? AND segment_id=?", (row["document_id"],row["request_hash"],segment["segment_id"]))
        return {**dict(row), "attempts": segment["attempts"] + 1, "lease_owner": owner, "segment_id": segment["segment_id"], "segment_payload": segment["payload_json"]}


def heartbeat(store, job):
    now = time.time()
    with store.connect() as db:
        updated = db.execute("UPDATE fact_jobs SET lease_until=? WHERE document_id=? AND status='processing' AND lease_owner=? AND lease_until>?",
                             (now + store.settings.lease_seconds, job["document_id"], job["lease_owner"], now))
        return updated.rowcount == 1


def _aggregate(db, document_id, request_hash):
    rows = db.execute("SELECT segment_id,status,attempts,error,output_json,payload_json FROM fact_segments WHERE document_id=? AND request_hash=? ORDER BY ordinal", (document_id, request_hash)).fetchall()
    result = {"document_type": "Segmented document", "organization": None, "facts": [], "review_candidates": [], "rejected_candidates": [], "review_issues": [], "warnings": [], "coverage": "partial", "coverage_note": "Model-estimated completeness varies by segment; review the source."}
    seen = set()
    outputs = []
    organizations, types, metadata = set(), set(), []
    for row in rows:
        if not row["output_json"]:
            continue
        output = json.loads(row["output_json"]); outputs.append(output)
        part = output.get("result", {})
        if part.get("document_type"): types.add(part["document_type"])
        if part.get("organization"): organizations.add(part["organization"])
        metadata.append({"segment_id": row["segment_id"], "document_type": part.get("document_type"), "organization": part.get("organization"), "model_coverage": part.get("coverage")})
        for category in ("facts", "review_candidates"):
            for fact in part.get(category, []):
                key = (tuple(fact.get("evidence", {}).get("reference_ids", [fact.get("evidence", {}).get("reference_id")])), tuple(fact.get("context_evidence", [{}])[0].get("reference_ids", [fact.get("context_evidence", [{}])[0].get("reference_id")]) if fact.get("context_evidence") else ()), fact.get("source_label"), fact.get("value"), fact.get("unit"), fact.get("period"), fact.get("currency"), fact.get("organization"))
                if key not in seen:
                    seen.add(key); result[category].append({**fact, "segment_id": row["segment_id"]})
        for category in ("rejected_candidates", "review_issues", "warnings"):
            result[category].extend(part.get(category, []))
    result["document_type"] = next(iter(types)) if len(types) == 1 else ("Mixed classifications" if types else "Segmented document")
    result["organization"] = next(iter(organizations)) if len(organizations) == 1 else None
    if len(organizations) > 1:
        result["warnings"].append("Segments identified different organizations; review attribution separately.")
    # Conflicting proposals sharing a source label and value reference are not silently merged.
    groups = {}
    for category in ("facts", "review_candidates"):
        for fact in result[category]:
            key = (fact.get("evidence", {}).get("reference_id"), fact.get("source_label"))
            groups.setdefault(key, set()).add((fact.get("value"), fact.get("unit"), fact.get("period"), fact.get("currency"), fact.get("organization")))
    conflicts = {key for key, values in groups.items() if len(values) > 1}
    if conflicts:
        result["warnings"].append("Conflicting proposals share source evidence; review them individually.")
        checked = []
        for fact in result["facts"]:
            key = (fact.get("evidence", {}).get("reference_id"), fact.get("source_label"))
            if key in conflicts:
                result["review_candidates"].append({**fact, "review_reason": "Conflicting proposals share this source evidence."})
            else:
                checked.append(fact)
        result["facts"] = checked
    completed = sum(row["status"] == "done" for row in rows)
    failed = sum(row["status"] == "failed" for row in rows)
    operational = "complete" if rows and completed == len(rows) else "partial"
    total_targets = sum(len(json.loads(row["payload_json"])["target_ids"]) for row in rows)
    completed_targets = sum(len(json.loads(row["payload_json"])["target_ids"]) for row in rows if row["status"] == "done")
    job = db.execute("SELECT provider,model,source_hash,document_hash,schema_hash,prompt_version FROM fact_jobs WHERE document_id=? AND request_hash=?", (document_id,request_hash)).fetchone()
    return {"result": result, "provider": job["provider"], "model": job["model"], "source_hash": job["source_hash"], "document_hash": job["document_hash"], "schema_hash": job["schema_hash"], "prompt_version": job["prompt_version"], "validator_version": outputs[0].get("validator_version") if outputs else None, "segment_metadata": metadata, "completed_target_records": completed_targets, "total_target_records": total_targets, "model_coverage": [{"segment_id": row["segment_id"], "coverage": (json.loads(row["output_json"]).get("result", {}).get("coverage") if row["output_json"] else None)} for row in rows], "segments": [{"id":r["segment_id"], "status":r["status"], "attempts":r["attempts"], "error":r["error"]} for r in rows],
            "segment_outputs": outputs, "operational_coverage": operational, "completed_segments": completed, "failed_segments": failed, "total_segments": len(rows)}


def _finalize(db, document_id, request_hash, now):
    output = _aggregate(db, document_id, request_hash)
    segments_failed = output["failed_segments"] > 0
    rejected_only = not output["result"]["facts"] and not output["result"]["review_candidates"] and bool(output["result"]["rejected_candidates"])
    error = "Some source segments failed; review and retry them." if segments_failed else ("No evidence-supported facts; review rejected candidates." if rejected_only else None)
    db.execute("UPDATE fact_jobs SET status=?,error=?,result_json=?,updated_at=?,lease_owner=NULL,lease_until=NULL WHERE document_id=?", ("failed" if error else "ready", error, json.dumps(output), now, document_id))


def finish(store, job, output=None, error=None, permanent=False, now=None):
    now = time.time() if now is None else now
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        owned = db.execute("SELECT 1 FROM fact_jobs WHERE document_id=? AND request_hash=? AND status='processing' AND lease_owner=? AND lease_until>?", (job["document_id"], job["request_hash"], job["lease_owner"], now)).fetchone()
        if not owned:
            return False
        status = "done" if error is None else ("failed" if permanent or job["attempts"] >= store.settings.max_attempts else "queued")
        db.execute("UPDATE fact_segments SET status=?,error=?,output_json=? WHERE document_id=? AND request_hash=? AND segment_id=? AND status='processing'", (status, error, json.dumps(output) if output is not None else None, job["document_id"],job["request_hash"],job["segment_id"]))
        remaining = db.execute("SELECT count(*) FROM fact_segments WHERE document_id=? AND request_hash=? AND status='queued'", (job["document_id"],job["request_hash"])).fetchone()[0]
        if remaining:
            delay = min(60, store.settings.retry_base_seconds * 2 ** (job["attempts"]-1)) if error and status == "queued" else 0
            partial = _aggregate(db, job["document_id"],job["request_hash"])
            db.execute("UPDATE fact_jobs SET status='queued',available_at=?,result_json=?,updated_at=?,lease_owner=NULL,lease_until=NULL WHERE document_id=?", (now+delay,json.dumps(partial),now,job["document_id"]))
        else:
            _finalize(db, job["document_id"],job["request_hash"],now)
        return True


def load_source(store, document_id):
    with store.connect() as db:
        source = db.execute("SELECT version,kind,summary_json FROM source_results WHERE document_id=? AND version=1", (document_id,)).fetchone()
        rows = db.execute("SELECT content_json FROM source_units WHERE document_id=? AND version=1 ORDER BY unit_index", (document_id,)).fetchall()
    if not source:
        raise ValueError("Source is not available.")
    return {"version": source["version"], "kind": source["kind"], "summary": json.loads(source["summary_json"]),
            "units": [json.loads(row["content_json"]) for row in rows]}



def revalidate(store, document_id):
    """Recheck saved segment candidates against their immutable request snapshot."""
    from .facts import FactError, project_saved_indexed, VALIDATOR_VERSION
    from pydantic import ValidationError
    with store.connect() as db:
        row = db.execute("SELECT * FROM fact_jobs WHERE document_id=?", (document_id,)).fetchone()
        if not row or row["status"] in ("queued", "processing") or not row["source_snapshot"]:
            return "unavailable"
        segments = db.execute("SELECT * FROM fact_segments WHERE document_id=? AND request_hash=? ORDER BY ordinal", (document_id,row["request_hash"])).fetchall()
    source = json.loads(row["source_snapshot"])
    updated = []
    try:
        for segment in segments:
            if not segment["output_json"]:
                continue
            output = json.loads(segment["output_json"])
            saved_version = output.get("index_version")
            if saved_version not in (INDEX_VERSION, "source-index-v2", "source-index-v1") or not output.get("proposed_result"):
                return "unavailable"
            if saved_version == "source-index-v1" and any(unit.get("reading_blocks") for unit in source["units"]):
                return "unavailable"
            output["result"] = project_saved_indexed(output, source, json.loads(segment["payload_json"]))
            output["validator_version"] = VALIDATOR_VERSION
            updated.append((json.dumps(output), segment["segment_id"], segment["output_json"]))
    except (ValueError, TypeError, KeyError, ValidationError, FactError):
        return "unavailable"
    if not updated:
        return "unavailable"
    if all(json.loads(new) == json.loads(old) for new, _, old in updated):
        return "ok"
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT status,result_json,source_snapshot,request_hash FROM fact_jobs WHERE document_id=?", (document_id,)).fetchone()
        if not current or any(current[key] != row[key] for key in ("status","result_json","source_snapshot","request_hash")):
            return "conflict"
        prior = dict(row)
        prior["segments"] = [dict(item) for item in segments]
        prior["audit"] = {"action": "local_revalidation", "validator_version": VALIDATOR_VERSION,
                          "before_hash": hashlib.sha256((row["result_json"] or "").encode("utf-8")).hexdigest()}
        archive_id = uuid.uuid4().hex
        for output, segment_id, old in updated:
            cursor = db.execute("UPDATE fact_segments SET output_json=? WHERE document_id=? AND request_hash=? AND segment_id=? AND output_json=?", (output,document_id,row["request_hash"],segment_id,old))
            if cursor.rowcount != 1:
                raise RuntimeError("Segment changed during local revalidation.")
        now = time.time()
        _finalize(db, document_id, row["request_hash"], now)
        after = db.execute("SELECT result_json FROM fact_jobs WHERE document_id=?", (document_id,)).fetchone()[0]
        prior["audit"]["after_hash"] = hashlib.sha256(after.encode("utf-8")).hexdigest()
        db.execute("INSERT INTO fact_runs(id,document_id,archived_at,job_json) VALUES (?,?,?,?)", (archive_id, document_id, now, json.dumps(prior)))
    return "ok"


def history(store, document_id):
    with store.connect() as db:
        rows = db.execute("SELECT id,archived_at,job_json FROM fact_runs WHERE document_id=? ORDER BY archived_at DESC", (document_id,)).fetchall()
    return [{"id": row["id"], "archived_at": row["archived_at"], "job": json.loads(row["job_json"])} for row in rows]
