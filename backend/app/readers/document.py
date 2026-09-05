"""Neutral in-memory representation of an uploaded file, plus the cell helpers every extractor uses."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

CODE_RE = re.compile(r"^\d{3,5}-\d{3,5}$")  # Yardi GL account codes such as 4000-0000
_NUM_RE = re.compile(r"^\(?-?\$?\s*[\d,]*\.?\d+\s*%?\)?$")
_NA = {"n/a", "na", "-", "—", "--", ""}
_DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%m/%d/%y", "%b %Y", "%B %Y", "%b-%y", "%Y-%m", "%b %d, %Y")


def norm(s: Any) -> str:
    """Lower-cased, whitespace-collapsed text for matching."""
    return re.sub(r"\s+", " ", str(s if s is not None else "")).strip().lower()


def to_number(v: Any) -> float | None:
    """Parse 1,234 / (1,234) / $1,234 / 12.5% / -3 into a float. None when not numeric."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s.lower() in _NA:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


def is_number(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    return isinstance(v, str) and bool(_NUM_RE.match(v.strip()))


def to_date(v: Any) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if v is None:
        return None
    s = str(v).strip()
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def as_fraction(x: float | None) -> float | None:
    """Percent values arrive as 91.71 (Yardi) or 0.9171 (CoStar/HelloData); store fractions."""
    if x is None:
        return None
    return x / 100.0 if abs(x) > 1.5 else x


@dataclass
class Sheet:
    name: str
    rows: list[list[Any]]

    @property
    def nrows(self) -> int:
        return len(self.rows)

    def cell(self, r: int, c: int) -> Any:
        if 0 <= r < len(self.rows) and 0 <= c < len(self.rows[r]):
            return self.rows[r][c]
        return None

    def text(self, r: int, c: int) -> str:
        v = self.cell(r, c)
        return "" if v is None else str(v).strip()

    def row_text(self, r: int) -> str:
        if not (0 <= r < self.nrows):
            return ""
        return " | ".join(t for t in (self.text(r, c) for c in range(len(self.rows[r]))) if t)

    def head_text(self, n: int = 15) -> str:
        return "\n".join(self.row_text(r) for r in range(min(n, self.nrows)))

    def has_numbers(self, r: int) -> bool:
        return 0 <= r < self.nrows and any(is_number(v) for v in self.rows[r])

    def find(self, pattern: str, max_row: int | None = None) -> tuple[int, int, str] | None:
        """First cell whose text matches the regex (case-insensitive) as (row, col, text)."""
        rx = re.compile(pattern, re.I)
        for r in range(min(max_row or self.nrows, self.nrows)):
            for c, v in enumerate(self.rows[r]):
                if v is not None and rx.search(str(v)):
                    return r, c, str(v)
        return None

    def _join(self, r: int, k: int) -> list[str]:
        end = min(r + k, self.nrows)
        width = max((len(self.rows[i]) for i in range(r, end)), default=0)
        return [norm(" ".join(self.text(i, c) for i in range(r, end))) for c in range(width)]

    def header_block(self, required: list[str], max_rows: int = 3, search_rows: int = 40) -> tuple[int, int, list[str]] | None:
        """Locate a header that may span several rows.

        Returns (start_row, row_count, headers) where headers are the per-column texts of rows
        start..start+row_count-1 joined and normalised. The start row itself must contain at least one
        required token (so a title line above a header is not swallowed); further rows are joined while
        they contain no numbers, up to max_rows.
        """
        for r in range(min(search_rows, self.nrows)):
            first = norm(self.row_text(r))
            if not first or not any(req in first for req in required):
                continue
            k = 1
            while k < max_rows and r + k < self.nrows and not self.has_numbers(r + k):
                k += 1
            headers = self._join(r, k)
            if all(any(req in h for h in headers) for req in required):
                return r, k, headers
        return None

    @staticmethod
    def col(headers: list[str], *patterns: str) -> int | None:
        """Index of the first header matching any pattern (patterns tried in order)."""
        for p in patterns:
            rx = re.compile(p, re.I)
            for i, h in enumerate(headers):
                if rx.search(h):
                    return i
        return None

    @staticmethod
    def cols_all(headers: list[str], pattern: str) -> list[int]:
        rx = re.compile(pattern, re.I)
        return [i for i, h in enumerate(headers) if rx.search(h)]

    def label_column(self, start: int, end: int | None = None) -> int:
        """Column holding row labels: most non-numeric, non-GL-code strings below `start`."""
        end = end or self.nrows
        width = max((len(x) for x in self.rows[start:end]), default=0)
        best, best_n = 0, -1
        for c in range(width):
            n = 0
            for r in range(start, end):
                v = self.cell(r, c)
                if isinstance(v, str) and v.strip() and not is_number(v) and not CODE_RE.match(v.strip()):
                    n += 1
            if n > best_n:
                best, best_n = c, n
        return best


@dataclass
class Page:
    number: int
    text: str

    @property
    def lines(self) -> list[str]:
        return [ln.rstrip() for ln in self.text.splitlines() if ln.strip()]


@dataclass
class Document:
    file_id: str
    filename: str
    kind: str  # "xlsx" | "pdf"
    sheets: list[Sheet] = field(default_factory=list)
    pages: list[Page] = field(default_factory=list)
    created: str | None = None  # document creation date (ISO) when the file carries one, e.g. PDF metadata

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.pages)
