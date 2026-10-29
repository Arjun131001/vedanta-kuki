"""Overview context must not be exhausted by the first selected file."""
import io
import json
from dataclasses import replace

import openpyxl
from fastapi.testclient import TestClient

from app import qa_store
from app.config import Settings
from app.main import create_app
from app.store import Store
from app.worker import process_one


def test_overview_reserves_context_for_small_second_document(tmp_path, monkeypatch):
    config = replace(Settings(), data_dir=tmp_path)
    store = Store(config)
    monkeypatch.setattr(qa_store, "MAX_RECORDS", 12)
    monkeypatch.setattr(qa_store, "MAX_CHARS", 12000)
    ids = []
    with TestClient(create_app(config)) as client:
        for filename, count in (("large.xlsx", 90), ("small.xlsx", 3)):
            book = openpyxl.Workbook()
            sheet = book.active
            sheet.append(["Reporting item", "Consumption (kWh)"])
            for index in range(count):
                sheet.append([f"Reported item {index}", index + 10])
            data = io.BytesIO()
            book.save(data)
            document = client.post("/api/documents", files=[("files", (filename, data.getvalue()))]).json()["results"][0]["document"]
            ids.append(document["id"])
            assert process_one(store)
        with store.connect() as db:
            frozen = qa_store.freeze_evidence(db, ids, "Give an overview of these documents", [])
    assert {record["document_id"] for record in frozen["records"]} == set(ids)
    assert len(frozen["records"]) <= 12
    assert any("context was limited" in warning for warning in frozen["warnings"])
    # The snapshot stays deterministic and bounded, rather than hiding truncation.
    with store.connect() as db:
        repeated = qa_store.freeze_evidence(db, ids, "Give an overview of these documents", [])
    assert frozen["sha256"] == repeated["sha256"]


def test_pdf_context_keeps_sentence_neighbors_inside_reading_block(monkeypatch):
    records = [
        {"id": ref, "unit_index": 1, "text": text, "cells": []}
        for ref, text in (("p1:b1:l1", "Our policy"),
                          ("p1:b1:l2", "We commit to food safety and"),
                          ("p1:b1:l3", "compliance across operations."),
                          ("p1:b1:l4", "Employees follow these requirements."),
                          ("p1:b2:l3", "Unrelated column text."))
    ]
    class Rows(list):
        def fetchone(self):
            return self[0] if self else None
    class SourceDatabase:
        def execute(self, sql, args):
            if "FROM documents" in sql:
                return Rows([{"filename": "policy.pdf", "kind": "pdf", "sha256": "doc-hash", "status": "ready"}])
            if "FROM source_results" in sql:
                return Rows([{"version": 1, "summary_json": '{"warnings": []}'}])
            return Rows([(json.dumps({"index": 1, "label": "Page 1"}),)])
    monkeypatch.setattr(qa_store, "build_index", lambda source: {"records": records})
    monkeypatch.setattr(qa_store, "MAX_RECORDS", 4)
    frozen = qa_store.freeze_evidence(SourceDatabase(), ["policy"], "What food safety commitment is reported?", [])
    assert {record["reference_id"] for record in frozen["records"]} == {
        "p1:b1:l1", "p1:b1:l2", "p1:b1:l3", "p1:b1:l4"}
