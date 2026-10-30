import json

import httpx
import pytest

from app.facts import FactError, call_openai, provider_schema
from app.segments import PDF_TARGET_LINES, build_manifest


def source(text):
    return {"version": 1, "kind": "pdf", "summary": {"warnings": []},
            "units": [{"index": 1, "label": "Page 1", "text": text}]}


def test_request_schema_binds_value_to_targets_and_other_refs_to_source():
    payload = {"records": [{"id": "p1:l1", "text": "Energy"},
                           {"id": "p1:l2", "text": "42 kWh"},
                           {"id": "p1:l3", "text": None}], "target_ids": ["p1:l2"]}
    schema = provider_schema(payload)
    props = schema["$defs"]["IndexedFact"]["properties"]
    assert schema["$defs"]["SourceReference"]["enum"] == ["p1:l1", "p1:l2"]
    assert schema["$defs"]["TargetReference"]["enum"] == ["p1:l2"]
    assert props["value_ref"]["$ref"] == "#/$defs/TargetReference"
    assert props["label_ref"]["$ref"] == "#/$defs/SourceReference"
    assert props["value_refs"]["items"]["$ref"] == "#/$defs/SourceReference"
    assert props["value"]["minLength"] == props["source_label"]["minLength"] == 1
    assert props["value"]["pattern"] == r"\S"
    assert {"type": "null"} in props["unit_ref"]["anyOf"]
    # Per-request changes must not leak into the reusable schema or other requests.
    assert "SourceReference" not in provider_schema()["$defs"]


@pytest.mark.parametrize("model,effort", [
    ("gpt-4o-mini", None),
    ("gpt-5-nano", "minimal"),
    ("gpt-5-mini-2025-08-07", "minimal"),
    ("gpt-5.1", None),
])
def test_provider_receives_bound_schema(model, effort):
    document = source("Energy 42 kWh")
    segment = build_manifest(document)[0]
    def handler(request):
        body = json.loads(request.content)
        assert body.get("reasoning_effort") == effort
        schema = body["response_format"]["json_schema"]["schema"]
        assert schema["$defs"]["TargetReference"]["enum"] == segment["target_ids"]
        result = {"document_type": "Bill", "organization": None, "organization_ref": None,
                  "facts": [], "warnings": ["Review source"], "coverage": "partial", "coverage_note": "Review"}
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        output = call_openai(document, model, "test-key", client, segment)
    assert output["result"]["coverage"] == "partial"
    assert output["request_schema_version"] == "source-bound-references-v1"
    assert len(output["request_schema_hash"]) == 64


@pytest.mark.parametrize("payload", [
    {"records": [], "target_ids": []},
    {"records": [{"id": "s1:A1", "text": None}], "target_ids": ["s1:A1"]},
    {"records": [{"id": "s1:A1", "text": "#DIV/0!", "type": "e"}], "target_ids": ["s1:A1"]},
    {"records": [{"id": "p1:l1", "text": "Energy"}], "target_ids": ["p1:l9"]},
])
def test_unusable_targets_fail_before_provider_call(payload):
    with pytest.raises(FactError, match="no usable"):
        provider_schema(payload)


def test_reference_schema_is_bounded():
    payload = {"records": [{"id": f"p1:l{i}", "text": "value"} for i in range(500)]}
    with pytest.raises(FactError, match="too many references"):
        provider_schema(payload)


@pytest.mark.parametrize("message,finish_reason", [
    ({"content": "{}"}, "stop"),
    ({"content": None}, "stop"),
    ({"content": "{}"}, "length"),
])
def test_malformed_provider_output_is_retryable(message, finish_reason):
    def handler(request):
        return httpx.Response(200, json={"choices": [
            {"finish_reason": finish_reason, "message": message}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(FactError) as error:
            call_openai(source("Energy 42 kWh"), "gpt-5-nano", "test-key", client)
    assert error.value.permanent is False


def test_pdf_smaller_segments_cover_each_line_once_with_context_separate():
    segments = build_manifest(source("\n".join(f"Value {i}" for i in range(105))))
    targets = [ref for segment in segments for ref in segment["target_ids"]]
    assert len(segments) == 3
    assert len(targets) == len(set(targets)) == 105
    assert all(len(segment["target_ids"]) <= PDF_TARGET_LINES for segment in segments)
    assert "p1:l40" in {r["id"] for r in segments[1]["records"]}
    assert "p1:l40" not in segments[1]["target_ids"]


def test_pdf_segments_do_not_mix_reading_blocks():
    document = source("")
    document["units"][0]["reading_blocks"] = [
        {"text": "Energy 42\nWater 12", "label": "Left", "bbox": [0, 0, 10, 10]},
        {"text": "Waste 3", "label": "Right", "bbox": [10, 0, 20, 10]}]
    segments = build_manifest(document)
    assert len(segments) == 2
    assert all(len({r["id"].rsplit(":l", 1)[0] for r in segment["records"]}) == 1 for segment in segments)
