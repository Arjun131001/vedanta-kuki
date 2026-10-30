"""Regression checks for source completeness and formatting failures."""
import json

import openpyxl
import pytest

from app.extraction import extract_source, json_value


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_values_are_rejected_before_json_serialization(value):
    with pytest.raises(ValueError, match="non-finite"):
        json_value(value)


def test_workbook_errors_are_preserved_with_cell_diagnostics(tmp_path):
    path = tmp_path / "errors.xlsx"
    book = openpyxl.Workbook()
    book.active["A1"] = "Amount"
    book.active["B1"] = "#DIV/0!"
    book.active["C1"] = "=1/0"
    book.active["D1"] = 12.5
    book.active["D1"].number_format = "0.00"
    book.save(path)
    source = extract_source(path, "xlsx")
    cells = {cell["coordinate"]: cell for cell in source["units"][0]["cells"]}
    assert cells["B1"]["value"] == "#DIV/0!"
    assert cells["C1"]["formula"] == "=1/0"
    assert cells["C1"]["value"] is None
    assert cells["D1"]["number_format"] == "0.00"
    assert source["summary"]["cell_count"] == 4
    assert any("cell B1" in warning for warning in source["summary"]["warnings"])
    assert any("cache(s) missing" in warning for warning in source["summary"]["warnings"])
    json.dumps(source, allow_nan=False)


def test_pdf_optional_layout_failure_preserves_text(tmp_path, monkeypatch):
    from test_intake import text_pdf
    import app.extraction as extraction

    path = tmp_path / "layout.pdf"
    path.write_bytes(text_pdf())

    def broken_layout(page):
        raise ValueError("Invalid crop geometry")

    monkeypatch.setattr(extraction, "narrative_columns", broken_layout)
    source = extract_source(path, "pdf")
    assert "Scope 1 emissions" in source["units"][0]["text"]
    assert source["units"][0]["reading_blocks"] is None
    assert any("Review reading order" in warning for warning in source["summary"]["warnings"])
