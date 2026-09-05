"""Completeness and consistency checks over the effective (override-applied, recomputed) ReportData."""
from __future__ import annotations

import datetime as dt

from ..models import Issue, ReportData

REQUIRED: dict[str, str] = {
    "property.fields.name": "error",
    "property.fields.units": "error",
    "financials.tables.lines.rows.total_revenue.ptd_actual": "error",
    "financials.tables.lines.rows.total_opex.ptd_actual": "error",
    "financials.tables.lines.rows.noi.ptd_actual": "error",
    "occupancy.fields.current_pct": "error",
    "capital.fields.purchase_price": "warning",
    "capital.fields.equity_invested": "warning",
    "financing.fields.loan_amount": "warning",
    "submarket.fields.vacancy": "warning",
    "property.fields.year_built": "warning",
    "property.fields.acquired_date": "warning",
}
TOLERANCE = 2.0
FIN = "financials.tables.lines.rows"
OPEX_ROWS = ("payroll", "g_and_a", "marketing", "r_and_m", "utilities", "management_fees", "property_taxes", "insurance")
REVENUE_ROWS = ("net_rental_income", "utility_income", "other_income")


def _fmt(v) -> str:
    return f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)


def _sum(data: ReportData, paths: list[str]) -> float | None:
    vals = [data.value(p) for p in paths]
    present = [v for v in vals if v is not None]
    return sum(present) if present else None


def _file_issues(files: list[dict]) -> list[Issue]:
    out: list[Issue] = []
    for f in files:
        name = f.get("original_filename", "?")
        status = f.get("status")
        if status in ("failed", "unsupported", "needs_ocr"):
            out.append(Issue(severity="warning", message=f"{name}: {f.get('error') or status}"))
        elif status == "unrecognized":
            out.append(Issue(severity="warning", message=f"{name}: {f.get('error') or 'not recognised; the file is not used'}"))
        elif f.get("ignored"):
            out.append(Issue(severity="info", message=f"{name}: excluded on the Files page; not used"))
        for p in f.get("parts") or []:
            for w in p.get("warnings") or []:
                out.append(Issue(severity="warning", message=f"{name} ({p.get('locator')}): {w}"))
    return out


def _field_issues(data: ReportData) -> list[Issue]:
    out: list[Issue] = []
    for path, fld in data.iter_fields():
        if fld.status == "conflict" and fld.override is None:
            alts = ", ".join(_fmt(a.value) for a in fld.alternatives)
            out.append(Issue(path=path, severity="warning", message=f"{fld.label}: sources disagree (using {_fmt(fld.value)}; alternatives: {alts})"))
        elif fld.effective in (None, "") and fld.status in ("missing", "extracted"):
            if path in REQUIRED:
                out.append(Issue(path=path, severity=REQUIRED[path], message=f"Missing: {fld.label}"))
            elif fld.kind == "longtext":
                out.append(Issue(path=path, severity="info", message=f"Narrative not written: {fld.label}"))
            else:
                out.append(Issue(path=path, severity="warning" if ".fields." in path else "info", message=f"Missing: {fld.label}"))
    return out


def _reconciliation_issues(data: ReportData) -> list[Issue]:
    out: list[Issue] = []
    v = data.value
    for total_key, parts, label in (("total_revenue", REVENUE_ROWS, "Total revenue"), ("total_opex", OPEX_ROWS, "Total operating expenses")):
        for col in ("ptd_actual", "ytd_actual"):
            total, s = v(f"{FIN}.{total_key}.{col}"), _sum(data, [f"{FIN}.{k}.{col}" for k in parts])
            if total is not None and s is not None and abs(total - s) > TOLERANCE:
                out.append(Issue(path=f"{FIN}.{total_key}.{col}", severity="warning",
                                 message=f"{label} ({col}) {_fmt(total)} does not equal the sum of its lines {_fmt(s)}"))
    for col in ("ptd_actual", "ytd_actual"):
        rev, opex, noi = v(f"{FIN}.total_revenue.{col}"), v(f"{FIN}.total_opex.{col}"), v(f"{FIN}.noi.{col}")
        if None not in (rev, opex, noi) and abs(rev - opex - noi) > TOLERANCE:
            out.append(Issue(path=f"{FIN}.noi.{col}", severity="warning", message=f"NOI ({col}) {_fmt(noi)} does not equal revenue minus opex {_fmt(rev - opex)}"))
        ds, ncf = v(f"{FIN}.debt_service.{col}"), v(f"{FIN}.net_cash_flow.{col}")
        if None not in (noi, ds, ncf) and abs(noi - ds - ncf) > TOLERANCE:
            out.append(Issue(path=f"{FIN}.net_cash_flow.{col}", severity="warning",
                             message=f"Net cash flow ({col}) {_fmt(ncf)} does not equal NOI minus debt service {_fmt(noi - ds)}"))
    occ, tot, pct = v("occupancy.fields.current_occupied"), v("occupancy.fields.total_units"), v("occupancy.fields.current_pct")
    if None not in (occ, tot, pct) and tot and abs(occ / tot - pct) > 0.001:
        out.append(Issue(path="occupancy.fields.current_pct", severity="warning",
                         message=f"Occupancy {pct * 100:.2f}% does not match occupied / total units ({occ:,.0f} / {tot:,.0f} = {occ / tot * 100:.2f}%)"))
    cap, src = v("capex.tables.lines.totals.ptd_actual"), v("capex.fields.source_total_ptd")
    if None not in (cap, src) and abs(cap - src) > TOLERANCE:
        out.append(Issue(path="capex.tables.lines.totals.ptd_actual", severity="warning",
                         message=f"Capital table total {_fmt(cap)} differs from Yardi's summary total {_fmt(src)}; check the sections in capex_mapping.toml"))
    return out


def _date(v):
    try:
        return dt.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _date_issues(data: ReportData) -> list[Issue]:
    out: list[Issue] = []
    v = data.value
    eff, mat, io_end = _date(v("financing.fields.effective_date")), _date(v("financing.fields.maturity_date")), _date(v("financing.fields.io_end_date"))
    if eff and mat and mat <= eff:
        out.append(Issue(path="financing.fields.maturity_date", severity="error", message=f"Maturity date {mat} is not after the effective date {eff}"))
    if io_end and ((eff and io_end < eff) or (mat and io_end > mat)):
        out.append(Issue(path="financing.fields.io_end_date", severity="warning", message=f"IO end date {io_end} falls outside the loan term"))
    ym = _date(v("financing.fields.yield_maintenance_through"))
    if ym and mat and ym > mat:
        out.append(Issue(path="financing.fields.yield_maintenance_through", severity="warning", message=f"Yield maintenance through {ym} is after the maturity date {mat}"))
    prior, cur = _date(v("occupancy.fields.prior_date")), _date(v("occupancy.fields.current_date"))
    if prior and cur and prior >= cur:
        out.append(Issue(path="occupancy.fields.prior_date", severity="warning", message=f"Prior rent roll date {prior} is not before the current one {cur}"))
    acq, end = _date(v("property.fields.acquired_date")), _date(v("property.fields.period_end"))
    if acq and end and acq > end:
        out.append(Issue(path="property.fields.acquired_date", severity="warning", message=f"Acquisition date {acq} is after the reporting period end {end}"))
    return out


def run(data: ReportData, notes: list[dict], files: list[dict]) -> list[Issue]:
    issues = [Issue(path=n.get("path"), severity=n.get("severity", "info"), message=n["message"]) for n in notes]
    issues += _file_issues(files)
    issues += _field_issues(data)
    issues += _reconciliation_issues(data)
    issues += _date_issues(data)
    order = {"error": 0, "warning": 1, "info": 2}
    return sorted(issues, key=lambda i: order[i.severity])


def summary(data: ReportData, issues: list[Issue]) -> dict:
    missing = conflicts = drafts = 0
    for _, fld in data.iter_fields():
        if fld.status == "conflict" and fld.override is None:
            conflicts += 1
        elif fld.status == "ai_draft" and fld.override is None:
            drafts += 1
        elif fld.effective in (None, "") and fld.status in ("missing", "extracted"):
            missing += 1
    return {"missing": missing, "conflicts": conflicts, "ai_drafts": drafts,
            "errors": sum(i.severity == "error" for i in issues), "warnings": sum(i.severity == "warning" for i in issues),
            "infos": sum(i.severity == "info" for i in issues)}
