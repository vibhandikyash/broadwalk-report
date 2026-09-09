# backend/tests/test_select_mapping.py
from app.classify.classifier import DocType
from app.config import settings
from app.consolidate.mapping import consume_capex, load_capex_mapping, load_pl_mapping, match_lines, section_matches
from app.consolidate.select import Src, collect, select


def line(label, section=(), total=False, **values):
    return {"code": "", "label": label, "norm": label.lower(), "indent": 0, "section": list(section),
            "is_total": total, "unlabeled": False, "values": values, "row": 1}


def test_match_lines_pattern_order_and_totals():
    lines = [line("Property Taxes", ptd_actual=5), line("TOTAL TAXES", total=True, ptd_actual=5)]
    assert match_lines(lines, [r"^total taxes$", r"^property taxes$"])[0]["label"] == "TOTAL TAXES"
    assert match_lines(lines, [r"taxes"], prefer_total=True)[0]["label"] == "TOTAL TAXES"
    assert match_lines(lines, [r"insurance"]) == []


def test_section_matches_innermost_wins():
    cfg = load_capex_mapping(settings.config_dir)["sections"]
    assert section_matches(["INTERIOR & EXTERIOR RENOVATIONS", "ROOF"], cfg["include"], cfg["exclude"])
    assert not section_matches(["INTERIOR & EXTERIOR RENOVATIONS", "LEASE UP COSTS"], cfg["include"], cfg["exclude"])
    assert not section_matches(["DEBT SERVICE", "NON-OPERATING EXPENSES"], cfg["include"], cfg["exclude"])
    assert section_matches(["RENO - X", "DEPR/AMORT EXPENSE", "NON-OPERATING ITEMS", "PLUMBING"], cfg["include"], cfg["exclude"])
    assert section_matches(["NON-OPERATING ITEMS", "PLUMBING"], cfg["negate"], [])


def test_consume_capex_consumes_each_line_once_in_order():
    rows = load_capex_mapping(settings.config_dir)["rows"]
    lines = [line("Reno - Plumbing"), line("Plumbing Replacement"), line("Boiler/Water Heater"), line("Paint"), line("Something Odd")]
    groups, leftover = consume_capex(lines, rows)
    by = {m["key"]: [ln["label"] for ln in hit] for m, hit in groups if hit}
    assert by["renovation_plumbing"] == ["Reno - Plumbing"]
    assert by["plumbing_water_heaters"] == ["Plumbing Replacement", "Boiler/Water Heater"]
    assert by["paint"] == ["Paint"] and [ln["label"] for ln in leftover] == ["Something Odd"]


def test_pl_mapping_has_all_report_rows():
    keys = [m["key"] for m in load_pl_mapping(settings.config_dir)]
    assert keys == ["gpr", "gain_loss_to_lease", "concessions", "vacancy", "pet_rent", "net_rental_income", "utility_income",
                    "other_income", "total_revenue", "payroll", "g_and_a", "marketing", "r_and_m", "utilities",
                    "management_fees", "property_taxes", "insurance", "total_opex", "noi", "debt_service", "net_cash_flow"]


def test_select_prefers_ytd_budget_single_part_listings_and_notes_alternatives():
    files = [
        {"id": "a", "original_filename": "ptd.xlsx", "status": "processed", "ignored": False, "parts": [{}],
         "extractions": [{"doc_type": DocType.YARDI_BUDGET_COMPARISON, "locator": "sheet 'R'", "data": {"columns": ["mtd_actual", "ptd_actual"], "period": {"end": "2026-06-30"}}}]},
        {"id": "b", "original_filename": "ytd.xlsx", "status": "processed", "ignored": False, "parts": [{}],
         "extractions": [{"doc_type": DocType.YARDI_BUDGET_COMPARISON, "locator": "sheet 'R'", "data": {"columns": ["ptd_actual", "ytd_actual"], "period": {"end": "2026-06-30"}}}]},
        {"id": "c", "original_filename": "full.xlsx", "status": "processed", "ignored": False, "parts": [{}, {}, {}],
         "extractions": [{"doc_type": DocType.HELLODATA_LISTINGS, "locator": "sheet 'U'", "data": {"row_count": 5000}}]},
        {"id": "d", "original_filename": "leasing.xlsx", "status": "processed", "ignored": False, "parts": [{}],
         "extractions": [{"doc_type": DocType.HELLODATA_LISTINGS, "locator": "sheet 'U'", "data": {"row_count": 2600}}]},
        {"id": "e", "original_filename": "ignored.xlsx", "status": "processed", "ignored": True, "parts": [{}],
         "extractions": [{"doc_type": DocType.COSTAR_SUBMARKET_EXCEL, "locator": "sheet 'D'", "data": {"series": [1]}}]},
        {"id": "f", "original_filename": "failed.xlsx", "status": "failed", "ignored": False, "parts": [], "extractions": []},
    ]
    srcs = collect(files)
    assert {s.file_id for s in srcs} == {"a", "b", "c", "d"}
    sel = select(srcs)
    assert sel.budget.file_id == "b" and sel.listings.file_id == "d" and sel.costar_excel is None
    assert len(sel.notes) == 2 and all(n["severity"] == "warning" for n in sel.notes)
    assert Src("x", "f.xlsx", "t", "sheet 'S'", {}).source("row 3", "GPR") == {
        "file_id": "x", "filename": "f.xlsx", "doc_type": "t", "locator": "sheet 'S' row 3", "text": "GPR",
        "method": "native", "ocr_confidence": None}
