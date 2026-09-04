# backend/tests/test_extract_hellodata.py
from app.classify.classifier import DocType
from app.extract.hellodata_comps import extract as extract_comps
from app.extract.hellodata_listings import extract as extract_listings
from tests.helpers import COMPS_ROWS, HELLODATA_PDF_TEXT, LISTINGS_ROWS, pdf_part, sheet_part


def test_listings_aggregate_per_property():
    d = extract_listings(sheet_part(LISTINGS_ROWS, DocType.HELLODATA_LISTINGS)).data
    assert d["row_count"] == 5 and set(d["properties"]) == {"The Boardwalk", "The Ashlar"}
    b = d["properties"]["The Boardwalk"]
    assert b["rows"] == 2 and b["leased"] == 1 and b["active"] == 1
    assert b["asking_sum"] == 2500 and b["asking_n"] == 2 and b["effective_sum"] == 2400
    assert b["address"].startswith("4637") and b["first_row"] == 3
    assert b["monthly"] == {"2026-04": {"n": 1, "asking_sum": 1300.0, "effective_sum": 1300.0, "sqft_sum": 657.0}}
    a = d["properties"]["The Ashlar"]
    assert a["rows"] == 3 and a["leased"] == 2 and a["active"] == 1 and a["max_leased"] == "2026-06-01"


def test_comps_from_sheet():
    d = extract_comps(sheet_part(COMPS_ROWS, DocType.HELLODATA_COMPS)).data
    assert d["source"] == "sheet" and [c["name"] for c in d["comps"]] == ["The Boardwalk", "The Ashlar"]
    b = d["comps"][0]
    assert (b["year_built"], b["units"], b["avg_sqft"], b["leased_pct"]) == (1973, 338, 843.73, 0.9)
    assert d["average"]["units"] == 298 and d["comps"][1]["row"] == 5


def test_comps_from_pdf():
    d = extract_comps(pdf_part(HELLODATA_PDF_TEXT, DocType.HELLODATA_COMPS)).data
    assert d["source"] == "pdf" and [c["name"] for c in d["comps"]] == ["The Boardwalk", "Westchase"]
    b = d["comps"][0]
    assert (b["leased_count"], b["active_count"], b["avg_sqft"], b["avg_rent"], b["ner"]) == (34, 45, 841, 1314, 1178)
    assert abs(b["concession_pct"] - 0.104) < 1e-9 and b["units"] is None
