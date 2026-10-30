from copy import deepcopy

from app.facts import project_saved_indexed


def test_retained_proposal_is_rechecked_without_mutating_provider_response():
    source = {"version": 1, "kind": "pdf", "summary": {"warnings": []},
              "units": [{"index": 1, "label": "Page 1", "text": "Recycled water rebate available"}]}
    segment = {"records": [{"id": "p1:l1", "unit_index": 1, "text": source["units"][0]["text"], "cells": []}],
               "target_ids": ["p1:l1"]}
    fact = {"label": "Water rebate", "source_label": "Recycled water rebate", "label_ref": "p1:l1",
            "value": "available", "value_ref": "p1:l1", "organization": None, "organization_ref": None,
            "unit": None, "unit_ref": None, "period": None, "period_ref": None, "currency": None,
            "currency_ref": None, "origin": "document_reported"}
    output = {"proposed_result": {"document_type": "Bill", "organization": None, "organization_ref": None,
                                   "facts": [], "warnings": [], "coverage": "partial", "coverage_note": "Review"},
              "retained_proposals": [fact]}
    original = deepcopy(output)
    result = project_saved_indexed(output, source, segment)
    assert len(result["facts"]) == 1 and not result["rejected_candidates"]
    assert output == original
    output["retained_proposals"][0]["value"] = "invented"
    assert project_saved_indexed(output, source, segment)["rejected_candidates"]
    output["retained_proposals"][0]["value"] = "available"
    segment["target_ids"] = []
    assert project_saved_indexed(output, source, segment)["rejected_candidates"]
