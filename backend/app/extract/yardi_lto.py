"""Yardi Lease Trade-Out report (RRG-10658 style): 'Lease Renewals', 'Move Ins', 'Unit Transfers' sections.

Each section has a header row with 'Resident Name' and 'Lease Rent'. A group row above it says where the
'Previous Lease Term' columns start; when that row is absent, the second occurrence of a duplicated header
name is treated as the previous-term column.
"""
from __future__ import annotations

import re

from ..classify.classifier import Part
from ..readers.document import norm, to_date, to_number
from .base import Extraction, ExtractionError

SECTION_TITLES = {"renewals": r"lease renewals?", "move_ins": r"move[- ]?ins?", "transfers": r"unit transfers?"}
RANGE_RE = re.compile(r"between\s+(\d{4}-\d{2}-\d{2})\s+and\s+(\d{4}-\d{2}-\d{2})", re.I)
HEADER_MAP = [
    ("resident_name", r"^resident name"), ("unit_type", r"^unit type"), ("sqft", r"^sq ?ft"), ("unit", r"^unit$"),
    ("start", r"renewal start|lease start|move.?in date|start date"), ("term", r"^lease term"),
    ("market_rent", r"^market rent"), ("lease_rent", r"^lease rent"), ("concessions", r"^total concessions"),
    ("months_free", r"months free"), ("effective_rent", r"^effective rent$"), ("rent_change", r"^rent change"),
    ("pct_change", r"^% change"),
]
PREV_KEYS = {"lease_rent", "concessions", "term", "effective_rent"}


def _map_columns(headers: list[str], prev_start: int | None) -> dict[str, int]:
    colmap: dict[str, int] = {}
    for i, h in enumerate(headers):
        for key, rx in HEADER_MAP:
            if re.search(rx, h):
                if key in PREV_KEYS and ((prev_start is not None and i >= prev_start) or key in colmap):
                    key = "prev_" + key
                colmap.setdefault(key, i)
                break
    return colmap


def _section_title(sh, hrow: int) -> tuple[str | None, dict | None]:
    title, period = None, None
    for r in range(hrow - 1, max(-1, hrow - 8), -1):
        t = norm(sh.row_text(r))
        if not t:
            continue
        m = RANGE_RE.search(t)
        if m:
            if period is None:
                period = {"start": m.group(1), "end": m.group(2)}
            continue  # a date-range subtitle ('Move In between ...') is not the section title
        for key, rx in SECTION_TITLES.items():
            if re.search(rx, t) and title is None:
                title = key
        if title and period:
            break
    return title, period


def extract(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    header_rows = [r for r in range(sh.nrows)
                   if "resident name" in norm(sh.row_text(r)) and "lease rent" in norm(sh.row_text(r))]
    if not header_rows:
        raise ExtractionError("No section header with 'Resident Name' and 'Lease Rent' found")
    header_set = set(header_rows)
    sections: dict[str, dict] = {}
    period: dict | None = None
    property_name: str | None = None
    for hrow in header_rows:
        headers = [norm(sh.text(hrow, c)) for c in range(len(sh.rows[hrow]))]
        group = [norm(sh.text(hrow - 1, c)) for c in range(len(sh.rows[hrow - 1]))] if hrow > 0 else []
        prev_start = next((i for i, g in enumerate(group) if "previous" in g), None)
        cm = _map_columns(headers, prev_start)
        if "unit_type" not in cm or "lease_rent" not in cm:
            continue
        title, sec_period = _section_title(sh, hrow)
        period = period or sec_period
        title = title or f"section_{hrow}"
        rows: list[dict] = []
        for r in range(hrow + 1, sh.nrows):
            if r in header_set:
                break
            rt = norm(sh.row_text(r))
            if not rt:
                continue
            if "averages for" in rt:
                continue
            if not sh.has_numbers(r) and any(re.search(rx, rt) for rx in SECTION_TITLES.values()):
                break
            unit_type = sh.text(r, cm["unit_type"])
            num = lambda key: to_number(sh.cell(r, cm[key])) if key in cm else None  # noqa: E731
            lease_rent, prev_rent = num("lease_rent"), num("prev_lease_rent")
            if not unit_type or (lease_rent is None and prev_rent is None):
                continue
            if property_name is None and sh.text(r, 0) and to_number(sh.cell(r, 0)) is None:
                property_name = sh.text(r, 0)
            start = to_date(sh.cell(r, cm["start"])) if "start" in cm else None
            rows.append({
                "unit_type": unit_type, "sqft": num("sqft"), "unit": sh.text(r, cm["unit"]) if "unit" in cm else None,
                "start": start.isoformat() if start else None, "term": num("term"), "market_rent": num("market_rent"),
                "lease_rent": lease_rent, "concessions": num("concessions"), "months_free": num("months_free"),
                "effective_rent": num("effective_rent"), "prev_lease_rent": prev_rent,
                "prev_concessions": num("prev_concessions"), "prev_term": num("prev_term"),
                "prev_effective_rent": num("prev_effective_rent"), "rent_change": num("rent_change"),
                "pct_change": num("pct_change"), "row": r,
            })
        key, n = title, 2
        while key in sections:  # never overwrite an earlier section with the same title
            key, n = f"{title}_{n}", n + 1
        sections[key] = {"rows": rows, "header_row": hrow, "columns": sorted(cm)}
    if not sections:
        raise ExtractionError("No usable trade-out sections found")
    warnings = [] if period else ["Lease date range not found above the section headers"]
    return Extraction(doc_type=part.doc_type, locator=part.locator, warnings=warnings,
                      data={"period": period, "property_name": property_name, "sections": sections})
