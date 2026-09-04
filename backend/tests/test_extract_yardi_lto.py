# backend/tests/test_extract_yardi_lto.py
from app.classify.classifier import DocType
from app.extract.yardi_lto import extract
from tests.helpers import LTO_ROWS, sheet_part


def test_lto_sections_rows_and_previous_term_columns():
    d = extract(sheet_part(LTO_ROWS, DocType.YARDI_LEASE_TRADE_OUT)).data
    assert d["period"] == {"start": "2026-04-01", "end": "2026-06-30"}
    assert d["property_name"] == "The Boardwalk"
    ren, mi = d["sections"]["renewals"]["rows"], d["sections"]["move_ins"]["rows"]
    assert len(ren) == 2 and len(mi) == 3
    r0 = ren[0]
    assert r0["unit_type"] == "BWK.A1" and r0["sqft"] == 657 and r0["unit"] == "4715D125"
    assert r0["lease_rent"] == 1425 and r0["prev_lease_rent"] == 1405
    assert r0["effective_rent"] == 1306.25 and r0["prev_effective_rent"] == 1405
    assert r0["start"] == "2026-04-22" and r0["term"] == 12 and r0["prev_term"] == 12
    assert r0["concessions"] == 1425 and r0["months_free"] == 1 and r0["market_rent"] == 1264
    assert r0["row"] == 5
    assert mi[2]["unit_type"] == "BWK.S1" and mi[2]["lease_rent"] == 900 and mi[2]["prev_lease_rent"] == 1000
    assert d["sections"]["renewals"]["header_row"] == 4


def test_lto_without_group_row_uses_duplicate_header_rule():
    rows = [[None, "Move Ins"], [None, "Move In between 2026-01-01 and 2026-03-31"],
            [None, "Resident Name", "Unit Type", "Sqft", "Unit", "Lease Start", "Lease Term", "Lease Rent", "Effective Rent", "Lease Rent", "Effective Rent"],
            ["P", "X", "A1", 600, "101", "2026-02-01", 12, 1000, 950, 1200, 1150]]
    d = extract(sheet_part(rows, DocType.YARDI_LEASE_TRADE_OUT)).data
    row = d["sections"]["move_ins"]["rows"][0]
    assert row["lease_rent"] == 1000 and row["prev_lease_rent"] == 1200 and row["prev_effective_rent"] == 1150
