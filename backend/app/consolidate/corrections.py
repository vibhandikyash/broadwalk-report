"""Typed validation of review corrections. Nothing here touches the database.

A correction is accepted only if its path exists in the effective report data, the target is an
input (not derived), and the value fits the field's kind plus a few semantic rules (occupancy in
0-1, counts non-negative, years four digits). Stored representations: money/number as float,
integer as int, percent as a fraction (0.0523 = 5.23%), date as ISO 'YYYY-MM-DD', text as str.
"""
from __future__ import annotations

import copy
import datetime as dt
import math
import re
from typing import Any

from ..models import ReportData
from .builder import apply_overrides

TEXT_MAX, LONGTEXT_MAX = 500, 5000
PERCENT_MAX = 10.0  # 1,000%: anything larger is almost certainly 90.5 typed instead of 0.905
KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
NON_NEGATIVE = {
    "units", "total_units", "current_occupied", "prior_occupied", "future_applicants", "site_acres", "hold_period_years",
    "avg_unit_sf", "avg_sf", "sqft", "count", "subject_n", "comp_n", "purchase_price", "equity_invested", "total_called",
    "distributions_itd", "quarter_contributions", "quarter_distributions", "original_budget", "spent_to_date", "loan_amount",
    "interest_monthly", "reserve_balance", "term_months", "io_months", "amort_years", "pi_payment", "open_prepay_months",
    "replacement_reserve_monthly", "repairs_escrow", "asking_rent", "effective_rent", "avg_asking_rent", "under_construction",
    "inventory", "current_rent", "prior_rent", "avg_prior", "avg_current", "subject_gross_psf", "subject_eff_psf",
    "comp_gross_psf", "comp_eff_psf", "collections_recovered",
}
UNIT_INTERVAL = {"current_pct", "prior_pct", "leased_pct", "vacancy", "prior_vacancy", "uc_pct", "rate", "pct_spent"}
YEAR_KEYS = {"year_built", "vintage"}


class CorrectionError(ValueError):
    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path, self.message = path, message


def coerce(kind: str, value: Any, key: str = "") -> Any:
    """Return the stored representation of `value` for a field of `kind`, or raise ValueError."""
    if isinstance(value, bool):
        raise ValueError("expected a value, got true/false")
    if kind in ("text", "longtext"):
        if isinstance(value, (int, float)) and math.isfinite(value):
            value = f"{value:g}"
        if not isinstance(value, str):
            raise ValueError("expected text")
        limit = LONGTEXT_MAX if kind == "longtext" else TEXT_MAX
        if len(value) > limit:
            raise ValueError(f"text is longer than {limit:,} characters")
        return value.strip()
    if kind == "date":
        if isinstance(value, (dt.date, dt.datetime)):
            return value.isoformat()[:10]
        if not isinstance(value, str):
            raise ValueError("expected a date as YYYY-MM-DD")
        try:
            return dt.date.fromisoformat(value.strip()[:10]).isoformat()
        except ValueError:
            raise ValueError("expected a date as YYYY-MM-DD") from None
    if isinstance(value, str):
        s = value.strip().replace(",", "").replace("$", "")
        if s.endswith("%"):
            raise ValueError("enter percentages as fractions (0.0523 for 5.23%), not with a % sign")
        try:
            value = float(s)
        except ValueError:
            raise ValueError("expected a number") from None
    if not isinstance(value, (int, float)):
        raise ValueError("expected a number")
    x = float(value)
    if not math.isfinite(x):
        raise ValueError("expected a finite number")
    if kind == "integer":
        if x != int(x):
            raise ValueError("expected a whole number")
    if kind == "percent" and abs(x) > PERCENT_MAX:
        raise ValueError("percentages are stored as fractions (0.0523 = 5.23%); this value is above 1,000%")
    if key in UNIT_INTERVAL and not 0 <= x <= 1:
        raise ValueError("must be between 0 and 1 (0.905 = 90.5%)")
    if key in NON_NEGATIVE and x < 0:
        raise ValueError("cannot be negative")
    if key in YEAR_KEYS and not 1800 <= x <= 2100:
        raise ValueError("expected a four-digit year")
    return int(x) if kind == "integer" else x


def _effective_shape(data: ReportData, overrides: dict) -> ReportData:
    """A scratch copy with the stored overrides applied, so manual rows resolve as paths."""
    scratch = data.model_copy(deep=True)
    apply_overrides(scratch, overrides)
    return scratch


def apply_patch(data: ReportData, overrides: dict, changes: list, add_rows: list, delete_rows: list) -> dict:
    """Validate a whole batch against the base data and return the new overrides dict.

    Raises CorrectionError on the first problem; the caller persists nothing in that case.
    `changes` items have .path/.value, `add_rows` .table/.key/.values, `delete_rows` .table/.key.
    """
    ov = copy.deepcopy(overrides or {})
    fields, rows, deleted = ov.setdefault("fields", {}), ov.setdefault("rows", {}), ov.setdefault("deleted_rows", {})
    shape = _effective_shape(data, ov)
    for ch in changes:
        f = shape.field(ch.path)
        if f is None:
            raise CorrectionError(ch.path, "unknown field path")
        if f.status == "derived":
            raise CorrectionError(ch.path, f"'{f.label}' is calculated from other values and cannot be edited")
        if ch.value is None or ch.value == "":
            fields.pop(ch.path, None)
            continue
        try:
            fields[ch.path] = coerce(f.kind, ch.value, ch.path.rsplit(".", 1)[-1])
        except ValueError as e:
            raise CorrectionError(ch.path, f"{f.label}: {e}") from None
    for ar in add_rows:
        t = shape.table(ar.table)
        if t is None:
            raise CorrectionError(ar.table, "unknown table")
        if not t.editable_rows:
            raise CorrectionError(ar.table, f"rows cannot be added to '{t.title}'")
        key = ar.key or f"manual-{_new_key()}"
        if not KEY_RE.match(key):
            raise CorrectionError(ar.table, "row keys may only contain letters, digits, '-' and '_'")
        cols = {c.key: c for c in t.columns}
        cells: dict[str, Any] = {}
        for ck, val in (ar.values or {}).items():
            c = cols.get(ck)
            if c is None:
                raise CorrectionError(f"{ar.table}.rows.{key}.{ck}", "unknown column")
            if c.derived:
                raise CorrectionError(f"{ar.table}.rows.{key}.{ck}", f"'{c.label}' is calculated and cannot be set")
            if val is None or val == "":
                continue
            try:
                cells[ck] = coerce(c.kind, val, ck)
            except ValueError as e:
                raise CorrectionError(f"{ar.table}.rows.{key}.{ck}", f"{c.label}: {e}") from None
        rows.setdefault(ar.table, {}).setdefault(key, {}).update(cells)
        if key in deleted.get(ar.table, []):
            deleted[ar.table].remove(key)
        shape = _effective_shape(data, ov)  # later changes may target the new row
    for dr in delete_rows:
        t = shape.table(dr.table)
        if t is None:
            raise CorrectionError(dr.table, "unknown table")
        manual = dr.key in rows.get(dr.table, {}) or bool(t.row_meta.get(dr.key, {}).get("manual"))
        if dr.key not in t.rows and not manual:
            raise CorrectionError(f"{dr.table}.rows.{dr.key}", "unknown row")
        if not (t.editable_rows or manual):
            raise CorrectionError(f"{dr.table}.rows.{dr.key}", f"rows cannot be removed from '{t.title}'")
        if dr.key in rows.get(dr.table, {}):
            rows[dr.table].pop(dr.key)
        else:
            deleted.setdefault(dr.table, [])
            if dr.key not in deleted[dr.table]:
                deleted[dr.table].append(dr.key)
        prefix = f"{dr.table}.rows.{dr.key}."
        for p in [p for p in fields if p.startswith(prefix)]:
            fields.pop(p)
    return ov


def sanitize(data: ReportData, overrides: dict) -> tuple[dict, list[str]]:
    """Drop stored overrides that no longer fit their field (legacy or hand-edited rows).

    Returns (clean overrides, human-readable reasons). Runs on every read so a bad row in the
    database can never take the review screen or report generation down.
    """
    ov = copy.deepcopy(overrides or {})
    dropped: list[str] = []
    for tpath, trows in list((ov.get("rows") or {}).items()):
        t = data.table(tpath)
        if not isinstance(trows, dict):
            ov["rows"].pop(tpath)
            dropped.append(f"{tpath}: manual rows were not a mapping")
            continue
        cols = {c.key: c for c in t.columns} if t else {}
        for rkey, cells in list(trows.items()):
            if not isinstance(cells, dict):
                trows.pop(rkey)
                dropped.append(f"{tpath}.rows.{rkey}: manual row was not a mapping")
                continue
            for ck, val in list(cells.items()):
                c = cols.get(ck)
                if c is None or c.derived:
                    cells.pop(ck)
                    dropped.append(f"{tpath}.rows.{rkey}.{ck}: not an editable column")
                    continue
                try:
                    cells[ck] = coerce(c.kind, val, ck)
                except ValueError as e:
                    cells.pop(ck)
                    dropped.append(f"{tpath}.rows.{rkey}.{ck}: {e}")
    shape = _effective_shape(data, ov)
    for path, val in list((ov.get("fields") or {}).items()):
        f = shape.field(path)
        if f is None:
            continue  # reported separately as a stale edit
        if f.status == "derived":
            ov["fields"].pop(path)
            dropped.append(f"{path}: calculated field")
            continue
        try:
            ov["fields"][path] = coerce(f.kind, val, path.rsplit(".", 1)[-1])
        except ValueError as e:
            ov["fields"].pop(path)
            dropped.append(f"{path}: {e}")
    for path, val in list((ov.get("ai_drafts") or {}).items()):
        text = val.get("text") if isinstance(val, dict) else val
        if not isinstance(text, str) or not text:
            ov["ai_drafts"].pop(path)
            dropped.append(f"{path}: AI draft was not text")
    return ov, dropped


def _new_key() -> str:
    import uuid

    return uuid.uuid4().hex[:6]
