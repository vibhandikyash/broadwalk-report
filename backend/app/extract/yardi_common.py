"""Helpers shared by the Yardi report extractors (Budget Comparison, Balance Sheet, Rent Roll, Rent Schedule)."""
from __future__ import annotations

import calendar
import datetime as dt
import re

from ..readers.document import CODE_RE, Sheet, norm, to_date, to_number

PERIOD_RE = re.compile(r"period\s*=\s*([A-Za-z]{3,9}\s+\d{4})\s*-\s*([A-Za-z]{3,9}\s+\d{4})", re.I)
AS_OF_RE = re.compile(r"as\s*of\s*=?\s*(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})", re.I)
PROPERTY_RE = re.compile(r"^(?P<name>[^()]+?)\s*\((?P<ref>[A-Za-z0-9]+)\)\s*$")
PROPERTY_REF_RE = re.compile(r"property\s*=\s*(\S+)", re.I)
TOTAL_RE = re.compile(r"\btotal\b|^net |^cash flow$", re.I)


def _month(s: str) -> dt.date:
    for fmt in ("%b %Y", "%B %Y"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"not a month: {s}")


def parse_period(text: str) -> dict | None:
    """'Period = Apr 2026-Jun 2026' -> {'start': '2026-04-01', 'end': '2026-06-30', 'label': ...}."""
    m = PERIOD_RE.search(text)
    if not m:
        return None
    try:
        start = _month(m.group(1)).replace(day=1)
        end_m = _month(m.group(2))
    except ValueError:
        return None
    end = end_m.replace(day=calendar.monthrange(end_m.year, end_m.month)[1])
    return {"start": start.isoformat(), "end": end.isoformat(), "label": f"{m.group(1).strip()} - {m.group(2).strip()}"}


def find_as_of(sheet: Sheet) -> str | None:
    hit = sheet.find(r"as\s*of", max_row=8)
    if not hit:
        return None
    m = AS_OF_RE.search(hit[2])
    d = to_date(m.group(1)) if m else None
    return d.isoformat() if d else None


def find_property(sheet: Sheet, max_row: int = 6) -> tuple[str | None, str | None]:
    """(name, ref) from a title cell such as 'The Boardwalk (45726)' in the rows above the header."""
    for r in range(min(max_row, sheet.nrows)):
        for c in range(len(sheet.rows[r])):
            m = PROPERTY_RE.match(sheet.text(r, c))
            if m and not norm(m.group("name")).startswith(("property", "as of", "month", "period", "book")):
                return m.group("name").strip(), m.group("ref")
    return None, None


def find_property_ref(text: str) -> str | None:
    m = PROPERTY_REF_RE.search(text)
    return m.group(1) if m else None


def walk_lines(sheet: Sheet, header_row: int, colmap: dict[str, int]) -> list[dict]:
    """Turn a Yardi report body into line records carrying a section path.

    A row with a label and no numbers is a section header. Headers nest by the leading-space indent of
    the label cell: a new header pops headers with an indent >= its own. Numeric lines never pop the
    stack because Yardi indents are not strictly hierarchical. Rows with numbers but no label (the
    summary block Yardi appends at the bottom) are kept with `unlabeled=True`.
    """
    label_col = sheet.label_column(header_row + 1)
    code_col = None
    for c in range(label_col):
        if any(CODE_RE.match(sheet.text(r, c)) for r in range(header_row + 1, min(header_row + 80, sheet.nrows))):
            code_col = c
            break
    lines: list[dict] = []
    stack: list[tuple[int, str]] = []
    for r in range(header_row + 1, sheet.nrows):
        raw = sheet.cell(r, label_col)
        label = sheet.text(r, label_col)
        values = {k: to_number(sheet.cell(r, c)) for k, c in colmap.items()}
        has_vals = any(v is not None for v in values.values())
        if not label:
            if has_vals:
                lines.append({"code": "", "label": "", "norm": "", "indent": 0, "section": [s for _, s in stack],
                              "is_total": False, "unlabeled": True, "values": values, "row": r})
            continue
        indent = len(raw) - len(raw.lstrip(" ")) if isinstance(raw, str) else 0
        code = sheet.text(r, code_col) if code_col is not None else ""
        if not CODE_RE.match(code):
            code = ""
        if not has_vals:
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, label))
            continue
        nl = norm(label)
        lines.append({"code": code, "label": label, "norm": nl, "indent": indent, "section": [s for _, s in stack],
                      "is_total": bool(TOTAL_RE.search(nl)), "unlabeled": False, "values": values, "row": r})
    return lines
