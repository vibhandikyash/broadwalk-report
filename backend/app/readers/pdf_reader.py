from __future__ import annotations

import datetime as dt
import logging
import re
from pathlib import Path
from typing import Callable

import pdfplumber

from .document import Document, Page
from ..services.vision_ocr import OcrResult, VisionOcrError, ocr_pdf_page

logging.getLogger("pdfminer").setLevel(logging.ERROR)  # font-descriptor warnings from vendor PDFs are noise


class NoTextError(ValueError):
    """The PDF has no usable text and configured OCR could not recover it."""


def pdf_date(raw) -> str | None:
    """'D:20260723000558+05'30'' (PDF metadata) -> '2026-07-23'."""
    m = re.match(r"D?:?(\d{4})(\d{2})(\d{2})", str(raw or ""))
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def _has_usable_text(text: str, minimum: int) -> bool:
    return sum(1 for char in text if char.isalnum()) >= minimum


def read_pdf(
    path: Path,
    file_id: str,
    filename: str,
    *,
    ocr_page: Callable[[Path, int], OcrResult] | None = None,
) -> Document:
    from ..config import settings

    pages: list[Page] = []
    warnings: list[str] = []
    with pdfplumber.open(path) as pdf:
        for i, p in enumerate(pdf.pages, start=1):
            pages.append(Page(number=i, text=p.extract_text(layout=True) or ""))
        meta = pdf.metadata or {}
    recover = ocr_page or (ocr_pdf_page if settings.ocr_enabled else None)
    for page in pages:
        if _has_usable_text(page.text, settings.ocr_min_text_chars):
            continue
        if recover is None:
            warnings.append(f"Page {page.number} has no usable text; configure GEMINI_API_KEY to enable vision OCR")
            continue
        try:
            result = recover(path, page.number)
            page.text = result.text
            page.ocr = True
            page.ocr_confidence = result.confidence
            page.ocr_blocks = result.blocks
            source = "cached Gemini vision OCR" if result.cached else "Gemini vision OCR"
            warnings.append(f"Page {page.number} text recovered by {source} ({result.confidence:.0%} confidence); review extracted values")
        except VisionOcrError as exc:
            warnings.append(f"Page {page.number} Gemini vision OCR failed: {exc}")
    if not any(_has_usable_text(page.text, 1) for page in pages):
        detail = "; ".join(warnings) if warnings else "no extractable text"
        raise NoTextError(f"PDF has no extractable text (scanned image). {detail}")
    return Document(
        file_id=file_id,
        filename=filename,
        kind="pdf",
        pages=pages,
        created=pdf_date(meta.get("CreationDate") or meta.get("ModDate")),
        warnings=warnings,
    )
