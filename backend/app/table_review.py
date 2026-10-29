"""Deterministic workbook facts from column headers; never invent computed totals."""
import math
import re

CELL = re.compile(r"^([A-Z]+)([1-9]\d*)$")
NUMBER = re.compile(r"^[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?$")
UNIT_HEADER = re.compile(
    r"(?:\b(?:kwh|mwh|gwh|wh|kva|kg|tonnes?|tons?|litres?|liters?|m3|m³|inr|usd|eur|rs|co2|co₂)\b|%|₹|\$)",
    re.IGNORECASE,
)
MONTH_OR_PERIOD = re.compile(
    r"^(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|"
    r"q[1-4]|fy\s*\d{2,4}(?:\s*[-–]\s*\d{2,4})?|\d{4})$",
    re.IGNORECASE,
)


def _header_above(cells, column, row, unit_index, records):
    """Find the nearest unit-bearing text header in the same column above the value."""
    for row_number in range(row - 1, 0, -1):
        header_cell = cells.get(f"{column}{row_number}")
        if not header_cell or header_cell.get("type") == "f":
            continue
        header_text = header_cell.get("value")
        header_id = f"s{unit_index}:{column}{row_number}"
        if not (isinstance(header_text, str) and re.search(r"[A-Za-z]", header_text)):
            continue
        if not UNIT_HEADER.search(header_text):
            continue
        if header_id not in records:
            continue
        return header_id, header_cell, header_text
    return None


def table_review_candidates(source, segment, proposed_facts, accepted_value_refs=None):
    """Map numeric cells under unit-bearing headers.

    Rejected model proposals do not block these structural facts. Only value
    refs already accepted as Checked are skipped to avoid duplicates.
    """
    if source["kind"] != "xlsx" or not segment:
        return []
    units = {unit["index"]: unit for unit in source["units"]}
    records = {record["id"]: record for record in segment["records"]}
    blocked = set(accepted_value_refs or ())
    candidates = []
    for ref in segment["target_ids"]:
        if ref in blocked or ref not in records:
            continue
        record = records[ref]
        if not record.get("cells"):
            continue
        unit = units.get(record["unit_index"])
        if not unit:
            continue
        cells = {cell["coordinate"]: cell for cell in unit["cells"]}
        coordinate = record["cells"][0]
        match = CELL.fullmatch(coordinate)
        if not match:
            continue
        column, row = match.group(1), int(match.group(2))
        cell = cells.get(coordinate)
        if not cell:
            continue
        value = cell.get("cached_value") if cell.get("type") == "f" else cell.get("value")
        if value is None or isinstance(value, bool) or (isinstance(value, float) and not math.isfinite(value)):
            continue
        text = str(value)
        if not NUMBER.fullmatch(text.strip()):
            continue
        header = _header_above(cells, column, row, unit["index"], records)
        if not header:
            continue
        header_id, header_cell, header_text = header
        value_evidence = {"unit_index": unit["index"], "quote": text, "cells": [coordinate],
                          "reference_id": ref, "reference_ids": [ref]}
        context = [{"unit_index": unit["index"], "quote": header_text, "cells": [header_cell["coordinate"]],
                    "reference_id": header_id, "reference_ids": [header_id]}]
        period = None
        # Exact first-column row descriptor as period when it is clearly a month/quarter/year label.
        row_cell = cells.get(f"A{row}")
        row_id = f"s{unit['index']}:A{row}"
        if row_cell and row_id in records and isinstance(row_cell.get("value"), str) and row_id != ref:
            row_text = row_cell["value"].strip()
            context.append({"unit_index": unit["index"], "quote": row_text, "cells": [row_cell["coordinate"]],
                            "reference_id": row_id, "reference_ids": [row_id]})
            if MONTH_OR_PERIOD.fullmatch(row_text):
                period = row_text
        candidates.append({
            "label": header_text,
            "source_label": header_text,
            "value": text,
            "organization": None,
            "unit": None,
            "period": period,
            "currency": None,
            "origin": "document_reported",
            "evidence": value_evidence,
            "context_evidence": context,
            "method": "deterministic_table_fact",
            "association": "column_header_supported",
        })
    return candidates
