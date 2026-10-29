"""Durable, document-scoped question answering with frozen evidence."""
import hashlib
import json
import re
import time
import uuid

from .evidence_index import build_index

MAX_RECORDS = 120
MAX_CHARS = 60000


def create_tables(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS qa_sessions (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, document_ids_json TEXT NOT NULL,
          created_at REAL NOT NULL, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS qa_turns (
          id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES qa_sessions(id),
          request_id TEXT NOT NULL, question TEXT NOT NULL, status TEXT NOT NULL,
          evidence_json TEXT NOT NULL, history_json TEXT NOT NULL, model TEXT NOT NULL,
          answer TEXT, citations_json TEXT, limitations_json TEXT, error TEXT,
          lease_owner TEXT, lease_until REAL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
          UNIQUE(session_id, request_id)
        );
        CREATE INDEX IF NOT EXISTS qa_turn_queue ON qa_turns(status, created_at);
        CREATE TABLE IF NOT EXISTS qa_local_history (
          id TEXT PRIMARY KEY, turn_id TEXT NOT NULL REFERENCES qa_turns(id),
          action TEXT NOT NULL, previous_json TEXT NOT NULL, created_at REAL NOT NULL
        );
    """)
    columns = {row[1] for row in db.execute("PRAGMA table_info(qa_turns)")}
    if "audit_json" not in columns:
        db.execute("ALTER TABLE qa_turns ADD COLUMN audit_json TEXT")
    if "calculations_json" not in columns:
        db.execute("ALTER TABLE qa_turns ADD COLUMN calculations_json TEXT")


def public_turn(row):
    calculations = []
    try:
        calculations = json.loads(row["calculations_json"] or "[]")
    except (KeyError, TypeError, json.JSONDecodeError):
        calculations = []
    return {"id":row["id"], "question":row["question"], "status":row["status"], "answer":row["answer"],
            "citations":json.loads(row["citations_json"] or "[]"), "limitations":json.loads(row["limitations_json"] or "[]"),
            "calculations":calculations, "error":row["error"], "created_at":row["created_at"], "updated_at":row["updated_at"]}


def session(store, session_id):
    with store.connect() as db:
        row=db.execute("SELECT * FROM qa_sessions WHERE id=?",(session_id,)).fetchone()
        if not row: return None
        turns=db.execute("SELECT * FROM qa_turns WHERE session_id=? ORDER BY created_at,id",(session_id,)).fetchall()
    return {"id":row["id"], "title":row["title"], "document_ids":json.loads(row["document_ids_json"]),
            "created_at":row["created_at"], "updated_at":row["updated_at"], "messages":[public_turn(turn) for turn in turns]}


def list_sessions(store):
    with store.connect() as db:
        rows=db.execute("SELECT * FROM qa_sessions ORDER BY updated_at DESC").fetchall()
    return [{"id":row["id"],"title":row["title"],"document_ids":json.loads(row["document_ids_json"]),
             "created_at":row["created_at"],"updated_at":row["updated_at"]} for row in rows]


def create_session(store, ids):
    if not ids or len(ids)>10 or len(set(ids)) != len(ids): raise ValueError("Select one to ten distinct documents.")
    now=time.time(); session_id=uuid.uuid4().hex
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        for document_id in ids:
            row=db.execute("SELECT status FROM documents WHERE id=?",(document_id,)).fetchone()
            if not row or row["status"] != "ready" or not db.execute("SELECT 1 FROM source_results WHERE document_id=? AND version=1",(document_id,)).fetchone():
                raise ValueError("Every selected document must exist and have extracted source.")
        db.execute("INSERT INTO qa_sessions VALUES (?,?,?,?,?)",(session_id,"Document conversation",json.dumps(ids),now,now))
    return session(store,session_id)


def load_records_for_documents(store, document_ids, record_limit=500, char_limit=200000):
    """Load a broad evidence snapshot for FY summaries (not question-ranked)."""
    if not document_ids or len(document_ids) > 10 or len(set(document_ids)) != len(document_ids):
        raise ValueError("Select one to ten distinct documents.")
    records = []
    warnings = []
    meta = []
    size = 0
    with store.connect() as db:
        for document_id in document_ids:
            doc = db.execute("SELECT id,filename,kind,sha256,status FROM documents WHERE id=?", (document_id,)).fetchone()
            result = db.execute("SELECT version,summary_json FROM source_results WHERE document_id=? AND version=1", (document_id,)).fetchone()
            if not doc or doc["status"] != "ready" or not result:
                raise ValueError("Every selected document must exist and have extracted source.")
            summary = json.loads(result["summary_json"])
            warnings.extend(f'{doc["filename"]}: {warning}' for warning in summary.get("warnings", []))
            units = [json.loads(row[0]) for row in db.execute(
                "SELECT content_json FROM source_units WHERE document_id=? AND version=1 ORDER BY unit_index", (document_id,))]
            source = {"version": result["version"], "kind": doc["kind"], "summary": summary, "units": units}
            source_hash = hashlib.sha256(json.dumps(source, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
            unit_labels = {unit["index"]: unit["label"] for unit in units}
            indexed = [record for record in build_index(source)["records"] if record.get("text")]
            meta.append({"id": doc["id"], "filename": doc["filename"], "kind": doc["kind"], "record_count": len(indexed)})
            for item in indexed:
                public = {
                    "id": f'{document_id}:{item["id"]}', "document_id": document_id, "filename": doc["filename"],
                    "unit_index": item["unit_index"], "unit_label": unit_labels[item["unit_index"]],
                    "reference_id": item["id"], "quote": item["text"], "cells": item["cells"],
                    "evidence_status": "source_text_unreviewed", "source_version": result["version"],
                    "source_sha256": source_hash, "document_sha256": doc["sha256"],
                }
                length = len(json.dumps(public, ensure_ascii=False))
                if len(records) >= record_limit or size + length > char_limit:
                    warnings.append("FY evidence was limited; some source rows may be missing from coverage.")
                    break
                records.append(public)
                size += length
    return {"records": records, "warnings": list(dict.fromkeys(warnings)), "document_ids": document_ids, "documents": meta}


def tokens(text):
    return {token.lower() for token in re.findall(r"[A-Za-z0-9]{3,}",text) if token.lower() not in {"the","and","for","what","are","was","this","that","from","with","how","does","which","document"}}


def freeze_evidence(db, document_ids, question, history):
    query=tokens(question + " " + " ".join(turn["question"] for turn in history[-3:]))
    candidates=[]; warnings=[]
    for document_id in document_ids:
        doc=db.execute("SELECT filename,kind,sha256,status FROM documents WHERE id=?",(document_id,)).fetchone()
        result=db.execute("SELECT version,summary_json FROM source_results WHERE document_id=? AND version=1",(document_id,)).fetchone()
        if not doc or doc["status"] != "ready" or not result: raise ValueError("A selected document no longer has ready source.")
        summary=json.loads(result["summary_json"])
        warnings.extend(f'{doc["filename"]}: {warning}' for warning in summary.get("warnings",[]))
        units=[json.loads(row[0]) for row in db.execute("SELECT content_json FROM source_units WHERE document_id=? AND version=1 ORDER BY unit_index",(document_id,))]
        source={"version":result["version"],"kind":doc["kind"],"summary":summary,"units":units}
        source_hash = hashlib.sha256(json.dumps(source,ensure_ascii=False,separators=(",", ":"),sort_keys=True).encode("utf-8")).hexdigest()
        unit_labels={unit["index"]:unit["label"] for unit in units}
        indexed = [record for record in build_index(source)["records"] if record.get("text")]
        record_map = {record["id"]: record for record in indexed}
        for position, record in enumerate(indexed):
            reference = record["id"]
            related = []
            if doc["kind"] == "xlsx" and record.get("cells"):
                match = re.fullmatch(r"([A-Z]+)([1-9]\d*)", record["cells"][0])
                if match:
                    column, row_number = match.group(1), int(match.group(2))
                    for related_ref in (f"s{record['unit_index']}:{column}1", f"s{record['unit_index']}:{column}2", f"s{record['unit_index']}:A{row_number}"):
                        if related_ref != reference and related_ref in record_map:
                            related.append(record_map[related_ref])
            elif doc["kind"] == "pdf":
                # Preserve nearby sentence context without crossing pages or
                # detected reading-order blocks; each line keeps its own ID.
                match = re.fullmatch(r"(p\d+:(?:b\d+:)?l)(\d+)", reference)
                if match:
                    for offset in (-1, 1, 2):
                        neighbor = record_map.get(match.group(1) + str(int(match.group(2)) + offset))
                        if neighbor:
                            related.append(neighbor)
            bundle = [record] + list({item["id"]: item for item in related}.values())
            score = len(query & tokens(" ".join(item["text"] for item in bundle)))
            def public_record(item):
                return {"id": f'{document_id}:{item["id"]}', "document_id":document_id, "filename":doc["filename"],
                        "unit_index":item["unit_index"], "unit_label":unit_labels[item["unit_index"]], "reference_id":item["id"],
                        "quote":item["text"], "cells":item["cells"], "evidence_status":"source_text_unreviewed",
                        "source_version":result["version"], "source_sha256":source_hash, "document_sha256":doc["sha256"]}
            candidates.append((score,document_id,position,[public_record(item) for item in bundle]))
    # Include each value and its explicit row/header context atomically.
    candidates.sort(key=lambda x:(-x[0],document_ids.index(x[1]),x[2]))
    selected=[]; selected_ids=set(); size=0
    def include(bundle, record_limit=MAX_RECORDS, char_limit=MAX_CHARS):
        nonlocal size
        needed=[item for item in bundle if item["id"] not in selected_ids]
        length=sum(len(json.dumps(item,ensure_ascii=False)) for item in needed)
        if len(selected)+len(needed)>record_limit or size+length>char_limit:
            return
        selected.extend(needed); selected_ids.update(item["id"] for item in needed); size+=length
    # Overview questions need representative context from every selected file.
    # Reserve equal budgets first, then reuse any spare capacity by relevance.
    overview = re.search(r"\b(?:overview|summari[sz]e|summary|what (?:all )?(?:details|information)|what(?:'s| is) (?:in|inside))\b", question, re.I)
    if overview and len(document_ids) > 1:
        for document_id in document_ids:
            record_limit = min(MAX_RECORDS, len(selected) + MAX_RECORDS // len(document_ids))
            char_limit = min(MAX_CHARS, size + MAX_CHARS // len(document_ids))
            for _, candidate_doc, _, bundle in candidates:
                if candidate_doc == document_id:
                    include(bundle, record_limit, char_limit)
    for _,_,_,bundle in candidates:
        include(bundle)
    total_unique = {item["id"] for _,_,_,bundle in candidates for item in bundle}
    if len(selected)<len(total_unique): warnings.append("The source context was limited; relevant information may be missing.")
    if not selected: warnings.append("No extractable source text or cell values were available.")
    snapshot={"records":selected,"warnings":list(dict.fromkeys(warnings)),"document_ids":document_ids}
    snapshot["sha256"]=hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return snapshot


def enqueue(store, session_id, question, request_id):
    question=question.strip()
    if not question or len(question)>4000 or not request_id or len(request_id)>128: raise ValueError("Question and request ID are required; question limit is 4,000 characters.")
    now=time.time()
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        session_row=db.execute("SELECT * FROM qa_sessions WHERE id=?",(session_id,)).fetchone()
        if not session_row: return None
        old=db.execute("SELECT * FROM qa_turns WHERE session_id=? AND request_id=?",(session_id,request_id)).fetchone()
        if old:
            if old["question"] != question: raise ValueError("This request ID was already used for another question.")
            return public_turn(old)
        if db.execute("SELECT 1 FROM qa_turns WHERE session_id=? AND status IN ('queued','processing')",(session_id,)).fetchone():
            raise RuntimeError("A question is already in progress for this conversation.")
        turns=db.execute("SELECT * FROM qa_turns WHERE session_id=? AND status='ready' ORDER BY created_at,id",(session_id,)).fetchall()
        history=[{"question":t["question"],"answer":t["answer"]} for t in turns[-5:]]
        evidence=freeze_evidence(db,json.loads(session_row["document_ids_json"]),question,history)
        turn_id=uuid.uuid4().hex
        db.execute("""INSERT INTO qa_turns(id,session_id,request_id,question,status,evidence_json,history_json,model,created_at,updated_at)
                    VALUES (?,?,?,?,'queued',?,?,?,?,?)""",(turn_id,session_id,request_id,question,json.dumps(evidence),json.dumps(history),store.settings.openai_model,now,now))
        db.execute("UPDATE qa_sessions SET updated_at=?,title=CASE WHEN title='Document conversation' THEN ? ELSE title END WHERE id=?",(now,question[:80],session_id))
        return public_turn(db.execute("SELECT * FROM qa_turns WHERE id=?",(turn_id,)).fetchone())


def claim(store, now=None):
    now=time.time() if now is None else now
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        # A crashed provider call is not retried automatically: it may already have been billed.
        db.execute("UPDATE qa_turns SET status='failed',error='The request was interrupted; submit a new question to retry.',lease_owner=NULL,lease_until=NULL,updated_at=? WHERE status='processing' AND lease_until<=?",(now,now))
        row=db.execute("SELECT * FROM qa_turns WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
        if not row: return None
        token=uuid.uuid4().hex
        db.execute("UPDATE qa_turns SET status='processing',lease_owner=?,lease_until=?,updated_at=? WHERE id=?",(token,now+store.settings.lease_seconds,now,row["id"]))
        return {**dict(row),"lease_owner":token}


def heartbeat(store, job):
    now=time.time()
    with store.connect() as db:
        return db.execute("UPDATE qa_turns SET lease_until=? WHERE id=? AND status='processing' AND lease_owner=? AND lease_until>?",(now+store.settings.lease_seconds,job["id"],job["lease_owner"],now)).rowcount==1


def finish(store, job, result=None, error=None, now=None, audit=None):
    now=time.time() if now is None else now
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        calculations = None
        if result is not None:
            calculations = json.dumps(result.get("calculations") or [])
        cursor=db.execute("""UPDATE qa_turns SET status=?,answer=?,citations_json=?,limitations_json=?,calculations_json=?,error=?,audit_json=?,updated_at=?,lease_owner=NULL,lease_until=NULL
                  WHERE id=? AND status='processing' AND lease_owner=? AND lease_until>?""",
                  ("failed" if error else "ready",result["answer"] if result else None,json.dumps(result["citations"]) if result else None,
                   json.dumps(result["limitations"]) if result else None,calculations,error,json.dumps(audit or (result or {}).get("_qa_audit")) if (audit or (result or {}).get("_qa_audit")) else None,now,job["id"],job["lease_owner"],now))
        if cursor.rowcount: db.execute("UPDATE qa_sessions SET updated_at=? WHERE id=?",(now,job["session_id"]))
        return cursor.rowcount==1


def replay_saved_proposal(store, turn_id):
    """Reproject a saved proposal against its original snapshot without a provider call."""
    from .qa import Answer, project_answer
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM qa_turns WHERE id=?", (turn_id,)).fetchone()
        if not row or row["status"] in ("queued", "processing") or not row["audit_json"]:
            raise ValueError("No saved proposal is available for local revalidation.")
        audit = json.loads(row["audit_json"])
        evidence = json.loads(row["evidence_json"])
        if audit.get("evidence_sha256") != evidence.get("sha256"):
            raise ValueError("The saved evidence does not match the proposal.")
        result = project_answer(Answer.model_validate_json(audit["proposal"]), evidence)
        db.execute("INSERT INTO qa_local_history VALUES (?,?,?,?,?)", (uuid.uuid4().hex, turn_id, "revalidate", json.dumps(public_turn(row)), time.time()))
        db.execute("UPDATE qa_turns SET status='ready', answer=?, citations_json=?, limitations_json=?, error=NULL, updated_at=? WHERE id=?",
                   (result["answer"], json.dumps(result["citations"]), json.dumps(result["limitations"]), time.time(), turn_id))
        return result


def recover_local_overview(store, turn_id):
    """Replace a failed broad-question result with clearly labeled local excerpts."""
    from .qa import local_overview
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM qa_turns WHERE id=?", (turn_id,)).fetchone()
        if not row or row["status"] != "failed":
            raise ValueError("Only a failed question can be recovered as a local overview.")
        result = local_overview(row["question"], json.loads(row["evidence_json"]))
        if result is None:
            raise ValueError("This question cannot be recovered as a local overview.")
        db.execute("INSERT INTO qa_local_history VALUES (?,?,?,?,?)", (uuid.uuid4().hex, turn_id, "extractive_overview", json.dumps(public_turn(row)), time.time()))
        db.execute("UPDATE qa_turns SET status='ready', answer=?, citations_json=?, limitations_json=?, error=NULL, updated_at=? WHERE id=?",
                   (result["answer"], json.dumps(result["citations"]), json.dumps(result["limitations"]), time.time(), turn_id))
        return result


def refresh_local_overview(store, turn_id):
    """Refresh only an existing local overview, retaining its earlier projection."""
    from .qa import local_overview
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM qa_turns WHERE id=?", (turn_id,)).fetchone()
        if not row or row["status"] != "ready" or not (row["answer"] or "").startswith("Local source overview (selected excerpts)"):
            raise ValueError("Only an existing local overview can be refreshed.")
        result = local_overview(row["question"], json.loads(row["evidence_json"]))
        if result is None:
            raise ValueError("The saved source does not contain usable overview excerpts.")
        db.execute("INSERT INTO qa_local_history VALUES (?,?,?,?,?)", (uuid.uuid4().hex, turn_id, "refresh_extractive_overview", json.dumps(public_turn(row)), time.time()))
        db.execute("UPDATE qa_turns SET answer=?, citations_json=?, limitations_json=?, updated_at=? WHERE id=?",
                   (result["answer"], json.dumps(result["citations"]), json.dumps(result["limitations"]), time.time(), turn_id))
        return result
