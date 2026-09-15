# backend/tests/test_classifier.py
from app.classify.classifier import DocType, classify
from app.readers.document import Document, Page, Sheet
from tests.helpers import (BALANCE_ROWS, BUDGET_ROWS, CAPITAL_CALLS_TEXT, COMPS_ROWS, COSTAR_PDF_TEXT, COSTAR_ROWS,
                           DISTRIBUTIONS_TEXT, HELLODATA_PDF_TEXT, LISTINGS_ROWS, LTO_ROWS, RENT_CHART_ROWS,
                           rent_roll_rows, schedule_rows)


def xdoc(**sheets):
    return Document("f", "f.xlsx", "xlsx", sheets=[Sheet(k, v) for k, v in sheets.items()])


def pdoc(text):
    return Document("p", "p.pdf", "pdf", pages=[Page(1, text)])


def test_classifies_each_sheet_type():
    doc = xdoc(
        b=BUDGET_ROWS, bs=BALANCE_ROWS, rr=rent_roll_rows("06/30/2026", 306, 338, 90.53, 14),
        sch=schedule_rows("06/30/2026", {"BWK.A1": 1, "BWK.B0": 1, "BWK.B1": 1, "BWK.S1": 1, "TOTAL": 1}),
        lto=LTO_ROWS, hd=LISTINGS_ROWS, comps=COMPS_ROWS, cs=COSTAR_ROWS, rc=RENT_CHART_ROWS, junk=[["hello"], ["world", 1]],
    )
    got = [p.doc_type for p in classify(doc)]
    assert got == [
        DocType.YARDI_BUDGET_COMPARISON, DocType.YARDI_BALANCE_SHEET, DocType.YARDI_RENT_ROLL,
        DocType.YARDI_MARKET_RENT_SCHEDULE, DocType.YARDI_LEASE_TRADE_OUT, DocType.HELLODATA_LISTINGS,
        DocType.HELLODATA_COMPS, DocType.COSTAR_SUBMARKET_EXCEL, DocType.RENT_CHART, DocType.UNKNOWN,
    ]
    assert classify(doc)[0].locator == "sheet 'b'"


def test_classifies_pdfs():
    assert classify(pdoc(COSTAR_PDF_TEXT))[0].doc_type == DocType.COSTAR_SUBMARKET_PDF
    assert classify(pdoc(CAPITAL_CALLS_TEXT))[0].doc_type == DocType.SLATE_CAPITAL_CALLS
    assert classify(pdoc(DISTRIBUTIONS_TEXT))[0].doc_type == DocType.SLATE_DISTRIBUTIONS
    assert classify(pdoc(HELLODATA_PDF_TEXT))[0].doc_type == DocType.HELLODATA_COMPS
    assert classify(pdoc("lorem ipsum"))[0].doc_type == DocType.UNKNOWN


def test_part_json_shape():
    p = classify(xdoc(b=BUDGET_ROWS))[0]
    assert set(p.to_json()) == {"doc_type", "confidence", "locator"} and 0.6 <= p.to_json()["confidence"] <= 1


def test_rent_roll_summary_below_first_hundred_rows():
    rows = [["Rent Roll"], ["As Of = 03/31/2026"]] + [["unit detail", i] for i in range(150)]
    rows += [["Summary Groups", "# Of Units", "% Unit Occupancy"],
             ["Occupied Units", 198, 82.5], ["Total Vacant Units", 42], ["Totals:", 240]]
    assert classify(xdoc(occupancy=rows))[0].doc_type == DocType.YARDI_RENT_ROLL
    assert classify(xdoc(unrelated=[["Rent Roll"], ["As Of = 03/31/2026"]] + rows[2:152]))[0].doc_type == DocType.UNKNOWN


def test_recognizes_dated_annual_statement():
    rows = [["Annual Statement"], ["Period = Jan 2024-Dec 2025"], [None, "EOY", "EOY"],
            [None, "Dec 2024", "Dec 2025"], ["Revenue", 100, 200]]
    assert classify(xdoc(history=rows))[0].doc_type == DocType.ANNUAL_FINANCIAL_STATEMENT
