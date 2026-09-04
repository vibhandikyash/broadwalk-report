"""Yardi 'Budget Comparison' (P&L with PTD/YTD or MTD/PTD actual vs budget, plus capital sections)."""
from __future__ import annotations

from ..classify.classifier import Part
from ..readers.document import Sheet
from .base import Extraction, ExtractionError
from .yardi_common import find_property_ref, parse_period, walk_lines

COLUMN_PATTERNS = [
    ("mtd_actual", r"^mtd actual"), ("mtd_budget", r"^mtd budget"),
    ("ptd_actual", r"^ptd actual"), ("ptd_budget", r"^ptd budget"),
    ("ytd_actual", r"^ytd actual"), ("ytd_budget", r"^ytd budget"),
    ("annual_budget", r"^annual"),
]


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    hb = sh.header_block(["actual", "budget"], max_rows=1, search_rows=15)
    if hb is None:
        raise ExtractionError("No header row containing 'Actual' and 'Budget' found in the first 15 rows")
    hrow, _, headers = hb
    colmap = {key: c for key, rx in COLUMN_PATTERNS if (c := Sheet.col(headers, rx)) is not None}
    if not ({"ptd_actual", "mtd_actual"} & colmap.keys()):
        raise ExtractionError("No 'PTD Actual' or 'MTD Actual' column found")
    lines = walk_lines(sh, hrow, colmap)
    if not lines:
        raise ExtractionError("No line items found under the header row")
    head = sh.head_text(6)
    period = parse_period(head)
    warnings = [] if period else ["Reporting period not found in the header; it will be taken from another file"]
    return Extraction(
        doc_type=part.doc_type, locator=part.locator, warnings=warnings,
        data={"period": period, "property_ref": find_property_ref(head), "columns": sorted(colmap),
              "header_row": hrow, "lines": lines},
    )
