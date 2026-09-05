"""Cross-file identity checks, period-aware Slate selection and material conflicts."""
from app.classify.classifier import DocType
from app.consolidate.builder import build
from app.consolidate.select import collect, select
from tests.test_builder import sample_files


def _file(fid, name, doc_type, data, locator="pages 1-1"):
    return {"id": fid, "original_filename": name, "status": "processed", "ignored": False, "parts": [{}],
            "extractions": [{"doc_type": doc_type, "locator": locator, "data": data}]}


def test_newer_zero_activity_export_beats_older_populated_one():
    old = _file("a", "calls-2025.pdf", DocType.SLATE_CAPITAL_CALLS,
                {"entity": "X LLC", "total_called": 500000, "calls": [{"title": "Call 1", "due_date": "2025-12-01", "amount": 500000}], "none": False,
                 "report_date": "2025-12-15", "latest_transaction": "2025-12-01"})
    new = _file("b", "calls-2026.pdf", DocType.SLATE_CAPITAL_CALLS,
                {"entity": "X LLC", "total_called": 0, "calls": [], "none": True, "report_date": "2026-07-23", "latest_transaction": None})
    for order in ((old, new), (new, old)):
        sel = select(collect(list(order)))
        assert sel.capital_calls.file_id == "b" and any("most recent export" in n["message"] for n in sel.notes)
    files = sample_files() + [old, new]
    data, notes = build({"id": "p", "name": "P"}, files)
    f = data.field("capital.fields.total_called")
    assert f.value == 0 and f.status != "conflict"  # the older export is not a conflicting source
    assert data.value("capital.fields.quarter_contributions") == 0
    # two exports of the same vintage that disagree do conflict
    twin = _file("c", "calls-2026b.pdf", DocType.SLATE_CAPITAL_CALLS,
                 {"entity": "X LLC", "total_called": 250000, "calls": [], "none": False, "report_date": "2026-07-23", "latest_transaction": None})
    data, notes = build({"id": "p", "name": "P"}, sample_files() + [new, twin])
    f = data.field("capital.fields.total_called")
    assert f.status == "conflict" and {a.value for a in f.alternatives} == {250000}
    assert any(n["path"] == "capital.fields.total_called" for n in notes)


def test_undated_exports_fall_back_to_transaction_dates_and_warn():
    a = _file("a", "d1.pdf", DocType.SLATE_DISTRIBUTIONS, {"entity": "X", "distributions": [{"title": "D", "date": "2026-05-01", "gross": 100, "net": 90}],
                                                          "total_gross": 100, "none": False, "report_date": "2026-05-01", "latest_transaction": "2026-05-01"})
    b = _file("b", "d2.pdf", DocType.SLATE_DISTRIBUTIONS, {"entity": "X", "distributions": [{"title": "D", "date": "2026-06-15", "gross": 50, "net": 45}],
                                                          "total_gross": 50, "none": False, "report_date": "2026-06-15", "latest_transaction": "2026-06-15"})
    sel = select(collect([a, b]))
    assert sel.distributions.file_id == "b"
    undated = _file("c", "d3.pdf", DocType.SLATE_DISTRIBUTIONS, {"entity": "X", "distributions": [], "total_gross": 0, "none": True, "report_date": None, "latest_transaction": None})
    data, notes = build({"id": "p", "name": "P"}, sample_files() + [undated])
    assert any("carries no export date" in n["message"] for n in notes)
    data, notes = build({"id": "p", "name": "P"}, sample_files() + [a])
    assert any("before the period end" in n["message"] for n in notes)


def test_files_about_another_property_are_set_aside():
    files = sample_files()
    stray = {"id": "z", "original_filename": "other-rr.xlsx", "status": "processed", "ignored": False, "parts": [{}],
             "extractions": [{"doc_type": DocType.YARDI_RENT_ROLL, "locator": "sheet 'R'",
                              "data": {"as_of": "2026-06-30", "property_name": "Lakeside Villas", "property_ref": "999", "total_units": 12,
                                       "occupied_units": 6, "occupancy_pct": 0.5, "future_applicants": 0}}]}
    sel = select(collect(files + [stray]))
    assert sel.property_name == "The Boardwalk" and [s.file_id for s in sel.excluded] == ["z"]
    assert all(s.data["property_name"] == "The Boardwalk" for s in sel.rent_rolls)
    data, notes = build({"id": "p", "name": "P"}, files + [stray])
    assert data.value("property.fields.units") == 338 and data.value("occupancy.fields.current_pct") != 0.5
    err = [n for n in notes if n["severity"] == "error" and "Lakeside Villas" in n["message"]]
    assert err and err[0]["path"] == "property.fields.name"
    assert [a.value for a in data.field("property.fields.name").alternatives] == ["Lakeside Villas"]


def test_material_unit_and_vacancy_differences_become_conflicts():
    files = sample_files()
    for f in files:
        for ex in f["extractions"]:
            if ex["doc_type"] == DocType.YARDI_MARKET_RENT_SCHEDULE:
                ex["data"]["total"]["units"] = 340
            if ex["doc_type"] == DocType.COSTAR_SUBMARKET_PDF:
                ex["data"]["key_stats"]["vacancy"] = 0.30
    data, notes = build({"id": "p", "name": "P"}, files)
    units = data.field("property.fields.units")
    assert units.value == 338 and units.status == "conflict" and 340 in [a.value for a in units.alternatives]
    vac = data.field("submarket.fields.vacancy")
    assert vac.status == "conflict" and 0.30 in [a.value for a in vac.alternatives]
    assert any(n["path"] == "property.fields.units" for n in notes) and any(n["path"] == "submarket.fields.vacancy" for n in notes)
    # agreeing sources raise nothing
    data, notes = build({"id": "p", "name": "P"}, sample_files())
    assert data.field("property.fields.units").status == "extracted" and data.field("submarket.fields.vacancy").status == "extracted"
