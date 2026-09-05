# backend/tests/test_extract_yardi_rent_schedule.py
from app.classify.classifier import DocType
from app.extract.yardi_rent_schedule import extract, parse_unit_type
from tests.helpers import schedule_rows, sheet_part

RENTS = {"BWK.A1": 1172.47, "BWK.B0": 1331.04, "BWK.B1": 1370.84, "BWK.S1": 1108.31, "TOTAL": 1250.5}


def test_parse_unit_type():
    assert parse_unit_type("1 Bedroom 1 Bathroom (BWK.A1)") == ("1 Bedroom 1 Bathroom", "BWK.A1", 1, 1.0)
    assert parse_unit_type("0 Bedroom 1 Bathroom (BWK.S2)")[2] == 0
    assert parse_unit_type("Studio (S1)") == ("Studio", "S1", 0, None)
    assert parse_unit_type("2x2 - Deluxe")[2:] == (2, 2.0)
    assert parse_unit_type("3BR/2.5BA")[2:] == (3, 2.5)
    assert parse_unit_type("Penthouse")[2:] == (None, None)


def test_schedule_rows_and_total():
    d = extract(sheet_part(schedule_rows("06/30/2026", RENTS), DocType.YARDI_MARKET_RENT_SCHEDULE)).data
    assert d["as_of"] == "2026-06-30" and d["property_name"] == "The Boardwalk"
    ut = d["unit_types"]
    assert [u["code"] for u in ut] == ["BWK.A1", "BWK.B0", "BWK.B1", "BWK.S1"]
    a1 = ut[0]
    assert (a1["bedrooms"], a1["bathrooms"], a1["units"], a1["sqft"], a1["occupied_units"]) == (1, 1.0, 40, 657, 38)
    assert a1["avg_resident_rent"] == 1172.47 and a1["market_rent"] == 999 and a1["row"] == 6
    assert ut[3]["bedrooms"] == 0 and ut[1]["bathrooms"] == 1.0 and ut[2]["bathrooms"] == 2.0
    assert d["total"] == {"units": 338, "sqft": 760, "occupied_units": 306, "avg_resident_rent": 1250.5, "market_rent": 1100, "row": 10}


def test_modified_schedule_variant_without_market_rent_column():
    rows = [["Market Rent Schedule"], ["For Selected Properties"], ["As Of = 03/31/2026"],
            ["Unit Type", "Units", "Unit Type", "Occupied", "Average", None, "Average"],
            [None, None, "Sq Ft", "Units", "Resident Rent", None, "Resident Rent (RR)"],
            ["1 Bedroom 1 Bathroom (BWK.A1)", 40, 657, 38, 1205.1, None, 1204.55, 0.55],
            ["Grand Total", 40, 657, 38, 1205.1, None, 1204.55, 0.55]]
    d = extract(sheet_part(rows, DocType.YARDI_MARKET_RENT_SCHEDULE)).data
    assert d["unit_types"][0]["avg_resident_rent"] == 1205.1 and d["unit_types"][0]["market_rent"] is None
    assert d["property_name"] is None
