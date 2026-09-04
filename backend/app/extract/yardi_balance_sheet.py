"""Yardi 'Balance Sheet (With Period Change)'."""
from __future__ import annotations

from ..classify.classifier import Part
from ..readers.document import Sheet
from .base import Extraction, ExtractionError
from .yardi_common import parse_period, walk_lines


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    hb = sh.header_block(["balance", "beginning"], max_rows=2, search_rows=15)
    if hb is None:
        raise ExtractionError("No 'Balance' / 'Beginning' header found")
    hrow, k, headers = hb
    colmap = {
        "current": Sheet.col(headers, r"^balance", r"current"),
        "beginning": Sheet.col(headers, r"beginning"),
        "change": Sheet.col(headers, r"change"),
    }
    colmap = {a: b for a, b in colmap.items() if b is not None}
    if "current" not in colmap:
        raise ExtractionError("No current-balance column found")
    lines = walk_lines(sh, hrow + k - 1, colmap)
    if not lines:
        raise ExtractionError("No balance sheet lines found")
    return Extraction(doc_type=part.doc_type, locator=part.locator,
                      data={"period": parse_period(sh.head_text(6)), "columns": sorted(colmap), "lines": lines})
