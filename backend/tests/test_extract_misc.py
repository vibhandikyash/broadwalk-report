# backend/tests/test_extract_misc.py
from app.classify.classifier import DocType
from app.extract.base import ExtractionError
from app.extract.rent_chart import extract as extract_chart
from app.extract.slate import extract_capital_calls, extract_distributions, parse_capital_calls_text, parse_distributions_text
from tests.helpers import CAPITAL_CALLS_TEXT, DISTRIBUTIONS_TEXT, RENT_CHART_ROWS, pdf_part, sheet_part
import pytest


def test_rent_chart_months_totals_and_names():
    d = extract_chart(sheet_part(RENT_CHART_ROWS, DocType.RENT_CHART)).data
    assert d["subject_name"] == "The Boardwalk" and d["comp_name"] == "Comp Set"
    assert d["title"] == "The Boardwalk vs. HelloData Comp Set"
    assert [m["month"] for m in d["months"]] == ["2025-07", "2025-08"]
    m0 = d["months"][0]
    assert (m0["subject_n"], m0["subject_gross_psf"], m0["subject_eff_psf"], m0["comp_n"], m0["comp_gross_psf"], m0["comp_eff_psf"]) == (12, 1.83, 1.63, 42, 1.71, 1.5)
    assert d["totals"]["subject_gross_psf"] == 1.78 and d["months"][1]["row"] == 6
    assert d["notes"][0] == "Methodology"


def test_slate_capital_calls_none():
    d = parse_capital_calls_text(CAPITAL_CALLS_TEXT)
    assert d == {"entity": "The Boardwalk Owner, LLC", "total_called": 0.0, "calls": [], "none": True}
    assert extract_capital_calls(pdf_part(CAPITAL_CALLS_TEXT, DocType.SLATE_CAPITAL_CALLS)).data["none"] is True


def test_slate_capital_calls_rows():
    text = "Capital Calls    New Capital Call\nTotal Called    $250,000    100%\nTitle    Due Date    From    To    Total Called\nQ3 Reno Call    07/15/2026    Fund I    LP    $250,000.00    100%\n"
    d = parse_capital_calls_text(text)
    assert d["total_called"] == 250000 and d["calls"] == [{"title": "Q3 Reno Call", "due_date": "2026-07-15", "amount": 250000.0}]


def test_slate_distributions():
    d = parse_distributions_text(DISTRIBUTIONS_TEXT)
    assert d == {"entity": "The Boardwalk Owner, LLC", "distributions": [], "total_gross": 0.0, "none": True}
    text = "Distributions    New Distribution\nTitle Period Date\nQ2 Distribution    2Q26    07/20/2026    Class A    Fund    LP    Yes    $100,000.00    $95,000.00\n"
    d2 = parse_distributions_text(text)
    assert d2["distributions"] == [{"title": "Q2 Distribution", "date": "2026-07-20", "gross": 100000.0, "net": 95000.0}]
    assert d2["total_gross"] == 100000.0 and d2["none"] is False
    assert extract_distributions(pdf_part(DISTRIBUTIONS_TEXT, DocType.SLATE_DISTRIBUTIONS)).data["entity"] == "The Boardwalk Owner, LLC"


def test_wrapped_distribution_cells_reconcile_to_net_summary():
    text = """New Distribution
$208,244.54
Distributed from this Entity (Net)
Title Date Gross Amount Net Amount
Dec GP
This 2 $125,0 $125,0
Distribution Published - 22nd, 100%
00 00
2022
Aug LP
This 2 $83,24 $83,24
Distribution Published - 1st, 100%
4.54 4.54
2022
"""
    data = extract_distributions(pdf_part(text, DocType.SLATE_DISTRIBUTIONS)).data
    assert [(r["date"], r["net"]) for r in data["distributions"]] == [
        ("2022-12-22", 125000), ("2022-08-01", 83244.54)]
    assert data["stated_total_net"] == 208244.54


def test_wrapped_distribution_mismatch_raises():
    text = """New Distribution
$200,000.00
Distributed from this Entity (Net)
Dec GP
This 2 $125,0 $125,0
Distribution Published - 22nd, 100%
00 00
2022
"""
    with pytest.raises(ExtractionError, match="reconcile"):
        extract_distributions(pdf_part(text, DocType.SLATE_DISTRIBUTIONS))
