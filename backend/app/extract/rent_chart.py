"""Pre-built rent trend workbook: monthly subject vs comp-set lease counts and gross/effective $/SF."""
from __future__ import annotations

from ..classify.classifier import Part
from ..readers.document import Sheet, norm, to_date, to_number
from .base import Extraction, ExtractionError


def _month_key(v) -> str | None:
    d = to_date(v)
    return d.strftime("%Y-%m") if d else None


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    hb = sh.header_block(["month", "gross psf", "effective psf"], max_rows=1, search_rows=15)
    if hb is None:
        raise ExtractionError("No 'Month' / 'Gross PSF' / 'Effective PSF' header found")
    hrow, _, headers = hb
    c_month = Sheet.col(headers, r"^month")
    counts = Sheet.cols_all(headers, r"lease count|# ?leases|\bcount\b")
    gross = Sheet.cols_all(headers, r"gross psf")
    eff = Sheet.cols_all(headers, r"effective psf")
    if c_month is None or not gross or not eff:
        raise ExtractionError("Month, Gross PSF or Effective PSF column missing")

    def series_name(c: int) -> str:
        return sh.text(hrow, c).split("/")[0].strip()

    months: list[dict] = []
    totals: dict | None = None
    last_row = hrow
    for r in range(hrow + 1, sh.nrows):
        txt = sh.text(r, c_month)
        if not txt:
            if months:
                last_row = r
                break
            continue
        num = lambda cols, i: to_number(sh.cell(r, cols[i])) if len(cols) > i else None  # noqa: E731
        rec = {"subject_n": num(counts, 0), "subject_gross_psf": num(gross, 0), "subject_eff_psf": num(eff, 0),
               "comp_n": num(counts, 1), "comp_gross_psf": num(gross, 1), "comp_eff_psf": num(eff, 1), "row": r}
        if "total" in norm(txt):
            totals = rec
            last_row = r
            break
        key = _month_key(sh.cell(r, c_month))
        if key is None:
            continue
        months.append({"month": key, **rec})
    if not months:
        raise ExtractionError("No monthly rows found")
    notes = []
    for r in range(last_row + 1, sh.nrows):
        t = sh.text(r, 0) or sh.text(r, 1)
        if t and not sh.has_numbers(r):
            notes.append(t)
        if len(notes) >= 60:
            break
    return Extraction(doc_type=part.doc_type, locator=part.locator, data={
        "title": sh.text(0, 0), "subtitle": sh.text(1, 0), "subject_name": series_name(gross[0]),
        "comp_name": series_name(gross[1]) if len(gross) > 1 else None, "months": months, "totals": totals, "notes": notes,
    })
