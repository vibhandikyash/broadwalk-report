"""Page 8 comparable rows: every property with any supported data stays visible; totals use available values only."""
from pathlib import Path

import pytest

from app.classify.classifier import DocType, classify
from app.consolidate.builder import build
from app.consolidate.calc import recompute
from app.extract.registry import run_extractor
from app.readers.registry import read_document
from tests.helpers import COMPS_ROWS, LISTINGS_ROWS, make_xlsx, rent_roll_rows


def _file(fid, name, doc_type, data, locator="sheet 'S'", parts=1):
    return {"id": fid, "original_filename": name, "status": "processed", "ignored": False, "parts": [{}] * parts,
            "extractions": [{"doc_type": doc_type, "locator": locator, "data": data}]}


def _rent_roll():
    return _file("rr", "roll.xlsx", DocType.YARDI_RENT_ROLL, {"as_of": "2026-06-30", "property_name": "Elm Court", "property_ref": "55001",
                                                            "total_units": 200, "occupied_units": 184, "occupancy_pct": 0.92, "future_applicants": 3})


def _listing(name, address, rows):
    """rows: (asking, effective, leased) tuples."""
    return {"address": address, "first_row": 3, "rows": len(rows), "leased": sum(1 for r in rows if r[2]),
            "asking_sum": sum(r[0] for r in rows if r[0] is not None), "asking_n": sum(1 for r in rows if r[0] is not None),
            "effective_sum": sum(r[1] for r in rows if r[1] is not None), "effective_n": sum(1 for r in rows if r[1] is not None), "monthly": {}}


def _listings(props):
    return _file("li", "listings.xlsx", DocType.HELLODATA_LISTINGS, {"row_count": 10, "properties": props})


def _comps_sheet(comps):
    return _file("cs", "comps.xlsx", DocType.HELLODATA_COMPS, {"source": "sheet", "average": None, "comps": comps})


def _comp(name, units=None, year=None, leased=None, row=5, **extra):
    return {"name": name, "address": None, "year_built": year, "units": units, "stories": None, "avg_sqft": None, "leased_pct": leased, "row": row, **extra}


def _rows(data):
    t = data.table("submarket.tables.comps")
    return {k: {c: f.effective for c, f in r.items()} | {"_subject": bool(t.row_meta[k].get("subject")), "_status": {c: f.status for c, f in r.items()}} for k, r in t.rows.items()}


def _totals(data):
    return {k: f.effective for k, f in data.table("submarket.tables.comps").totals.items()}


def test_metadata_only_comp_rows_are_kept_with_missing_rents():
    files = [_rent_roll(), _comps_sheet([_comp("Elm Court", 200, 1999, 0.92), _comp("Oak Row", 150, 2005, 0.95), _comp("Birch Place", 90, 1988, 0.9)])]
    data, notes = build({"id": "p", "name": "P"}, files)
    rows = _rows(data)
    assert set(rows) == {"elm-court", "oak-row", "birch-place"} and rows["elm-court"]["_subject"] and not rows["oak-row"]["_subject"]
    assert rows["oak-row"]["units"] == 150 and rows["oak-row"]["vintage"] == 2005 and rows["oak-row"]["leased_pct"] == 0.95
    assert rows["oak-row"]["asking_rent"] is None and rows["oak-row"]["_status"]["asking_rent"] == "missing"
    assert rows["oak-row"]["effective_rent"] is None and rows["oak-row"]["_status"]["effective_rent"] == "missing"
    assert rows["elm-court"]["leased_pct"] == 0.92  # the subject's leased % comes from the rent roll
    src = data.table("submarket.tables.comps").rows["oak-row"]["units"].source
    assert src and src.filename == "comps.xlsx" and "row 6" in src.locator
    totals = _totals(data)
    assert totals["asking_rent"] is None and totals["effective_rent"] is None and totals["units"] == 120 and totals["vintage"] == 1997
    assert totals["leased_pct"] == pytest.approx((0.95 * 150 + 0.9 * 90) / 240)  # unit-weighted: every contributing comp has units
    assert not any("comp table is empty" in n["message"] for n in notes)


def test_mixed_complete_and_metadata_only_rows_and_totals_from_available_values():
    props = {"Elm Court": _listing("Elm Court", "1 Elm St, Denver, CO 80202", [(1500, 1450, True), (1520, 1520, False)]),
             "Oak Row": _listing("Oak Row", "2 Oak St, Denver, CO 80202", [(1700, 1600, True), (1800, 1700, True)]),
             "Birch Place": _listing("Birch Place", "3 Birch St, Denver, CO 80202", [(1400, None, True), (1450, None, False)])}
    files = [_rent_roll(), _listings(props), _comps_sheet([_comp("Elm Court", 200, 1999, 0.92), _comp("Oak Row", 150, 2005, 0.95),
                                                            _comp("Birch Place", 90, 1988, 0.9), _comp("Cedar Lane", 120, 2012, 0.97)])]
    data, notes = build({"id": "p", "name": "P"}, files)
    rows = _rows(data)
    assert set(rows) == {"elm-court", "oak-row", "birch-place"}  # the listings export defines the set
    assert rows["oak-row"]["asking_rent"] == 1750 and rows["oak-row"]["effective_rent"] == 1650 and rows["oak-row"]["concession"] == 100
    assert rows["oak-row"]["units"] == 150 and rows["oak-row"]["vintage"] == 2005  # enriched from the comp sheet
    assert rows["birch-place"]["asking_rent"] == 1425 and rows["birch-place"]["effective_rent"] is None and rows["birch-place"]["concession"] is None
    assert rows["birch-place"]["leased_pct"] == 0.5  # listings are the leased % source when they exist for the property
    assert rows["oak-row"]["leased_pct"] == 1.0  # both Oak Row listings leased: listings beat the summary's 0.95
    extra = [n for n in notes if n["path"] == "submarket.tables.comps"]
    assert extra and "Cedar Lane" in extra[0]["message"] and extra[0]["severity"] == "info"  # never silently lost
    totals = _totals(data)
    assert totals["leased_pct"] == pytest.approx((1.0 * 150 + 0.5 * 90) / 240)
    assert totals["asking_rent"] == pytest.approx((1750 * 150 + 1425 * 90) / 240)   # both comps with an asking rent have units
    assert totals["effective_rent"] == 1650                                            # only Oak Row has an effective rent
    assert totals["units"] == pytest.approx(120) and totals["concession"] == pytest.approx(totals["asking_rent"] - 1650)
    note = data.value("submarket.fields.footnote")
    assert "2 comparable" in note and "unit-weighted" in note and "effective rent" in note and "1 of 2" in note

def test_missing_unit_count_falls_back_to_a_simple_average_and_says_so():
    props = {"Oak Row": _listing("Oak Row", "2 Oak St", [(1700, 1600, True)]), "Birch Place": _listing("Birch Place", "3 Birch St", [(1400, 1300, True)])}
    files = [_rent_roll(), _listings(props), _comps_sheet([_comp("Oak Row", 150, 2005, 0.95), _comp("Birch Place", None, 1988, 0.9)])]
    data, _ = build({"id": "p", "name": "P"}, files)
    totals = _totals(data)
    assert totals["asking_rent"] == 1550 and totals["effective_rent"] == 1450  # simple averages: Birch Place has no unit count
    assert totals["units"] == 150
    assert "simple average" in data.value("submarket.fields.footnote")


def test_subject_never_enters_the_comp_averages():
    props = {"Elm Court": _listing("Elm Court", "1 Elm St", [(9000, 9000, True)]), "Oak Row": _listing("Oak Row", "2 Oak St", [(1700, 1600, True)])}
    data, _ = build({"id": "p", "name": "P"}, [_rent_roll(), _listings(props), _comps_sheet([_comp("Elm Court", 200, 1999, 0.92), _comp("Oak Row", 150, 2005, 0.95)])])
    totals = _totals(data)
    assert totals["asking_rent"] == 1700 and totals["effective_rent"] == 1600 and totals["units"] == 150 and totals["vintage"] == 2005
    assert "1 comparable" in data.value("submarket.fields.footnote")


def test_pdf_summary_supplies_rents_when_no_listings_exist():
    pdf = _file("cp", "comps.pdf", DocType.HELLODATA_COMPS, {"source": "pdf", "average": None, "comps": [
        {"name": "Elm Court", "address": None, "year_built": None, "units": None, "stories": None, "avg_sqft": 800, "leased_pct": None, "leased_count": 30, "active_count": 5, "avg_rent": 1500, "ner": 1400, "concession_pct": 0.066, "page": 1},
        {"name": "Oak Row", "address": None, "year_built": None, "units": None, "stories": None, "avg_sqft": 850, "leased_pct": None, "leased_count": 10, "active_count": 10, "avg_rent": 1700, "ner": None, "concession_pct": 0, "page": 1},
    ]}, locator="pages 1-1")
    data, _ = build({"id": "p", "name": "P"}, [_rent_roll(), pdf])
    rows = _rows(data)
    assert rows["oak-row"]["asking_rent"] == 1700 and rows["oak-row"]["effective_rent"] is None and rows["oak-row"]["leased_pct"] == 0.5
    assert rows["elm-court"]["_subject"] and rows["elm-court"]["leased_pct"] == 0.92 and rows["elm-court"]["effective_rent"] == 1400
    assert _totals(data)["asking_rent"] == 1700


def test_comps_survive_other_workbook_names_and_sheet_positions(tmp_path):
    a = make_xlsx(tmp_path / "peer_set_final(3).xlsx", {"Cover": [["Prepared for review"], ["n/a", 1]], "Peer Set": COMPS_ROWS, "Notes": [["x"]]})
    b = make_xlsx(tmp_path / "export-9f2.xlsx", {"Notes": [["internal"]], "Units Export": LISTINGS_ROWS, "RR": rent_roll_rows("06/30/2026", 306, 338, 90.53, 14)})
    files = []
    for i, p in enumerate((a, b)):
        doc = read_document(p, f"f{i}", p.name)
        parts = classify(doc)
        exs = [run_extractor(part).model_dump() for part in parts if part.doc_type != DocType.UNKNOWN.value]
        files.append({"id": f"f{i}", "original_filename": p.name, "status": "processed", "ignored": False, "parts": [{"doc_type": pt.doc_type} for pt in parts], "extractions": exs})
    data, _ = build({"id": "p", "name": "P"}, files)
    rows = _rows(data)
    assert set(rows) == {"the-boardwalk", "the-ashlar"} and rows["the-boardwalk"]["_subject"]
    assert rows["the-ashlar"]["units"] == 428 and rows["the-ashlar"]["vintage"] == 1998 and rows["the-ashlar"]["asking_rent"] == 1700
    assert rows["the-ashlar"]["_status"]["units"] == "extracted" and "peer_set_final(3).xlsx" == data.table("submarket.tables.comps").rows["the-ashlar"]["units"].source.filename


def test_pdf_summary_only_enriches_when_a_listings_export_defines_the_set():
    props = {"Elm Court": _listing("Elm Court", "1 Elm St", [(1500, 1450, True)]), "Westchase Apartments": _listing("Westchase Apartments", "9 W St", [(1700, 1600, True)])}
    pdf = _file("cp", "comps.pdf", DocType.HELLODATA_COMPS, {"source": "pdf", "average": None, "comps": [
        {"name": "Westchase", "address": None, "year_built": None, "units": None, "stories": None, "avg_sqft": 900, "leased_pct": None, "leased_count": 8, "active_count": 2, "avg_rent": 1650, "ner": 1600, "concession_pct": 0.03, "page": 1},
        {"name": "Coral Cove", "address": None, "year_built": None, "units": None, "stories": None, "avg_sqft": 950, "leased_pct": None, "leased_count": 5, "active_count": 5, "avg_rent": 1400, "ner": 1300, "concession_pct": 0.07, "page": 1},
    ]}, locator="pages 1-1")
    data, notes = build({"id": "p", "name": "P"}, [_rent_roll(), _listings(props), pdf])
    rows = _rows(data)
    assert set(rows) == {"elm-court", "westchase-apartments"}  # a different comp set in the PDF does not add rows
    assert rows["westchase-apartments"]["asking_rent"] == 1700 and rows["westchase-apartments"]["leased_pct"] == 1.0  # listings stay the primary source
    assert any("Coral Cove" in n["message"] for n in notes if n["path"] == "submarket.tables.comps")
    # without a listings export the comp sheet defines the set, and the PDF fills rents for a sheet-only property
    sheet = _comps_sheet([_comp("Elm Court", 200, 1999, 0.92), _comp("Coral Cove", 120, 2010, 0.9)])
    data, notes = build({"id": "p", "name": "P"}, [_rent_roll(), sheet, pdf])
    rows = _rows(data)
    assert set(rows) == {"elm-court", "coral-cove"}
    assert rows["coral-cove"]["units"] == 120 and rows["coral-cove"]["asking_rent"] == 1400 and rows["coral-cove"]["effective_rent"] == 1300 and rows["coral-cove"]["leased_pct"] == 0.9
    assert any("Westchase" in n["message"] for n in notes if n["path"] == "submarket.tables.comps")