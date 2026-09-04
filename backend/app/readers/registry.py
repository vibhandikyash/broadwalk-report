"""Extension -> reader. Add a new format by adding one entry."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .document import Document
from .pdf_reader import read_pdf
from .xlsx_reader import read_xlsx

READERS: dict[str, Callable[[Path, str, str], Document]] = {
    ".xlsx": read_xlsx,
    ".xlsm": read_xlsx,
    ".pdf": read_pdf,
}
SUPPORTED_EXTENSIONS = tuple(READERS)


class UnsupportedFileType(ValueError):
    pass


def read_document(path: Path, file_id: str, filename: str) -> Document:
    ext = Path(filename).suffix.lower() or path.suffix.lower()
    reader = READERS.get(ext)
    if reader is None:
        raise UnsupportedFileType(f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}")
    return reader(path, file_id, filename)
