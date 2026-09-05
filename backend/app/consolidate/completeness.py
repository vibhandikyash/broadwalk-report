"""What a finished investor report needs, decided in one place.

`structural` (files ingested, values extracted, a PDF renders) is decided elsewhere and always allowed.
`complete` means every requirement below is met on the effective data. Requirements name the page they
land on so the review screen and the validation evidence can show gaps page by page.

Rules: a genuine zero satisfies a numeric requirement, None does not; reviewer text, extracted values and
AI drafts all count as populated (drafts are counted separately as pending review); an empty leasing table
is "no activity" only when the reviewed note says so, otherwise it is missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..models import Issue, ReportData


@dataclass
class Gap:
    path: str
    label: str
    page: int
    group: str
    reason: str

    def to_json(self) -> dict:
        return {"path": self.path, "label": self.label, "page": self.page, "group": self.group, "reason": self.reason}


@dataclass
class Group:
    key: str
    label: str
    page: int
    gaps: list[Gap] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.gaps

    def to_json(self) -> dict:
        return {"key": self.key, "label": self.label, "page": self.page, "complete": self.complete, "gap_count": len(self.gaps)}


@dataclass
class Completeness:
    complete: bool
    gap_count: int
    gaps: list[Gap]
    groups: list[Group]
    ai_drafts_pending: int

    def to_json(self) -> dict:
        return {"complete": self.complete, "gap_count": self.gap_count, "ai_drafts_pending": self.ai_drafts_pending,
                "gaps": [g.to_json() for g in self.gaps], "groups": [g.to_json() for g in self.groups]}


@dataclass(frozen=True)
class Requirement:
    key: str
    label: str
    page: int
    fields: tuple[str, ...] = ()                                   # field paths that must hold a value
    check: Callable[[ReportData, list[Issue]], list[Gap]] | None = None  # extra structural checks


def _present(v: Any) -> bool:
    return v is not None and v != ""


def _val(data: ReportData, path: str) -> Any:
    f = data.field(path)
    return f.effective if f is not None else None


def _gap(data: ReportData, path: str, page: int, group: str, reason: str) -> Gap:
    f = data.field(path)
    return Gap(path, f.label if f is not None else path, page, group, reason)


def _table_rows(data: ReportData, tpath: str) -> list[tuple[str, dict]]:
    t = data.table(tpath)
    return list(t.rows.items()) if t else []


# ---------- structural checks ----------
def _in_place_rent(data: ReportData, issues: list[Issue]) -> list[Gap]:
    rows = _table_rows(data, "in_place_rent.tables.by_floor_plan")
    if not rows:
        return [Gap("in_place_rent.tables.by_floor_plan", "In-place rent by floor plan", 2, "in_place_rent", "no floor-plan rows; a Market Rent Schedule or manual rows are needed")]
    out = []
    for col, label in (("current_rent", "current in-place rent"), ("prior_rent", "prior-quarter in-place rent")):
        if not _present(_val(data, f"in_place_rent.tables.by_floor_plan.totals.{col}")):
            out.append(Gap(f"in_place_rent.tables.by_floor_plan.totals.{col}", f"Weighted {label}", 2, "in_place_rent", f"no {label} on any floor plan"))
    return out


def _underwriting(data: ReportData, issues: list[Issue]) -> list[Gap]:
    rows = _table_rows(data, "underwriting.tables.budget")
    ok = [k for k, r in rows if all(_present(r[c].effective) for c in ("category", "original_budget", "spent_to_date") if c in r)]
    if ok:
        return []
    return [Gap("underwriting.tables.budget", "Original underwriting budget", 3, "underwriting",
                "at least one row with a category, original budget and spent to date (enter the underwriting; it is not in any source export)")]


def _rent_trend(data: ReportData, issues: list[Issue]) -> list[Gap]:
    if _table_rows(data, "rent_trend.tables.monthly"):
        return []
    return [Gap("rent_trend.tables.monthly", "Submarket rent trend", 3, "rent_trend", "no monthly rent trend rows; supply the rent chart workbook, LTO and listings, or enter rows")]


def _payment(data: ReportData, issues: list[Issue]) -> list[Gap]:
    if _present(_val(data, "financing.fields.interest_monthly")) or _present(_val(data, "financing.fields.pi_payment")):
        return []
    return [_gap(data, "financing.fields.pi_payment", 4, "financing", "enter the monthly IO or P&I payment")]


FIN_ROWS = ("total_revenue", "total_opex", "noi", "net_cash_flow")
FIN_COLS = ("ptd_actual", "ptd_budget", "ytd_actual")


def _financials(data: ReportData, issues: list[Issue]) -> list[Gap]:
    out = []
    for rk in FIN_ROWS:
        for ck in FIN_COLS:
            path = f"financials.tables.lines.rows.{rk}.{ck}"
            if not _present(_val(data, path)):
                out.append(_gap(data, path, 6, "financials", "core financial line without a value"))
    for i in issues:
        if i.severity == "warning" and (i.path or "").startswith("financials.tables") and "does not equal" in i.message:
            out.append(Gap(i.path or "financials.tables.lines", "Financial reconciliation", 6, "financials", f"reconciliation warning: {i.message}"))
    return out


def _capex(data: ReportData, issues: list[Issue]) -> list[Gap]:
    rows = _table_rows(data, "capex.tables.lines")
    if any(_present(r[c].effective) for _, r in rows for c in ("ptd_actual", "ptd_budget") if c in r):
        return []
    return [Gap("capex.tables.lines", "Capital projects", 7, "capex", "no capital line with a quarter actual or budget")]


def _comps(data: ReportData, issues: list[Issue]) -> list[Gap]:
    t = data.table("submarket.tables.comps")
    rows = list(t.rows.items()) if t else []
    out = []
    if not any(t.row_meta.get(k, {}).get("subject") for k, _ in rows):
        out.append(Gap("submarket.tables.comps", "Comp set", 8, "comps", "no subject row; the property must appear in the comp table"))
    usable = [k for k, r in rows if not t.row_meta.get(k, {}).get("subject") and any(_present(r[c].effective) for c in ("leased_pct", "asking_rent", "effective_rent") if c in r)]
    if len(usable) < 2:
        out.append(Gap("submarket.tables.comps", "Comp set", 8, "comps", f"{len(usable)} comparable(s) with leased %, asking or effective rent; at least 2 are needed"))
    if not _present(_val(data, "submarket.tables.comps.totals.asking_rent")):
        out.append(Gap("submarket.tables.comps.totals.asking_rent", "Comp set asking rent average", 8, "comps", "no comparable has an asking rent"))
    return out


LEASING_TABLES = (("new_leases", "New leases", "new_lease_narrative"), ("renewals", "Renewals", "renewal_narrative"))


def _leasing(data: ReportData, issues: list[Issue]) -> list[Gap]:
    note = _present(_val(data, "occupancy.fields.no_activity_note"))
    out = []
    for key, label, _narr in LEASING_TABLES:
        if _table_rows(data, f"occupancy.tables.{key}") or note:
            continue
        out.append(Gap(f"occupancy.tables.{key}", f"{label} by floor plan", 9, "leasing", "no rows; supply the Lease Trade-Out report or state in the no-activity note that none occurred"))
    if out:
        out.append(_gap(data, "occupancy.fields.no_activity_note", 9, "leasing", "required when a leasing table is empty: state that no activity occurred"))
    return out


def _items(prefix: str, label: str, page: int, group: str) -> Callable[[ReportData, list[Issue]], list[Gap]]:
    def check(data: ReportData, issues: list[Issue]) -> list[Gap]:
        for i in (1, 2, 3):
            if _present(_val(data, f"status.fields.{prefix}{i}_title")) and _present(_val(data, f"status.fields.{prefix}{i}_body")):
                return []
        return [_gap(data, f"status.fields.{prefix}1_title", page, group, f"at least one {label} with a title and body")]
    return check


def _narratives(data: ReportData, issues: list[Issue]) -> list[Gap]:
    out = []
    for path, page in NARRATIVE_FIELDS:
        if not _present(_val(data, path)):
            out.append(_gap(data, path, page, "narratives", "narrative text (reviewer written or AI drafted and reviewed)"))
    for key, _label, narr in LEASING_TABLES:
        if _table_rows(data, f"occupancy.tables.{key}") and not _present(_val(data, f"occupancy.fields.{narr}")):
            out.append(_gap(data, f"occupancy.fields.{narr}", 9, "narratives", "commentary for a leasing table that has rows"))
    if _table_rows(data, "rent_trend.tables.monthly") and not _present(_val(data, "rent_trend.fields.caption")):
        out.append(_gap(data, "rent_trend.fields.caption", 3, "narratives", "caption for the rent trend chart"))
    return out


NARRATIVE_FIELDS: tuple[tuple[str, int], ...] = (
    ("commentary.fields.takeaway", 5), ("commentary.fields.revenue_body", 5), ("commentary.fields.opex_body", 5), ("commentary.fields.noi_body", 5),
    ("commentary.fields.revenue_outlook", 5), ("commentary.fields.opex_outlook", 5), ("commentary.fields.noi_outlook", 5),
    ("in_place_rent.fields.narrative", 2), ("submarket.fields.occupancy_narrative", 8), ("submarket.fields.rent_narrative", 8),
    ("submarket.fields.concession_narrative", 8), ("occupancy.fields.occupancy_narrative", 9), ("capex.fields.narrative", 7),
)

REQUIREMENTS: tuple[Requirement, ...] = (
    Requirement("property", "Property identity and facts", 2, fields=(
        "property.fields.name", "property.fields.units", "property.fields.year_built", "property.fields.acquired_date", "property.fields.city_state",
        "property.fields.submarket", "property.fields.msa", "property.fields.prepared_by", "property.fields.building_class",
        "property.fields.site_acres", "property.fields.hold_period_years", "property.fields.description")),
    Requirement("in_place_rent", "Current and prior in-place rent", 2, check=_in_place_rent),
    Requirement("capital", "Capital summary", 3, fields=(
        "capital.fields.purchase_price", "capital.fields.equity_invested", "capital.fields.quarter_contributions", "capital.fields.total_called",
        "capital.fields.distributions_itd", "capital.fields.quarter_distributions")),
    Requirement("business_plan", "Business plan summary", 3, fields=("capital.fields.business_plan_summary",)),
    Requirement("underwriting", "Original underwriting budget", 3, fields=("underwriting.fields.spent_period_note",), check=_underwriting),
    Requirement("rent_trend", "Submarket rent trend", 3, check=_rent_trend),
    Requirement("financing", "Financing terms", 4, fields=(
        "financing.fields.loan_amount", "financing.fields.lender", "financing.fields.rate", "financing.fields.rate_type", "financing.fields.effective_date",
        "financing.fields.maturity_date", "financing.fields.term_months", "financing.fields.io_months", "financing.fields.amort_years",
        "financing.fields.recourse", "financing.fields.prepayment", "financing.fields.narrative"), check=_payment),
    Requirement("financials", "Financial performance", 6, check=_financials),
    Requirement("capex", "Capital projects", 7, check=_capex),
    Requirement("submarket", "Submarket KPIs", 8, fields=(
        "submarket.fields.vacancy", "submarket.fields.rent_growth_yoy", "submarket.fields.avg_asking_rent", "submarket.fields.under_construction",
        "submarket.fields.submarket_name", "submarket.fields.market_name")),
    Requirement("comps", "Comparable set", 8, check=_comps),
    Requirement("occupancy", "Occupancy", 9, fields=(
        "occupancy.fields.current_date", "occupancy.fields.prior_date", "occupancy.fields.current_pct", "occupancy.fields.prior_pct",
        "occupancy.fields.current_occupied", "occupancy.fields.prior_occupied", "occupancy.fields.total_units")),
    Requirement("leasing", "Leasing activity", 9, check=_leasing),
    Requirement("status", "Status update", 10, check=_items("status", "status item", 10, "status")),
    Requirement("goals", "Next-quarter goals", 10, check=_items("goal", "goal", 10, "goals")),
    Requirement("narratives", "Commentary and narratives", 5, check=_narratives),
)

# Every field path that any requirement can name, so validation can grade a missing value as required or optional.
REQUIRED_PATHS: frozenset[str] = frozenset(
    [p for r in REQUIREMENTS for p in r.fields] + [p for p, _ in NARRATIVE_FIELDS]
    + ["financing.fields.pi_payment", "financing.fields.interest_monthly", "occupancy.fields.no_activity_note", "rent_trend.fields.caption",
       "occupancy.fields.new_lease_narrative", "occupancy.fields.renewal_narrative"]
    + [f"financials.tables.lines.rows.{r}.{c}" for r in FIN_ROWS for c in FIN_COLS]
)


CONDITIONAL: dict[str, Callable[[ReportData], bool]] = {
    "occupancy.fields.no_activity_note": lambda d: any(not _table_rows(d, f"occupancy.tables.{k}") for k, _l, _n in LEASING_TABLES),
    "occupancy.fields.new_lease_narrative": lambda d: bool(_table_rows(d, "occupancy.tables.new_leases")),
    "occupancy.fields.renewal_narrative": lambda d: bool(_table_rows(d, "occupancy.tables.renewals")),
    "rent_trend.fields.caption": lambda d: bool(_table_rows(d, "rent_trend.tables.monthly")),
    "financing.fields.pi_payment": lambda d: not _present(_val(d, "financing.fields.interest_monthly")),   # one monthly payment is enough
    "financing.fields.interest_monthly": lambda d: not _present(_val(d, "financing.fields.pi_payment")),
}


def is_required(path: str, data: ReportData | None = None) -> bool:
    """Whether a missing value at `path` blocks a complete report. Some paths depend on the data: the no-activity
    note only when a leasing table is empty, table commentary only when the table has rows."""
    if path in CONDITIONAL and data is not None:
        return CONDITIONAL[path](data)
    return path in REQUIRED_PATHS


def page_of(path: str) -> int | None:
    for r in REQUIREMENTS:
        if path in r.fields:
            return r.page
    return dict(NARRATIVE_FIELDS).get(path) or {"financing.fields.pi_payment": 4, "financing.fields.interest_monthly": 4, "occupancy.fields.no_activity_note": 9,
                                                 "rent_trend.fields.caption": 3, "occupancy.fields.new_lease_narrative": 9, "occupancy.fields.renewal_narrative": 9}.get(path)


def evaluate(data: ReportData, issues: list[Issue] | None = None) -> Completeness:
    issues = issues or []
    groups: list[Group] = []
    for r in REQUIREMENTS:
        gaps = [_gap(data, p, r.page, r.key, "needed for a complete report") for p in r.fields if not _present(_val(data, p))]
        if r.check:
            gaps += r.check(data, issues)
        groups.append(Group(r.key, r.label, r.page, gaps))
    all_gaps = [g for grp in groups for g in grp.gaps]
    pending = sum(1 for _p, f in data.iter_fields() if f.status == "ai_draft" and f.override is None)
    return Completeness(complete=not all_gaps, gap_count=len(all_gaps), gaps=all_gaps, groups=groups, ai_drafts_pending=pending)


# ---------- test support: plausible reviewer entries for every gap ----------
_SAMPLE = {"money": 100000, "number": 12.5, "integer": 12, "percent": 0.05, "date": "2024-01-15", "text": "Reviewed entry", "longtext": "Reviewed narrative text."}
_SAMPLE_BY_KEY = {"maturity_date": "2029-01-15", "io_end_date": "2027-01-15", "effective_date": "2024-01-15", "yield_maintenance_through": "2028-07-15",
                  "prior_date": "2026-03-31", "current_date": "2026-06-30", "acquired_date": "2024-01-15", "hold_period_years": 5, "io_months": 36,
                  "term_months": 60, "amort_years": 30, "year_built": 1995, "rate_type": "Fixed", "recourse": "Non-recourse"}


def fill_gaps_for_test(data: ReportData) -> dict:
    """Overrides that satisfy every gap of `data` with typed, plausible values, the way a reviewer would.
    Used by tests and by the validation harness to prove the specification is satisfiable."""
    overrides: dict = {"fields": {}, "rows": {}}
    for _ in range(3):  # filling one gap can reveal a conditional one (a narrative for a table that now has rows)
        result = evaluate(data)
        if result.complete:
            break
        for g in result.gaps:
            if g.path == "underwriting.tables.budget":
                overrides["rows"].setdefault(g.path, {})["test-roof"] = {"category": "Roof replacement", "section": "recurring", "original_budget": 250000, "spent_to_date": 60000}
            elif g.path == "submarket.tables.comps":
                overrides["rows"].setdefault(g.path, {})["test-comp"] = {"name": "Test Comparable", "units": 100, "vintage": 2001, "leased_pct": 0.94, "asking_rent": 1500, "effective_rent": 1450}
            elif g.path.startswith("occupancy.tables."):
                overrides["fields"]["occupancy.fields.no_activity_note"] = "No leases commenced or renewed in the quarter."
            elif g.group in ("status", "goals"):
                stem = g.path.rsplit("_", 1)[0]
                overrides["fields"][f"{stem}_title"] = "Reviewed item"
                overrides["fields"][f"{stem}_subtitle"] = "Reviewed headline"
                overrides["fields"][f"{stem}_body"] = "Reviewed body text."
            elif ".totals." in g.path:  # a total is derived from its rows: enter the missing row values instead
                tpath, col = g.path.split(".totals.")
                t = data.table(tpath)
                for rk, row in (t.rows.items() if t else []):
                    if col in row and row[col].status != "derived" and not _present(row[col].effective):
                        overrides["fields"][f"{tpath}.rows.{rk}.{col}"] = _SAMPLE.get(row[col].kind, 1)
            elif ".tables." in g.path:
                continue  # table content that manual rows cannot sensibly fabricate in a test
            else:
                f = data.field(g.path)
                key = g.path.rsplit(".", 1)[-1]
                if f is not None and f.status == "derived":
                    continue
                overrides["fields"][g.path] = _SAMPLE_BY_KEY.get(key, _SAMPLE.get(f.kind if f else "text", "Reviewed entry"))
        from .builder import apply_overrides
        from .calc import recompute

        apply_overrides(data, overrides)
        recompute(data)
    return overrides
