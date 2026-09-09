"""Slate investor-portal exports (capital calls and distributions), typically printed pages."""
from __future__ import annotations

import re

from ..classify.classifier import Part
from ..readers.document import to_date, to_number
from .base import Extraction, ExtractionError

ENTITY_RE = re.compile(r"([A-Z][A-Za-z0-9&.,' -]*?(?:LLC|L\.L\.C\.|L\.P\.|LP|Inc\.?|Ltd\.?|LLP))(?=\s|\(|$)")
TOTAL_CALLED_RE = re.compile(r"total called\s+\$?\s*([\d,]+(?:\.\d+)?)", re.I)
CALL_ROW_RE = re.compile(r"^(?P<title>.+?)\s+(?P<due>\d{1,2}/\d{1,2}/\d{4})\s+.*?\$(?P<amount>[\d,]+(?:\.\d+)?)", re.M)
DIST_ROW_RE = re.compile(
    r"^(?P<title>.+?)\s+(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+.*?\$(?P<gross>[\d,]+(?:\.\d+)?)\s+\$(?P<net>[\d,]+(?:\.\d+)?)", re.M
)
_SKIP_TITLES = ("title", "total", "date")


def _reporting_period(text: str) -> dict | None:
    match = re.search(r"reporting period\s+(\d{4}-\d{2}-\d{2})\s+through\s+(\d{4}-\d{2}-\d{2})", text, re.I)
    return {"start": match.group(1), "end": match.group(2)} if match else None


def _entity(text: str) -> str | None:
    m = ENTITY_RE.search(text)
    return m.group(1).strip() if m else None


def _iso(s: str) -> str | None:
    d = to_date(s)
    return d.isoformat() if d else None


def _clean_title(s: str) -> str:
    """Drop a trailing period token ('2Q26', 'Q2 2026', '2026') that Slate prints between title and date."""
    return re.sub(r"\s+(\d[qQ]\d{2,4}|[qQ]\d\s*\d{4}|\d{4})$", "", s.strip())


def parse_capital_calls_text(text: str) -> dict:
    flat = re.sub(r"[ \t]+", " ", text)
    m = TOTAL_CALLED_RE.search(flat)
    none = "no capital calls" in flat.lower()
    calls = [{"title": _clean_title(g["title"]), "due_date": _iso(g["due"]), "amount": to_number(g["amount"])}
             for g in (mm.groupdict() for mm in CALL_ROW_RE.finditer(flat))
             if not g["title"].strip().lower().startswith(_SKIP_TITLES)]
    generic = re.search(r"capital call:\s*(\d{4}-\d{2}-\d{2});.*?amount\s+\$([\d,]+)", flat, re.I)
    if generic and not calls:
        calls = [{"title": "Capital call", "due_date": generic.group(1), "amount": to_number(generic.group(2))}]
    total = to_number(m.group(1)) if m else (0.0 if none else None)
    if total is None and calls:
        total = sum(call["amount"] or 0 for call in calls)
    property_match = re.search(r"scope\s+([^;\n]+);", text, re.I)
    data = {"entity": _entity(text), "total_called": total, "calls": calls, "none": none}
    if property_match:
        data["property_name"] = property_match.group(1).strip()
    if period := _reporting_period(text):
        data["period"] = period
    return data


def parse_distributions_text(text: str) -> dict:
    flat = re.sub(r"[ \t]+", " ", text)
    none = "no distributions yet" in flat.lower()
    dists = [{"title": _clean_title(g["title"]), "date": _iso(g["date"]), "gross": to_number(g["gross"]), "net": to_number(g["net"])}
             for g in (mm.groupdict() for mm in DIST_ROW_RE.finditer(flat))
             if not g["title"].strip().lower().startswith(_SKIP_TITLES)]
    generic = re.search(r"distribution:\s*(\d{4}-\d{2}-\d{2});.*?amount\s+\$([\d,]+)", flat, re.I)
    if generic and not dists:
        amount = to_number(generic.group(2))
        dists = [{"title": "Distribution", "date": generic.group(1), "gross": amount, "net": amount}]
    total = sum(d["gross"] or 0 for d in dists) if dists else (0.0 if none else None)
    property_match = re.search(r"scope\s+([^;\n]+);", text, re.I)
    unknown = bool(re.search(r"status unknown|register was not supplied", text, re.I))
    data = {"entity": _entity(text), "distributions": dists, "total_gross": total, "none": none}
    if property_match:
        data["property_name"] = property_match.group(1).strip()
    if period := _reporting_period(text):
        data["period"] = period
    if unknown:
        data["unknown"] = True
    return data


def _dated(data: dict, part: Part, key: str, date_key: str) -> dict:
    """report_date: when the export was printed (PDF metadata), else the latest transaction date it lists."""
    latest = max((r.get(date_key) for r in data.get(key, []) if r.get(date_key)), default=None)
    data["report_date"] = (data.get("period") or {}).get("end") or part.created or latest
    data["latest_transaction"] = latest
    return data


def extract_capital_calls(part: Part) -> Extraction:
    data = parse_capital_calls_text("\n".join(p.text for p in part.pages))
    if data["total_called"] is None and not data["calls"]:
        raise ExtractionError("Neither a 'Total Called' amount nor capital call rows found")
    warnings = [] if part.created else ["The export carries no date; the reporting period cannot be checked against it"]
    return Extraction(doc_type=part.doc_type, locator=part.locator, data=_dated(data, part, "calls", "due_date"), warnings=warnings)


def extract_distributions(part: Part) -> Extraction:
    data = parse_distributions_text("\n".join(p.text for p in part.pages))
    if data["total_gross"] is None and not data.get("unknown"):
        raise ExtractionError("Neither 'No Distributions Yet' nor distribution rows found")
    warnings = [] if part.created else ["The export carries no date; the reporting period cannot be checked against it"]
    return Extraction(doc_type=part.doc_type, locator=part.locator, data=_dated(data, part, "distributions", "date"), warnings=warnings)
