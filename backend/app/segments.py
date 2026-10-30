from collections import defaultdict
import json
import math
import re
from .evidence_index import build_index
from .table_review import UNIT_HEADER

SEGMENT_VERSION = "coverage-segments-v3"
PDF_TARGET_LINES = 40
MAX_SEGMENT_CHARS = 80000
CELL = re.compile(r"^([A-Z]+)([1-9]\d*)$")
NUMBER = re.compile(r"^[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?$")


def _is_numeric_target(record):
    """Prefer quantity cells as model targets; labels stay context-only."""
    if record.get("kind") == "sheet_title" or not record.get("value_available", True):
        return False
    if record.get("type") == "s":
        return False
    value = record.get("typed_value")
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    if isinstance(value, (int, float)):
        return True
    text = record.get("text")
    return isinstance(text, str) and bool(NUMBER.fullmatch(text.strip()))


def _header_row_numbers(rows):
    """Keep the first two rows and any row that carries a unit-bearing header."""
    selected = set(sorted(rows)[:2])
    for row_number, records in rows.items():
        for record in records:
            text = record.get("text")
            if isinstance(text, str) and UNIT_HEADER.search(text):
                selected.add(row_number)
                break
    return sorted(selected)


def build_manifest(source):
    index = build_index(source)
    units = defaultdict(list)
    for record in index["records"]:
        units[record["unit_index"]].append(record)
    segments = []
    for unit in source["units"]:
        records = units[unit["index"]]
        if source["kind"] == "pdf":
            # Keep independent reading blocks separate and leave room below the
            # 60-fact cap for lines that report multiple quantities.
            groups = []
            for record in records:
                block = record["id"].rsplit(":l", 1)[0]
                if (not groups or len(groups[-1]) >= PDF_TARGET_LINES
                        or groups[-1][0]["id"].rsplit(":l", 1)[0] != block):
                    groups.append([])
                groups[-1].append(record)
            if not groups:
                continue  # Blank pages are captured as source warnings, not model targets.
            start = 0
            for number, group in enumerate(groups):
                block = group[0]["id"].rsplit(":l", 1)[0]
                context = [r for r in records[max(0, start-7):start] if r["id"].rsplit(":l", 1)[0] == block]
                after = [r for r in records[start+len(group):start+len(group)+7] if r["id"].rsplit(":l", 1)[0] == block]
                segments.append({"id": f"p{unit['index']}-{number+1}", "kind": "pdf", "records": context + group + after,
                                 "target_ids": [r["id"] for r in group]})
                start += len(group)
        else:
            title = [r for r in records if r.get("kind") == "sheet_title"]
            rows = defaultdict(list)
            for record in records:
                if record.get("kind") != "sheet_title":
                    match = re.search(r"(\d+)$", record["id"])
                    rows[int(match.group(1))].append(record)
            if not rows:
                continue
            header_rows = _header_row_numbers(rows)
            headers = [record for row in header_rows for record in rows[row]]
            ordered = sorted(rows)
            for number in range(0, len(ordered), 4):
                selected = ordered[number:number+4]
                row_records = [r for row in selected for r in rows[row]]
                # Model targets: numeric quantities only. Labels/headers remain context.
                targets = [r for r in row_records if _is_numeric_target(r)]
                if not targets:
                    # Fall back so sparse label-only windows are still covered once.
                    targets = row_records
                target_set = {r["id"] for r in targets}
                # Always keep sheet title, unit-bearing headers, and same-row labels in context.
                context = title + [r for r in headers if r["id"] not in target_set]
                for record in row_records:
                    if record["id"] in target_set:
                        continue
                    match = CELL.fullmatch(record["cells"][0]) if record.get("cells") else None
                    # Keep non-target cells from the window (row labels, remarks) as context.
                    if match or record["id"] not in {item["id"] for item in context}:
                        context.append(record)
                # Deduplicate context while preserving order.
                seen = set()
                ordered_context = []
                for record in context:
                    if record["id"] in seen or record["id"] in target_set:
                        continue
                    seen.add(record["id"])
                    ordered_context.append(record)
                segments.append({
                    "id": f"s{unit['index']}-{number//4+1}",
                    "kind": "xlsx",
                    "records": ordered_context + targets,
                    "target_ids": [r["id"] for r in targets],
                    "extraction_hints": {
                        "prefer_numeric_targets_under_unit_headers": True,
                        "use_header_text_as_source_label": True,
                        "max_facts_suggested": 25,
                        "do_not_invent_ids": True,
                    },
                })
    for segment in segments:
        if len(json.dumps(segment, ensure_ascii=False, separators=(",", ":"))) > MAX_SEGMENT_CHARS:
            raise ValueError("A source segment exceeds the safe request size; nothing was submitted.")
    return segments
