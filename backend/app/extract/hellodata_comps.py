"""HelloData comp-set summary.

Two shapes feed the same payload: the 'Rent Comps' sheet of the full report workbook (year built, units,
leased %) and the one-page 'Rents by Unit Type' PDF (leased/active counts, average rent, NER, concession %).
"""
from __future__ import annotations

import re

from ..classify.classifier import Part
from ..readers.document import Sheet, as_fraction, norm, to_number
from .base import Extraction, ExtractionError

_PDF_ROW = re.compile(
    r"^(?P<name>.+?) (?P<leased>\d+) (?P<active>\d+) (?P<dom>\d+) (?P<minsf>[\d,]+) (?P<avgsf>[\d,]+) (?P<maxsf>[\d,]+) "
    r"\$(?P<minrent>[\d,]+) \$(?P<avgrent>[\d,]+) \$(?P<maxrent>[\d,]+) \$(?P<psf>[\d.]+) \$(?P<ner>[\d,]+) "
    r"\$(?P<nerpsf>[\d.]+) (?P<conc>[\d.]+)%"
)


def _int(v: float | None) -> int | None:
    return int(round(v)) if v is not None else None


def _from_sheet(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    hb = sh.header_block(["property", "units"], max_rows=1, search_rows=30)
    if hb is None:
        raise ExtractionError("No 'Property' header found")
    hrow, _, headers = hb
    c_name = Sheet.col(headers, r"^property$", r"^property name")
    c_addr, c_built = Sheet.col(headers, r"^address"), Sheet.col(headers, r"built")
    c_units = Sheet.col(headers, r"^# ?units$", r"^units$")
    c_sqft, c_leased = Sheet.col(headers, r"avg sqft|avg sf"), Sheet.col(headers, r"^leased %")
    c_occupied = Sheet.col(headers, r"^occupied units$")
    c_leased_units = Sheet.col(headers, r"^leased units$")
    c_asking = Sheet.col(headers, r"^asking rent$")
    c_effective = Sheet.col(headers, r"^effective rent$")
    c_stories = Sheet.col(headers, r"stories")
    if c_name is None:
        raise ExtractionError("'Property' column not found")
    comps: list[dict] = []
    average: dict | None = None
    blanks = 0
    for r in range(hrow + 1, sh.nrows):
        name = sh.text(r, c_name)
        if not name:
            blanks += 1
            if blanks > 2:
                break
            continue
        blanks = 0
        units = _int(to_number(sh.cell(r, c_units))) if c_units is not None else None
        leased_units = _int(to_number(sh.cell(r, c_leased_units))) if c_leased_units is not None else None
        rec = {
            "name": name, "address": (sh.text(r, c_addr) or None) if c_addr is not None else None,
            "year_built": _int(to_number(sh.cell(r, c_built))) if c_built is not None else None,
            "units": units,
            "stories": _int(to_number(sh.cell(r, c_stories))) if c_stories is not None else None,
            "avg_sqft": to_number(sh.cell(r, c_sqft)) if c_sqft is not None else None,
            "leased_pct": (as_fraction(to_number(sh.cell(r, c_leased))) if c_leased is not None
                           else leased_units / units if leased_units is not None and units else None),
            "occupied_units": _int(to_number(sh.cell(r, c_occupied))) if c_occupied is not None else None,
            "leased_units": leased_units,
            "asking_rent": to_number(sh.cell(r, c_asking)) if c_asking is not None else None,
            "effective_rent": to_number(sh.cell(r, c_effective)) if c_effective is not None else None,
            "row": r,
        }
        if norm(name).startswith("comp average"):
            average = rec
        else:
            comps.append(rec)
    if not comps:
        raise ExtractionError("No comp rows found")
    return Extraction(doc_type=part.doc_type, locator=part.locator, data={"comps": comps, "average": average, "source": "sheet"})


def _from_pdf(part: Part) -> Extraction:
    comps: list[dict] = []
    for page in part.pages:
        for line in page.lines:
            m = _PDF_ROW.match(re.sub(r"\s+", " ", line).strip())
            if not m:
                continue
            g = m.groupdict()
            comps.append({
                "name": g["name"].strip(), "address": None, "year_built": None, "units": None, "stories": None,
                "avg_sqft": to_number(g["avgsf"]), "leased_pct": None,
                "leased_count": int(g["leased"]), "active_count": int(g["active"]),
                "avg_rent": to_number(g["avgrent"]), "ner": to_number(g["ner"]),
                "concession_pct": (to_number(g["conc"]) or 0) / 100, "page": page.number,
            })
    if not comps:
        raise ExtractionError("No 'Rents by Unit Type' rows found in the PDF")
    return Extraction(doc_type=part.doc_type, locator=part.locator, data={"comps": comps, "average": None, "source": "pdf"})


def extract(part: Part) -> Extraction:
    return _from_sheet(part) if part.sheet is not None else _from_pdf(part)
