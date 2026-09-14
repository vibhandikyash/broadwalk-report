"""Where every value in the report came from, or why it is not there.

One answer per field, derived from the field itself plus `data.meta['sources']`, so it works on a
stored report snapshot with no access to the database or the uploaded files. The review screen and
the report's provenance appendix both render exactly what this module returns.

Origins:
  extracted  read from a source file whose text was machine-readable
  inferred   interpreted from a differently labelled source value
  ocr        read from a source file page whose text had to be recovered by vision OCR
  computed   calculated by the system from other values (variances, weighted averages, totals)
  manual     typed by the reviewer on the review screen
  ai_draft   drafted by the language model from the structured values, pending review
  missing    no value; `reason` says why
"""
from __future__ import annotations

from dataclasses import dataclass

from ..classify.classifier import DOC_TYPE_LABELS, DocType
from ..models import Field, ReportData
from ..report.formatters import FILTERS
from .calc import KPI_SOURCES

ORIGIN_LABELS = {
    "extracted": "Extracted",
    "inferred": "Inferred",
    "ocr": "Extracted by OCR",
    "computed": "Calculated",
    "manual": "Entered by reviewer",
    "ai_draft": "AI draft",
    "missing": "Not found",
}

# Which uploaded reports can supply a value, so a missing one can say whether the report that carries
# it was never uploaded or was read and simply did not contain the line. Looked up by exact path
# first, then by table prefix, then by section prefix.
D = DocType
EXPECTED_BY_PATH: dict[str, tuple[DocType, ...]] = {
    "property.fields.name": (D.YARDI_RENT_ROLL, D.YARDI_MARKET_RENT_SCHEDULE, D.YARDI_LEASE_TRADE_OUT, D.MANAGEMENT_MEMO),
    "property.fields.units": (D.YARDI_RENT_ROLL, D.YARDI_MARKET_RENT_SCHEDULE, D.MANAGEMENT_MEMO),
    "property.fields.year_built": (D.COSTAR_SUBMARKET_PDF, D.HELLODATA_COMPS, D.MANAGEMENT_MEMO),
    "property.fields.acquired_date": (D.COSTAR_SUBMARKET_PDF, D.MANAGEMENT_MEMO),
    "property.fields.address": (D.HELLODATA_COMPS, D.HELLODATA_LISTINGS, D.MANAGEMENT_MEMO),
    "property.fields.zip": (D.HELLODATA_COMPS, D.HELLODATA_LISTINGS, D.MANAGEMENT_MEMO),
    "property.fields.city_state": (D.HELLODATA_COMPS, D.HELLODATA_LISTINGS, D.COSTAR_SUBMARKET_PDF, D.MANAGEMENT_MEMO),
    "property.fields.submarket": (D.COSTAR_SUBMARKET_PDF,),
    "property.fields.msa": (D.COSTAR_SUBMARKET_PDF,),
    "property.fields.prepared_by": (D.COSTAR_SUBMARKET_PDF,),
    "property.fields.avg_unit_sf": (D.YARDI_MARKET_RENT_SCHEDULE, D.HELLODATA_COMPS),
    "property.fields.building_class": (D.MANAGEMENT_MEMO,),
    "property.fields.site_acres": (D.MANAGEMENT_MEMO,),
    "property.fields.hold_period_years": (D.MANAGEMENT_MEMO,),
    "property.fields.description": (D.MANAGEMENT_MEMO,),
    "capital.fields.purchase_price": (D.YARDI_BALANCE_SHEET, D.MANAGEMENT_MEMO, D.COSTAR_SUBMARKET_PDF),
    "capital.fields.equity_invested": (D.YARDI_BALANCE_SHEET, D.MANAGEMENT_MEMO),
    "capital.fields.quarter_contributions": (D.SLATE_CAPITAL_CALLS,),
    "capital.fields.total_called": (D.SLATE_CAPITAL_CALLS,),
    "capital.fields.distributions_itd": (D.SLATE_DISTRIBUTIONS,),
    "capital.fields.quarter_distributions": (D.SLATE_DISTRIBUTIONS,),
    "capital.fields.business_plan_summary": (D.MANAGEMENT_MEMO,),
    "financing.fields.loan_amount": (D.LOAN_SUMMARY, D.YARDI_BALANCE_SHEET),
    "financing.fields.reserve_balance": (D.YARDI_BALANCE_SHEET,),
    "financing.fields.borrower": (D.SLATE_CAPITAL_CALLS, D.SLATE_DISTRIBUTIONS),
    "financing.fields.interest_monthly": (D.LOAN_SUMMARY, D.YARDI_BALANCE_SHEET, D.YARDI_BUDGET_COMPARISON),
}
EXPECTED_BY_PREFIX: tuple[tuple[str, tuple[DocType, ...]], ...] = (
    ("in_place_rent.tables.by_floor_plan.", (D.YARDI_MARKET_RENT_SCHEDULE,)),
    ("underwriting.tables.budget.", (D.UNDERWRITING_PLAN,)),
    ("rent_trend.tables.monthly.", (D.RENT_CHART, D.YARDI_LEASE_TRADE_OUT, D.HELLODATA_LISTINGS)),
    ("rent_trend.fields.", (D.RENT_CHART, D.YARDI_LEASE_TRADE_OUT, D.HELLODATA_LISTINGS)),
    ("financials.tables.lines.", (D.YARDI_BUDGET_COMPARISON,)),
    ("capex.tables.lines.", (D.CAPITAL_PROJECTS, D.YARDI_BUDGET_COMPARISON)),
    ("capex.fields.", (D.CAPITAL_PROJECTS, D.YARDI_BUDGET_COMPARISON)),
    ("submarket.tables.comps.", (D.HELLODATA_COMPS, D.HELLODATA_LISTINGS)),
    ("submarket.fields.", (D.COSTAR_SUBMARKET_EXCEL, D.COSTAR_SUBMARKET_PDF)),
    ("occupancy.tables.", (D.YARDI_LEASE_TRADE_OUT,)),
    ("occupancy.fields.", (D.YARDI_RENT_ROLL, D.YARDI_LEASE_TRADE_OUT)),
    ("financing.fields.", (D.LOAN_SUMMARY,)),
    ("status.fields.", (D.MANAGEMENT_MEMO,)),
)
# Fields no export carries: the reviewer writes them, optionally starting from an AI draft. The
# override prefix names sections where an export does carry the prose after all (the memo's status
# items and goals), so the section mapping above wins there.
AUTHORED_SUFFIXES = ("narrative", "caption", "takeaway", "_body", "_outlook", "_note")
AUTHORED_OVERRIDE_PREFIXES = ("status.fields.",)
AUTHORED_REASON = "No source file carries this text. Write it on the review screen, or draft it with AI and review it."
GENERIC_NOTES = {"Not found in any source file; enter manually"}
NO_EXPECTATION_REASON = "Not present in any uploaded source file; enter it on the review screen."


def _sentence(text: str) -> str:
    """Builder notes are written as fragments; make one safe to put in front of another sentence."""
    flat = " ".join(text.split())
    return flat if flat.endswith((".", "!", "?")) else flat + "."


def _clip(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _doc_label(doc_type: str | None) -> str | None:
    if not doc_type:
        return None
    try:
        return DOC_TYPE_LABELS[DocType(doc_type)]
    except ValueError:
        return doc_type


def _join(labels: list[str]) -> str:
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " or " + labels[-1]


def expected_sources(path: str) -> tuple[DocType, ...]:
    if path in EXPECTED_BY_PATH:
        return EXPECTED_BY_PATH[path]
    for prefix, docs in EXPECTED_BY_PREFIX:
        if path.startswith(prefix):
            return docs
    return ()


def _authored(path: str, field: Field) -> bool:
    """True when the reviewer is the author of record: no export carries this prose."""
    if path in EXPECTED_BY_PATH or path.startswith(AUTHORED_OVERRIDE_PREFIXES):
        return False
    return field.kind == "longtext" or path.rsplit(".", 1)[-1].endswith(AUTHORED_SUFFIXES)


def _missing_reason(path: str, field: Field, data: ReportData) -> str:
    note = _sentence(field.note) if field.note and field.note not in GENERIC_NOTES else None
    if _authored(path, field):
        return f"{note} {AUTHORED_REASON}" if note else AUTHORED_REASON
    expected = expected_sources(path)
    if not expected:
        return note or NO_EXPECTATION_REASON
    uploaded = {s.get("doc_type") for s in data.meta.get("sources") or []}
    present = [d for d in expected if d.value in uploaded]
    if not present:
        availability = (f"{_join([DOC_TYPE_LABELS[d] for d in expected])} would carry this value, "
                        "and no such file was uploaded.")
    else:
        names = sorted({s.get("filename") for s in data.meta.get("sources") or []
                        if s.get("doc_type") in {d.value for d in present} and s.get("filename")})
        where = f" ({', '.join(names)})" if names else ""
        availability = (f"{_join([DOC_TYPE_LABELS[d] for d in present])}{where} was read, "
                        "but it contains no line for this value.")
    return f"{note} {availability}" if note else availability


# ---------- what a calculated value was calculated from ----------
# Derived cells in a table take their inputs from siblings in the same row: (operator, input columns).
# A variance follows the report's convention, favourable-positive, so the operator depends on whether
# the row is an expense; recompute() reads the same row_meta flag.
CELL_INPUTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ptd_var": ("variance", ("ptd_actual", "ptd_budget")),
    "ytd_var": ("variance", ("ytd_actual", "ytd_budget")),
    "ptd_var_pct": ("variance_pct", ("ptd_var", "ptd_budget")),
    "ytd_var_pct": ("variance_pct", ("ytd_var", "ytd_budget")),
    "variance": ("minus", ("current_rent", "prior_rent")),
    "variance_pct": ("over", ("variance", "prior_rent")),
    "pct_spent": ("over", ("spent_to_date", "original_budget")),
    "concession": ("minus", ("asking_rent", "effective_rent")),
    "concession_pct": ("over", ("concession", "asking_rent")),
    "lto": ("minus", ("avg_current", "avg_prior")),
    "lto_pct": ("over", ("lto", "avg_prior")),
}
# Scalar derived fields, as (operator, input paths).
FIELD_INPUTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "property.fields.density": ("over", ("property.fields.units", "property.fields.site_acres")),
    "capital.fields.price_per_unit": ("over", ("capital.fields.purchase_price", "property.fields.units")),
    "financing.fields.implied_rate": ("annualised", ("financing.fields.interest_monthly", "financing.fields.loan_amount")),
    "financing.fields.replacement_reserve_annual": ("times12", ("financing.fields.replacement_reserve_monthly",)),
    "occupancy.fields.change_bps": ("bps", ("occupancy.fields.current_pct", "occupancy.fields.prior_pct")),
}
# How a table's totals row is arrived at, keyed by table path then column.
TOTAL_INPUTS: dict[str, dict[str, str]] = {
    "in_place_rent.tables.by_floor_plan": {
        "units": "sum of the floor-plan rows", "current_rent": "floor-plan rents weighted by units",
        "prior_rent": "prior floor-plan rents weighted by units"},
    "underwriting.tables.budget": {"original_budget": "sum of the rows", "spent_to_date": "sum of the rows"},
    "capex.tables.lines": {c: "sum of the capital lines" for c in
                           ("ptd_actual", "ptd_budget", "ptd_var", "ytd_actual", "ytd_budget", "ytd_var", "annual_budget")},
    "submarket.tables.comps": {"units": "average of the comparables", "vintage": "average of the comparables"},
    "occupancy.tables.new_leases": {"count": "sum of the floor-plan rows", "avg_prior": "weighted by lease count",
                                    "avg_current": "weighted by lease count"},
    "occupancy.tables.renewals": {"count": "sum of the floor-plan rows", "avg_prior": "weighted by lease count",
                                  "avg_current": "weighted by lease count"},
}
# Derived values that are worded rather than calculated: labels taken from the reporting period, and
# captions phrased from a figure elsewhere on the page.
DERIVED_PROSE: dict[str, str] = {
    "property.fields.quarter_label": "the reporting period's quarter",
    "property.fields.period_label": "the reporting period, from its first and last month",
    "property.fields.period_end": "the last day of the reporting period",
    "property.fields.prior_quarter_label": "the quarter before the reporting period",
    "in_place_rent.fields.prior_quarter_label": "the quarter before the reporting period",
    "financials.fields.period_label": "the reporting period, from its first and last month",
    "financials.fields.ytd_label": "January to the last month of the reporting period",
    "status.fields.next_quarter_label": "the quarter after the reporting period",
    "submarket.fields.data_quarter": "the reporting period's quarter",
    "capital.fields.contributions_note": "worded from the quarter's equity contributions",
    "capital.fields.distributions_note": "worded from the distributions to date",
    "submarket.fields.pipeline_note": "worded from the units under construction and their share of inventory",
    "submarket.fields.footnote": "states how many comparables the averages cover and how each was averaged",
    "submarket.fields.source_note": "a fixed attribution line for the submarket data",
    "occupancy.fields.new_lease_count": "sum of the new-lease counts by floor plan",
    "occupancy.fields.renewal_count": "sum of the renewal counts by floor plan",
    "occupancy.fields.new_lease_lto_pct": "the new-lease trade-out total, over the average prior rent",
    "occupancy.fields.renewal_lto_pct": "the renewal trade-out total, over the average prior rent",
}
# Comp-set averages state their own method in the page-8 footnote, which recompute writes.
COMP_AVERAGE = ("submarket.tables.comps.totals.leased_pct", "submarket.tables.comps.totals.asking_rent",
                "submarket.tables.comps.totals.effective_rent")

OPERATORS = {
    "minus": "{n0} {v0}{s0} − {n1} {v1}{s1}",
    "over": "{n0} {v0}{s0} ÷ {n1} {v1}{s1}",
    "variance": "{n0} {v0}{s0} − {n1} {v1}{s1}",
    "variance_expense": "{n1} {v1}{s1} − {n0} {v0}{s0}, the favourable-positive convention for an expense",
    "variance_pct": "{n0} {v0}{s0} ÷ {n1} {v1}{s1}",
    "annualised": "{n0} {v0}{s0} × 12 ÷ {n1} {v1}{s1}",
    "times12": "{n0} {v0}{s0} × 12",
    "bps": "({n0} {v0}{s0} − {n1} {v1}{s1}) × 10,000",
}


def _shown(field: Field | None) -> str:
    """An input's value as the report prints it, so the arithmetic can be followed by eye."""
    if field is None or field.effective in (None, ""):
        return "—"
    kind = field.kind
    if kind == "money":
        return FILTERS["money"](field.effective)
    if kind == "percent":
        return FILTERS["pct"](field.effective, 2)
    if kind == "integer":
        return FILTERS["integer"](field.effective)
    if kind == "number":
        return FILTERS["num"](field.effective, 2)
    return FILTERS["text"](field.effective)


def where_from(field: Field | None) -> str | None:
    """Where one input came from, short enough to sit inside a formula."""
    if field is None or field.effective in (None, ""):
        return None
    if field.override is not None:
        return "entered by reviewer"
    if field.status == "derived":
        return "calculated"
    if field.status == "ai_draft":
        return "AI-written"
    src = field.source
    if src is None or not src.filename:
        return None
    where = " · ".join(x for x in (src.filename, _clip(src.locator, 60)) if x)
    return f"{where}, recovered by OCR" if src.method in ("ocr", "mixed") else where


def _formula(op: str, paths: tuple[str, ...], data: ReportData) -> str | None:
    fields = [data.field(p) for p in paths]
    if any(f is None for f in fields):
        return None
    slots: dict[str, str] = {}
    for i, f in enumerate(fields):
        origin = where_from(f)
        slots[f"n{i}"], slots[f"v{i}"] = (f.label if f else ""), _shown(f)
        slots[f"s{i}"] = f" [{origin}]" if origin else ""
    return OPERATORS[op].format(**slots)


def _location(path: str, data: ReportData) -> str:
    """Where a value sits, in the words the report uses: 'Financial Performance: NOI, Var $'."""
    parts = path.split(".")
    section = data.sections.get(parts[0])
    where = section.title if section else parts[0]
    field = data.field(path)
    column = field.label if field else parts[-1]
    if len(parts) >= 6 and parts[3] == "rows":
        table = data.table(f"{parts[0]}.tables.{parts[2]}")
        row = table.row_meta.get(parts[4], {}).get("label", parts[4]) if table else parts[4]
        return f"{where}: {row}, {column}"
    if len(parts) >= 5 and parts[3] == "totals":
        return f"{where}: total {column}"
    return f"{where}: {column}"


def calculated_from(path: str, field: Field, data: ReportData) -> str | None:
    """The inputs behind a calculated value, named and valued. None when the source is not modelled."""
    parts = path.split(".")
    if path in DERIVED_PROSE:
        return DERIVED_PROSE[path]
    if path in COMP_AVERAGE:
        return _sentence(str(data.value("submarket.fields.footnote") or "average of the comparables that carry a value"))
    if path in FIELD_INPUTS:
        op, inputs = FIELD_INPUTS[path]
        return _formula(op, inputs, data)
    if parts[0] == "commentary" and parts[1] == "fields" and parts[2] in KPI_SOURCES:
        src = KPI_SOURCES[parts[2]]
        return f"the same figure as {_location(src, data)} ({_shown(data.field(src))})"
    if len(parts) >= 6 and parts[1] == "tables" and parts[3] == "rows":
        column = parts[5]
        entry = CELL_INPUTS.get(column)
        if not entry:
            return None
        op, columns = entry
        table = data.table(f"{parts[0]}.tables.{parts[2]}")
        if table is None:
            return None
        if op == "variance" and table.row_meta.get(parts[4], {}).get("expense"):
            op = "variance_expense"
        return _formula(op, tuple(f"{parts[0]}.tables.{parts[2]}.rows.{parts[4]}.{c}" for c in columns), data)
    if len(parts) >= 5 and parts[1] == "tables" and parts[3] == "totals":
        if field.kind == "text":
            return "the caption on the totals row"
        described = TOTAL_INPUTS.get(f"{parts[0]}.tables.{parts[2]}", {}).get(parts[4])
        if described:
            return described
        entry = CELL_INPUTS.get(parts[4])
        if entry:
            op, columns = entry
            return _formula(op, tuple(f"{parts[0]}.tables.{parts[2]}.totals.{c}" for c in columns), data)
    return None


@dataclass
class FieldProvenance:
    """Why a field holds the value it holds, in the words shown to a reviewer and to the client."""

    origin: str
    label: str
    detail: str
    filename: str | None = None
    locator: str | None = None
    doc_type: str | None = None
    doc_label: str | None = None
    quote: str | None = None
    ocr_confidence: float | None = None
    reason: str | None = None

    @property
    def ocr(self) -> bool:
        return self.origin == "ocr"

    def to_json(self) -> dict:
        return {"origin": self.origin, "label": self.label, "detail": self.detail, "filename": self.filename,
                "locator": self.locator, "doc_type": self.doc_type, "doc_label": self.doc_label, "quote": self.quote,
                "ocr_confidence": self.ocr_confidence, "reason": self.reason, "ocr": self.ocr}


def describe(path: str, field: Field, data: ReportData) -> FieldProvenance:
    """The one provenance answer for a field, in precedence order: reviewer, AI, calculated, source, absent."""
    status = "manual" if field.override is not None else field.status
    if field.effective in (None, ""):
        if status == "derived":  # a calculated value is absent only because one of its inputs is
            reason = f"{field.note or 'Calculated from other values in this report'}; at least one input value is missing."
        else:
            reason = _missing_reason(path, field, data)
        return FieldProvenance("missing", ORIGIN_LABELS["missing"], reason, reason=reason)
    if status == "manual":
        return FieldProvenance("manual", ORIGIN_LABELS["manual"], "Typed on the review screen, overriding whatever the files said")
    if status == "ai_draft":
        return FieldProvenance("ai_draft", ORIGIN_LABELS["ai_draft"],
                               "Drafted by AI from this report's own extracted figures; pending reviewer approval")
    if status == "derived":
        formula = calculated_from(path, field, data)
        detail = f"Calculated: {formula}" if formula else (field.note or "Calculated by the system from other values in this report")
        return FieldProvenance("computed", ORIGIN_LABELS["computed"], detail)
    if status == "inferred":
        src = field.source
        where = " · ".join(x for x in (src.filename, _clip(src.locator, 90)) if x) if src else "the uploaded files"
        if src and src.text:
            where = f'{where} — "{_clip(src.text, 120)}"'
        detail = f"{field.note or 'Inferred from a source value with a different label'}: {where}"
        return FieldProvenance("inferred", ORIGIN_LABELS["inferred"], detail,
                               filename=src.filename if src else None, locator=src.locator if src else None,
                               doc_type=src.doc_type if src else None,
                               doc_label=_doc_label(src.doc_type) if src else None,
                               quote=_clip(src.text, 120) if src else None,
                               ocr_confidence=src.ocr_confidence if src else None)
    src = field.source
    if src is None or not src.filename:
        return FieldProvenance("extracted", ORIGIN_LABELS["extracted"],
                               field.note or "Consolidated from the uploaded files; no single line recorded")
    ocr = src.method in ("ocr", "mixed")
    origin = "ocr" if ocr else "extracted"
    where = " · ".join(x for x in (src.filename, _clip(src.locator, 90)) if x)
    if src.text:
        where = f'{where} — "{_clip(src.text, 120)}"'
    if src.method == "ocr":
        how = "text recovered by Gemini vision OCR"
    elif src.method == "mixed":
        how = "this file needed vision OCR on some pages; the exact page could not be pinned down"
    else:
        how = None
    if how and src.ocr_confidence is not None:
        how = f"{how}, {src.ocr_confidence:.0%} confidence"
    return FieldProvenance(origin, ORIGIN_LABELS[origin], f"{where} ({how})" if how else where,
                           filename=src.filename, locator=src.locator, doc_type=src.doc_type,
                           doc_label=_doc_label(src.doc_type), quote=_clip(src.text, 120),
                           ocr_confidence=src.ocr_confidence)


def counts(data: ReportData) -> dict[str, int]:
    """How many of the report's values came from each origin, for the appendix summary."""
    out = {k: 0 for k in ORIGIN_LABELS}
    for path, field in data.iter_fields():
        out[describe(path, field, data).origin] += 1
    return out


def source_files(data: ReportData) -> list[dict]:
    """The files that fed this report, de-duplicated by name, each saying whether it needed OCR."""
    seen: dict[str, dict] = {}
    for entry in data.meta.get("sources") or []:
        name = entry.get("filename")
        if not name:
            continue
        row = seen.setdefault(name, {"filename": name, "doc_labels": [], "method": "native", "ocr_pages": [],
                                     "ocr_confidence": entry.get("ocr_confidence")})
        label = _doc_label(entry.get("doc_type"))
        if label and label not in row["doc_labels"]:
            row["doc_labels"].append(label)
        if entry.get("method") in ("ocr", "mixed"):
            row["method"] = entry["method"]
            row["ocr_pages"] = sorted(set(row["ocr_pages"]) | set(entry.get("ocr_pages") or []))
            row["ocr_confidence"] = entry.get("ocr_confidence")
    return sorted(seen.values(), key=lambda r: r["filename"])
