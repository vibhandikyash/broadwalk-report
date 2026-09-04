"""CoStar 'Multi-Family Submarket Report' PDF: submarket name, market, report date, licensee, key stats,
annual trend peaks/troughs, recent deliveries, and the sale-comps table (which lists the subject's own trade)."""
from __future__ import annotations

import re

from ..classify.classifier import Part
from ..readers.document import to_date, to_number
from .base import Extraction, ExtractionError

_DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
_LICENSED_RE = re.compile(r"licensed to (.+?)\s+-\s+\d+", re.I)
_MARKET_RE = re.compile(r"^(?P<market>.+?)\s*-\s*(?P<state>[A-Z]{2})\s+USA$")
_OVERVIEW_HDR = re.compile(r"12 mo delivered units.*12 mo absorption units.*vacancy rate.*asking rent growth", re.I)
_OVERVIEW_VALS = re.compile(r"^([\d,]+) ([\d,()-]+) (-?[\d.]+)% (-?[\d.]+)%$")
_SUBMARKET_ROW = re.compile(r"^Submarket ([\d,]+) ([\d.]+)% \$([\d,]+) \$([\d,]+) \(?(-?[\d,]+)\)? ([\d,]+) ([\d,]+)$")
_TREND_ROW = re.compile(
    r"^(Vacancy|Asking Rent Growth|Effective Rent Growth) (-?[\d.]+)%(?: \(YOY\))? (-?[\d.]+)% (-?[\d.]+)% "
    r"(-?[\d.]+)% (\d{4} Q\d) (-?[\d.]+)% (\d{4} Q\d)$"
)
_SALE_ROW = re.compile(r"^(\d+) (\S+) (\d{4}) ([\d,]+) ([\d.]+)% (\d{1,2}/\d{1,2}/\d{4}) \$([\d,]+) \$([\d,]+) \$([\d,]+)$")
_DELIVERY_ROW = re.compile(r"^(\d+) (\d+) (\d+) ([A-Z][a-z]{2} \d{4}) ([A-Z][a-z]{2} \d{4})$")


def _pct(s: str) -> float | None:
    v = to_number(s)
    return None if v is None else round(v / 100, 6)


def parse_costar_text(pages: list[str]) -> dict:
    out: dict = {"submarket": None, "market": None, "state": None, "report_date": None, "licensed_to": None,
                 "overview": {}, "key_stats": {}, "trends": {}, "sales": [], "deliveries": []}
    for pno, text in enumerate(pages, start=1):
        raw_lines = [ln for ln in text.splitlines() if ln.strip()]
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw_lines]
        for i, line in enumerate(lines):
            low = line.lower()
            if out["submarket"] is None and "multi-family submarket report" in low and i + 1 < len(lines):
                out["submarket"] = lines[i + 1]
                if i + 2 < len(lines) and (mm := _MARKET_RE.match(lines[i + 2])):
                    out["market"], out["state"] = mm.group("market").strip(), mm.group("state")
            if out["report_date"] is None and (md := _DATE_RE.search(line)):
                d = to_date(md.group(1))
                out["report_date"] = d.isoformat() if d else None
            if out["licensed_to"] is None and (ml := _LICENSED_RE.search(line)):
                out["licensed_to"] = ml.group(1).strip()
            if _OVERVIEW_HDR.search(line) and i + 1 < len(lines) and (mo := _OVERVIEW_VALS.match(lines[i + 1])):
                out["overview"] = {"delivered_12m": to_number(mo.group(1)), "absorption_12m": to_number(mo.group(2)),
                                   "vacancy": _pct(mo.group(3)), "rent_growth_12m": _pct(mo.group(4))}
            if not out["key_stats"] and (ms := _SUBMARKET_ROW.match(line)):
                out["key_stats"] = {"inventory": to_number(ms.group(1)), "vacancy": _pct(ms.group(2)),
                                    "asking_rent": to_number(ms.group(3)), "effective_rent": to_number(ms.group(4)),
                                    "absorption": to_number(ms.group(5)), "delivered": to_number(ms.group(6)),
                                    "under_construction": to_number(ms.group(7))}
            if (mt := _TREND_ROW.match(line)):
                key = mt.group(1).lower().replace(" ", "_")
                out["trends"][key] = {"yoy": _pct(mt.group(2)), "historical": _pct(mt.group(3)), "forecast": _pct(mt.group(4)),
                                      "peak": _pct(mt.group(5)), "peak_when": mt.group(6), "trough": _pct(mt.group(7)),
                                      "trough_when": mt.group(8)}
            if i > 0 and (msale := _SALE_ROW.match(line)):
                d = to_date(msale.group(6))
                out["sales"].append({"rank": int(msale.group(1)), "name": lines[i - 1], "year_built": int(msale.group(3)),
                                     "units": to_number(msale.group(4)), "vacancy": _pct(msale.group(5)),
                                     "sale_date": d.isoformat() if d else None, "price": to_number(msale.group(7)),
                                     "price_per_unit": to_number(msale.group(8)), "price_psf": to_number(msale.group(9)),
                                     "page": pno})
            if i > 0 and (mdel := _DELIVERY_ROW.match(line)):
                name = re.split(r"\s{2,}", raw_lines[i - 1].strip())[0]
                out["deliveries"].append({"name": name, "units": int(mdel.group(2)), "stories": int(mdel.group(3)),
                                          "start": mdel.group(4), "complete": mdel.group(5), "page": pno})
    return out


def extract(part: Part) -> Extraction:
    data = parse_costar_text([p.text for p in part.pages])
    if not (data["submarket"] or data["key_stats"] or data["sales"]):
        raise ExtractionError("No submarket name, key statistics or sale comps found in the PDF")
    warnings = [] if data["sales"] else ["No sale comps table found; acquisition date and year built need another source"]
    return Extraction(doc_type=part.doc_type, locator=part.locator, data=data, warnings=warnings)
