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
from .yardi_common import find_property

SECTION_TITLES = {"renewals": r"lease renewals?", "move_ins": r"move[- ]?ins?", "transfers": r"unit transfers?"}
RANGE_RE = re.compile(r"between\s+(\d{4}-\d{2}-\d{2})\s+and\s+(\d{4}-\d{2}-\d{2})", re.I)
NOT_PROPERTY_HEADERS = {"source", "section", "type", "status", "report", "category"}


def _looks_like_section(text: str) -> bool:
    """'Move Ins' / 'Lease Renewals' in a text column are section labels, not a property name."""
    t = norm(text)
    return any(re.search(rx, t) for rx in SECTION_TITLES.values()) or t in ("total", "totals", "averages")
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
    generic = sh.header_block(["lease id", "event type", "lease rent"], max_rows=1, search_rows=120)
    if generic is not None:
        hrow, _, headers = generic
        patterns = {
            "lease_id": r"^lease id$", "property_name": r"^property name$", "event_type": r"^event type$",
            "unit": r"^unit$", "unit_type": r"^unit type$", "resident_name": r"resident name",
            "start": r"lease start", "prev_lease_rent": r"previous lease rent", "lease_rent": r"^lease rent$",
            "effective_rent": r"^effective rent$", "sqft": r"sq ?ft", "term": r"lease term",
        }
        columns = {key: next((i for i, header in enumerate(headers) if re.search(rx, header)), None)
                   for key, rx in patterns.items()}
        sections = {"move_ins": {"rows": []}, "renewals": {"rows": []}, "transfers": {"rows": []}}
        property_name = None
        for r in range(hrow + 1, sh.nrows):
            event = norm(sh.text(r, columns["event_type"])) if columns["event_type"] is not None else ""
            section = "move_ins" if event in ("new", "move in", "move-in") else "renewals" if event.startswith("renew") else "transfers" if event.startswith("transfer") else None
            if section is None:
                continue
            def text_value(key: str):
                column = columns[key]
                return sh.text(r, column) if column is not None else None
            def number_value(key: str):
                column = columns[key]
                return to_number(sh.cell(r, column)) if column is not None else None
            start = to_date(sh.cell(r, columns["start"])) if columns["start"] is not None else None
            property_name = property_name or text_value("property_name")
            sections[section]["rows"].append({
                "lease_id": text_value("lease_id"), "unit": text_value("unit"), "unit_type": text_value("unit_type"),
                "resident_name": text_value("resident_name"), "start": start.isoformat() if start else None,
                "prev_lease_rent": number_value("prev_lease_rent"), "lease_rent": number_value("lease_rent"),
                "effective_rent": number_value("effective_rent"), "sqft": number_value("sqft"),
                "term": number_value("term"), "row": r,
            })
        period_match = re.search(r"period\s*=\s*(\d{4}-\d{2}-\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})", sh.head_text(hrow), re.I)
        period = {"start": period_match.group(1), "end": period_match.group(2)} if period_match else None
        return Extraction(doc_type=part.doc_type, locator=part.locator,
                          data={"period": period, "property_name": property_name,
                                "property_ref": find_property(sh, max_row=hrow)[1], "sections": sections})
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
            if property_name is None:  # property name sits in a text column left of the resident name
                for c in range(cm.get("resident_name", 0)):
                    val = sh.text(r, c)
                    if val and to_number(sh.cell(r, c)) is None and not _looks_like_section(val) and headers[c] not in NOT_PROPERTY_HEADERS:
                        property_name = val
                        break
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
