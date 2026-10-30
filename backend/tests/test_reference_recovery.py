from copy import deepcopy

from app.evidence_index import build_index
from app.facts import IndexedFactResult, project_indexed


def fixture():
    source = {"version": 1, "kind": "xlsx", "summary": {"warnings": []}, "units": [
        {"index": 1, "label": "Report", "cells": [
            {"coordinate": "A1", "value": "Grid supply", "type": "s"},
            {"coordinate": "A2", "value": 42, "type": "n"}]}]}
    records = build_index(source)["records"]
    segment = {"records": records, "target_ids": ["s1:A2"]}
    proposal = {"document_type": "Report", "organization": None, "organization_ref": None,
        "warnings": [], "coverage": "partial", "coverage_note": "Review", "facts": [
        {"label": "Grid supply", "source_label": "Grid supply", "label_ref": "s1:A2",
         "value": "42", "value_ref": "s1:A2", "organization": None, "organization_ref": None,
         "unit": None, "unit_ref": None, "period": None, "period_ref": None,
         "currency": None, "currency_ref": None, "origin": "document_reported"}]}
    return source, segment, proposal


def test_unique_workbook_header_recovered_for_review_without_mutating_proposal():
    source, segment, proposal = fixture()
    original = deepcopy(proposal)
    output = project_indexed(IndexedFactResult.model_validate(proposal), source, segment)
    assert not output["rejected_candidates"]
    assert not output["facts"]
    candidate = output["review_candidates"][0]
    assert candidate["context_evidence"][0]["reference_id"] == "s1:A1"
    assert candidate["recovery_audit"][0]["original_ids"] == ["s1:A2"]
    assert output["coverage"] == "partial"
    assert proposal == original


def test_ambiguous_workbook_labels_are_not_guessed():
    source, segment, proposal = fixture()
    source["units"][0]["cells"].append({"coordinate": "B1", "value": "Grid supply", "type": "s"})
    segment["records"] = build_index(source)["records"]
    output = project_indexed(IndexedFactResult.model_validate(proposal), source, segment)
    assert len(output["rejected_candidates"]) == 1


def test_recovery_cannot_use_another_sheet_or_context_only_value():
    source, segment, proposal = fixture()
    proposal["facts"][0]["label_ref"] = "s2:A2"
    assert project_indexed(IndexedFactResult.model_validate(proposal), source, segment)["rejected_candidates"]
    proposal["facts"][0]["label_ref"] = "s1:A1"
    segment["target_ids"] = []
    assert project_indexed(IndexedFactResult.model_validate(proposal), source, segment)["rejected_candidates"]


def test_fabricated_value_is_still_rejected():
    source, segment, proposal = fixture()
    proposal["facts"][0]["value"] = "999"
    assert project_indexed(IndexedFactResult.model_validate(proposal), source, segment)["rejected_candidates"]
