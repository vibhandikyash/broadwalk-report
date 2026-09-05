"""Structural and raster check of a generated report PDF.

Structure: page count, page size, embedded fonts, no Type 3 fonts, the end-of-page footer markers, expected text.
Raster: every page is rendered with PDFium (the engine behind Chrome's viewer) and each extracted word's box must
contain ink, so text that survives extraction but does not draw (missing or broken glyphs) fails the check.

Usage: python scripts/check_pdf.py report.pdf [--pages 10] [--expect "Fannie Mae" --expect "Total capital spend"]
"""
from __future__ import annotations

import argparse
import math
import sys

import pdfplumber
import pypdfium2 as pdfium
from pdfminer.pdftypes import resolve1

SCALE = 2.0        # 144 dpi
INK_MIN = 0.02     # share of dark pixels a word's box must contain
DARK = 170         # 8-bit luminance below which a pixel counts as ink


def _type3_fonts(page) -> list[str]:
    out = []
    fonts = resolve1((page.page_obj.resources or {}).get("Font")) or {}
    for name, ref in fonts.items():
        fd = resolve1(ref) or {}
        if str(resolve1(fd.get("Subtype"))) == "/Type3":
            base = resolve1(fd.get("Name")) or resolve1(fd.get("BaseFont")) or name
            out.append(str(base))
    return out


def _words_without_ink(page, image) -> list[str]:
    gray = image.convert("L")
    w_img, h_img = gray.size
    missing = []
    for w in page.extract_words(keep_blank_chars=False):
        if w["bottom"] - w["top"] < 3 or not any(ch.isalnum() for ch in w["text"]):
            continue  # separators such as the middle dot are too small for the ink share to mean anything
        box = (max(0, int(w["x0"] * SCALE)), max(0, int(w["top"] * SCALE)),
               min(w_img, math.ceil(w["x1"] * SCALE)), min(h_img, math.ceil(w["bottom"] * SCALE)))
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        pixels = gray.crop(box).tobytes()  # one luminance byte per pixel
        dark = sum(1 for px in pixels if px < DARK) / len(pixels)
        if dark < INK_MIN:
            missing.append(w["text"])
    return missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", type=int, default=10)
    ap.add_argument("--expect", action="append", default=[])
    a = ap.parse_args()
    problems: list[str] = []
    raster = pdfium.PdfDocument(a.pdf)
    with pdfplumber.open(a.pdf) as doc:
        n = len(doc.pages)
        if n != a.pages:
            problems.append(f"expected {a.pages} pages, found {n}")
        text_parts, fonts = [], set()
        for i, p in enumerate(doc.pages, start=1):
            if abs(p.width - 720) > 0.5 or abs(p.height - 404.88) > 0.5:
                problems.append(f"page {i} is {p.width:.2f} x {p.height:.2f} pt, expected 720 x 404.88")
            text_parts.append(p.extract_text() or "")
            fonts |= {c["fontname"].split("+")[-1] for c in p.chars}
            t3 = _type3_fonts(p)
            if t3:
                problems.append(f"page {i} uses Type 3 font(s) {sorted(set(t3))}: glyphs drawn as outlines, which some viewers mishandle (check font-synthesis)")
            image = raster[i - 1].render(scale=SCALE).to_pil()
            missing = _words_without_ink(p, image)
            if missing:
                problems.append(f"page {i}: {len(missing)} word(s) extract but draw no ink when rasterised, e.g. {missing[:5]}")
    text = "\n".join(text_parts)
    for k in range(2, a.pages + 1):
        if text.count(f"{k:02d} / {a.pages}") != 1:
            problems.append(f"footer marker '{k:02d} / {a.pages}' missing or duplicated (content overflowed?)")
    if not any("SourceSerif" in f for f in fonts) or not any("JetBrainsMono" in f for f in fonts):
        problems.append(f"expected Source Serif 4 and JetBrains Mono to be embedded; found {sorted(fonts)}")
    for s in a.expect:
        if s not in text:
            problems.append(f"expected text not found: {s!r}")
    print(f"{a.pdf}: {n} pages, fonts {', '.join(sorted(fonts))}, rasterised with PDFium at {int(72 * SCALE)} dpi")
    for p in problems:
        print("PROBLEM:", p)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
