"""Dated account observations from an annual financial statement."""
from __future__ import annotations

from ..classify.classifier import Part
from ..readers.document import norm, to_date, to_number
from .base import Extraction, ExtractionError


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    periods: dict[int, str] = {}
    header_row = None
    for r in range(min(sh.nrows - 1, 100)):
        if not any("eoy" in norm(value) for value in sh.rows[r] if value is not None):
            continue
        dates = {c: date.isoformat() for c in range(len(sh.rows[r + 1]))
                 if (date := to_date(sh.cell(r + 1, c))) is not None and "eoy" in norm(sh.cell(r, c))}
        if len(dates) >= 2:
            periods, header_row = dates, r
            break
    if header_row is None:
        raise ExtractionError("Annual statement has no dated end-of-year columns")

    lines = []
    for r in range(header_row + 2, sh.nrows):
        values = {date: number for c, date in periods.items()
                  if (number := to_number(sh.cell(r, c))) is not None}
        if not values:
            continue
        labels = [(c, sh.text(r, c)) for c in range(min(periods)) if sh.text(r, c)]
        if not labels:
            continue
        lines.append({"account": labels[0][1] if len(labels) > 1 else None,
                      "label": labels[-1][1].strip(), "row": r, "values": values})
    if not lines:
        raise ExtractionError("Annual statement has no account values under its dated columns")
    return Extraction(doc_type=part.doc_type, locator=part.locator,
                      data={"periods": list(periods.values()), "header_row": header_row, "lines": lines},
                      warnings=["Annual account values are retained as source observations; they are not quarterly actuals"])
