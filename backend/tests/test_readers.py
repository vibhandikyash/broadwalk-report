import pytest

from app.readers.registry import SUPPORTED_EXTENSIONS, UnsupportedFileType, read_document
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
