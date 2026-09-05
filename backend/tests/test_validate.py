# backend/tests/test_validate.py
from app.consolidate.builder import build
from app.consolidate.calc import recompute
from app.consolidate.validate import run, summary
from tests.test_builder import sample_files


def test_validate_reports_conflicts_missing_and_file_problems():
    data, notes = build({"id": "p", "name": "P"}, sample_files())
    files = [{"original_filename": "bad.docx", "status": "unsupported", "error": "Unsupported file type '.docx'", "parts": []},
             {"original_filename": "odd.xlsx", "status": "unrecognized", "error": "No recognised report found in this file, so it is not used.", "parts": [{"doc_type": "unknown", "locator": "sheet 'S'", "warnings": []}]},
             {"original_filename": "warn.xlsx", "status": "processed", "parts": [{"doc_type": "yardi_rent_roll", "locator": "sheet 'R'", "warnings": ["'As Of' date not found"]}]}]
    issues = run(data, notes, files)
    msgs = [i.message for i in issues]
    assert any(i.path == "capital.fields.purchase_price" and i.severity == "warning" and "sources disagree" in i.message for i in issues)
    assert any(i.path == "financing.fields.lender" and i.severity == "warning" and i.message == "Missing: Lender (needed for a complete report, page 4)" for i in issues)
    assert any(i.path == "status.fields.status1_subtitle" and i.severity == "info" and "optional" in i.message for i in issues)
    assert not any(i.path == "underwriting.fields.business_plan_title" and i.severity == "warning" for i in issues)
    assert any(m.startswith("bad.docx") for m in msgs) and any("odd.xlsx" in m and "not used" in m for m in msgs)
    assert any("warn.xlsx (sheet 'R'): 'As Of' date not found" == m for m in msgs)
    assert not any("does not equal" in m for m in msgs)
    s = summary(data, issues)
    assert s["conflicts"] == 1 and s["missing"] > 10 and s["errors"] == 0 and s["warnings"] > 0


def test_validate_reconciliation_warnings_after_edit():
    data, notes = build({"id": "p", "name": "P"}, sample_files())
    data.field("financials.tables.lines.rows.total_revenue.ptd_actual").override = 2000
    data.field("occupancy.fields.current_occupied").override = 200
    recompute(data)
    issues = run(data, notes, [])
    assert any(i.path == "financials.tables.lines.rows.total_revenue.ptd_actual" and "does not equal the sum" in i.message for i in issues)
    assert any(i.path == "financials.tables.lines.rows.noi.ptd_actual" and "revenue minus opex" in i.message for i in issues)
    assert any(i.path == "occupancy.fields.current_pct" and "occupied / total" in i.message for i in issues)


def test_required_fields_are_errors_when_missing():
    data, notes = build({"id": "p", "name": "P"}, sample_files()[:1])
    issues = run(data, notes, [])
    assert any(i.path == "property.fields.units" and i.severity == "error" for i in issues)
    assert any(i.path == "occupancy.fields.current_pct" and i.severity == "error" for i in issues)
