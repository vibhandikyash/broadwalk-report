from __future__ import annotations

from pathlib import Path

import logging

import pdfplumber

from .document import Document, Page

logging.getLogger("pdfminer").setLevel(logging.ERROR)  # font-descriptor warnings from vendor PDFs are noise


class NoTextError(ValueError):
    """The PDF has no text layer (scanned image). OCR is not implemented."""


def read_pdf(path: Path, file_id: str, filename: str) -> Document:
    pages: list[Page] = []
    with pdfplumber.open(path) as pdf:
        for i, p in enumerate(pdf.pages, start=1):
            pages.append(Page(number=i, text=p.extract_text(layout=True) or ""))
    if not any(p.text.strip() for p in pages):
        raise NoTextError("PDF has no extractable text (scanned image?). OCR is not supported in this version.")
    return Document(file_id=file_id, filename=filename, kind="pdf", pages=pages)
