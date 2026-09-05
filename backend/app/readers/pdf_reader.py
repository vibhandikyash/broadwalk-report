from __future__ import annotations

import datetime as dt
import logging
import re
from pathlib import Path

import pdfplumber

from .document import Document, Page

logging.getLogger("pdfminer").setLevel(logging.ERROR)  # font-descriptor warnings from vendor PDFs are noise


class NoTextError(ValueError):
    """The PDF has no text layer (scanned image). OCR is not implemented."""


def pdf_date(raw) -> str | None:
    """'D:20260723000558+05'30'' (PDF metadata) -> '2026-07-23'."""
    m = re.match(r"D?:?(\d{4})(\d{2})(\d{2})", str(raw or ""))
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def read_pdf(path: Path, file_id: str, filename: str) -> Document:
    pages: list[Page] = []
    with pdfplumber.open(path) as pdf:
        for i, p in enumerate(pdf.pages, start=1):
            pages.append(Page(number=i, text=p.extract_text(layout=True) or ""))
        meta = pdf.metadata or {}
    if not any(p.text.strip() for p in pages):
        raise NoTextError("PDF has no extractable text (scanned image?). OCR is not supported in this version.")
    return Document(file_id=file_id, filename=filename, kind="pdf", pages=pages, created=pdf_date(meta.get("CreationDate") or meta.get("ModDate")))
