"""Structural check of a generated report PDF: page count, page size, embedded fonts, footers, expected text.

Usage: python scripts/check_pdf.py report.pdf [--pages 10] [--expect "Fannie Mae" --expect "Total capital spend"]
"""
from __future__ import annotations

import argparse
import sys

import pdfplumber


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", type=int, default=10)
    ap.add_argument("--expect", action="append", default=[])
    a = ap.parse_args()
    problems: list[str] = []
    with pdfplumber.open(a.pdf) as doc:
        n = len(doc.pages)
        if n != a.pages:
            problems.append(f"expected {a.pages} pages, found {n}")
        for i, p in enumerate(doc.pages, start=1):
            if abs(p.width - 720) > 0.5 or abs(p.height - 404.88) > 0.5:
                problems.append(f"page {i} is {p.width:.2f} x {p.height:.2f} pt, expected 720 x 404.88")
        text = "\n".join(p.extract_text() or "" for p in doc.pages)
        fonts = sorted({c["fontname"].split("+")[-1] for p in doc.pages for c in p.chars})
    for k in range(2, a.pages + 1):
        if text.count(f"{k:02d} / {a.pages}") != 1:
            problems.append(f"footer marker '{k:02d} / {a.pages}' missing or duplicated (content overflowed?)")
    if not any("SourceSerif" in f for f in fonts) or not any("JetBrainsMono" in f for f in fonts):
        problems.append(f"expected Source Serif 4 and JetBrains Mono to be embedded; found {fonts}")
    for s in a.expect:
        if s not in text:
            problems.append(f"expected text not found: {s!r}")
    print(f"{a.pdf}: {n} pages, fonts {', '.join(fonts)}")
    for p in problems:
        print("PROBLEM:", p)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
