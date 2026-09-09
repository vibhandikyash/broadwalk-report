import pytest

from app.classify.classifier import classify
from app.readers.registry import SUPPORTED_EXTENSIONS, UnsupportedFileType, read_document
from app.readers.pdf_reader import NoTextError, read_pdf
from app.services.vision_ocr import OcrResult, VisionOcrError
from tests.helpers import BUDGET_ROWS, make_xlsx


def test_read_xlsx_keeps_sheet_names_and_values(tmp_path):
    p = make_xlsx(tmp_path / "a.xlsx", {"Report1": BUDGET_ROWS, "Empty": [[None, None]]})
    doc = read_document(p, "f1", "a.xlsx")
    assert doc.kind == "xlsx" and [s.name for s in doc.sheets] == ["Report1", "Empty"]
    sh = doc.sheets[0]
    assert sh.text(1, 0) == "Budget Comparison"
    assert sh.cell(7, 2) == 1000
    assert doc.sheets[1].nrows == 0  # trailing empty rows trimmed


def test_unsupported_extension(tmp_path):
    p = tmp_path / "x.docx"
    p.write_bytes(b"hello")
    with pytest.raises(UnsupportedFileType):
        read_document(p, "f", "x.docx")
    assert ".xlsx" in SUPPORTED_EXTENSIONS and ".pdf" in SUPPORTED_EXTENSIONS


def test_corrupt_xlsx_raises(tmp_path):
    p = tmp_path / "bad.xlsx"
    p.write_bytes(b"not a zip")
    with pytest.raises(Exception):
        read_document(p, "f", "bad.xlsx")


def test_scanned_pdf_uses_page_level_vision_ocr(tmp_path):
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument.new()
    pdf.new_page(400, 300)
    path = tmp_path / "scan.pdf"
    pdf.save(path)
    seen = []

    def recover(source, page_number):
        seen.append((source, page_number))
        return OcrResult("New distribution\nNo distributions yet", 0.93, [{"kind": "text", "text": "New distribution", "box_2d": [0, 0, 50, 500]}])

    doc = read_pdf(path, "f1", "scan.pdf", ocr_page=recover)
    assert seen == [(path, 1)]
    assert doc.pages[0].ocr is True and doc.pages[0].ocr_confidence == 0.93
    assert "No distributions yet" in doc.text
    assert "Gemini vision OCR" in doc.warnings[0]
    assert "Gemini vision OCR pages 1" in classify(doc)[0].locator


def test_scanned_pdf_stays_unusable_when_vision_ocr_fails(tmp_path):
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument.new()
    pdf.new_page(400, 300)
    path = tmp_path / "scan.pdf"
    pdf.save(path)

    def fail(_source, _page_number):
        raise VisionOcrError("service unavailable")

    with pytest.raises(NoTextError, match="service unavailable"):
        read_pdf(path, "f1", "scan.pdf", ocr_page=fail)
