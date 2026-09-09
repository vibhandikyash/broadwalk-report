"""Yardi 'Rent Roll' summary block: occupancy, vacant and future/applicant counts, average rents."""
from __future__ import annotations

import re

from ..classify.classifier import Part
from ..readers.document import Sheet, as_fraction, norm, to_number
from .base import Extraction, ExtractionError
from .yardi_common import find_as_of, find_property

_ROW_PATTERNS = {
    "occupied": [r"^occupied units"],
    "vacant": [r"^total vacant", r"^vacant units"],
    "future": [r"^future residents", r"applicants"],
    "totals": [r"^totals?:?$"],
    "current": [r"^current/notice/vacant", r"^current residents"],
}


def _pick(found: dict[str, tuple], patterns: list[str]) -> tuple:
    for p in patterns:
        rx = re.compile(p)
        for label, v in found.items():
            if rx.search(label):
                return v
    return (None, None, None)


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    name, ref = find_property(sh)
    as_of = find_as_of(sh)
    simple = sh.header_block(["as of", "occupied units"], max_rows=1, search_rows=120)
    if simple is not None:
        hrow, _, headers = simple
        c_date, c_total = Sheet.col(headers, r"^as of$"), Sheet.col(headers, r"# of units", r"^units$")
        c_occ, c_vac = Sheet.col(headers, r"occupied units"), Sheet.col(headers, r"vacant units")
        snapshots = []
        for r in range(hrow + 1, sh.nrows):
            from ..readers.document import to_date
            date = to_date(sh.cell(r, c_date)) if c_date is not None else None
            total = to_number(sh.cell(r, c_total)) if c_total is not None else None
            occupied = to_number(sh.cell(r, c_occ)) if c_occ is not None else None
            if date and total is not None and occupied is not None:
                snapshots.append({"as_of": date.isoformat(), "property_name": name, "property_ref": ref,
                                  "total_units": total, "occupied_units": occupied,
                                  "vacant_units": to_number(sh.cell(r, c_vac)) if c_vac is not None else total - occupied,
                                  "occupancy_pct": occupied / total if total else None, "future_applicants": None})
        if snapshots:
            return Extraction(doc_type=part.doc_type, locator=part.locator, data={"_snapshots": snapshots})
    hb = sh.header_block(["summary groups", "# of"], max_rows=3, search_rows=120)
    if hb is None:
        raise ExtractionError("Rent Roll summary block ('Summary Groups' with '# Of Units') not found")
    hrow, k, headers = hb
    c_units = Sheet.col(headers, r"# of units", r"^units$")
    c_pct = Sheet.col(headers, r"% unit occupancy", r"occupancy")
    c_label = Sheet.col(headers, r"summary groups")
    if c_units is None:
        raise ExtractionError("'# Of Units' column not found in the summary block")
    if c_label is None:
        c_label = 0
    found: dict[str, tuple] = {}
    for r in range(hrow + k, min(hrow + k + 20, sh.nrows)):
        label = norm(sh.text(r, c_label))
        if not label:
            continue
        pct = to_number(sh.cell(r, c_pct)) if c_pct is not None else None
        found[label] = (to_number(sh.cell(r, c_units)), pct, r)
        if re.match(r"^totals?:?$", label):
            break
    occ_units, occ_pct, occ_row = _pick(found, _ROW_PATTERNS["occupied"])
    if occ_units is None:
        raise ExtractionError("'Occupied Units' row not found in the summary block")
    vac_units, _, _ = _pick(found, _ROW_PATTERNS["vacant"])
    fut_units, _, _ = _pick(found, _ROW_PATTERNS["future"])
    tot_units, _, _ = _pick(found, _ROW_PATTERNS["totals"])
    if tot_units is None:
        tot_units, _, _ = _pick(found, _ROW_PATTERNS["current"])
    total_units = tot_units if tot_units else ((occ_units or 0) + (vac_units or 0)) or None
    occupancy = as_fraction(occ_pct) if occ_pct is not None else (occ_units / total_units if total_units else None)

    avg_market = avg_resident = None
    pb = sh.header_block(["property", "total"], max_rows=3, search_rows=hrow)
    if pb is not None:
        prow, pk, ph = pb
        c_name, c_tot = Sheet.col(ph, r"^name$"), Sheet.col(ph, r"total units")
        c_mkt, c_res = Sheet.col(ph, r"average market rent"), Sheet.col(ph, r"average resident rent")
        for r in range(prow + pk, hrow):
            row_name = norm(sh.text(r, c_name)) if c_name is not None else ""
            is_property_row = bool(name) and row_name == norm(name)
            is_total_row = c_tot is not None and total_units and to_number(sh.cell(r, c_tot)) == total_units and bool(row_name)
            if is_property_row or is_total_row:
                avg_market = to_number(sh.cell(r, c_mkt)) if c_mkt is not None else None
                avg_resident = to_number(sh.cell(r, c_res)) if c_res is not None else None
                break
    warnings = [] if as_of else ["'As Of' date not found; this rent roll cannot be placed in time automatically"]
    return Extraction(
        doc_type=part.doc_type, locator=part.locator, warnings=warnings,
        data={"as_of": as_of, "property_name": name, "property_ref": ref, "total_units": total_units,
              "occupied_units": occ_units, "occupancy_pct": occupancy, "vacant_units": vac_units,
              "future_applicants": fut_units, "avg_market_rent": avg_market, "avg_resident_rent": avg_resident,
              "prov": {"occupied_row": occ_row, "summary_header_row": hrow}},
    )
