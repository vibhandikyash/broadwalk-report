# backend/tests/test_extract_yardi_budget.py
import pytest

from app.classify.classifier import DocType
from app.extract.base import ExtractionError
from app.extract.yardi_budget import extract
from app.extract.yardi_common import parse_period, walk_lines
from tests.helpers import BUDGET_ROWS, sheet_part


def test_parse_period():
    assert parse_period("Period = Apr 2026-Jun 2026") == {"start": "2026-04-01", "end": "2026-06-30", "label": "Apr 2026 - Jun 2026"}
    assert parse_period("Period = January 2026 - March 2026")["end"] == "2026-03-31"
    assert parse_period("no period here") is None


def test_budget_extractor_lines_sections_and_period():
    ex = extract(sheet_part(BUDGET_ROWS, DocType.YARDI_BUDGET_COMPARISON))
    d = ex.data
    assert d["period"] == {"start": "2026-04-01", "end": "2026-06-30", "label": "Apr 2026 - Jun 2026"}
    assert d["property_ref"] == "45726"
    assert d["columns"] == ["annual_budget", "ptd_actual", "ptd_budget", "ytd_actual", "ytd_budget"]
    by = {ln["norm"]: ln for ln in d["lines"] if not ln["unlabeled"]}
    gpr = by["gross potential rent"]
    assert gpr["values"]["ptd_actual"] == 1000 and gpr["values"]["ytd_budget"] == 1800 and gpr["code"] == "4000-0000"
    assert gpr["section"] == ["REVENUE", "Rental Income"] and gpr["is_total"] is False and gpr["row"] == 7
    assert by["total payroll"]["is_total"] is True and by["net rental income"]["is_total"] is True
    assert by["less:concessions-mthly"]["values"]["ptd_budget"] == 0
    assert by["roof"]["values"]["ptd_budget"] == 0 and "INTERIOR & EXTERIOR RENOVATIONS" in by["roof"]["section"]
    assert "NON-OPERATING ITEMS" in by["plumbing"]["section"] and by["plumbing"]["section"][-1] == "PLUMBING"
    assert by["marketing & promotion"]["section"][-1] == "LEASE UP COSTS"
    unlabeled = [ln for ln in d["lines"] if ln["unlabeled"]]
    assert unlabeled and unlabeled[-1]["values"]["ptd_actual"] == 61 and unlabeled[-1]["values"]["ytd_budget"] == 69


def test_budget_extractor_requires_actual_and_budget_columns():
    with pytest.raises(ExtractionError):
        extract(sheet_part([["Budget Comparison"], ["Something", "Else"], ["x", 1]], DocType.YARDI_BUDGET_COMPARISON))


def test_walk_lines_handles_missing_leading_spaces():
    rows = [[None, None, "PTD Actual", "PTD Budget"], [None, "REVENUE"], ["4000-0000", "Gross Potential Rent", 5, 4], [None, "EXPENSES"], ["5000-0000", "Payroll", 3, 2]]
    from app.readers.document import Sheet
    lines = walk_lines(Sheet("R", rows), 0, {"ptd_actual": 2, "ptd_budget": 3})
    assert [ln["section"] for ln in lines] == [["REVENUE"], ["EXPENSES"]]
