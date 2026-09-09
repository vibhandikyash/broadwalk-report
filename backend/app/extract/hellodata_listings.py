"""HelloData unit-level listings export: one row per listing for the subject and its comps.

The payload is aggregated per property (counts and sums) so it stays small; monthly sums of leased
listings feed the rent-trend chart when no pre-built chart workbook is supplied.
"""
from __future__ import annotations

from ..classify.classifier import Part
from ..readers.document import Sheet, to_date, to_number
from .base import Extraction, ExtractionError


def _new_property(address: str | None, row: int) -> dict:
    return {"address": address, "first_row": row, "rows": 0, "leased": 0, "active": 0,
            "asking_sum": 0.0, "asking_n": 0, "effective_sum": 0.0, "effective_n": 0,
            "sqft_sum": 0.0, "sqft_n": 0, "monthly": {}, "min_leased": None, "max_leased": None}


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    hb = sh.header_block(["property name", "asking rent", "effective rent"], max_rows=1, search_rows=15)
    if hb is None:
        raise ExtractionError("No header with 'Property Name', 'Asking Rent' and 'Effective Rent' found")
    hrow, _, headers = hb
    c_name = Sheet.col(headers, r"^property name")
    c_addr = Sheet.col(headers, r"^address")
    c_sqft = Sheet.col(headers, r"^sqft$|^sq ?ft|square")
    c_leased = Sheet.col(headers, r"leased date")
    c_active = Sheet.col(headers, r"active listing")
    c_ask = Sheet.col(headers, r"^asking rent$")
    c_eff = Sheet.col(headers, r"^effective rent$")
    if c_name is None or c_ask is None:
        raise ExtractionError("'Property Name' or 'Asking Rent' column not found")
    props: dict[str, dict] = {}
    total = 0
    for r in range(hrow + 1, sh.nrows):
        name = sh.text(r, c_name)
        if not name:
            continue
        total += 1
        p = props.setdefault(name, _new_property(sh.text(r, c_addr) or None if c_addr is not None else None, r))
        p["rows"] += 1
        asking = to_number(sh.cell(r, c_ask))
        eff = to_number(sh.cell(r, c_eff)) if c_eff is not None else None
        sqft = to_number(sh.cell(r, c_sqft)) if c_sqft is not None else None
        if asking is not None:
            p["asking_sum"] += asking
            p["asking_n"] += 1
        if eff is not None:
            p["effective_sum"] += eff
            p["effective_n"] += 1
        if sqft:
            p["sqft_sum"] += sqft
            p["sqft_n"] += 1
        if c_active is not None and str(sh.cell(r, c_active)).strip().lower() in ("true", "1", "yes"):
            p["active"] += 1
        leased = to_date(sh.cell(r, c_leased)) if c_leased is not None else None
        if leased:
            p["leased"] += 1
            iso = leased.isoformat()
            p["min_leased"] = iso if p["min_leased"] is None or iso < p["min_leased"] else p["min_leased"]
            p["max_leased"] = iso if p["max_leased"] is None or iso > p["max_leased"] else p["max_leased"]
            if asking is not None and eff is not None and sqft:
                m = p["monthly"].setdefault(leased.strftime("%Y-%m"), {"n": 0, "asking_sum": 0.0, "effective_sum": 0.0, "sqft_sum": 0.0})
                m["n"] += 1
                m["asking_sum"] += asking
                m["effective_sum"] += eff
                m["sqft_sum"] += sqft
    if not props:
        raise ExtractionError("No listing rows found under the header")
    return Extraction(doc_type=part.doc_type, locator=part.locator,
                      data={"properties": props, "row_count": total, "header_row": hrow})
