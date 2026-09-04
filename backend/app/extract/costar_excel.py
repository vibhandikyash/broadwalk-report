"""CoStar submarket 'DataTable' export: one row per quarter with vacancy, asking rent, growth, pipeline."""
from __future__ import annotations

import re

from ..classify.classifier import Part
from ..readers.document import Sheet, as_fraction, to_number
from .base import Extraction, ExtractionError

PERIOD_RE = re.compile(r"^(\d{4})\s*Q([1-4])\s*([A-Za-z]+)?$")
COLUMNS = [
    ("vacancy", r"vacancy rate"), ("asking_rent", r"asking rent"), ("rent_growth", r"rent growth"),
    ("inventory", r"inventory"), ("under_construction", r"under constr(uction)? units"),
    ("uc_pct", r"under constr(uction)? %"), ("absorption_12m", r"absorp"),
    ("sale_price_unit", r"sale price/unit|price/unit"), ("sales_vol_12m", r"^12 mo sales vol$|sales vol(ume)?$"),
    ("cap_rate", r"cap rate"),
]
FRACTION_KEYS = ("vacancy", "rent_growth", "uc_pct", "cap_rate")


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    hb = sh.header_block(["period", "vacancy rate"], max_rows=1, search_rows=10)
    if hb is None:
        raise ExtractionError("No 'Period' / 'Vacancy Rate' header found")
    hrow, _, headers = hb
    c_period = Sheet.col(headers, r"^period$")
    colmap = {k: c for k, rx in COLUMNS if (c := Sheet.col(headers, rx)) is not None}
    if c_period is None or "vacancy" not in colmap:
        raise ExtractionError("'Period' or 'Vacancy Rate' column not found")
    series: list[dict] = []
    for r in range(hrow + 1, sh.nrows):
        m = PERIOD_RE.match(sh.text(r, c_period))
        if not m:
            continue
        rec: dict = {"period": sh.text(r, c_period), "year": int(m.group(1)), "quarter": int(m.group(2)),
                     "flag": (m.group(3) or "").upper(), "row": r}
        for k, c in colmap.items():
            rec[k] = to_number(sh.cell(r, c))
        for k in FRACTION_KEYS:
            if rec.get(k) is not None:
                rec[k] = as_fraction(rec[k])
        series.append(rec)
    if not series:
        raise ExtractionError("No quarterly rows found")
    return Extraction(doc_type=part.doc_type, locator=part.locator, data={"series": series, "columns": sorted(colmap)})
