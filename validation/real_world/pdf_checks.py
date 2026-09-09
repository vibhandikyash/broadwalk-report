"""PDF inspection helpers shared by the validation harness: per-page text, headings, images, raster ink and Type 3 fonts."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pdfplumber
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[2]
HEADINGS = ["Property Description", "Property Summary & Business Plan", "Financing Overview", "Financial & Capital Commentary",
            "Financial Performance", "Capital Projects", "Submarket Comparison", "Occupancy & Leasing", "Status Update"]  # pages 2..10
# Each fixed page is followed by its data-sources sheet(s), so a physical page index is not a report
# page number. The sheets carry this tag in their header; the fixed pages never do.
PROVENANCE_MARK = "SOURCE PROVENANCE"


def _check_pdf_module():
    spec = importlib.util.spec_from_file_location("check_pdf", ROOT / "scripts" / "check_pdf.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def page_texts(pdf_path: Path) -> list[str]:
    doc = pdfium.PdfDocument(str(pdf_path))
    texts = []
    for page in doc:
        tp = page.get_textpage()
        texts.append(tp.get_text_range())
        tp.close()
        page.close()
    doc.close()
    return texts


def image_counts(pdf_path: Path) -> list[int]:
    with pdfplumber.open(str(pdf_path)) as doc:
        return [len(p.images) for p in doc.pages]


def first_image_digest(pdf_path: Path, page_index: int) -> str | None:
    import hashlib

    with pdfplumber.open(str(pdf_path)) as doc:
        imgs = doc.pages[page_index].images
        if not imgs:
            return None
        return hashlib.sha256(imgs[0]["stream"].get_data()).hexdigest()


def render_pages(pdf_path: Path, out_dir: Path, scale: float = 1.5) -> list[Path]:
    """One PNG per page (108 dpi at scale 1.5), the evidence a human inspects."""
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument(str(pdf_path))
    paths = []
    for i, page in enumerate(doc, start=1):
        path = out_dir / f"page-{i:02d}.png"
        page.render(scale=scale).to_pil().save(path)
        paths.append(path)
        page.close()
    doc.close()
    return paths


def structural_problems(pdf_path: Path, pages: int = 10) -> list[str]:
    """Page size, embedded fonts, no Type 3 fonts, footer markers, and every word draws ink (PDFium raster)."""
    m = _check_pdf_module()
    problems: list[str] = []
    raster = pdfium.PdfDocument(str(pdf_path))
    with pdfplumber.open(str(pdf_path)) as doc:
        if len(doc.pages) != pages:
            problems.append(f"expected {pages} pages, found {len(doc.pages)}")
        fonts: set[str] = set()
        text_parts = []
        for i, p in enumerate(doc.pages, start=1):
            if abs(p.width - 720) > 0.5 or abs(p.height - 404.88) > 0.5:
                problems.append(f"page {i} is {p.width:.2f} x {p.height:.2f} pt")
            fonts |= {c["fontname"].split("+")[-1] for c in p.chars}
            text_parts.append(p.extract_text() or "")
            t3 = m._type3_fonts(p)
            if t3:
                problems.append(f"page {i} uses Type 3 fonts {sorted(set(t3))}")
            missing = m._words_without_ink(p, raster[i - 1].render(scale=m.SCALE).to_pil())
            if missing:
                problems.append(f"page {i}: {len(missing)} word(s) draw no ink, e.g. {missing[:4]}")
        text = "\n".join(text_parts)
    for k in range(2, pages + 1):
        if len(m.footer_marks(text, k, pages)) != 1:
            problems.append(f"footer marker '{k:02d} / {pages}' missing or duplicated")
    if not any("SourceSerif" in f for f in fonts) or not any("JetBrainsMono" in f for f in fonts):
        problems.append(f"expected fonts not embedded: {sorted(fonts)}")
    return problems


def report_page_indices(texts: list[str]) -> list[int]:
    """Positions of the fixed report pages, with the interleaved data-sources sheets filtered out."""
    return [i for i, t in enumerate(texts) if PROVENANCE_MARK not in t]


def heading_problems(texts: list[str]) -> list[str]:
    """`texts` must already be the fixed report pages (see report_page_indices)."""
    problems = []
    for i, heading in enumerate(HEADINGS, start=2):
        if i > len(texts) or heading.casefold() not in texts[i - 1].casefold():
            problems.append(f"page {i}: heading {heading!r} not found")
    return problems


def evidence(pdf_path: Path) -> dict[str, Any]:
    return {"page_count": len(page_texts(pdf_path)), "images_per_page": image_counts(pdf_path)}
