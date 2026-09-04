# backend/tests/test_calc.py
import datetime as dt

from app.consolidate import calc
from app.models import Column, Field, ReportData, Section, Table


def test_pure_helpers():
    assert calc.variance(100, 90, expense=False) == 10 and calc.variance(100, 90, expense=True) == -10
    assert calc.variance(None, 5, False) is None
    assert abs(calc.variance_pct(100, 90, False) - 0.1111) < 1e-3 and calc.variance_pct(5, 0, False) is None
    assert calc.wavg([(10, 2), (20, 2)]) == 15 and calc.wavg([]) is None and calc.wavg([(10, None)]) is None
    assert calc.mean([1, None, 3]) == 2 and calc.mean([]) is None
    assert calc.sum_or_none([1, None]) == 1 and calc.sum_or_none([None]) is None
    assert calc.bps(0.9053, 0.9171) == -118 and calc.ratio(48000000, 338) == 48000000 / 338
    assert abs(calc.implied_rate(159161.98, 36519000) - 0.0523) < 1e-4
    assert calc.quarter_end(2026, 2) == dt.date(2026, 6, 30) and calc.quarter_label(dt.date(2026, 6, 30)) == "2Q26"
    assert calc.next_quarter_label(dt.date(2026, 12, 31)) == "1Q27" and calc.month_label("2026-04") == "Apr 2026"


def _financials_table() -> Table:
    cols = [Column(key="ptd_actual", label="A"), Column(key="ptd_budget", label="B"), Column(key="ptd_var", label="V", derived=True),
            Column(key="ptd_var_pct", label="V%", kind="percent", derived=True), Column(key="ytd_actual", label="YA"),
            Column(key="ytd_budget", label="YB"), Column(key="ytd_var", label="YV", derived=True),
            Column(key="ytd_var_pct", label="YV%", kind="percent", derived=True), Column(key="annual_budget", label="AB")]
    t = Table(title="lines", columns=cols)
    for key, expense, a, b in (("total_revenue", False, 1000, 954), ("payroll", True, 100, 90), ("noi", False, 550, 514)):
        row = t.new_row(key, label=key)
        t.row_meta[key]["expense"] = expense
        row["ptd_actual"].value, row["ptd_budget"].value = a, b
        row["ytd_actual"].value, row["ytd_budget"].value = a * 2, b * 2
    return t


def test_recompute_financials_and_commentary_kpis():
    d = ReportData(meta={"period": {"start": "2026-04-01", "end": "2026-06-30", "quarter_label": "2Q26"}})
    d.sections["financials"] = Section(key="financials", title="F", page=6, tables={"lines": _financials_table()},
                                       fields={"period_label": Field(label="P", status="derived"), "ytd_label": Field(label="Y", status="derived")})
    d.sections["commentary"] = Section(key="commentary", title="C", page=5, fields={
        "revenue_var": Field(label="rv", kind="money", status="derived"), "opex_var": Field(label="ov", kind="money", status="derived"),
        "noi_var_pct": Field(label="nv", kind="percent", status="derived")})
    calc.recompute(d)
    assert d.value("financials.tables.lines.rows.total_revenue.ptd_var") == 46
    assert d.value("financials.tables.lines.rows.payroll.ptd_var") == -10 and d.value("financials.tables.lines.rows.payroll.ytd_var") == -20
    assert abs(d.value("financials.tables.lines.rows.noi.ptd_var_pct") - 36 / 514) < 1e-9
    assert d.value("financials.fields.period_label") == "Apr-Jun 2026" and d.value("financials.fields.ytd_label") == "Jan-Jun 2026"
    assert d.value("commentary.fields.revenue_var") == 46 and d.value("commentary.fields.opex_var") is None
    assert abs(d.value("commentary.fields.noi_var_pct") - 36 / 514) < 1e-9
    d.field("financials.tables.lines.rows.total_revenue.ptd_actual").override = 1100
    calc.recompute(d)
    assert d.value("financials.tables.lines.rows.total_revenue.ptd_var") == 146 and d.value("commentary.fields.revenue_var") == 146


def test_recompute_occupancy_lto_and_comps():
    d = ReportData(meta={"period": {"start": "2026-04-01", "end": "2026-06-30", "quarter_label": "2Q26"}})
    occ = Section(key="occupancy", title="O", page=9, fields={
        "prior_pct": Field(label="p", kind="percent", value=0.9171, status="extracted"),
        "current_pct": Field(label="c", kind="percent", value=0.9053, status="extracted"),
        "change_bps": Field(label="b", kind="number", status="derived"),
        "new_lease_count": Field(label="n", kind="integer", status="derived"),
        "new_lease_lto_pct": Field(label="n", kind="percent", status="derived")})
    t = Table(title="nl", columns=[Column(key="floor_plan", label="fp", kind="text"), Column(key="count", label="n", kind="integer"),
                                   Column(key="avg_prior", label="p"), Column(key="avg_current", label="c"),
                                   Column(key="lto", label="l", derived=True), Column(key="lto_pct", label="lp", kind="percent", derived=True)])
    for key, n, p, c in (("a1", 2, 1250, 1050), ("s1", 1, 1000, 900)):
        row = t.new_row(key, label=key)
        row["count"].value, row["avg_prior"].value, row["avg_current"].value = n, p, c
    for ck in ("count", "avg_prior", "avg_current", "lto", "lto_pct"):
        t.totals[ck] = Field(label=ck, status="derived")
    occ.tables["new_leases"] = t
    d.sections["occupancy"] = occ
    comps = Table(title="c", columns=[Column(key="name", label="n", kind="text"), Column(key="units", label="u", kind="integer"),
                                      Column(key="vintage", label="v", kind="integer"), Column(key="leased_pct", label="l", kind="percent"),
                                      Column(key="asking_rent", label="a"), Column(key="effective_rent", label="e"),
                                      Column(key="concession", label="c", derived=True), Column(key="concession_pct", label="cp", kind="percent", derived=True)])
    for key, subject, units, vint, leased, ask, eff in (("subj", True, 338, 1973, 0.9053, 1250, 1200), ("ash", False, 428, 1998, 0.6667, 1700, 1600), ("brant", False, None, 1989, 0.8, 1600, 1400)):
        row = comps.new_row(key, label=key)
        comps.row_meta[key]["subject"] = subject
        row["units"].value, row["vintage"].value, row["leased_pct"].value, row["asking_rent"].value, row["effective_rent"].value = units, vint, leased, ask, eff
    for ck in ("units", "vintage", "leased_pct", "asking_rent", "effective_rent", "concession", "concession_pct"):
        comps.totals[ck] = Field(label=ck, status="derived")
    d.sections["submarket"] = Section(key="submarket", title="S", page=8, tables={"comps": comps},
                                      fields={"pipeline_note": Field(label="pn", status="derived"), "data_quarter": Field(label="dq", status="derived"),
                                              "under_construction": Field(label="uc", kind="integer", value=0, status="extracted"),
                                              "uc_pct": Field(label="ucp", kind="percent", value=0.0, status="extracted"),
                                              "footnote": Field(label="fn", status="derived"), "source_note": Field(label="sn", status="derived")})
    calc.recompute(d)
    assert d.value("occupancy.fields.change_bps") == -118
    assert d.value("occupancy.tables.new_leases.rows.a1.lto") == -200 and abs(d.value("occupancy.tables.new_leases.rows.a1.lto_pct") + 0.16) < 1e-9
    tot = d.table("occupancy.tables.new_leases").totals
    assert tot["count"].value == 3 and abs(tot["avg_prior"].value - 1166.6667) < 1e-3 and tot["avg_current"].value == 1000
    assert abs(tot["lto"].value + 166.6667) < 1e-3 and d.value("occupancy.fields.new_lease_count") == 3
    assert d.value("submarket.tables.comps.rows.ash.concession") == 100
    ct = d.table("submarket.tables.comps").totals
    assert ct["asking_rent"].value == 1650 and ct["units"].value == 428 and ct["vintage"].value == 1994 and abs(ct["leased_pct"].value - 0.73335) < 1e-4
    assert d.value("submarket.fields.pipeline_note") == "0 units under construction (0.0% of inventory)"
    assert d.value("submarket.fields.data_quarter") == "2Q26"
