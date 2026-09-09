"""Where every value in the report came from, or why it is not there.

One answer per field, derived from the field itself plus `data.meta['sources']`, so it works on a
stored report snapshot with no access to the database or the uploaded files. The review screen and
the report's provenance appendix both render exactly what this module returns.

Origins:
  extracted  read from a source file whose text was machine-readable
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

ORIGIN_LABELS = {
    "extracted": "Extracted",
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
        return FieldProvenance("computed", ORIGIN_LABELS["computed"],
                               field.note or "Calculated by the system from other values in this report")
    src = field.source
    if src is None or not src.filename:
        return FieldProvenance("extracted", ORIGIN_LABELS["extracted"],
                               field.note or "Consolidated from the uploaded files; no single line recorded")
    ocr = src.method in ("ocr", "mixed")
    origin = "ocr" if ocr else "extracted"
    where = " · ".join(x for x in (src.filename, _clip(src.locator, 90)) if x)
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
