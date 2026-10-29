from decimal import Decimal

from app.calculations import (
    answer_calculation,
    compare_or_sum,
    fy_bounds,
    overlaps_fy,
    parse_fy_year,
    parse_period_span,
    summarize_fy,
)
from app.qa import answer_question, requires_calculation
from datetime import date


def test_fy_bounds_and_parsing():
    assert fy_bounds(2024) == ("2024-04-01", "2025-03-31")
    assert parse_fy_year("total for financial year 2024") == 2024
    assert parse_fy_year("FY 24-25 electricity") == 2024
    start, end = parse_period_span("Bill Period: 01-04-2024 - 30.04.2024")
    assert start == date(2024, 4, 1) and end == date(2024, 4, 30)
    assert overlaps_fy(date(2024, 4, 1), date(2024, 4, 30), 2024)
    assert not overlaps_fy(date(2025, 12, 1), date(2025, 12, 31), 2024)


def test_fy_total_includes_matching_excludes_others():
    evidence = {
        "records": [
            {
                "id": "a:1",
                "document_id": "a",
                "filename": "Adani commercial electricity bill.pdf",
                "quote": "Bill Period: 01-04-2024 - 30.04.2024 Consumption 47407 kWh",
                "cells": [],
                "unit_index": 1,
            },
            {
                "id": "b:1",
                "document_id": "b",
                "filename": "BESCOM Commercial Electricity Bill.pdf",
                "quote": "Billing Period 01-06-2024 - 01-07-2024 Consumption 63000 kWh",
                "cells": [],
                "unit_index": 1,
            },
            {
                "id": "w:1",
                "document_id": "w",
                "filename": "water_bill_invoice.pdf",
                "quote": "Units Consumed (December 2025): 2,321 Cubic Meters",
                "cells": [],
                "unit_index": 1,
            },
        ],
        "warnings": [],
    }
    # Different organisations: combined total refused
    combined = answer_calculation("What is the total electricity for financial year 2024?", evidence)
    assert combined["calculations"] == [] or "different organisations" in " ".join(combined["limitations"]).lower()
    # Same org style single-doc still works
    single = summarize_fy([evidence["records"][0]], 2024, "total electricity financial year 2024")
    assert single["coverage"] in ("complete", "partial")
    assert single["calculations"]
    assert single["calculations"][0]["result"] == "47407"


def test_monthly_vs_annual_comparison():
    records = []
    months = [
        ("January", "2026-01-01", "200823"),
        ("February", "2026-02-01", "181700"),
    ]
    for name, iso, value in months:
        records.append(
            {
                "id": f"x:{name}",
                "document_id": "x",
                "filename": "Annual Electricity Consumption.xlsx",
                "quote": f"{name} Total Consumption (kWh) {value}",
                "cells": ["F3"] if name == "January" else ["F4"],
                "unit_index": 1,
            }
        )
    records.append(
        {
            "id": "x:annual",
            "document_id": "x",
            "filename": "Annual Electricity Consumption.xlsx",
            "quote": "ANNUAL TOTAL Total Consumption (kWh) 382523",
            "cells": ["F16"],
            "unit_index": 1,
        }
    )
    # Force period on months via quote month+year
    records[0]["quote"] = "January 2026 Total Consumption (kWh) 200823"
    records[1]["quote"] = "February 2026 Total Consumption (kWh) 181700"
    result = compare_or_sum(records, "Do the workbook monthly values and annual summaries agree?")
    assert result["calculations"]
    assert result["calculations"][0]["operation"] == "compare_reported_vs_sum"
    assert Decimal(result["calculations"][0]["result"]) == Decimal("382523")
    assert "agree" in result["answer"].lower()


def test_waste_sum():
    evidence = {
        "records": [
            {"id": "f:1", "document_id": "f", "filename": "form 3 filled.docx.pdf", "quote": "ETP sludge 1.0 T", "cells": [], "unit_index": 1},
            {"id": "f:2", "document_id": "f", "filename": "form 3 filled.docx.pdf", "quote": "residues containing oil 0.4 T", "cells": [], "unit_index": 1},
        ],
        "warnings": [],
    }
    result = answer_calculation("What is the total waste quantity recorded? Calculate the sum.", evidence)
    assert result["calculations"]
    assert result["calculations"][0]["result"] == "1.4"
    assert result["calculations"][0]["kind"] == "calculated"


def test_answer_question_uses_calculator_without_provider():
    evidence = {
        "records": [
            {
                "id": "a:1",
                "document_id": "a",
                "filename": "Adani.pdf",
                "quote": "Bill Period: 01-04-2024 - 30.04.2024 Consumption 100 kWh",
                "cells": [],
                "unit_index": 1,
            }
        ],
        "warnings": [],
    }
    assert requires_calculation("What is the total for financial year 2024?")
    result = answer_question("What is the total for financial year 2024?", evidence, [], "model", "key", client=None)
    assert result["calculations"]
    assert "not available yet" not in (result["limitations"][0] if result["limitations"] else "")
