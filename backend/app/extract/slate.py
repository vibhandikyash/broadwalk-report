"""Slate investor-portal exports (capital calls and distributions), typically printed pages."""
from __future__ import annotations

import re
from datetime import datetime

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
_MONTH = r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
_MONEY = re.compile(r"\$([\d,]+(?:\.\d{1,2})?)")
_ORDINAL = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th),?\b", re.I)
_YEAR = re.compile(r"\b20\d{2}\b")
_NET_SUMMARY = re.compile(r"\$([\d,]+\.\d{2})\s*\n\s*distributed from this entity\s*\(net\)", re.I)


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
    if not dists:
        dists = _wrapped_distribution_rows(text)
    total = sum(d["gross"] or 0 for d in dists) if dists else (0.0 if none else None)
    property_match = re.search(r"scope\s+([^;\n]+);", text, re.I)
    unknown = bool(re.search(r"status unknown|register was not supplied", text, re.I))
    net_match = _NET_SUMMARY.search(text)
    data = {"entity": _entity(text), "distributions": dists, "total_gross": total, "none": none}
    if net_match:
        data["stated_total_net"] = to_number(net_match.group(1))
    if property_match:
        data["property_name"] = property_match.group(1).strip()
    if period := _reporting_period(text):
        data["period"] = period
    if unknown:
        data["unknown"] = True
    return data


def _wrapped_distribution_rows(text: str) -> list[dict]:
    """Recover transactions whose PDF table wraps dates and monetary cells onto adjacent lines."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rows = []
    for i, line in enumerate(lines):
        prefixes = _MONEY.findall(line)
        if len(prefixes) != 2 or i + 1 >= len(lines):
            continue
        nearby = lines[max(0, i - 2):min(len(lines), i + 5)]
        month = next((re.search(rf"\b({_MONTH})\b", item, re.I) for item in nearby[:2]
                      if re.search(rf"\b({_MONTH})\b", item, re.I)), None)
        day = next((_ORDINAL.search(item) for item in nearby[1:4] if _ORDINAL.search(item)), None)
        year = next((_YEAR.search(item) for item in nearby[2:] if _YEAR.search(item)), None)
        if not (month and day and year):
            continue
        continuation = next((tokens for item in nearby[4:6]
                             if (tokens := re.findall(r"\b\d{1,2}(?:\.\d{1,2})?\b", item))
                             and len(tokens) == 2 and "$" not in item), None)
        if continuation is None or len(continuation) != 2:
            continue
        amounts = [to_number(prefix + suffix) for prefix, suffix in zip(prefixes, continuation)]
        try:
            date = datetime.strptime(f"{month.group(1)[:3]} {day.group(1)} {year.group()}", "%b %d %Y").date()
        except ValueError:
            continue
        if any(amount is None for amount in amounts):
            continue
        title_line = next((item for item in nearby[2:5] if _ORDINAL.search(item)), "")
        title = re.split(r"\bpublished\s*-", title_line, maxsplit=1, flags=re.I)[0].strip()
        rows.append({"title": _clean_title(title) or "Distribution", "date": date.isoformat(),
                     "gross": amounts[0], "net": amounts[1]})
    return rows


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
    stated_net = data.get("stated_total_net")
    if stated_net is not None and data["distributions"]:
        parsed_net = sum(row["net"] for row in data["distributions"])
        if abs(parsed_net - stated_net) > 0.01:
            raise ExtractionError("Parsed distribution amounts do not reconcile to the stated net total")
    return Extraction(doc_type=part.doc_type, locator=part.locator, data=_dated(data, part, "distributions", "date"), warnings=warnings)
