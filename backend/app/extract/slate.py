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
    total = to_number(m.group(1)) if m else (0.0 if none else None)
    return {"entity": _entity(text), "total_called": total, "calls": calls, "none": none}


def parse_distributions_text(text: str) -> dict:
    flat = re.sub(r"[ \t]+", " ", text)
    none = "no distributions yet" in flat.lower()
    dists = [{"title": _clean_title(g["title"]), "date": _iso(g["date"]), "gross": to_number(g["gross"]), "net": to_number(g["net"])}
             for g in (mm.groupdict() for mm in DIST_ROW_RE.finditer(flat))
             if not g["title"].strip().lower().startswith(_SKIP_TITLES)]
    total = sum(d["gross"] or 0 for d in dists) if dists else (0.0 if none else None)
    return {"entity": _entity(text), "distributions": dists, "total_gross": total, "none": none}


def extract_capital_calls(part: Part) -> Extraction:
    data = parse_capital_calls_text("\n".join(p.text for p in part.pages))
    if data["total_called"] is None and not data["calls"]:
        raise ExtractionError("Neither a 'Total Called' amount nor capital call rows found")
    return Extraction(doc_type=part.doc_type, locator=part.locator, data=data)


def extract_distributions(part: Part) -> Extraction:
    data = parse_distributions_text("\n".join(p.text for p in part.pages))
    if data["total_gross"] is None:
        raise ExtractionError("Neither 'No Distributions Yet' nor distribution rows found")
    return Extraction(doc_type=part.doc_type, locator=part.locator, data=data)
