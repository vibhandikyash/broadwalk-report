"""Provenance: the file and line behind every value, the OCR flag, and the reason a value is absent."""
from __future__ import annotations

from app.classify.classifier import DocType
from app.consolidate.builder import build
from app.consolidate.provenance import counts, describe, expected_sources, source_files
from app.extract.registry import part_provenance, run_extractor
from app.readers.document import Page
from app.report.render import appendix_items, number_pages, paginate
from tests.helpers import CAPITAL_CALLS_TEXT, pdf_part
from tests.test_builder import file_of, sample_files


def _data():
    return build({"id": "p", "name": "P"}, sample_files())[0]


def _describe(data, path):
    return describe(path, data.field(path), data)


def test_workbook_values_are_native_and_name_their_file_and_line():
    data = _data()
    p = _describe(data, "property.fields.units")
    assert p.origin == "extracted" and p.filename == "rr-jun.xlsx" and "summary block" in p.locator
    assert p.doc_type == DocType.YARDI_RENT_ROLL.value and p.doc_label.startswith("Yardi Rent Roll")
    assert p.ocr is False and p.ocr_confidence is None
    assert "rr-jun.xlsx" in p.detail and "OCR" not in p.detail


def test_accrued_interest_used_as_io_payment_is_marked_inferred():
    data = _data()
    p = _describe(data, "financing.fields.interest_monthly")
    assert p.origin == "inferred" and p.label == "Inferred"
    assert "Inferred monthly IO payment from accrued interest" in p.detail
    assert "bs.xlsx" in p.detail and "Accrued Interest" in p.detail


def test_ocr_pages_are_flagged_and_native_pages_in_the_same_file_are_not():
    """A file where only page 2 needed OCR: a value read from page 2 is flagged, one from page 1 is not."""
    part = pdf_part(CAPITAL_CALLS_TEXT, DocType.SLATE_CAPITAL_CALLS, file_id="fx", filename="scan.pdf")
    part.pages.append(Page(len(part.pages) + 1, "second page", ocr=True, ocr_confidence=0.88))
    prov = part_provenance(part)
    assert prov["method"] == "mixed" and prov["ocr_pages"] == [2] and prov["ocr_confidence"] == 0.88

    from app.consolidate.select import Src

    src = Src("fx", "scan.pdf", part.doc_type, "pages 1-2", {}, 1, prov)
    assert src.source("page 2")["method"] == "ocr" and src.source("page 2")["ocr_confidence"] == 0.88
    assert src.source("page 1")["method"] == "native" and src.source("page 1")["ocr_confidence"] is None
    assert src.source("entity header")["method"] == "mixed"  # no page named: reported as needing review, not as native


def test_an_all_ocr_document_reaches_the_report_as_ocr():
    part = pdf_part(CAPITAL_CALLS_TEXT, DocType.SLATE_CAPITAL_CALLS, file_id="fx", filename="scan.pdf")
    for page in part.pages:
        page.ocr, page.ocr_confidence = True, 0.91
    assert run_extractor(part).provenance["method"] == "ocr"
    files = [f for f in sample_files() if f["id"] != "f13"] + [file_of("fx", "scan.pdf", part)]
    data, _ = build({"id": "p", "name": "P"}, files)
    p = _describe(data, "capital.fields.total_called")
    assert p.origin == "ocr" and p.ocr is True and "OCR" in p.detail and "91%" in p.detail
    assert any(f["filename"] == "scan.pdf" and f["method"] == "ocr" for f in source_files(data))


def test_a_missing_value_says_whether_the_report_that_carries_it_was_uploaded():
    data = _data()  # this upload has no management memorandum and no loan summary
    memo = _describe(data, "property.fields.building_class")
    assert memo.origin == "missing" and "Asset management memorandum" in memo.reason and "no such file was uploaded" in memo.reason
    # The balance sheet was uploaded and read, so the reserve line is absent from a file that was consulted.
    reserve = _describe(data, "financing.fields.reserve_balance")
    assert "Yardi Balance Sheet" in reserve.reason and "bs.xlsx" in reserve.reason and "no line for this value" in reserve.reason


def test_reviewer_authored_text_is_not_blamed_on_a_missing_file():
    data = _data()
    p = _describe(data, "commentary.fields.takeaway")
    assert p.origin == "missing" and "No source file carries this text" in p.reason and "draft it with AI" in p.reason


def test_a_calculated_value_without_inputs_says_so_rather_than_blaming_the_files():
    data = _data()  # density needs site acres, which only the memorandum carries
    p = _describe(data, "property.fields.density")
    assert p.origin == "missing" and "at least one input value is missing" in p.reason
    assert "uploaded" not in p.reason


def test_reviewer_and_calculated_origins_are_reported_over_the_extracted_source():
    data = _data()
    data.field("property.fields.units").override = 340
    assert _describe(data, "property.fields.units").origin == "manual"
    assert _describe(data, "commentary.fields.noi_actual").origin == "computed"


def test_expected_sources_resolve_by_exact_path_then_table_then_section():
    assert expected_sources("property.fields.submarket") == (DocType.COSTAR_SUBMARKET_PDF,)
    assert expected_sources("financials.tables.lines.rows.noi.ptd_actual") == (DocType.YARDI_BUDGET_COMPARISON,)
    assert expected_sources("status.fields.goal2_body") == (DocType.MANAGEMENT_MEMO,)
    assert expected_sources("nowhere.fields.x") == ()


def test_every_value_is_accounted_for_and_the_sheets_cover_them_all():
    data = _data()
    tally = counts(data)
    assert sum(tally.values()) == sum(1 for _ in data.iter_fields())
    assert tally["extracted"] > 0 and tally["computed"] > 0 and tally["missing"] > 0
    by_page = appendix_items(data)
    assert set(by_page) <= set(range(1, 11)), "every sheet belongs to one of the ten fixed pages"
    rows = [i for items in by_page.values() for i in items if i["kind"] == "row"]
    assert all(r["label"] and r["method"] and r["detail"] for r in rows)
    assert "AI draft" not in " ".join(r["method"] for r in rows)  # DRAFT is reserved for the incomplete-version marker
    # a page fed by several sections is grouped by section; a page fed by one is not
    assert [i["label"] for i in by_page[3] if i["kind"] == "head"] == ["Capital Summary", "Original Underwriting Budget", "Submarket Rent Trend"]
    assert not [i for i in by_page[6] if i["kind"] == "head"]


def test_a_sheet_paginates_without_stranding_a_heading():
    items = [{"kind": "head", "label": "S", "page": 1}] + [{"kind": "row"} for _ in range(60)]
    pages = paginate(items, per_page=10)
    assert all(len(p) <= 10 for p in pages)
    assert sum(len(p) for p in pages) == len(items)
    assert all(p[-1]["kind"] != "head" for p in pages)


def test_sheets_are_numbered_after_the_page_they_explain():
    printed, sheets, total = number_pages({2: [{"kind": "row"}] * 3, 4: [{"kind": "row"}] * 5}, per_page=2)
    assert printed[1] == 1 and printed[2] == 2  # the cover has no sheet, so page 2 keeps its number
    assert [s["page"] for s in sheets[2]] == [3, 4]  # two sheets follow page 2
    assert printed[3] == 5 and printed[4] == 6     # page 3 is pushed down by them
    assert [s["page"] for s in sheets[4]] == [7, 8, 9] and sheets[4][0]["count"] == 3
    assert printed[10] == 15 and total == 17       # + the closing source-file summary and the method sheet
    assert sheets[1] == [] and sheets[5] == []


def test_source_files_deduplicate_by_name_and_keep_the_ocr_flag():
    data = _data()
    files = source_files(data)
    assert len({f["filename"] for f in files}) == len(files)
    assert all(f["doc_labels"] for f in files) and all(f["method"] == "native" for f in files)
