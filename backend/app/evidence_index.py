"""Stable, snapshot-bound references for model evidence."""
INDEX_VERSION = "source-index-v3"


def build_index(source):
    records = []
    for unit in source["units"]:
        index = unit["index"]
        if source["kind"] == "pdf":
            blocks = unit.get("reading_blocks")
            if blocks:
                for block_number, block in enumerate(blocks, 1):
                    for number, line in enumerate(block["text"].splitlines(), 1):
                        if line.strip():
                            records.append({"id": f"p{index}:b{block_number}:l{number}", "unit_index": index,
                                            "text": line, "cells": [], "block_label": block["label"], "bbox": block["bbox"]})
            else:
                for number, line in enumerate(unit["text"].splitlines(), 1):
                    if line.strip():
                        records.append({"id": f"p{index}:l{number}", "unit_index": index, "text": line, "cells": []})
        else:
            records.append({"id": f"s{index}:title", "unit_index": index, "text": unit["label"], "cells": [], "kind": "sheet_title"})
            for cell in unit["cells"]:
                is_formula = cell.get("type") == "f"
                value = cell.get("cached_value") if is_formula else cell.get("value")
                origin = ("formula_cache" if value is not None else "missing_formula_cache") if is_formula else "literal"
                record = {"id": f"s{index}:{cell['coordinate']}", "unit_index": index,
                          "text": str(value) if value is not None else None, "typed_value": value,
                          "value_origin": origin, "value_available": value is not None,
                          "cells": [cell["coordinate"]], "type": cell["type"],
                          "number_format": cell.get("number_format")}
                if is_formula:
                    record.update(formula=cell.get("formula"), cached_value=cell.get("cached_value"))
                records.append(record)
    return {"version": INDEX_VERSION, "kind": source["kind"], "records": records}
