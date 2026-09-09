"""Yardi 'Market Rent Schedule': per unit type units, sqft, market rent, occupied units, average resident rent."""
from __future__ import annotations

import re

from ..classify.classifier import Part
from ..readers.document import Sheet, norm, to_number
from .base import Extraction, ExtractionError
from .yardi_common import find_as_of, find_property

_CODE_RE = re.compile(r"^(?P<label>.*?)\s*\((?P<code>[A-Za-z0-9.\-_/ ]+)\)\s*$")
_X_RE = re.compile(r"^\s*(\d+)\s*x\s*(\d+(?:\.\d)?)", re.I)
_BED_RE = re.compile(r"(\d+)\s*(?:bed|br\b|bd\b|bdrm)", re.I)
_BATH_RE = re.compile(r"(\d+(?:\.\d)?)\s*(?:bath|ba\b)", re.I)


def parse_unit_type(label: str) -> tuple[str, str | None, int | None, float | None]:
    """'1 Bedroom 1 Bathroom (BWK.A1)' -> ('1 Bedroom 1 Bathroom', 'BWK.A1', 1, 1.0)."""
    label = label.strip()
    code = None
    m = _CODE_RE.match(label)
    if m:
        label, code = m.group("label").strip(), m.group("code").strip()
    low = label.lower()
    beds: int | None = None
    baths: float | None = None
    if (mx := _X_RE.match(low)):
        beds, baths = int(mx.group(1)), float(mx.group(2))
    else:
        if (mb := _BED_RE.search(low)):
            beds = int(mb.group(1))
        elif "studio" in low or "efficiency" in low:
            beds = 0
        if (mt := _BATH_RE.search(low)):
            baths = float(mt.group(1))
    return label, code, beds, baths


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    as_of = find_as_of(sh)
    hb = sh.header_block(["unit type"], max_rows=3, search_rows=120)
    if hb is None:
        raise ExtractionError("No 'Unit Type' / 'Units' header found")
    hrow, k, headers = hb
    name, ref = find_property(sh, max_row=hrow)
    c_label = Sheet.col(headers, r"^unit type$")
    c_units = Sheet.col(headers, r"^units$", r"# of units")
    if c_label is None or c_units is None:
        raise ExtractionError("'Unit Type' or 'Units' column not found")
    c_sqft = Sheet.col(headers, r"sq ?ft|sqft|square")
    c_occ = Sheet.col(headers, r"occupied")
    c_arr = Sheet.col(headers, r"^average resident rent", r"^avg resident rent", r"resident rent")
    c_mkt = Sheet.col(headers, r"^unit type rent$", r"^market rent")
    c_date = Sheet.col(headers, r"^as of$")
    unit_types: list[dict] = []
    total: dict | None = None
    for r in range(hrow + k, sh.nrows):
        label = sheet_text = sh.text(r, c_label)
        if not label:
            continue
        rec = {
            "units": to_number(sh.cell(r, c_units)),
            "sqft": to_number(sh.cell(r, c_sqft)) if c_sqft is not None else None,
            "market_rent": to_number(sh.cell(r, c_mkt)) if c_mkt is not None else None,
            "occupied_units": to_number(sh.cell(r, c_occ)) if c_occ is not None else None,
            "avg_resident_rent": to_number(sh.cell(r, c_arr)) if c_arr is not None else None,
            "row": r,
        }
        if c_date is not None:
            from ..readers.document import to_date
            date = to_date(sh.cell(r, c_date))
            rec["as_of"] = date.isoformat() if date else None
        nl = norm(label)
        if nl.startswith("grand total") or nl.startswith("total"):
            total = rec
            break
        if rec["units"] is None:
            continue
        clean, code, beds, baths = parse_unit_type(sheet_text)
        unit_types.append({"label": clean, "code": code, "bedrooms": beds, "bathrooms": baths, **rec})
    if not unit_types:
        raise ExtractionError("No unit-type rows found")
    dated = sorted({u.get("as_of") for u in unit_types if u.get("as_of")})
    if dated:
        snapshots = []
        for date in dated:
            rows = [u for u in unit_types if u.get("as_of") == date]
            snapshots.append({"as_of": date, "property_name": name, "property_ref": ref, "unit_types": rows,
                              "total": {"units": sum(u["units"] or 0 for u in rows),
                                        "sqft": sum((u["sqft"] or 0) * (u["units"] or 0) for u in rows) / sum(u["units"] or 0 for u in rows),
                                        "avg_resident_rent": sum((u["avg_resident_rent"] or 0) * (u["units"] or 0) for u in rows) / sum(u["units"] or 0 for u in rows)}})
        return Extraction(doc_type=part.doc_type, locator=part.locator, data={"_snapshots": snapshots})
    warnings = [] if as_of else ["'As Of' date not found"]
    if any(u["bedrooms"] is None for u in unit_types):
        warnings.append("Bedroom count could not be parsed for some unit types; they are grouped as 'Other'")
    return Extraction(doc_type=part.doc_type, locator=part.locator, warnings=warnings,
                      data={"as_of": as_of, "property_name": name, "property_ref": ref, "unit_types": unit_types, "total": total})
