# backend/tests/test_extract_yardi_balance_sheet.py
from app.classify.classifier import DocType
from app.extract.yardi_balance_sheet import extract
from tests.helpers import BALANCE_ROWS, sheet_part


def test_balance_sheet_lines():
    ex = extract(sheet_part(BALANCE_ROWS, DocType.YARDI_BALANCE_SHEET))
    by = {ln["norm"]: ln for ln in ex.data["lines"]}
    assert by["mortgage payable"]["values"]["current"] == 36519000
    assert by["total building"]["is_total"] is True and by["total building"]["values"]["current"] == 47520000
    assert by["owner contributions"]["values"]["current"] == 14259605.94
    assert by["accrued interest"]["values"] == {"current": 159161.98, "beginning": 164467.37, "change": -5305.39}
    assert by["accrued interest"]["section"] == ["LIABILITIES"]
    assert ex.data["period"]["end"] == "2026-06-30"
