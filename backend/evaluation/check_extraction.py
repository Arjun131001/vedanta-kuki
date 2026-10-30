"""Check extraction probes against local sources and persisted API results.

No provider calls. Run from backend: python evaluation/check_extraction.py DATASET_DIR
Output is saved under ignored tmp/ by default because results may contain bill data.
"""

import argparse
import json
import logging
import re
from decimal import Decimal
from pathlib import Path

import httpx
import openpyxl
import pdfplumber


def normalized(text):
    return " ".join(str(text).split())


def numbers(text):
    return {Decimal(value.replace(",", "")) for value in re.findall(
        r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w.])", str(text))}


def verify_source(case, directory):
    source = case["source"]
    path = directory / case["document"]
    if "cell" in source:
        book = openpyxl.load_workbook(path, data_only=True, read_only=True)
        try:
            value = book[source["sheet"]][source["cell"]].value
            return Decimal(str(value)) == Decimal(case["value"])
        finally:
            book.close()
    with pdfplumber.open(path) as pdf:
        if case["kind"] == "absence":
            return all(1 <= page <= len(pdf.pages) for page in source["pages_reviewed"])
        text = normalized(pdf.pages[source["page"] - 1].extract_text() or "")
        return all(normalized(source[key]) in text for key in ("text", "additional_text") if key in source)


def matches(case, fact, units):
    label = (fact.get("label", "") + " " + fact.get("source_label", "")).casefold()
    if not any(term in label for term in case.get("label_terms", [])):
        return False
    value = str(fact.get("value", ""))
    if case["kind"] == "numeric":
        if Decimal(case["value"]) not in numbers(value):
            return False
    elif case["value"].casefold() not in value.casefold():
        return False
    evidence = fact.get("evidence") or {}
    if "page" in case["source"]:
        return evidence.get("unit_index") in case.get("acceptable_pages", [case["source"]["page"]])
    # A workbook value must retain the expected value cell, not just repeat its number.
    return (units.get(evidence.get("unit_index")) == case["source"]["sheet"]
            and case["source"]["cell"] in evidence.get("cells", []))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--api-url", default="http://127.0.0.1:5174")
    parser.add_argument("--output", type=Path, default=Path("../tmp/extraction-probes.json"))
    args = parser.parse_args()
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    cases = json.loads(Path(__file__).with_name("extraction_expectations.json").read_text())["cases"]
    rows = []
    with httpx.Client(base_url=args.api_url, timeout=30) as client:
        response = client.get("/api/documents")
        response.raise_for_status()
        documents = {doc["filename"]: doc for doc in response.json()["documents"]}
        outputs, source_units = {}, {}
        for case in cases:
            verified = verify_source(case, args.dataset)
            if not verified:
                raise ValueError(f"Expectation source check failed: {case['id']}")
            doc = documents.get(case["document"])
            if not doc:
                rows.append({"id": case["id"], "status": "document_missing", "source_checked": True})
                continue
            if doc["id"] not in outputs:
                result = client.get(f"/api/documents/{doc['id']}/facts")
                result.raise_for_status()
                outputs[doc["id"]] = result.json()
                sources = client.get(f"/api/documents/{doc['id']}/sources")
                sources.raise_for_status()
                source_units[doc["id"]] = {unit["index"]: unit["label"] for unit in sources.json()["units"]}
            job = outputs[doc["id"]]
            output = (job.get("output") or {}).get("result") or {}
            accepted = output.get("facts", [])
            review = output.get("review_candidates", [])
            if job["status"] != "ready":
                status = "not_completed"
            elif case["kind"] == "absence":
                labels = " ".join(str(f.get("label", "")) for f in accepted).casefold()
                status = "unsupported_addition" if any(term in labels for term in case["forbidden_label_terms"]) else "no_explicit_fabrication_detected"
            else:
                status = "matched" if any(matches(case, fact, source_units[doc["id"]]) for fact in accepted) else (
                    "needs_review" if any(matches(case, fact, source_units[doc["id"]]) for fact in review) else "missing")
            rows.append({"id": case["id"], "status": status, "source_checked": True,
                         "job_status": job["status"], "source": case["source"]})
    counts = {status: sum(row["status"] == status for row in rows) for status in sorted({row["status"] for row in rows})}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"scope": "Extraction probes, not semantic QA evaluation; matches require manual relationship review.",
                                     "counts": counts, "cases": rows}, indent=2), encoding="utf-8")
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
