"""Pure calculations and recompute(): fills every derived field from effective values.

Signs follow the Yardi convention used by the example report: a variance is favourable-positive,
so revenue variance = actual - budget and expense variance = budget - actual.
"""
from __future__ import annotations

import calendar
import datetime as dt
from typing import Iterable

from ..models import ReportData, Table

Num = float | int | None


def sum_or_none(vals: Iterable[Num]) -> float | None:
    xs = [float(v) for v in vals if v is not None]
    return sum(xs) if xs else None


def mean(vals: Iterable[Num]) -> float | None:
    xs = [float(v) for v in vals if v is not None]
    return sum(xs) / len(xs) if xs else None


def wavg(pairs: Iterable[tuple[Num, Num]]) -> float | None:
    """Weighted average of (value, weight) pairs; pairs with a missing value or weight are skipped."""
    num = den = 0.0
    for v, w in pairs:
        if v is None or w is None:
            continue
        num += float(v) * float(w)
        den += float(w)
    return num / den if den else None


def ratio(a: Num, b: Num) -> float | None:
    return None if a is None or not b else float(a) / float(b)


def variance(actual: Num, budget: Num, expense: bool) -> float | None:
    if actual is None or budget is None:
        return None
    return float(budget) - float(actual) if expense else float(actual) - float(budget)


def variance_pct(actual: Num, budget: Num, expense: bool) -> float | None:
    v = variance(actual, budget, expense)
    return None if v is None or not budget else v / abs(float(budget))


def bps(current: Num, prior: Num) -> float | None:
    return None if current is None or prior is None else round((float(current) - float(prior)) * 10000)


def implied_rate(monthly_interest: Num, principal: Num) -> float | None:
    return None if monthly_interest is None or not principal else float(monthly_interest) * 12 / float(principal)


def quarter_end(year: int, q: int) -> dt.date:
    m = q * 3
    return dt.date(year, m, calendar.monthrange(year, m)[1])


def quarter_label(d: dt.date) -> str:
    return f"{(d.month - 1) // 3 + 1}Q{d.year % 100:02d}"


def next_quarter_label(period_end: dt.date) -> str:
    q, y = (period_end.month - 1) // 3 + 1, period_end.year
    return f"{1}Q{(y + 1) % 100:02d}" if q == 4 else f"{q + 1}Q{y % 100:02d}"


def month_label(ym: str) -> str:
    y, m = ym.split("-")
    return f"{calendar.month_abbr[int(m)]} {y}"


FIN = "financials.tables.lines.rows"
CAPEX_TOTALS = "capex.tables.lines.totals"
# Page 5's headline figures are copies of lines on pages 6 and 7. Naming the source once means the
# calculation and the provenance sheet that explains it cannot drift apart.
KPI_SOURCES: dict[str, str] = {
    "revenue_actual": f"{FIN}.total_revenue.ptd_actual", "revenue_budget": f"{FIN}.total_revenue.ptd_budget",
    "revenue_var": f"{FIN}.total_revenue.ptd_var", "revenue_var_pct": f"{FIN}.total_revenue.ptd_var_pct",
    "gpr_var_pct": f"{FIN}.gpr.ptd_var_pct", "gain_to_lease_actual": f"{FIN}.gain_loss_to_lease.ptd_actual",
    "gain_to_lease_budget": f"{FIN}.gain_loss_to_lease.ptd_budget", "gain_to_lease_var_pct": f"{FIN}.gain_loss_to_lease.ptd_var_pct",
    "concessions_var": f"{FIN}.concessions.ptd_var", "opex_actual": f"{FIN}.total_opex.ptd_actual",
    "opex_budget": f"{FIN}.total_opex.ptd_budget", "opex_var": f"{FIN}.total_opex.ptd_var", "opex_var_pct": f"{FIN}.total_opex.ptd_var_pct",
    "insurance_var": f"{FIN}.insurance.ptd_var", "utilities_var": f"{FIN}.utilities.ptd_var",
    "noi_actual": f"{FIN}.noi.ptd_actual", "noi_budget": f"{FIN}.noi.ptd_budget", "noi_var": f"{FIN}.noi.ptd_var",
    "noi_var_pct": f"{FIN}.noi.ptd_var_pct", "debt_service_actual": f"{FIN}.debt_service.ptd_actual",
    "ncf_actual": f"{FIN}.net_cash_flow.ptd_actual", "ncf_budget": f"{FIN}.net_cash_flow.ptd_budget",
    "ncf_var": f"{FIN}.net_cash_flow.ptd_var", "ncf_var_pct": f"{FIN}.net_cash_flow.ptd_var_pct",
    "noi_ytd_var_pct": f"{FIN}.noi.ytd_var_pct",
    **{k: f"{CAPEX_TOTALS}.{c}" for k, c in (
        ("capex_actual", "ptd_actual"), ("capex_budget", "ptd_budget"), ("capex_var", "ptd_var"),
        ("capex_ytd_actual", "ytd_actual"), ("capex_ytd_budget", "ytd_budget"), ("capex_ytd_var", "ytd_var"),
        ("capex_annual_budget", "annual_budget"))},
}


def _row_val(row: dict, key: str):
    f = row.get(key)
    return None if f is None else f.effective


def _set_total(t: Table, key: str, value) -> None:
    f = t.totals.get(key)
    if f is not None and f.status == "derived":
        f.value = value


def _recompute_variances(t: Table, prefixes: tuple[str, ...] = ("ptd", "ytd")) -> None:
    for key, row in t.rows.items():
        expense = bool(t.row_meta.get(key, {}).get("expense"))
        for p in prefixes:
            a, b = _row_val(row, f"{p}_actual"), _row_val(row, f"{p}_budget")
            if f"{p}_var" in row and row[f"{p}_var"].status == "derived":
                row[f"{p}_var"].value = variance(a, b, expense)
            if f"{p}_var_pct" in row and row[f"{p}_var_pct"].status == "derived":
                row[f"{p}_var_pct"].value = variance_pct(a, b, expense)


def _period(d: ReportData) -> tuple[dt.date | None, dt.date | None, str | None]:
    p = d.meta.get("period") or {}
    s = dt.date.fromisoformat(p["start"]) if p.get("start") else None
    e = dt.date.fromisoformat(p["end"]) if p.get("end") else None
    return s, e, p.get("quarter_label")


def recompute(d: ReportData) -> None:  # noqa: C901 - one long, explicit pass over the model
    v, setv = d.value, d.set_derived
    start, end, qlabel = _period(d)
    if start and end:
        period_label = f"{start:%b}-{end:%b} {end:%Y}"
        prior_end = start - dt.timedelta(days=1)
        setv("property.fields.quarter_label", qlabel)
        setv("property.fields.period_label", period_label)
        setv("property.fields.period_end", end.isoformat())
        setv("property.fields.prior_quarter_label", quarter_label(prior_end))
        setv("financials.fields.period_label", period_label)
        setv("financials.fields.ytd_label", f"Jan-{end:%b} {end:%Y}")
        setv("in_place_rent.fields.prior_quarter_label", quarter_label(prior_end))
        setv("status.fields.next_quarter_label", next_quarter_label(end))
        setv("submarket.fields.data_quarter", qlabel)

    # property
    setv("property.fields.density", ratio(v("property.fields.units"), v("property.fields.site_acres")))

    # in-place rent
    t = d.table("in_place_rent.tables.by_floor_plan")
    if t:
        for row in t.rows.values():
            cur, pri = _row_val(row, "current_rent"), _row_val(row, "prior_rent")
            diff = None if cur is None or pri is None else cur - pri
            if "variance" in row:
                row["variance"].value = diff
            if "variance_pct" in row:
                row["variance_pct"].value = ratio(diff, pri)
        _set_total(t, "units", sum_or_none(_row_val(r, "units") for r in t.rows.values()))
        cur, pri = _row_val(t.totals, "current_rent"), _row_val(t.totals, "prior_rent")
        if cur is None:
            cur = wavg((_row_val(r, "current_rent"), _row_val(r, "units")) for r in t.rows.values())
            _set_total(t, "current_rent", cur)
        if pri is None:
            pri = wavg((_row_val(r, "prior_rent"), _row_val(r, "units")) for r in t.rows.values())
            _set_total(t, "prior_rent", pri)
        diff = None if cur is None or pri is None else cur - pri
        _set_total(t, "variance", diff)
        _set_total(t, "variance_pct", ratio(diff, pri))

    # capital
    setv("capital.fields.price_per_unit", ratio(v("capital.fields.purchase_price"), v("property.fields.units")))
    qc = v("capital.fields.quarter_contributions")
    setv("capital.fields.contributions_note", None if qc is None else ("No capital called this quarter" if qc == 0 else f"${qc:,.0f} called this quarter"))
    di = v("capital.fields.distributions_itd")
    setv("capital.fields.distributions_note", None if di is None else ("No distributions issued to date" if di == 0 else f"${di:,.0f} distributed to date"))

    # underwriting budget
    t = d.table("underwriting.tables.budget")
    if t:
        for row in t.rows.values():
            if "pct_spent" in row:
                row["pct_spent"].value = ratio(_row_val(row, "spent_to_date"), _row_val(row, "original_budget"))
        ob = sum_or_none(_row_val(r, "original_budget") for r in t.rows.values())
        sp = sum_or_none(_row_val(r, "spent_to_date") for r in t.rows.values())
        _set_total(t, "original_budget", ob)
        _set_total(t, "spent_to_date", sp)
        _set_total(t, "pct_spent", ratio(sp, ob))

    # financing
    setv("financing.fields.implied_rate", implied_rate(v("financing.fields.interest_monthly"), v("financing.fields.loan_amount")))
    rr = v("financing.fields.replacement_reserve_monthly")
    setv("financing.fields.replacement_reserve_annual", None if rr is None else rr * 12)

    # financials
    t = d.table("financials.tables.lines")
    if t:
        _recompute_variances(t)

    # capex
    t = d.table("capex.tables.lines")
    if t:
        _recompute_variances(t)
        for ck in ("ptd_actual", "ptd_budget", "ptd_var", "ytd_actual", "ytd_budget", "ytd_var", "annual_budget"):
            _set_total(t, ck, sum_or_none(_row_val(r, ck) for r in t.rows.values()))

    # page 5 mirrors lines from pages 6 and 7, so it is filled once both are final
    for key, path in KPI_SOURCES.items():
        setv(f"commentary.fields.{key}", v(path))

    # submarket
    uc, ucp = v("submarket.fields.under_construction"), v("submarket.fields.uc_pct")
    if uc is not None:
        setv("submarket.fields.pipeline_note", f"{int(uc):,} units under construction" + (f" ({ucp * 100:.1f}% of inventory)" if ucp is not None else ""))
    t = d.table("submarket.tables.comps")
    if t:
        for row in t.rows.values():
            ask, eff = _row_val(row, "asking_rent"), _row_val(row, "effective_rent")
            conc = None if ask is None or eff is None else ask - eff
            if "concession" in row:
                row["concession"].value = conc
            if "concession_pct" in row:
                row["concession_pct"].value = ratio(conc, ask)
        comps = [r for k, r in t.rows.items() if not t.row_meta.get(k, {}).get("subject")]
        n = len(comps)

        def agg(col: str) -> tuple[float | None, str | None, int]:
            """Average of the comparables that have a value: unit-weighted only when every one of them has a unit count."""
            have = [r for r in comps if _row_val(r, col) is not None]
            if not have:
                return None, None, 0
            if all(_row_val(r, "units") is not None for r in have):
                return wavg((_row_val(r, col), _row_val(r, "units")) for r in have), "unit-weighted", len(have)
            return mean(_row_val(r, col) for r in have), "simple average", len(have)

        _set_total(t, "units", mean(_row_val(r, "units") for r in comps))
        vint = mean(_row_val(r, "vintage") for r in comps)
        _set_total(t, "vintage", None if vint is None else int(vint + 0.5))
        methods = []
        for col, label in (("leased_pct", "leased %"), ("asking_rent", "asking rent"), ("effective_rent", "effective rent")):
            val, method, k = agg(col)
            _set_total(t, col, val)
            if method:
                methods.append(f"{label} {method}" + (f" ({k} of {n} with values)" if k < n else ""))
        ta, te = _row_val(t.totals, "asking_rent"), _row_val(t.totals, "effective_rent")
        _set_total(t, "concession", None if ta is None or te is None else ta - te)
        _set_total(t, "concession_pct", ratio(None if ta is None or te is None else ta - te, ta))
        setv("submarket.fields.footnote", f"Comp set average across {n} comparable{'s' if n != 1 else ''}" + (": " + "; ".join(methods) if methods else "") + ".")
    setv("submarket.fields.source_note", "Source: HelloData.ai listings and CoStar submarket data")

    # occupancy and trade-out
    setv("occupancy.fields.change_bps", bps(v("occupancy.fields.current_pct"), v("occupancy.fields.prior_pct")))
    for tkey, count_field, pct_field in (("new_leases", "new_lease_count", "new_lease_lto_pct"), ("renewals", "renewal_count", "renewal_lto_pct")):
        t = d.table(f"occupancy.tables.{tkey}")
        if not t:
            continue
        for row in t.rows.values():
            pri, cur = _row_val(row, "avg_prior"), _row_val(row, "avg_current")
            diff = None if pri is None or cur is None else cur - pri
            if "lto" in row:
                row["lto"].value = diff
            if "lto_pct" in row:
                row["lto_pct"].value = ratio(diff, pri)
        n = sum_or_none(_row_val(r, "count") for r in t.rows.values())
        pri = wavg((_row_val(r, "avg_prior"), _row_val(r, "count")) for r in t.rows.values())
        cur = wavg((_row_val(r, "avg_current"), _row_val(r, "count")) for r in t.rows.values())
        diff = None if pri is None or cur is None else cur - pri
        _set_total(t, "count", n)
        _set_total(t, "avg_prior", pri)
        _set_total(t, "avg_current", cur)
        _set_total(t, "lto", diff)
        _set_total(t, "lto_pct", ratio(diff, pri))
        setv(f"occupancy.fields.{count_field}", n)
        setv(f"occupancy.fields.{pct_field}", ratio(diff, pri))
