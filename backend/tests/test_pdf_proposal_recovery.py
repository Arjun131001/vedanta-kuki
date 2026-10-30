from copy import deepcopy

import pytest

from app.evidence_index import build_index
from app.facts import IndexedFactResult, project_indexed


def project(text, **changes):
    source = {"version": 1, "kind": "pdf", "summary": {"warnings": []},
              "units": [{"index": 1, "label": "Page 1", "text": text}]}
    fact = {"label": "Previous units", "source_label": "PREVIOUS UNITS",
            "label_ref": "p1:l1", "value": "42", "value_ref": "p1:l1",
            "organization": None, "organization_ref": None,
            "unit": None, "unit_ref": None, "period": None, "period_ref": None,
            "currency": None, "currency_ref": None, "origin": "document_reported"}
    fact.update(changes)
    proposal = {"document_type": "Bill", "organization": None, "organization_ref": None,
                "warnings": [], "coverage": "complete", "coverage_note": "", "facts": [fact]}
    original = deepcopy(proposal)
    segment = {"records": build_index(source)["records"], "target_ids": ["p1:l1"]}
    output = project_indexed(IndexedFactResult.model_validate(proposal), source, segment)
    assert proposal == original
    return output


@pytest.mark.parametrize("label", ["Previous Units", "PreviousU nits", "Pre vious Units"])
def test_pdf_label_formatting_recovery_retains_source_wording_and_review(label):
    output = project(label + " : 42")
    assert not output["rejected_candidates"]
    assert not output["facts"]
    candidate = output["review_candidates"][0]
    assert candidate["source_label"] == label
    assert candidate["recovery_audit"][0]["original_text"] == "PREVIOUS UNITS"
    assert output["proposed_facts"][0]["source_label"] == "PREVIOUS UNITS"
    assert output["coverage"] == "partial"


def test_literal_value_used_as_reference_is_recovered_on_target_label_line():
    output = project("Previous Units : 42", value_ref="42")
    assert not output["rejected_candidates"]
    assert output["review_candidates"][0]["evidence"]["reference_id"] == "p1:l1"


def test_unique_formatted_header_can_be_located_on_cited_page():
    output = project("Amount : 42\nPreviousU nits")
    assert not output["rejected_candidates"]
    candidate = output["review_candidates"][0]
    assert candidate["source_label"] == "PreviousU nits"
    assert candidate["context_evidence"][0]["reference_id"] == "p1:l2"


def test_formatted_header_on_multiple_lines_is_ambiguous():
    output = project("Amount : 42\nPreviousU nits\nPrevious U nits")
    assert output["rejected_candidates"]


def test_wrapped_table_label_uses_only_its_verbatim_prefix_for_review():
    output = project("Sewerage Charges (50% 26,401.38\nof water)", label="Sewerage Charges",
                     source_label="Sewerage Charges (50% of water)", value="26,401.38")
    assert not output["rejected_candidates"] and not output["facts"]
    candidate = output["review_candidates"][0]
    assert candidate["source_label"] == "Sewerage Charges"
    assert candidate["recovery_audit"][0]["field"] == "source_label_prefix"
    assert output["proposed_facts"][0]["source_label"] == "Sewerage Charges (50% of water)"


def test_prefix_recovery_does_not_invent_a_label_or_drop_numeric_qualifier():
    for text in ("Different Charge 42", "Previous Units about 42"):
        output = project(text, label="Previous Units", source_label="Previous Units invented suffix")
        assert output["rejected_candidates"]


@pytest.mark.parametrize("text,changes", [
    ("Previous Units : 42", {"value": "999", "value_ref": "999"}),
    ("Previous Units : 42", {"value": "", "value_ref": ""}),
    ("Previous Units : 42", {"label_ref": "p2:l1"}),
    ("Previous Units : 42", {"source_label": "Previous consumption"}),
    ("Previous Units Previous Units : 42", {}),
    ("Previous Units : about 42", {"value_ref": "42"}),
    ("Previous Units : 42 million", {"value_ref": "42"}),
])
def test_pdf_recovery_keeps_unsupported_and_ambiguous_proposals_rejected(text, changes):
    output = project(text, **changes)
    assert output["rejected_candidates"]
    assert not output["facts"]
    assert not output["review_candidates"]
