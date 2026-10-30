import json

import httpx
import pytest
from pydantic import ValidationError

from app.qa import Answer, answer_question, project_answer, MAX_ANSWER_TOKENS, PROMPT_VERSION


def evidence():
    return {"records": [
        {"id": "energy:a", "document_id": "energy", "filename": "energy.pdf", "unit_index": 1,
         "unit_label": "Page 1", "reference_id": "p1:l1", "quote": "Energy consumption 42 kWh",
         "cells": [], "evidence_status": "source_text_unreviewed"},
        {"id": "water:a", "document_id": "water", "filename": "water.pdf", "unit_index": 1,
         "unit_label": "Page 1", "reference_id": "p1:l1", "quote": "Water consumption 25 litres",
         "cells": [], "evidence_status": "source_text_unreviewed"}], "warnings": [], "sha256": "snapshot"}


def test_detailed_sections_preserve_claim_citations_and_natural_paragraphs():
    parsed = Answer.model_validate({"claims": [
        {"text": "Energy consumption is reported as 42 kWh.", "citation_ids": ["energy:a"], "section": "Summary"},
        {"text": "The energy document records consumption of 42 kWh.", "citation_ids": ["energy:a"], "section": "Reported data"},
        {"text": "The water document records consumption of 25 litres.", "citation_ids": ["water:a"], "section": "Reported data"}], "limitations": []})
    result = project_answer(parsed, evidence())
    assert result["answer"].startswith("## Summary\n\nEnergy consumption is reported as 42 kWh. [1]")
    assert result["answer"].count("## Reported data") == 1
    assert "42 kWh. [1]\n\nThe water document" in result["answer"]
    assert result["answer"].endswith("25 litres. [2]")
    assert [record["document_id"] for record in result["citations"]] == ["energy", "water"]


def test_unsupported_data_does_not_survive_as_a_detailed_section():
    parsed = Answer.model_validate({"claims": [
        {"text": "Energy consumption 42 kWh", "citation_ids": ["energy:a"], "section": "Summary"},
        {"text": "Water consumption 999 litres", "citation_ids": ["water:a"], "section": "Reported data"},
        {"text": "Unsupported assertion", "citation_ids": ["other:a"], "section": "Explanation"}], "limitations": []})
    result = project_answer(parsed, evidence())
    assert "999" not in result["answer"]
    assert "Reported data" not in result["answer"] and "Explanation" not in result["answer"]
    assert len(result["_qa_rejections"]) == 2


def test_headings_cannot_introduce_unvalidated_claims_or_numbers():
    with pytest.raises(ValidationError):
        Answer.model_validate({"claims": [{"text": "Energy consumption 42 kWh", "citation_ids": ["energy:a"],
                                            "section": "Guaranteed savings of 999 percent"}], "limitations": []})


def test_detailed_request_budget_strict_schema_and_audit():
    def provider(request):
        body = json.loads(request.content)
        assert body["max_completion_tokens"] == MAX_ANSWER_TOKENS == 12000
        assert body["model"] == "gpt-4o-mini"
        schema = body["response_format"]["json_schema"]["schema"]
        claim = schema["$defs"]["Claim"]
        assert set(claim["required"]) == set(claim["properties"])
        assert "default" not in claim["properties"]["section"]
        assert body["store"] is False
        payload = json.loads(body["messages"][1]["content"])
        assert payload["question"] == "Explain the reported data in detail"
        assert len(payload["evidence"]) == 2
        result = {"claims": [{"text": "Energy consumption 42 kWh", "citation_ids": ["energy:a"], "section": "Reported data"}], "limitations": []}
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]})
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        result = answer_question("Explain the reported data in detail", evidence(), [], "gpt-4o-mini", "mock-key", client)
    assert result["_qa_audit"]["prompt_version"] == PROMPT_VERSION
    assert "## Reported data" in result["answer"]


def test_long_cited_explanation_is_not_truncated_by_projection():
    statement = "The policy commits to protecting product quality throughout operations. " * 30
    source = {"records": [{"id": "policy:a", "quote": statement, "cells": []}], "warnings": []}
    parsed = Answer.model_validate({"claims": [{"text": statement.strip(), "citation_ids": ["policy:a"], "section": "Policy commitments"}], "limitations": []})
    result = project_answer(parsed, source)
    assert statement.strip() in result["answer"] and result["answer"].endswith("[1]")
