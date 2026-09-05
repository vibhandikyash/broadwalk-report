"""Consolidate the selected extractions into ReportData.

Only inputs are set here (statuses extracted / missing / conflict); derived shells are created and
filled by calc.recompute. Every extracted Field carries the locator of the line it came from.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from ..config import settings
from ..models import Alternative, Column, Field, ReportData, Section, Source, Table
from ..readers.document import norm
from . import calc
from .mapping import consume_capex, load_capex_mapping, load_pl_mapping, match_lines, section_matches
from .select import Selection, Src, collect, select

ADDRESS_RE = re.compile(r"^(?P<street>.+?),\s*(?P<city>[^,]+?),\s*(?P<state>[A-Z]{2})\b\s*(?P<zip>\d{5})?")
VALUE_COLS = ("ptd_actual", "ptd_budget", "ytd_actual", "ytd_budget", "annual_budget")


# ---------- small constructors ----------
def F(label: str, kind: str = "text", value=None, source: dict | None = None, note: str | None = None, status: str | None = None) -> Field:
    st = status or ("extracted" if value is not None else "missing")
    return Field(label=label, kind=kind, value=value, status=st, source=Source(**source) if source else None, note=note)


def D(label: str, kind: str = "number", note: str | None = None) -> Field:
    return Field(label=label, kind=kind, status="derived", note=note)


def M(label: str, kind: str = "text", note: str | None = None) -> Field:
    return Field(label=label, kind=kind, status="missing", note=note or "Not found in any source file; enter manually")


def C(key: str, label: str, kind: str = "money", derived: bool = False) -> Column:
    return Column(key=key, label=label, kind=kind, derived=derived)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(s)).strip("-") or "row"


def names_match(a: str | None, b: str | None) -> bool:
    ka, kb = (re.sub(r"[^a-z0-9]", "", re.sub(r"^the\s+", "", norm(x))) for x in (a or "", b or ""))
    return bool(ka) and bool(kb) and (ka == kb or ka in kb or kb in ka)


def _date(s: str | None) -> dt.date | None:
    return dt.date.fromisoformat(s) if s else None


@dataclass
class Period:
    start: dt.date
    end: dt.date

    @property
    def quarter(self) -> int:
        return (self.end.month - 1) // 3 + 1

    @property
    def year(self) -> int:
        return self.end.year

    @property
    def quarter_label(self) -> str:
        return calc.quarter_label(self.end)

    @property
    def prior_end(self) -> dt.date:
        return self.start - dt.timedelta(days=1)

    @property
    def prior_quarter_label(self) -> str:
        return calc.quarter_label(self.prior_end)

    @property
    def months(self) -> int:
        return (self.end.year - self.start.year) * 12 + self.end.month - self.start.month + 1


@dataclass
class Ctx:
    sel: Selection
    period: Period
    notes: list[dict] = field(default_factory=list)
    property_name: str | None = None
    units: float | None = None

    def note(self, severity: str, message: str, path: str | None = None) -> None:
        self.notes.append({"severity": severity, "message": message, "path": path})


# ---------- source lookups ----------
def _at_or_before(srcs: list[Src], date: dt.date) -> Src | None:
    dated = [s for s in srcs if s.data.get("as_of")]
    on_or_before = [s for s in dated if s.data["as_of"] <= date.isoformat()]
    if on_or_before:
        return max(on_or_before, key=lambda s: s.data["as_of"])
    if dated:
        return max(dated, key=lambda s: s.data["as_of"])
    return srcs[-1] if srcs else None


def _before(srcs: list[Src], as_of: str) -> Src | None:
    earlier = [s for s in srcs if s.data.get("as_of") and s.data["as_of"] < as_of]
    return max(earlier, key=lambda s: s.data["as_of"]) if earlier else None


def _subject_sale(sel: Selection, name: str | None) -> dict | None:
    if not (sel.costar_pdf and name):
        return None
    return next((s for s in sel.costar_pdf.data.get("sales", []) if names_match(s.get("name"), name)), None)


def _comp_meta(sel: Selection, name: str | None) -> dict | None:
    if not name:
        return None
    for src in sel.comps:
        for c in src.data.get("comps", []):
            if names_match(c.get("name"), name):
                loc = f"row {c['row'] + 1}" if c.get("row") is not None else f"page {c.get('page', '')}".strip()
                return {**c, "_src": src.source(loc, c.get("name"))}
    return None


def _subject_listing(sel: Selection, name: str | None) -> tuple[str | None, dict | None]:
    if not (sel.listings and name):
        return None, None
    for pname, prop in sel.listings.data.get("properties", {}).items():
        if names_match(pname, name):
            return pname, prop
    return None, None


def _split_address(addr: str | None) -> tuple[str | None, str | None, str | None, str | None]:
    if not addr:
        return None, None, None, None
    m = ADDRESS_RE.match(addr.strip())
    if not m:
        return addr.strip(), None, None, None
    return m.group("street"), m.group("city"), m.group("state"), m.group("zip")


def _period(sel: Selection) -> tuple[Period, list[dict]]:
    for src in (sel.budget, sel.lto):
        p = src.data.get("period") if src else None
        if p and p.get("start") and p.get("end"):
            return Period(_date(p["start"]), _date(p["end"])), []
    as_ofs = [s.data["as_of"] for s in sel.rent_rolls + sel.schedules if s.data.get("as_of")]
    if as_ofs:
        end = _date(max(as_ofs))
        q = (end.month - 1) // 3 + 1
        note = {"severity": "warning", "path": "financials",
                "message": f"Reporting period inferred from the latest rent roll / rent schedule date ({end.isoformat()})"}
        return Period(dt.date(end.year, (q - 1) * 3 + 1, 1), calc.quarter_end(end.year, q)), [note]
    today = dt.date.today()
    q = (today.month - 1) // 3 + 1
    note = {"severity": "error", "path": "financials",
            "message": "Reporting period could not be determined from any file; defaulted to the current quarter. "
                       "Upload a Budget Comparison, Lease Trade-Out or rent roll."}
    return Period(dt.date(today.year, (q - 1) * 3 + 1, 1), calc.quarter_end(today.year, q)), [note]


def _sources_used(sel: Selection) -> list[dict]:
    out = []
    for key in ("budget", "balance_sheet", "lto", "listings", "costar_excel", "costar_pdf", "rent_chart", "capital_calls", "distributions"):
        src = getattr(sel, key)
        if src:
            out.append({"role": key, "doc_type": src.doc_type, "filename": src.filename, "locator": src.locator})
    for key in ("rent_rolls", "schedules", "comps"):
        for src in getattr(sel, key):
            out.append({"role": key, "doc_type": src.doc_type, "filename": src.filename, "locator": src.locator})
    return out


# ---------- sections ----------
def _property(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="property", title="Property", page=1)
    f = s.fields
    rr = _at_or_before(sel.rent_rolls, p.end)
    sch = _at_or_before(sel.schedules, p.end)
    named = [x for x in (rr, sch, *sel.rent_rolls, *sel.schedules) if x and x.data.get("property_name")]
    name_src = named[0] if named else None
    name = name_src.data["property_name"] if name_src else (sel.lto.data.get("property_name") if sel.lto else None)
    ctx.property_name = name
    f["name"] = F("Property name", "text", name,
                  name_src.source("title") if name_src else (sel.lto.source("first row") if sel.lto and name else None))
    units_src = rr or (sel.rent_rolls[-1] if sel.rent_rolls else None)
    if units_src and units_src.data.get("total_units"):
        units, units_source = units_src.data["total_units"], units_src.source("summary block", "Totals")
    elif sch and (sch.data.get("total") or {}).get("units"):
        units, units_source = sch.data["total"]["units"], sch.source("grand total")
    else:
        units, units_source = None, None
    ctx.units = units
    f["units"] = F("Units", "integer", units, units_source)
    sale = _subject_sale(sel, name)
    meta = _comp_meta(sel, name)
    sale_src = sel.costar_pdf.source(f"page {sale['page']}", "sale comps") if sale else None
    yb = sale["year_built"] if sale else (meta.get("year_built") if meta else None)
    f["year_built"] = F("Year built", "integer", yb, sale_src if sale else (meta["_src"] if meta and yb else None))
    f["acquired_date"] = F("Acquisition date", "date", sale["sale_date"] if sale else None, sale_src)
    addr, addr_src = (meta["address"], meta["_src"]) if meta and meta.get("address") else (None, None)
    if addr is None:
        _, prop = _subject_listing(sel, name)
        if prop and prop.get("address"):
            addr, addr_src = prop["address"], sel.listings.source(f"row {prop['first_row'] + 1}", prop["address"])
    street, city, state, zip_ = _split_address(addr)
    f["address"] = F("Street address", "text", street, addr_src)
    city_state, cs_src = (f"{city}, {state}" if city and state else None), addr_src
    cp = sel.costar_pdf
    if city_state is None and cp and cp.data.get("market"):
        city_state = ", ".join(x for x in (cp.data.get("market"), cp.data.get("state")) if x)
        cs_src = cp.source("page 1", "market")
    f["city_state"] = F("City, State", "text", city_state, cs_src)
    f["zip"] = F("ZIP", "text", zip_, addr_src)
    f["submarket"] = F("Submarket", "text", cp.data.get("submarket") if cp else None, cp.source("page 1") if cp and cp.data.get("submarket") else None)
    f["msa"] = F("Market / MSA", "text", cp.data.get("market") if cp else None, cp.source("page 1") if cp and cp.data.get("market") else None)
    sqft = (sch.data.get("total") or {}).get("sqft") if sch else None
    f["avg_unit_sf"] = F("Average unit size (SF)", "number", sqft if sqft else (meta.get("avg_sqft") if meta else None),
                         sch.source("grand total") if sqft else (meta["_src"] if meta and meta.get("avg_sqft") else None))
    f["prepared_by"] = F("Prepared by", "text", cp.data.get("licensed_to") if cp else None,
                         cp.source("footer", "Licensed to") if cp and cp.data.get("licensed_to") else None)
    f["building_class"] = M("Building class", "text")
    f["site_acres"] = M("Site size (acres)", "number")
    f["density"] = D("Density (units per acre)", "number")
    f["hold_period_years"] = M("Hold period (years)", "integer")
    f["description"] = M("Property description", "longtext")
    f["quarter_label"] = D("Quarter", "text")
    f["period_label"] = D("Period", "text")
    f["period_end"] = D("Period end", "date")
    f["prior_quarter_label"] = D("Prior quarter", "text")
    if not name:
        ctx.note("error", "Property name not found in any rent roll, rent schedule or trade-out report", "property.fields.name")
    return s


def _group_label(units: list[dict]) -> str:
    beds = units[0].get("bedrooms")
    baths = sorted({u["bathrooms"] for u in units if u.get("bathrooms") is not None})
    bed_txt = "Other" if beds is None else ("Studio" if beds == 0 else f"{beds} BR")
    if not baths:
        return bed_txt
    bath_txt = f"{baths[0]:g} BA" if len(baths) == 1 else f"{baths[0]:g}-{baths[-1]:g} BA"
    return f"{bed_txt} · {bath_txt}"


def _in_place_rent(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="in_place_rent", title="In-Place Rent by Floor Plan", page=2)
    cur = _at_or_before(sel.schedules, p.end)
    prior = _before(sel.schedules, cur.data["as_of"]) if cur and cur.data.get("as_of") else None
    t = Table(title="In-place rent by floor plan", columns=[
        C("type", "Type", "text"), C("units", "Units", "integer"), C("avg_sf", "Avg SF", "number"),
        C("prior_rent", f"{p.prior_quarter_label} in-place rent"), C("current_rent", f"{p.quarter_label} in-place rent"),
        C("variance", "QoQ variance", derived=True), C("variance_pct", "QoQ variance %", "percent", derived=True)])

    def groups(src: Src | None) -> dict[str, list[dict]]:
        g: dict[str, list[dict]] = {}
        for u in (src.data.get("unit_types", []) if src else []):
            key = f"{u['bedrooms']}br" if u.get("bedrooms") is not None else "other"
            g.setdefault(key, []).append(u)
        return g

    cur_groups, prior_groups = groups(cur), groups(prior)
    for key in sorted(cur_groups, key=lambda k: (k == "other", int(k[:-2]) if k != "other" else 99)):
        us = cur_groups[key]
        label = _group_label(us)
        row = t.new_row(key, label=label)
        src = cur.source(f"rows {', '.join(str(u['row'] + 1) for u in us)}", ", ".join(u.get("code") or u["label"] for u in us))
        row["type"] = F("Type", "text", label, src)
        row["units"] = F("Units", "integer", calc.sum_or_none(u.get("units") for u in us), src)
        row["avg_sf"] = F("Avg SF", "number", calc.wavg((u.get("sqft"), u.get("units")) for u in us), src)
        row["current_rent"] = F(f"{p.quarter_label} in-place rent", "money",
                                calc.wavg((u.get("avg_resident_rent"), u.get("occupied_units")) for u in us), src,
                                note="Average resident rent weighted by occupied units")
        pus = prior_groups.get(key, [])
        row["prior_rent"] = F(f"{p.prior_quarter_label} in-place rent", "money",
                              calc.wavg((u.get("avg_resident_rent"), u.get("occupied_units")) for u in pus) if pus else None,
                              prior.source(f"rows {', '.join(str(u['row'] + 1) for u in pus)}") if pus else None,
                              note=None if pus else "No prior-quarter Market Rent Schedule found for this floor plan")
    t.totals["type"] = F("Type", "text", "Total / Weighted", status="derived")
    t.totals["units"] = D("Units", "integer")
    cur_tot, prior_tot = (cur.data.get("total") or {}) if cur else {}, (prior.data.get("total") or {}) if prior else {}
    t.totals["avg_sf"] = F("Avg SF", "number", cur_tot.get("sqft"), cur.source("grand total") if cur_tot.get("sqft") else None)
    t.totals["current_rent"] = F(f"{p.quarter_label} in-place rent", "money", cur_tot.get("avg_resident_rent"),
                                 cur.source("grand total") if cur_tot.get("avg_resident_rent") else None, status="extracted" if cur_tot.get("avg_resident_rent") else "derived")
    t.totals["prior_rent"] = F(f"{p.prior_quarter_label} in-place rent", "money", prior_tot.get("avg_resident_rent"),
                               prior.source("grand total") if prior_tot.get("avg_resident_rent") else None, status="extracted" if prior_tot.get("avg_resident_rent") else "derived")
    t.totals["variance"] = D("QoQ variance", "money")
    t.totals["variance_pct"] = D("QoQ variance %", "percent")
    s.tables["by_floor_plan"] = t
    s.fields["prior_quarter_label"] = D("Prior quarter", "text")
    s.fields["prior_variance_note"] = M("Prior quarter variance note", "text", note="Optional, e.g. 'vs. -$118 / -8.1% (4Q25 to 1Q26)'")
    s.fields["narrative"] = M("In-place rent commentary", "longtext")
    if not cur:
        ctx.note("error", "No Market Rent Schedule found; the in-place rent table is empty", "in_place_rent")
    elif not prior:
        ctx.note("warning", "Only one Market Rent Schedule found; prior-quarter in-place rents are missing", "in_place_rent")
    return s


def _capital(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="capital", title="Capital Summary", page=3)
    f = s.fields
    bs = sel.balance_sheet
    lines = bs.data["lines"] if bs else []
    used: list[dict] = []
    price = None
    tb = match_lines(lines, [r"^total building"], prefer_total=True)
    tf = match_lines(lines, [r"^total furniture"], prefer_total=True)
    if tb:
        used = tb + tf
        price = (tb[0]["values"].get("current") or 0) + ((tf[0]["values"].get("current") or 0) if tf else 0)
    else:
        for pat in (r"^land$", r"^buildings?$", r"^furniture"):
            hit = match_lines(lines, [pat])
            if hit:
                used.append(hit[0])
        if used:
            price = sum(h["values"].get("current") or 0 for h in used)
    src = bs.source(f"rows {', '.join(str(h['row'] + 1) for h in used)}", " + ".join(h["label"] for h in used)) if used else None
    f["purchase_price"] = F("Purchase price", "money", price, src, note="Land + Building + FF&E at cost from the balance sheet" if used else None)
    sale = _subject_sale(sel, ctx.property_name)
    if sale and sale.get("price"):
        alt_src = sel.costar_pdf.source(f"page {sale['page']}", "CoStar sale comps")
        if price is None:
            f["purchase_price"] = F("Purchase price", "money", sale["price"], alt_src, note="CoStar recorded sale price")
        elif abs(sale["price"] - price) / price > 0.01:
            f["purchase_price"].status = "conflict"
            f["purchase_price"].alternatives.append(Alternative(value=sale["price"], source=Source(**alt_src), note="CoStar recorded sale price"))
            ctx.note("warning", f"Purchase price: balance sheet basis ${price:,.0f} differs from the CoStar sale price ${sale['price']:,.0f}. "
                                "The balance sheet value is used; choose the alternative to show the contract price.", "capital.fields.purchase_price")
    f["price_per_unit"] = D("Price per unit", "money")
    eq = match_lines(lines, [r"owner'?s? contributions?", r"contributed capital", r"partners?'? contributions?", r"capital contributions?", r"members?'? contributions?"])
    f["equity_invested"] = F("Equity invested (ITD)", "money", eq[0]["values"].get("current") if eq else None,
                             bs.source(f"row {eq[0]['row'] + 1}", eq[0]["label"]) if eq else None)
    cc = sel.capital_calls
    if cc:
        in_q = [c for c in cc.data.get("calls", []) if c.get("due_date") and p.start.isoformat() <= c["due_date"] <= p.end.isoformat()]
        if in_q:
            q_amt = sum(c.get("amount") or 0 for c in in_q)
        elif cc.data.get("none") or cc.data.get("total_called") == 0:
            q_amt = 0.0
        else:
            q_amt = None
        f["quarter_contributions"] = F(f"{p.quarter_label} equity contributions", "money", q_amt, cc.source(),
                                       note=None if q_amt is not None else "Capital calls exist but none fall in the reporting period; confirm")
        f["total_called"] = F("Total called (ITD)", "money", cc.data.get("total_called"), cc.source())
    else:
        f["quarter_contributions"] = M(f"{p.quarter_label} equity contributions", "money")
        f["total_called"] = M("Total called (ITD)", "money")
    dd = sel.distributions
    if dd:
        dl = dd.data.get("distributions", [])
        in_q = [x for x in dl if x.get("date") and p.start.isoformat() <= x["date"] <= p.end.isoformat()]
        f["distributions_itd"] = F("Cash distributions (ITD)", "money", dd.data.get("total_gross"), dd.source())
        f["quarter_distributions"] = F(f"{p.quarter_label} distributions", "money",
                                       sum(x.get("gross") or 0 for x in in_q) if dl else (0.0 if dd.data.get("none") else None), dd.source())
    else:
        f["distributions_itd"] = M("Cash distributions (ITD)", "money")
        f["quarter_distributions"] = M(f"{p.quarter_label} distributions", "money")
    f["contributions_note"] = D("Contributions caption", "text")
    f["distributions_note"] = D("Distributions caption", "text")
    f["business_plan_summary"] = M("Business plan summary", "longtext")
    if not bs:
        ctx.note("warning", "No balance sheet found; purchase price, equity and loan principal are missing", "capital")
    return s


def _underwriting(ctx: Ctx, data: ReportData) -> Section:
    s = Section(key="underwriting", title="Original Underwriting Budget", page=3)
    t = Table(title="Original underwriting budget", columns=[
        C("category", "Category", "text"), C("section", "Section (value_add | recurring)", "text"),
        C("original_budget", "Original budget"), C("spent_to_date", "Spent to date"),
        C("pct_spent", "% spent", "percent", derived=True)], editable_rows=True)
    for ck in ("original_budget", "spent_to_date", "pct_spent"):
        t.totals[ck] = D(t.columns[[c.key for c in t.columns].index(ck)].label, "percent" if ck == "pct_spent" else "money")
    t.totals["category"] = F("Category", "text", "Total Underwritten Capital", status="derived")
    s.tables["budget"] = t
    s.fields["spent_period_note"] = M("Spent-to-date period note", "text", note="e.g. 'Spent to Date reflects the period 08/2025 - 06/2026'")
    s.fields["business_plan_title"] = M("Business plan headline", "text")
    ctx.note("info", "The original underwriting budget is not in any source file; add rows on the review screen", "underwriting")
    return s


def _computed_trend(ctx: Ctx) -> list[dict]:
    sel = ctx.sel
    months: dict[str, dict] = {}

    def slot(ym: str) -> dict:
        return months.setdefault(ym, {"sn": 0, "sr": 0.0, "se": 0.0, "ss": 0.0, "cn": 0, "cr": 0.0, "ce": 0.0, "cs": 0.0})

    if sel.lto:
        for r in sel.lto.data.get("sections", {}).get("move_ins", {}).get("rows", []):
            if not (r.get("start") and r.get("sqft") and r.get("lease_rent") is not None):
                continue
            m = slot(r["start"][:7])
            m["sn"] += 1
            m["sr"] += r["lease_rent"]
            m["se"] += r["effective_rent"] if r.get("effective_rent") is not None else r["lease_rent"]
            m["ss"] += r["sqft"]
    if sel.listings:
        subject, _ = _subject_listing(sel, ctx.property_name)
        for pname, prop in sel.listings.data.get("properties", {}).items():
            if pname == subject:
                continue
            for ym, agg in prop.get("monthly", {}).items():
                m = slot(ym)
                m["cn"] += agg["n"]
                m["cr"] += agg["asking_sum"]
                m["ce"] += agg["effective_sum"]
                m["cs"] += agg["sqft_sum"]
    end = ctx.period.end
    first = dt.date(end.year - 1, end.month, 1) + dt.timedelta(days=32)  # twelve months ending at the period end
    lo, hi = first.strftime("%Y-%m"), end.strftime("%Y-%m")
    return [{"month": ym, "subject_n": m["sn"] or None, "subject_gross_psf": calc.ratio(m["sr"], m["ss"]),
             "subject_eff_psf": calc.ratio(m["se"], m["ss"]), "comp_n": m["cn"] or None,
             "comp_gross_psf": calc.ratio(m["cr"], m["cs"]), "comp_eff_psf": calc.ratio(m["ce"], m["cs"])}
            for ym, m in sorted(months.items()) if lo <= ym <= hi]


def _rent_trend(ctx: Ctx, data: ReportData) -> Section:
    sel = ctx.sel
    s = Section(key="rent_trend", title="Submarket Rent Trend", page=3)
    f = s.fields
    t = Table(title="New-lease rent per SF by month", columns=[
        C("month", "Month", "text"), C("subject_n", "Subject leases", "integer"), C("subject_gross_psf", "Subject gross $/SF", "number"),
        C("subject_eff_psf", "Subject effective $/SF", "number"), C("comp_n", "Comp leases", "integer"),
        C("comp_gross_psf", "Comp gross $/SF", "number"), C("comp_eff_psf", "Comp effective $/SF", "number")], editable_rows=True)
    rc = sel.rent_chart
    if rc:
        for m in rc.data.get("months", []):
            row = t.new_row(m["month"], label=calc.month_label(m["month"]))
            src = rc.source(f"row {m['row'] + 1}", m["month"])
            for c in t.columns:
                val = m["month"] if c.key == "month" else m.get(c.key)
                row[c.key] = F(c.label, c.kind, val, src if val is not None else None)
        f["subject_name"] = F("Subject series name", "text", rc.data.get("subject_name") or ctx.property_name, rc.source("header row"))
        f["comp_name"] = F("Comp series name", "text", rc.data.get("comp_name") or "Comp Set", rc.source("header row"))
        f["chart_title"] = F("Chart title", "text", rc.data.get("title") or None, rc.source("row 1"))
        f["chart_subtitle"] = F("Chart subtitle", "text", rc.data.get("subtitle") or None, rc.source("row 2"))
        note = next((n for n in rc.data.get("notes", []) if n.lower().startswith("source")), None)
        f["methodology_note"] = F("Methodology note", "text", note, rc.source("notes") if note else None)
    else:
        months = _computed_trend(ctx)
        base = sel.lto or sel.listings
        src = base.source("computed") if base else None
        for m in months:
            row = t.new_row(m["month"], label=calc.month_label(m["month"]))
            for c in t.columns:
                val = m["month"] if c.key == "month" else m.get(c.key)
                row[c.key] = F(c.label, c.kind, val, src if val is not None else None,
                               note="Computed from LTO move-ins and HelloData leased listings" if val is not None else None)
        f["subject_name"] = F("Subject series name", "text", ctx.property_name)
        f["comp_name"] = F("Comp series name", "text", "HelloData Comp Set" if sel.listings else None)
        f["chart_title"] = F("Chart title", "text", f"{ctx.property_name} vs. HelloData Comp Set" if ctx.property_name and months else None)
        f["chart_subtitle"] = F("Chart subtitle", "text",
                                f"{calc.month_label(months[0]['month'])} - {calc.month_label(months[-1]['month'])}" if months else None)
        f["methodology_note"] = F("Methodology note", "text",
                                  "Computed: SF-weighted new-lease gross and effective rent per month from Yardi LTO move-ins (subject) "
                                  "and HelloData leased listings (comps). Window limited to the files supplied." if months else None)
        if not months:
            ctx.note("warning", "No rent chart workbook and not enough LTO / HelloData data to compute the rent trend; the page 3 chart will be empty", "rent_trend")
    f["caption"] = M("Chart caption", "longtext")
    s.tables["monthly"] = t
    return s


def _financing(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="financing", title="Financing", page=4)
    f = s.fields
    bs = sel.balance_sheet
    lines = bs.data["lines"] if bs else []
    loan = match_lines(lines, [r"^total mortgage payable", r"mortgage payable", r"notes? payable", r"loan payable", r"^total long term liabilities"], prefer_total=True)
    f["loan_amount"] = F("Loan principal", "money", loan[0]["values"].get("current") if loan else None,
                         bs.source(f"row {loan[0]['row'] + 1}", loan[0]["label"]) if loan else None)
    interest, i_src, i_note = None, None, None
    acc = match_lines(lines, [r"accrued interest"])
    if acc and acc[0]["values"].get("current"):
        interest, i_src, i_note = acc[0]["values"]["current"], bs.source(f"row {acc[0]['row'] + 1}", acc[0]["label"]), "Accrued interest at period end (one month of interest)"
    elif sel.budget:
        il = match_lines(sel.budget.data["lines"], [r"^total debt service", r"interest expense"], prefer_total=True)
        ptd = il[0]["values"].get("ptd_actual") if il else None
        if ptd is not None:
            interest, i_src = ptd / p.months, sel.budget.source(f"row {il[0]['row'] + 1}", il[0]["label"])
            i_note = f"PTD debt service / {p.months} months (approximate)"
    f["interest_monthly"] = F("Monthly interest (IO payment)", "money", interest, i_src, note=i_note)
    f["implied_rate"] = D("Implied interest rate", "percent", note="interest_monthly x 12 / loan_amount")
    reserve = match_lines(lines, [r"capital improvements? escrow", r"replacement reserve", r"escrow / reserve"])
    f["reserve_balance"] = F("Replacement reserve balance", "money", reserve[0]["values"].get("current") if reserve else None,
                             bs.source(f"row {reserve[0]['row'] + 1}", reserve[0]["label"]) if reserve else None)
    ent = sel.capital_calls or sel.distributions
    f["borrower"] = F("Borrower", "text", ent.data.get("entity") if ent else None, ent.source("entity header") if ent and ent.data.get("entity") else None)
    for key, label, kind in (
        ("lender", "Lender", "text"), ("servicer", "Servicer", "text"), ("rate", "Interest rate", "percent"), ("rate_type", "Rate type", "text"),
        ("effective_date", "Effective date", "date"), ("maturity_date", "Maturity date", "date"), ("term_months", "Loan term (months)", "integer"),
        ("io_months", "Interest-only period (months)", "integer"), ("io_end_date", "IO end date", "date"), ("amort_years", "Amortization (years)", "integer"),
        ("pi_payment", "P&I payment (monthly)", "money"), ("recourse", "Recourse", "text"), ("prepayment", "Prepayment terms", "text"),
        ("yield_maintenance_through", "Yield maintenance through", "date"), ("open_prepay_months", "Open prepayment window (months)", "integer"),
        ("replacement_reserve_monthly", "Replacement reserve (monthly)", "money"), ("repairs_escrow", "Repairs escrow (one-time)", "money"),
    ):
        f[key] = M(label, kind, note="Loan documents were not supplied; enter manually")
    f["replacement_reserve_annual"] = D("Replacement reserve (annual)", "money")
    f["narrative"] = M("Financing commentary", "longtext")
    return s


def _financials(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="financials", title="Financial Performance", page=6)
    cols = [C("ptd_actual", f"{p.quarter_label} actual"), C("ptd_budget", f"{p.quarter_label} budget"), C("ptd_var", "Var $", derived=True),
            C("ptd_var_pct", "Var %", "percent", derived=True), C("ytd_actual", "YTD actual"), C("ytd_budget", "YTD budget"),
            C("ytd_var", "YTD var $", derived=True), C("ytd_var_pct", "YTD var %", "percent", derived=True), C("annual_budget", "Annual budget")]
    t = Table(title="Actual vs budget", columns=cols)
    labels = {c.key: c.label for c in cols}
    b = sel.budget
    lines = b.data["lines"] if b else []
    have = set(b.data.get("columns", [])) if b else set()
    key_map = {k: k for k in VALUE_COLS}
    if b and "ptd_actual" not in have and "mtd_actual" in have:
        key_map["ptd_actual"], key_map["ptd_budget"] = "mtd_actual", "mtd_budget"
        ctx.note("warning", "The Budget Comparison has only MTD columns; the quarter columns show one month", "financials")
    for m in load_pl_mapping(settings.config_dir):
        row = t.new_row(m["key"], label=m["label"])
        t.row_meta[m["key"]].update({"group": m["group"], "expense": bool(m.get("expense", False))})
        hits = match_lines(lines, m["match"], prefer_total=bool(m.get("total", False))) if lines else []
        if hits and not m.get("sum"):
            hits = hits[:1]
        src = b.source(f"rows {', '.join(str(h['row'] + 1) for h in hits)}", " + ".join(h["label"] for h in hits)) if hits else None
        for ck in VALUE_COLS:
            vals = [h["values"].get(key_map[ck]) for h in hits]
            val = calc.sum_or_none(vals) if hits else None
            row[ck] = F(labels[ck], "money", val, src if val is not None else None,
                        note=None if hits else "No line in the Budget Comparison matched this row")
    s.tables["lines"] = t
    s.fields["period_label"] = D("Period", "text")
    s.fields["ytd_label"] = D("YTD period", "text")
    if not b:
        ctx.note("error", "No Yardi Budget Comparison found; the financial performance table is empty", "financials")
    return s


KPI_FIELDS = [
    ("revenue_actual", "Revenue actual", "money"), ("revenue_budget", "Revenue budget", "money"), ("revenue_var", "Revenue variance", "money"),
    ("revenue_var_pct", "Revenue variance %", "percent"), ("gpr_var_pct", "GPR variance %", "percent"),
    ("gain_to_lease_actual", "Gain/loss to lease actual", "money"), ("gain_to_lease_budget", "Gain/loss to lease budget", "money"),
    ("gain_to_lease_var_pct", "Gain/loss to lease variance %", "percent"), ("concessions_var", "Concessions variance", "money"),
    ("opex_actual", "Opex actual", "money"), ("opex_budget", "Opex budget", "money"), ("opex_var", "Opex variance", "money"),
    ("opex_var_pct", "Opex variance %", "percent"), ("insurance_var", "Insurance variance", "money"), ("utilities_var", "Utilities variance", "money"),
    ("noi_actual", "NOI actual", "money"), ("noi_budget", "NOI budget", "money"), ("noi_var", "NOI variance", "money"),
    ("noi_var_pct", "NOI variance %", "percent"), ("noi_ytd_var_pct", "NOI YTD variance %", "percent"),
    ("debt_service_actual", "Debt service", "money"), ("ncf_actual", "Net cash flow actual", "money"), ("ncf_budget", "Net cash flow budget", "money"),
    ("ncf_var", "Net cash flow variance", "money"), ("ncf_var_pct", "Net cash flow variance %", "percent"),
    ("capex_actual", "Capital spend actual", "money"), ("capex_budget", "Capital spend budget", "money"), ("capex_var", "Capital spend variance", "money"),
    ("capex_ytd_actual", "Capital spend YTD actual", "money"), ("capex_ytd_budget", "Capital spend YTD budget", "money"),
    ("capex_ytd_var", "Capital spend YTD variance", "money"), ("capex_annual_budget", "Capital annual budget", "money"),
]
NARRATIVE_FIELDS = [
    ("takeaway", "Quarter takeaway"), ("revenue_body", "Revenue commentary"), ("revenue_outlook", "Revenue outlook"),
    ("opex_body", "Operating expense commentary"), ("opex_outlook", "Operating expense outlook"),
    ("noi_body", "NOI and cash flow commentary"), ("noi_outlook", "NOI outlook"),
]


def _commentary(ctx: Ctx, data: ReportData) -> Section:
    s = Section(key="commentary", title="Financial & Capital Commentary", page=5)
    for key, label, kind in KPI_FIELDS:
        s.fields[key] = D(label, kind)
    for key, label in NARRATIVE_FIELDS:
        s.fields[key] = M(label, "longtext", note="Write or draft with AI from the numbers above")
    return s


def _capex(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="capex", title="Capital Projects", page=7)
    cfg = load_capex_mapping(settings.config_dir)
    sec = cfg["sections"]
    cols = [C("ptd_actual", f"{p.quarter_label} actual"), C("ptd_budget", f"{p.quarter_label} budget"), C("ptd_var", "Var $", derived=True),
            C("ytd_actual", "YTD actual"), C("ytd_budget", "YTD budget"), C("ytd_var", "YTD var $", derived=True), C("annual_budget", "Annual budget")]
    t = Table(title="Capital projects", columns=cols)
    labels = {c.key: c.label for c in cols}
    b = sel.budget
    if b:
        lines = []
        for ln in b.data["lines"]:
            if ln["is_total"] or ln["unlabeled"] or not section_matches(ln["section"], sec["include"], sec["exclude"]):
                continue
            copy = dict(ln)
            copy["_sign"] = -1 if section_matches(ln["section"], sec["negate"], []) else 1
            lines.append(copy)
        groups, leftover = consume_capex(lines, cfg.get("rows", []))
        entries = [(m["key"], m["label"], hit) for m, hit in groups if hit] + [(slug(ln["label"]), ln["label"], [ln]) for ln in leftover]
        for key, label, hit in entries:
            k, i = key, 2
            while k in t.rows:
                k, i = f"{key}-{i}", i + 1
            row = t.new_row(k, label=label)
            t.row_meta[k].update({"expense": True, "accounts": [h["code"] or h["label"] for h in hit]})
            src = b.source(f"rows {', '.join(str(h['row'] + 1) for h in hit)}", " + ".join(h["label"] for h in hit))
            for ck in VALUE_COLS:
                vals = [(h["values"][ck]) * h["_sign"] for h in hit if h["values"].get(ck) is not None]
                row[ck] = F(labels[ck], "money", sum(vals) if vals else None, src if vals else None)
        unl = [ln for ln in b.data["lines"] if ln["unlabeled"] and ln["values"].get("ptd_actual") is not None]
        if unl:
            s.fields["source_total_ptd"] = F("Source capital total (Yardi summary row)", "money", unl[-1]["values"]["ptd_actual"],
                                             b.source(f"row {unl[-1]['row'] + 1}"), note="Yardi's own capital total; used to cross-check the table")
        if not entries:
            ctx.note("warning", "No capital lines found in the Budget Comparison (no renovation / improvement sections)", "capex")
    for ck in VALUE_COLS + ("ptd_var", "ytd_var"):
        t.totals[ck] = D(labels[ck], "money")
    s.tables["lines"] = t
    s.fields["narrative"] = M("Capital commentary", "longtext")
    return s


def _submarket(ctx: Ctx, data: ReportData) -> Section:  # noqa: C901
    sel, p = ctx.sel, ctx.period
    s = Section(key="submarket", title="Submarket Comparison", page=8)
    f = s.fields
    cx, cp = sel.costar_excel, sel.costar_pdf
    cur = prior = None
    if cx:
        series = cx.data.get("series", [])
        cur = next((r for r in series if r["year"] == p.year and r["quarter"] == p.quarter and not r["flag"]), None)
        pq = (p.year, p.quarter - 1) if p.quarter > 1 else (p.year - 1, 4)
        prior = next((r for r in series if (r["year"], r["quarter"]) == pq and not r["flag"]), None)
        if cur is None:
            ctx.note("warning", f"The CoStar table has no row for {p.year} Q{p.quarter}", "submarket")

    def cs(key: str, label: str, kind: str, rec: dict | None) -> Field:
        val = rec.get(key) if rec else None
        return F(label, kind, val, cx.source(f"row {rec['row'] + 1}", rec["period"]) if rec and val is not None else None)

    f["vacancy"] = cs("vacancy", "Submarket vacancy", "percent", cur)
    f["prior_vacancy"] = cs("vacancy", "Prior quarter vacancy", "percent", prior)
    f["rent_growth_yoy"] = cs("rent_growth", "YoY asking rent growth", "percent", cur)
    f["prior_rent_growth"] = cs("rent_growth", "Prior quarter YoY rent growth", "percent", prior)
    f["avg_asking_rent"] = cs("asking_rent", "Average market asking rent", "money", cur)
    f["under_construction"] = cs("under_construction", "Units under construction", "integer", cur)
    f["uc_pct"] = cs("uc_pct", "Under construction % of inventory", "percent", cur)
    f["inventory"] = cs("inventory", "Submarket inventory (units)", "integer", cur)
    if cp:
        ks = cp.data.get("key_stats") or {}
        for key, ks_key, label, kind in (("vacancy", "vacancy", "Submarket vacancy", "percent"), ("avg_asking_rent", "asking_rent", "Average market asking rent", "money"),
                                         ("under_construction", "under_construction", "Units under construction", "integer"), ("inventory", "inventory", "Submarket inventory (units)", "integer")):
            if f[key].value is None and ks.get(ks_key) is not None:
                f[key] = F(label, kind, ks[ks_key], cp.source("key indicators"), note="From the CoStar PDF key indicators (report date, not quarter end)")
        f["submarket_name"] = F("Submarket", "text", cp.data.get("submarket"), cp.source("page 1"))
        f["market_name"] = F("Market", "text", cp.data.get("market"), cp.source("page 1"))
        dl = cp.data.get("deliveries", [])
        f["recent_deliveries"] = F("Recent deliveries", "text", "; ".join(f"{d['name']} ({d['units']} units, {d['complete']})" for d in dl) or None,
                                   cp.source("recent deliveries") if dl else None)
    else:
        f["submarket_name"], f["market_name"], f["recent_deliveries"] = M("Submarket", "text"), M("Market", "text"), M("Recent deliveries", "text")
    f["pipeline_note"] = D("Pipeline caption", "text")
    f["data_quarter"] = D("CoStar data quarter", "text")
    f["source_note"] = D("Source note", "text")
    f["footnote"] = D("Comp table footnote", "text")
    t = Table(title="Comp set", columns=[
        C("name", "Property", "text"), C("units", "Units", "integer"), C("vintage", "Vintage", "integer"), C("leased_pct", "Leased %", "percent"),
        C("asking_rent", "Asking rent"), C("effective_rent", "Effective rent (NER)"), C("concession", "Concession $/mo", derived=True),
        C("concession_pct", "Concession %", "percent", derived=True)], editable_rows=True)
    cur_rr = _at_or_before(sel.rent_rolls, p.end)
    li = sel.listings
    if li:
        props = li.data.get("properties", {})
        subject = next((n for n in props if names_match(n, ctx.property_name)), None) if ctx.property_name else None
        order = ([subject] if subject else []) + sorted((n for n in props if n != subject),
                                                        key=lambda n: -(props[n]["asking_sum"] / props[n]["asking_n"] if props[n]["asking_n"] else 0))
        for name in order:
            pr = props[name]
            key = slug(name)
            row = t.new_row(key, label=name)
            is_subject = name == subject
            t.row_meta[key]["subject"] = is_subject
            src = li.source(f"rows from {pr['first_row'] + 1}", f"{pr['rows']} listings")
            row["name"] = F("Property", "text", name, src)
            meta = _comp_meta(sel, name)
            row["units"] = F("Units", "integer", meta.get("units") if meta else None, meta["_src"] if meta and meta.get("units") else None,
                             note=None if meta and meta.get("units") else "Unit count is not in the listings export; supply a HelloData comp summary or enter it")
            row["vintage"] = F("Vintage", "integer", meta.get("year_built") if meta else None, meta["_src"] if meta and meta.get("year_built") else None,
                               note=None if meta and meta.get("year_built") else "Year built is not in the listings export; enter it")
            row["asking_rent"] = F("Asking rent", "money", calc.ratio(pr["asking_sum"], pr["asking_n"]), src, note="Mean asking rent across all listing rows")
            row["effective_rent"] = F("Effective rent (NER)", "money", calc.ratio(pr["effective_sum"], pr["effective_n"]), src, note="Mean effective rent across all listing rows")
            if is_subject and cur_rr and cur_rr.data.get("occupancy_pct") is not None:
                row["leased_pct"] = F("Leased %", "percent", cur_rr.data["occupancy_pct"], cur_rr.source("summary block"), note="Physical occupancy per the Yardi rent roll")
            else:
                row["leased_pct"] = F("Leased %", "percent", calc.ratio(pr["leased"], pr["rows"]), src, note="Leased listings / all listings")
    else:
        for src in sel.comps:
            for c in src.data.get("comps", []):
                if c.get("avg_rent") is None:
                    continue
                key = slug(c["name"])
                if key in t.rows:
                    continue
                row = t.new_row(key, label=c["name"])
                t.row_meta[key]["subject"] = names_match(c["name"], ctx.property_name)
                loc = src.source(f"page {c.get('page', '')}".strip(), c["name"])
                row["name"] = F("Property", "text", c["name"], loc)
                row["units"] = F("Units", "integer", c.get("units"), loc if c.get("units") else None)
                row["vintage"] = F("Vintage", "integer", c.get("year_built"), loc if c.get("year_built") else None)
                row["asking_rent"] = F("Asking rent", "money", c.get("avg_rent"), loc)
                row["effective_rent"] = F("Effective rent (NER)", "money", c.get("ner"), loc)
                lc, ac = c.get("leased_count"), c.get("active_count")
                row["leased_pct"] = F("Leased %", "percent", calc.ratio(lc, (lc or 0) + (ac or 0)) if lc is not None else c.get("leased_pct"), loc)
        if not t.rows:
            ctx.note("warning", "No HelloData listings export or comp summary found; the comp table is empty (add rows manually)", "submarket")
    t.totals["name"] = F("Property", "text", "Comp set average", status="derived")
    for ck, label, kind in (("units", "Units", "integer"), ("vintage", "Vintage", "integer"), ("leased_pct", "Leased %", "percent"),
                            ("asking_rent", "Asking rent", "money"), ("effective_rent", "Effective rent (NER)", "money"),
                            ("concession", "Concession $/mo", "money"), ("concession_pct", "Concession %", "percent")):
        t.totals[ck] = D(label, kind)
    s.tables["comps"] = t
    for key, label in (("occupancy_narrative", "Occupancy commentary"), ("rent_narrative", "Effective rent commentary"), ("concession_narrative", "Concessions commentary")):
        f[key] = M(label, "longtext")
    if not cx and not cp:
        ctx.note("warning", "No CoStar submarket data found; vacancy, rent growth and pipeline are missing", "submarket")
    return s


def _occupancy(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="occupancy", title="Occupancy & Leasing", page=9)
    f = s.fields
    cur = _at_or_before(sel.rent_rolls, p.end)
    prior = _before(sel.rent_rolls, cur.data["as_of"]) if cur and cur.data.get("as_of") else None

    def rr(rec: Src | None, key: str, label: str, kind: str) -> Field:
        val = rec.data.get(key) if rec else None
        return F(label, kind, val, rec.source("summary block") if rec and val is not None else None)

    f["current_date"] = F("Current as-of date", "date", cur.data.get("as_of") if cur else None, cur.source("header") if cur and cur.data.get("as_of") else None)
    f["current_pct"] = rr(cur, "occupancy_pct", "Occupancy (current)", "percent")
    f["current_occupied"] = rr(cur, "occupied_units", "Occupied units (current)", "integer")
    f["total_units"] = rr(cur, "total_units", "Total units", "integer")
    f["future_applicants"] = rr(cur, "future_applicants", "Future residents / applicants", "integer")
    f["prior_date"] = F("Prior as-of date", "date", prior.data.get("as_of") if prior else None, prior.source("header") if prior and prior.data.get("as_of") else None)
    f["prior_pct"] = rr(prior, "occupancy_pct", "Occupancy (prior)", "percent")
    f["prior_occupied"] = rr(prior, "occupied_units", "Occupied units (prior)", "integer")
    f["change_bps"] = D("Occupancy change (bps)", "number")
    if not cur:
        ctx.note("error", "No rent roll found; occupancy is missing", "occupancy")
    else:
        if cur.data.get("as_of") and cur.data["as_of"] != p.end.isoformat():
            ctx.note("warning", f"The latest rent roll is dated {cur.data['as_of']}, not the period end {p.end.isoformat()}", "occupancy.fields.current_date")
        if not prior:
            ctx.note("warning", "Only one rent roll found; prior-quarter occupancy is missing", "occupancy.fields.prior_pct")
    lto = sel.lto
    for tkey, skey, title in (("new_leases", "move_ins", "New leases by floor plan"), ("renewals", "renewals", "Renewals by floor plan")):
        t = Table(title=title, columns=[
            C("floor_plan", "Floor plan", "text"), C("sqft", "SF", "integer"), C("count", "Count", "integer"), C("avg_prior", "Avg prior rent"),
            C("avg_current", "Avg current rent"), C("lto", "$ trade-out", derived=True), C("lto_pct", "% trade-out", "percent", derived=True)])
        rows = lto.data.get("sections", {}).get(skey, {}).get("rows", []) if lto else []
        groups: dict[str, list[dict]] = {}
        for r in rows:
            groups.setdefault(r["unit_type"], []).append(r)
        for ut, rs in sorted(groups.items(), key=lambda kv: (kv[1][0].get("sqft") or 0, kv[0])):
            key = slug(ut)
            row = t.new_row(key, label=ut)
            src = lto.source(f"rows {rs[0]['row'] + 1}-{rs[-1]['row'] + 1}", ut)
            row["floor_plan"] = F("Floor plan", "text", ut, src)
            row["sqft"] = F("SF", "integer", rs[0].get("sqft"), src)
            row["count"] = F("Count", "integer", len(rs), src)
            row["avg_prior"] = F("Avg prior rent", "money", calc.mean(r.get("prev_lease_rent") for r in rs), src)
            row["avg_current"] = F("Avg current rent", "money", calc.mean(r.get("lease_rent") for r in rs), src)
        t.totals["floor_plan"] = F("Floor plan", "text", "Total", status="derived")
        for ck, label, kind in (("count", "Count", "integer"), ("avg_prior", "Avg prior rent", "money"), ("avg_current", "Avg current rent", "money"),
                                ("lto", "$ trade-out", "money"), ("lto_pct", "% trade-out", "percent")):
            t.totals[ck] = D(label, kind)
        s.tables[tkey] = t
    f["new_lease_count"] = D("New leases executed", "integer")
    f["renewal_count"] = D("Renewals executed", "integer")
    f["new_lease_lto_pct"] = D("New lease trade-out %", "percent")
    f["renewal_lto_pct"] = D("Renewal trade-out %", "percent")
    lp = (lto.data.get("period") or {}) if lto else {}
    f["lto_period_note"] = F("Trade-out period note", "text",
                             f"LTO reflects leases of all terms with a renewal commencement or new lease start date within {p.quarter_label} "
                             f"({lp.get('start', p.start.isoformat())} to {lp.get('end', p.end.isoformat())}). Source: Yardi Lease Trade-Out report." if lto else None,
                             lto.source("section headers") if lto else None)
    if not lto:
        ctx.note("warning", "No Lease Trade-Out report found; new-lease and renewal tables are empty", "occupancy")
    elif lp.get("end") and lp["end"] != p.end.isoformat():
        ctx.note("warning", f"The Lease Trade-Out report covers {lp.get('start')} to {lp.get('end')}, which is not the reporting period", "occupancy")
    for key, label in (("occupancy_narrative", "Occupancy commentary"), ("new_lease_narrative", "New lease commentary"), ("renewal_narrative", "Renewal commentary")):
        f[key] = M(label, "longtext")
    return s


def _status(ctx: Ctx, data: ReportData) -> Section:
    sel, p = ctx.sel, ctx.period
    s = Section(key="status", title="Status Update & Next Quarter Goals", page=10)
    f = s.fields
    b = sel.budget
    lines = b.data["lines"] if b else []
    col = match_lines(lines, [r"former resident collections", r"collections? recover", r"bad debt recover", r"^collections"])
    wo = match_lines(lines, [r"write.?off bad debt", r"bad debt write", r"^bad debt"])
    f["collections_recovered"] = F(f"{p.quarter_label} collections recovered", "money", col[0]["values"].get("ptd_actual") if col else None,
                                   b.source(f"row {col[0]['row'] + 1}", col[0]["label"]) if col else None)
    f["bad_debt_writeoff"] = F(f"{p.quarter_label} bad debt write-offs", "money", wo[0]["values"].get("ptd_actual") if wo else None,
                               b.source(f"row {wo[0]['row'] + 1}", wo[0]["label"]) if wo else None)
    f["next_quarter_label"] = D("Next quarter", "text")
    for i in (1, 2, 3):
        f[f"status{i}_title"] = M(f"Status item {i}: title", "text")
        f[f"status{i}_subtitle"] = M(f"Status item {i}: headline", "text")
        f[f"status{i}_body"] = M(f"Status item {i}: body", "longtext")
    for i in (1, 2, 3):
        f[f"goal{i}_title"] = M(f"Goal {i}: title", "text")
        f[f"goal{i}_subtitle"] = M(f"Goal {i}: headline", "text")
        f[f"goal{i}_body"] = M(f"Goal {i}: body", "longtext")
    return s


SECTION_BUILDERS = (_property, _in_place_rent, _capital, _underwriting, _rent_trend, _financing, _financials, _commentary, _capex, _submarket, _occupancy, _status)


def build(project: dict, files: list[dict]) -> tuple[ReportData, list[dict]]:
    """Consolidate processed files into ReportData. Returns (data, notes) where notes are selection/period issues."""
    sel = select(collect(files))
    period, period_notes = _period(sel)
    ctx = Ctx(sel=sel, period=period, notes=list(sel.notes) + period_notes)
    data = ReportData(meta={
        "project_id": project.get("id"), "project_name": project.get("name"),
        "period": {"start": period.start.isoformat(), "end": period.end.isoformat(), "quarter_label": period.quarter_label},
        "sources": _sources_used(sel),
    })
    for fn in SECTION_BUILDERS:
        sec = fn(ctx, data)
        data.sections[sec.key] = sec
    data.meta["property_name"] = ctx.property_name
    calc.recompute(data)
    return data, ctx.notes


def apply_overrides(data: ReportData, overrides: dict) -> list[str]:
    """Apply AI drafts, manual rows, row deletions and field overrides. Returns paths that no longer exist."""
    stale: list[str] = []
    for path, text in (overrides.get("ai_drafts") or {}).items():
        f = data.field(path)
        if f is None:
            stale.append(path)
            continue
        if f.value in (None, "") or f.status in ("missing", "ai_draft"):
            f.value, f.status = text, "ai_draft"
            f.source = Source(text="Drafted by AI from the section's structured data only; review before publishing")
    for tpath, rows in (overrides.get("rows") or {}).items():
        t = data.table(tpath)
        if t is None:
            stale.append(tpath)
            continue
        for rkey, cells in rows.items():
            label = next((str(v) for v in cells.values() if isinstance(v, str) and v), rkey)
            row = t.rows.get(rkey) or t.new_row(rkey, label=label, manual=True)
            t.row_meta.setdefault(rkey, {})["manual"] = True
            for ckey, val in cells.items():
                if ckey in row and row[ckey].status != "derived":
                    row[ckey].value, row[ckey].status = val, "manual"
    for tpath, keys in (overrides.get("deleted_rows") or {}).items():
        t = data.table(tpath)
        if t is None:
            continue
        for k in keys:
            t.rows.pop(k, None)
            t.row_meta.pop(k, None)
    for path, val in (overrides.get("fields") or {}).items():
        f = data.field(path)
        if f is None:
            stale.append(path)
            continue
        f.override = val
    return stale
