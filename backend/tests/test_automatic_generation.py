import io
import json
from dataclasses import replace

import httpx
import openpyxl

from app.config import Settings
from app.store import Store
from app.worker import process_one, process_fact
from app import fact_queue
from app.facts import call_openai


def ingest(store, rows=1):
    book = openpyxl.Workbook()
    for row in range(1, rows + 1):
        book.active[f"A{row}"] = "Energy"
        book.active[f"B{row}"] = 42
    stream = io.BytesIO()
    book.save(stream)
    path = store.settings.data_dir / "incoming-test.xlsx"
    path.write_bytes(stream.getvalue())
    return store.ingest(path, "test.xlsx", "xlsx", len(stream.getvalue()), "test-digest")


def test_upload_automatically_generates_and_deduplicates_after_restart(tmp_path):
    settings = replace(Settings(), data_dir=tmp_path, openai_api_key="test-key")
    store = Store(settings)
    document, duplicate = ingest(store)
    assert not duplicate and document["generation_status"] == "generating"
    assert process_one(store)
    # A restarted worker recovers intent even if the source worker stopped here.
    restarted = Store(settings)
    assert restarted.get(document["id"])["generation_status"] == "generating"
    assert fact_queue.enqueue_automatic(restarted)
    progress = restarted.get(document["id"])
    assert progress["generation_total_segments"] == 1
    assert progress["generation_completed_segments"] == 0
    assert not fact_queue.enqueue_automatic(restarted)
    requests = []
    def provider(request):
        requests.append(json.loads(request.content))
        proposal = {"document_type": "Workbook", "organization": None, "organization_ref": None,
                    "coverage": "partial", "coverage_note": "Review", "warnings": [], "facts": [
            {"label": "Energy", "source_label": "Energy", "label_ref": "s1:A1", "value": "42", "value_ref": "s1:B1",
             "organization": None, "organization_ref": None, "unit": None, "unit_ref": None, "period": None,
             "period_ref": None, "currency": None, "currency_ref": None, "origin": "document_reported"}]}
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(proposal)}}]})
    def caller(source, model, key, segment):
        with httpx.Client(transport=httpx.MockTransport(provider)) as client:
            return call_openai(source, model, key, client, segment)
    assert process_fact(restarted, caller)
    generated = restarted.get(document["id"])
    assert generated["status"] == "ready" and generated["generation_status"] == "generated"
    assert generated["generation_completed_segments"] == generated["generation_total_segments"] == 1
    assert fact_queue.get(restarted, document["id"])["output"]["result"]["facts"][0]["value"] == "42"
    assert len(requests) == 1
    existing, duplicate = ingest(restarted)
    assert duplicate and existing["id"] == document["id"]
    assert existing["generation_status"] == "generated"
    assert not fact_queue.enqueue_automatic(restarted)
    assert not process_fact(restarted, caller)
    assert len(requests) == 1


def test_missing_key_fails_visibly_without_repeated_queueing(tmp_path):
    store = Store(replace(Settings(), data_dir=tmp_path, openai_api_key=""))
    document, _ = ingest(store)
    assert process_one(store)
    assert fact_queue.enqueue_automatic(store)
    failed = store.get(document["id"])
    assert failed["status"] == "ready" and failed["generation_status"] == "failed"
    assert "not configured" in failed["generation_error"]
    assert fact_queue.get(store, document["id"])["status"] == "not_requested"
    assert not fact_queue.enqueue_automatic(store)
    configured = Store(replace(store.settings, openai_api_key="test-key"))
    assert fact_queue.enqueue(configured, document["id"]) == "queued"
    assert configured.get(document["id"])["generation_error"] is None
    assert configured.get(document["id"])["generation_status"] == "generating"


def test_generation_failure_is_not_reported_as_generated(tmp_path):
    from app.facts import FactError
    store = Store(replace(Settings(), data_dir=tmp_path, openai_api_key="test-key"))
    document, _ = ingest(store)
    assert process_one(store) and fact_queue.enqueue_automatic(store)
    def fail(*args, **kwargs):
        raise FactError("Provider quota unavailable.")
    assert process_fact(store, fail)
    failed = store.get(document["id"])
    assert failed["generation_status"] == "failed"
    assert "quota" in failed["generation_error"]
    assert not fact_queue.enqueue_automatic(store)


def test_unreadable_upload_does_not_start_openai(tmp_path):
    store = Store(replace(Settings(), data_dir=tmp_path, openai_api_key="test-key"))
    path = tmp_path / "invalid.xlsx"
    path.write_bytes(b"invalid")
    document, _ = store.ingest(path, "bad.xlsx", "xlsx", 7, "bad-digest")
    assert process_one(store)
    assert store.get(document["id"])["generation_status"] == "failed"
    assert not fact_queue.enqueue_automatic(store)


def test_legacy_documents_do_not_trigger_new_model_calls(tmp_path):
    store = Store(replace(Settings(), data_dir=tmp_path, openai_api_key="test-key"))
    document, _ = ingest(store)
    with store.connect() as db:
        db.execute("UPDATE documents SET auto_generate=0 WHERE id=?", (document["id"],))
    assert process_one(store)
    assert store.get(document["id"])["generation_status"] == "not_requested"
    assert not fact_queue.enqueue_automatic(store)


def test_partial_segment_failure_stays_generating_until_job_finishes(tmp_path):
    from app.facts import FactError
    store = Store(replace(Settings(), data_dir=tmp_path, openai_api_key="test-key"))
    document, _ = ingest(store, rows=9)
    assert process_one(store) and fact_queue.enqueue_automatic(store)
    def fail(*args, **kwargs):
        raise FactError("Provider unavailable.")
    assert process_fact(store, fail)
    assert fact_queue.get(store, document["id"])["status"] == "queued"
    assert store.get(document["id"])["generation_status"] == "generating"
    assert store.get(document["id"])["generation_error"] is None
    assert process_fact(store, fail) and process_fact(store, fail)
    assert store.get(document["id"])["generation_status"] == "failed"


def test_library_retry_requeues_generation_without_reprocessing_source(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.facts import FactError
    settings = replace(Settings(), data_dir=tmp_path, openai_api_key="test-key")
    store = Store(settings)
    document, _ = ingest(store)
    assert process_one(store) and fact_queue.enqueue_automatic(store)
    def fail(*args, **kwargs):
        raise FactError("Provider unavailable.")
    assert process_fact(store, fail)
    with TestClient(create_app(settings)) as client:
        response = client.post(f"/api/documents/{document['id']}/retry")
        assert response.status_code == 200
        assert response.json()["generation_status"] == "generating"
    assert not process_one(store)
    assert fact_queue.get(store, document["id"])["status"] == "queued"


def test_library_retry_requires_key_then_recovers_after_configuration(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    settings = replace(Settings(), data_dir=tmp_path, openai_api_key="")
    store = Store(settings)
    document, _ = ingest(store)
    assert process_one(store) and fact_queue.enqueue_automatic(store)
    with TestClient(create_app(settings)) as client:
        assert client.post(f"/api/documents/{document['id']}/retry").status_code == 503
    with TestClient(create_app(replace(settings, openai_api_key="test-key"))) as client:
        response = client.post(f"/api/documents/{document['id']}/retry")
        assert response.status_code == 200 and response.json()["generation_status"] == "generating"
        assert response.json()["generation_error"] is None
