from app.classify.classifier import DocType
from app.extract.annual_statement import extract
from tests.helpers import sheet_part


def test_annual_statement_keeps_dated_account_values():
    rows = [["Annual Statement"], ["Period = Jan 2024-Dec 2025"],
            [None, None, "EOY", "EOY"], [None, None, "Dec 2024", "Dec 2025"],
            ["4000-0000", "Gross Potential Rent", 100, 200],
            [None, "Total Revenue", 90, 180]]
    data = extract(sheet_part(rows, DocType.ANNUAL_FINANCIAL_STATEMENT)).data
    assert data["periods"] == ["2024-12-01", "2025-12-01"]
    assert data["lines"][0] == {"account": "4000-0000", "label": "Gross Potential Rent",
                                "row": 4, "values": {"2024-12-01": 100, "2025-12-01": 200}}
    assert data["lines"][1]["account"] is None
