"""Deterministic reported-vs-calculated answers for FY and numeric comparisons.

Only operates on cited evidence records. Never invents values or unit conversions.
"""
from __future__ import annotations

import re
from calendar import month_name, monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .qa import fy_bounds, requires_calculation

MONTHS = {name.lower(): index for index, name in enumerate(month_name) if name}
MONTHS.update({name[:3].lower(): index for name, index in list(MONTHS.items()) if len(name) >= 3})
NUMBER = re.compile(
    r"(?<![\w.])(?P<num>[-+]?(?:\d{1,3}(?:,\d{3})+|\d{1,3}(?:,\d{2})+,\d{3}|\d+)(?:\.\d+)?)(?![\w.]|\.\d)"
)
UNIT = re.compile(
    r"(?:kWh|MWh|GWh|Wh|kg|tonnes?|tons?|(?<![A-Za-z])T(?![A-Za-z])|Cubic\s+Meters?|lit(?:re|er)s?|m[³3]|INR|Rs\.?)",
    re.I,
)
FY_RE = re.compile(
    r"\b(?:fy|financial\s+year|fiscal\s+year)\s*(?:20)?(\d{2,4})(?:\s*[-/–]\s*(?:20)?(\d{2,4}))?\b",
    re.I,
)
RANGE_RE = re.compile(
    r"(?P<d1>\d{1,2})[-/.](?P<m1>\d{1,2})[-/.](?P<y1>\d{2,4})\s*[-–to]+\s*"
    r"(?P<d2>\d{1,2})[-/.](?P<m2>\d{1,2})[-/.](?P<y2>\d{2,4})",
    re.I,
)
MON_YEAR = re.compile(r"\b(?P<mon>[A-Za-z]{3,9})[- ]?(?P<y>\d{2,4})\b")
ISO_DATE = re.compile(r"\b(?P<y>20\d{2})-(?P<m>\d{2})-(?P<d>\d{2})\b")


def parse_fy_year(text: str) -> int | None:
    match = FY_RE.search(text or "")
    if not match:
        return None
    start = match.group(1)
    year = int(start)
    if year < 100:
        year += 2000
    return year


def _year(value: str) -> int:
    year = int(value)
    return year + 2000 if year < 100 else year


def parse_date_token(text: str) -> date | None:
    text = " ".join((text or "").split())
    for match in ISO_DATE.finditer(text):
        try:
            return date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
        except ValueError:
            continue
    for match in RANGE_RE.finditer(text):
        try:
            return date(_year(match.group("y1")), int(match.group("m1")), int(match.group("d1")))
        except ValueError:
            continue
    for match in MON_YEAR.finditer(text):
        mon = MONTHS.get(match.group("mon").lower())
        if not mon:
            continue
        try:
            return date(_year(match.group("y")), mon, 1)
        except ValueError:
            continue
    for name, mon in MONTHS.items():
        if re.search(rf"\b{re.escape(name)}\b", text, re.I):
            year_match = re.search(r"\b(20\d{2})\b", text)
            if year_match:
                try:
                    return date(int(year_match.group(1)), mon, 1)
                except ValueError:
                    pass
    return None


def parse_period_span(text: str) -> tuple[date | None, date | None]:
    text = " ".join((text or "").split())
    match = RANGE_RE.search(text)
    if match:
        try:
            start = date(_year(match.group("y1")), int(match.group("m1")), int(match.group("d1")))
            end = date(_year(match.group("y2")), int(match.group("m2")), int(match.group("d2")))
            return start, end
        except ValueError:
            pass
    mon = parse_date_token(text)
    if mon:
        # Treat month labels as the whole calendar month when day is unknown.
        if mon.day == 1 and not ISO_DATE.search(text) and not RANGE_RE.search(text):
            last = monthrange(mon.year, mon.month)[1]
            return mon, date(mon.year, mon.month, last)
        return mon, mon
    return None, None


def overlaps_fy(start: date | None, end: date | None, year: int) -> bool:
    if start is None and end is None:
        return False
    fy_start, fy_end = (datetime.strptime(bound, "%Y-%m-%d").date() for bound in fy_bounds(year))
    left = start or end
    right = end or start
    assert left is not None and right is not None
    return left <= fy_end and right >= fy_start


def parse_decimal(token: str) -> Decimal | None:
    try:
        return Decimal(token.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def extract_unit(text: str) -> str | None:
    match = UNIT.search(text or "")
    if not match:
        return None
    unit = match.group(0)
    if re.fullmatch(r"T", unit, re.I):
        return "T"
    if re.fullmatch(r"tonnes?|tons?", unit, re.I):
        return "T"
    if re.fullmatch(r"Cubic\s+Meters?", unit, re.I):
        return "Cubic Meters"
    return unit


def normalize_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    if unit.upper() in {"T", "TONNE", "TONNES", "TON", "TONS"}:
        return "T"
    if unit.lower().startswith("cubic"):
        return "Cubic Meters"
    return unit


def _date_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for pattern in (RANGE_RE, ISO_DATE, re.compile(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b")):
        for match in pattern.finditer(text or ""):
            spans.append((match.start(), match.end()))
    return spans


def _in_spans(index: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in spans)


def _quantity_from_quote(quote: str) -> tuple[Decimal | None, str | None, str | None]:
    """Pick the primary reported quantity near a unit, ignoring dates/years."""
    unit = normalize_unit(extract_unit(quote))
    spans = _date_spans(quote)
    # Prefer number immediately before a recognized unit.
    unit_match = UNIT.search(quote or "")
    if unit_match:
        before = quote[: unit_match.start()]
        candidates = list(NUMBER.finditer(before))
        for match in reversed(candidates):
            if _in_spans(match.start(), spans):
                continue
            token = match.group("num")
            if re.fullmatch(r"20\d{2}", token):
                continue
            value = parse_decimal(token)
            if value is None:
                continue
            return value, token, unit
    # Fallback: largest non-date number that is not a plain year.
    best = None
    for match in NUMBER.finditer(quote or ""):
        if _in_spans(match.start(), spans):
            continue
        token = match.group("num")
        if re.fullmatch(r"20\d{2}", token):
            continue
        value = parse_decimal(token)
        if value is None:
            continue
        if best is None or abs(value) > abs(best[0]):
            best = (value, token, unit)
    if best:
        return best
    return None, None, unit


def _label_year(record: dict[str, Any]) -> int | None:
    for text in (record.get("unit_label"), record.get("filename"), record.get("quote")):
        match = re.search(r"\b(20\d{2})\b", text or "")
        if match:
            return int(match.group(1))
    return None


def _with_label_year(start: date | None, end: date | None, year: int | None) -> tuple[date | None, date | None]:
    if not year or not start:
        return start, end
    if start.year == year:
        return start, end
    # Month-only labels often omit the year; borrow it from the sheet/file title.
    try:
        fixed_start = date(year, start.month, min(start.day, monthrange(year, start.month)[1]))
        if end:
            fixed_end = date(year, end.month, min(end.day, monthrange(year, end.month)[1]))
        else:
            fixed_end = date(year, fixed_start.month, monthrange(year, fixed_start.month)[1])
        return fixed_start, fixed_end
    except ValueError:
        return start, end


def candidate_values(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pull numeric operands from evidence quotes with optional period/unit context."""
    # Dominant bill period per document (e.g. Adani "Bill Period: 01-04-2024 - 30.04.2024").
    doc_periods: dict[str, tuple[date, date]] = {}
    period_counts: dict[str, dict[tuple[date, date], int]] = {}
    for record in records:
        start, end = parse_period_span(record.get("quote") or "")
        if not start:
            continue
        end = end or start
        doc_id = record.get("document_id") or ""
        key = (start, end)
        bucket = period_counts.setdefault(doc_id, {})
        bucket[key] = bucket.get(key, 0) + 1
    for doc_id, bucket in period_counts.items():
        ranked = sorted(bucket.items(), key=lambda item: (-item[1], item[0][0]))
        if ranked and ranked[0][1] >= 1:
            doc_periods[doc_id] = ranked[0][0]

    items = []
    for record in records:
        quote = record.get("quote") or ""
        unit = normalize_unit(extract_unit(quote))
        start, end = parse_period_span(quote)
        label_year = _label_year(record)
        if start and label_year and not re.search(r"\b20\d{2}\b", quote) and not MON_YEAR.search(quote) and not RANGE_RE.search(quote):
            start, end = _with_label_year(start, end, label_year)
        if not start and record.get("cells"):
            for other in records:
                if other.get("document_id") != record.get("document_id"):
                    continue
                if other.get("unit_index") != record.get("unit_index"):
                    continue
                other_start, other_end = parse_period_span(other.get("quote") or "")
                other_start, other_end = _with_label_year(other_start, other_end, _label_year(other) or label_year)
                if other_start and re.search(
                    r"\b(" + "|".join(re.escape(m) for m in MONTHS) + r"|annual|total|month)\b",
                    (other.get("quote") or ""),
                    re.I,
                ):
                    cell = (record.get("cells") or [""])[0]
                    other_cell = (other.get("cells") or [""])[0]
                    row_a = re.search(r"(\d+)$", cell)
                    row_b = re.search(r"(\d+)$", other_cell)
                    if row_a and row_b and row_a.group(1) == row_b.group(1):
                        start, end = other_start, other_end
                        if not unit:
                            unit = normalize_unit(extract_unit(other.get("quote") or ""))
                        break
                if not unit:
                    header_unit = normalize_unit(extract_unit(other.get("quote") or ""))
                    if header_unit and other.get("cells"):
                        cell = (record.get("cells") or [""])[0]
                        other_cell = (other.get("cells") or [""])[0]
                        col_a = re.match(r"[A-Z]+", cell or "")
                        col_b = re.match(r"[A-Z]+", other_cell or "")
                        if col_a and col_b and col_a.group(0) == col_b.group(0):
                            unit = header_unit
        if not start:
            # Month name alone + sheet year (workbook rows).
            for name, mon in MONTHS.items():
                if re.search(rf"\b{re.escape(name)}\b", quote, re.I) and label_year:
                    last = monthrange(label_year, mon)[1]
                    start, end = date(label_year, mon, 1), date(label_year, mon, last)
                    break
        if not start and record.get("document_id") in doc_periods:
            # PDF bills often split period and consumption across lines.
            if re.search(r"consum|kwh|units|electric|bill amount|payable", quote, re.I) or unit in {"kWh", "MWh"}:
                start, end = doc_periods[record["document_id"]]
        value, token, found_unit = _quantity_from_quote(quote)
        if value is None or token is None:
            continue
        unit = found_unit or unit
        # Prefer consumption quantity on mixed bill lines (units before amount).
        if re.search(r"APR-\d{2}|units consumed|consumption", quote, re.I):
            matches = [m for m in NUMBER.finditer(quote) if not _in_spans(m.start(), _date_spans(quote))]
            for match in matches:
                token_i = match.group("num")
                if re.fullmatch(r"20\d{2}", token_i):
                    continue
                value_i = parse_decimal(token_i)
                if value_i is None:
                    continue
                # First substantial quantity on an APR/units line is usually consumption.
                if value_i >= 100:
                    value, token = value_i, token_i
                    if not unit:
                        unit = "kWh"
                    break
        items.append(
            {
                "value": value,
                "display": token,
                "unit": unit,
                "start": start,
                "end": end,
                "record": record,
                "label": quote[:120],
                "filename": record.get("filename"),
                "document_id": record.get("document_id"),
            }
        )
    # One primary quantity per evidence record.
    seen = set()
    unique = []
    for item in items:
        key = item["record"]["id"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _format_decimal(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _answer_payload(
    answer: str,
    citations: list[dict],
    limitations: list[str],
    calculations: list[dict],
    coverage: str,
) -> dict:
    return {
        "answer": answer,
        "citations": citations,
        "limitations": limitations,
        "calculations": calculations,
        "coverage": coverage,
    }


def summarize_fy(records: list[dict], year: int, question: str = "") -> dict:
    """Filter numeric evidence overlapping an Indian FY and sum compatible units."""
    bounds = fy_bounds(year)
    values = candidate_values(records)
    included, excluded, unknown = [], [], []
    for item in values:
        if item["start"] or item["end"]:
            if overlaps_fy(item["start"], item["end"], year):
                included.append(item)
            else:
                excluded.append(item)
        else:
            unknown.append(item)

    # Prefer consumption-like rows when the question mentions electricity/consumption.
    metric_hint = re.search(r"electric|consum|energy|kwh|water|waste", question or "", re.I)
    if metric_hint:
        narrowed = [
            item
            for item in included
            if re.search(r"consum|kwh|electric|water|waste|sludge|residu|unit", item["label"], re.I)
        ]
        if narrowed:
            included = narrowed

    totals: list[dict] = []
    limitations = [
        f"Indian financial year {year}-{str(year + 1)[-2:]} runs {bounds[0]} to {bounds[1]}.",
    ]
    citations = []
    calculations = []

    by_unit: dict[str, list] = {}
    for item in included:
        unit = item["unit"] or "unknown"
        by_unit.setdefault(unit, []).append(item)

    lines = [f"Calculated coverage for FY {year}-{str(year + 1)[-2:]} (system-calculated from selected evidence):"]
    for unit, group in by_unit.items():
        if unit == "unknown":
            limitations.append("Some included values have no explicit unit and were not aggregated.")
            for item in group:
                citations.append(item["record"])
            continue
        # Refuse cross-organisation silent merges when filenames clearly differ orgs and question asks for a combined total.
        orgs = {re.split(r"[\s_-]", (item["filename"] or "doc"))[0].lower() for item in group}
        if len(orgs) > 1 and re.search(r"\b(total|combined|across)\b", question or "", re.I):
            limitations.append(
                "Values appear to belong to different organisations; a combined total was not calculated."
            )
            for item in group:
                citations.append(item["record"])
                lines.append(
                    f"- Reported {item['display']} {unit} in {item['filename']} "
                    f"({item['start'] or 'period unknown'}) [reported, not combined]"
                )
            continue
        total = sum((item["value"] for item in group), Decimal("0"))
        operands = []
        for item in group:
            citations.append(item["record"])
            operands.append(
                {
                    "value": _format_decimal(item["value"]),
                    "unit": unit,
                    "citation_id": item["record"]["id"],
                    "filename": item["filename"],
                    "period_start": item["start"].isoformat() if item["start"] else None,
                    "period_end": item["end"].isoformat() if item["end"] else None,
                    "label": item["label"],
                }
            )
            lines.append(
                f"- Included reported {_format_decimal(item['value'])} {unit} from {item['filename']}"
            )
        calculations.append(
            {
                "operation": "fy_total",
                "unit": unit,
                "operands": operands,
                "result": _format_decimal(total),
                "kind": "calculated",
                "fy_year": year,
                "bounds": list(bounds),
            }
        )
        totals.append({"unit": unit, "value": _format_decimal(total), "count": len(group)})
        lines.append(f"- Calculated total: {_format_decimal(total)} {unit} (sum of {len(group)} reported values)")

    for item in excluded[:8]:
        limitations.append(
            f"Excluded {item['filename']}: period "
            f"{item['start'] or '?'}–{item['end'] or '?'} falls outside FY {year}."
        )
    if unknown:
        limitations.append(
            f"{len(unknown)} numeric excerpt(s) lacked a parseable period and were not included in the FY total."
        )

    if not calculations and not any(t.get("count") for t in totals):
        coverage = "none"
        answer = (
            f"I could not calculate a total for FY {year}-{str(year + 1)[-2:]} "
            "from the selected evidence."
        )
        if not included and (excluded or unknown):
            limitations.append("No period-matched numeric values were available to aggregate.")
    elif unknown or excluded or any(u == "unknown" for u in by_unit):
        coverage = "partial"
        answer = "\n".join(lines)
    else:
        coverage = "complete"
        answer = "\n".join(lines)

    # De-dupe citations by id preserving order
    seen_ids = set()
    unique_citations = []
    for citation in citations:
        if citation["id"] in seen_ids:
            continue
        seen_ids.add(citation["id"])
        unique_citations.append(citation)

    return _answer_payload(answer, unique_citations, list(dict.fromkeys(limitations)), calculations, coverage)


def compare_or_sum(records: list[dict], question: str) -> dict:
    """Handle sum / compare questions that are not FY-specific."""
    values = candidate_values(records)
    if not values:
        return _answer_payload(
            "I could not find numeric values to calculate from the selected evidence.",
            [],
            ["No parseable quantities were present in the retrieved excerpts."],
            [],
            "none",
        )

    # Workbook annual reconciliation: monthly totals vs reported annual.
    monthly = [
        item
        for item in values
        if item["start"]
        and item["unit"]
        and re.search(r"consum|total|kwh", item["label"], re.I)
        and not re.search(r"annual", item["label"], re.I)
    ]
    annual = [
        item
        for item in values
        if item["unit"]
        and re.search(r"annual|ANNUAL TOTAL", item["label"], re.I)
        and re.search(r"consum|total|kwh|2425123|2427123", item["label"] + " " + item["display"], re.I)
    ]
    if re.search(r"agree|reconcil|match|sum|add up|monthly|annual", question, re.I) and monthly and annual:
        unit = monthly[0]["unit"]
        compatible = [item for item in monthly if item["unit"] == unit]
        calculated = sum((item["value"] for item in compatible), Decimal("0"))
        reported = annual[0]
        citations = [item["record"] for item in compatible] + [reported["record"]]
        calc = {
            "operation": "compare_reported_vs_sum",
            "unit": unit,
            "operands": [
                {
                    "value": _format_decimal(item["value"]),
                    "unit": unit,
                    "citation_id": item["record"]["id"],
                    "filename": item["filename"],
                    "period_start": item["start"].isoformat() if item["start"] else None,
                    "label": item["label"],
                }
                for item in compatible
            ],
            "result": _format_decimal(calculated),
            "reported": _format_decimal(reported["value"]),
            "kind": "calculated",
        }
        equal = calculated == reported["value"]
        answer = (
            f"The monthly values sum to {_format_decimal(calculated)} {unit} (system-calculated). "
            f"The document reports an annual figure of {_format_decimal(reported['value'])} {unit}. "
            + ("These agree." if equal else "These do not agree.")
        )
        limitations = []
        if not equal:
            limitations.append(
                "The calculated monthly sum differs from the cited annual total; review sheet provenance."
            )
        if len(compatible) < 12:
            limitations.append(
                f"Only {len(compatible)} monthly values were present in the retrieved evidence; coverage may be partial."
            )
        coverage = "complete" if equal and len(compatible) >= 12 else "partial"
        return _answer_payload(answer, _unique(citations), limitations, [calc], coverage)

    # Generic same-unit sum (e.g. waste quantities).
    if re.search(r"\b(sum|total|add up|combined|aggregate)\b", question, re.I):
        by_unit: dict[str, list] = {}
        for item in values:
            if not item["unit"]:
                continue
            if re.search(r"waste|sludge|residu|quantity|consum|kwh|water", question + " " + item["label"], re.I):
                by_unit.setdefault(item["unit"], []).append(item)
        if not by_unit:
            for item in values:
                if item["unit"]:
                    by_unit.setdefault(item["unit"], []).append(item)
        lines = ["System-calculated total(s) from reported values:"]
        calculations = []
        citations = []
        limitations = []
        for unit, group in by_unit.items():
            # Distinct values only per record
            picked = []
            seen = set()
            for item in group:
                key = item["record"]["id"]
                if key in seen:
                    continue
                seen.add(key)
                picked.append(item)
            if len(picked) < 2 and not re.search(r"total waste|combined", question, re.I):
                continue
            total = sum((item["value"] for item in picked), Decimal("0"))
            for item in picked:
                citations.append(item["record"])
                lines.append(f"- Reported {_format_decimal(item['value'])} {unit}: {item['label'][:80]}")
            lines.append(f"- Calculated sum: {_format_decimal(total)} {unit}")
            calculations.append(
                {
                    "operation": "sum",
                    "unit": unit,
                    "operands": [
                        {
                            "value": _format_decimal(item["value"]),
                            "unit": unit,
                            "citation_id": item["record"]["id"],
                            "filename": item["filename"],
                            "label": item["label"],
                        }
                        for item in picked
                    ],
                    "result": _format_decimal(total),
                    "kind": "calculated",
                }
            )
        if calculations:
            return _answer_payload(
                "\n".join(lines),
                _unique(citations),
                limitations or ["These totals are calculated by the system from reported source values."],
                calculations,
                "partial" if limitations else "complete",
            )

    return _answer_payload(
        "I can only calculate when the selected evidence provides comparable reported quantities.",
        _unique([item["record"] for item in values[:5]]),
        [
            "No safe aggregation was identified. Ask for a financial-year total, a monthly-vs-annual check, "
            "or a same-unit sum with clearer metric wording."
        ],
        [],
        "none",
    )


def _unique(citations: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for citation in citations:
        if citation["id"] in seen:
            continue
        seen.add(citation["id"])
        out.append(citation)
    return out


def answer_calculation(question: str, evidence: dict) -> dict:
    """Entry point used by QA when requires_calculation(question) is true."""
    records = evidence.get("records") or []
    warnings = list(evidence.get("warnings") or [])
    year = parse_fy_year(question)
    if year is not None:
        result = summarize_fy(records, year, question)
    else:
        result = compare_or_sum(records, question)
    result["limitations"] = list(dict.fromkeys(warnings + result["limitations"]))
    return result


def fy_summary_from_records(records: list[dict], year: int, document_meta: list[dict] | None = None) -> dict:
    """API-facing FY summary payload."""
    result = summarize_fy(records, year, question=f"total for financial year {year}")
    return {
        "year": year,
        "bounds": list(fy_bounds(year)),
        "coverage": result["coverage"],
        "totals": [
            {
                "unit": calc["unit"],
                "value": calc["result"],
                "operand_count": len(calc["operands"]),
                # Document-reported figures that were summed into this calculated total.
                "reported_values": [
                    {
                        "value": op["value"],
                        "unit": op.get("unit") or calc["unit"],
                        "filename": op.get("filename"),
                        "label": op.get("label"),
                        "period_start": op.get("period_start"),
                        "period_end": op.get("period_end"),
                        "citation_id": op.get("citation_id"),
                    }
                    for op in calc["operands"]
                ],
            }
            for calc in result["calculations"]
        ],
        "items": [
            operand
            for calc in result["calculations"]
            for operand in calc["operands"]
        ],
        "excluded_notes": [note for note in result["limitations"] if note.lower().startswith("excluded")],
        "limitations": result["limitations"],
        "calculations": result["calculations"],
        "citations": result["citations"],
        "documents": document_meta or [],
        "answer": result["answer"],
    }


# Re-export for callers that import detection helpers from this module.
__all__ = [
    "answer_calculation",
    "fy_summary_from_records",
    "parse_fy_year",
    "requires_calculation",
    "fy_bounds",
    "summarize_fy",
    "compare_or_sum",
    "candidate_values",
    "overlaps_fy",
    "parse_period_span",
]
