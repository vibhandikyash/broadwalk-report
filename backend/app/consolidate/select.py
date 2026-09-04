"""Choose which extraction feeds which section when several files could, and record the alternatives."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..classify.classifier import DocType


@dataclass
class Src:
    file_id: str
    filename: str
    doc_type: str
    locator: str
    data: dict
    parts_in_file: int = 1

    def source(self, suffix: str = "", text: str = "") -> dict:
        return {"file_id": self.file_id, "filename": self.filename,
                "locator": f"{self.locator} {suffix}".strip(), "text": text or None}


@dataclass
class Selection:
    budget: Src | None = None
    balance_sheet: Src | None = None
    rent_rolls: list[Src] = field(default_factory=list)
    schedules: list[Src] = field(default_factory=list)
    lto: Src | None = None
    listings: Src | None = None
    comps: list[Src] = field(default_factory=list)
    costar_excel: Src | None = None
    costar_pdf: Src | None = None
    rent_chart: Src | None = None
    capital_calls: Src | None = None
    distributions: Src | None = None
    notes: list[dict] = field(default_factory=list)


def collect(files: list[dict]) -> list[Src]:
    out: list[Src] = []
    for f in files:
        if f.get("ignored") or f.get("status") != "processed":
            continue
        n_parts = len(f.get("parts") or [])
        for ex in f.get("extractions") or []:
            out.append(Src(f["id"], f["original_filename"], ex["doc_type"], ex["locator"], ex["data"], n_parts))
    return out


def _by_type(srcs: list[Src], t: DocType) -> list[Src]:
    return [s for s in srcs if s.doc_type == t.value]


def _period_end(s: Src) -> str:
    return (s.data.get("period") or {}).get("end") or ""


def _pick(sel: Selection, cands: list[Src], key: Callable[[Src], tuple], label: str, path: str) -> Src | None:
    if not cands:
        return None
    ranked = sorted(cands, key=key, reverse=True)
    if len(ranked) > 1:
        others = "; ".join(f"{s.filename} ({s.locator})" for s in ranked[1:])
        sel.notes.append({"severity": "warning", "path": path,
                          "message": f"{label}: using {ranked[0].filename} ({ranked[0].locator}). Also found: {others}. "
                                     "Exclude a file on the Files page to switch."})
    return ranked[0]


def select(srcs: list[Src]) -> Selection:
    sel = Selection()
    sel.budget = _pick(sel, _by_type(srcs, DocType.YARDI_BUDGET_COMPARISON),
                       lambda s: ("ytd_actual" in s.data.get("columns", []), _period_end(s)), "Financials source", "financials")
    sel.balance_sheet = _pick(sel, _by_type(srcs, DocType.YARDI_BALANCE_SHEET), lambda s: (_period_end(s),), "Balance sheet", "capital")
    sel.rent_rolls = sorted(_by_type(srcs, DocType.YARDI_RENT_ROLL), key=lambda s: s.data.get("as_of") or "")
    sel.schedules = sorted(_by_type(srcs, DocType.YARDI_MARKET_RENT_SCHEDULE), key=lambda s: s.data.get("as_of") or "")
    budget_end = _period_end(sel.budget) if sel.budget else ""
    sel.lto = _pick(sel, _by_type(srcs, DocType.YARDI_LEASE_TRADE_OUT),
                    lambda s: (_period_end(s) == budget_end, "renewals" in s.data.get("sections", {}), _period_end(s)),
                    "Lease trade-out source", "occupancy")
    sel.listings = _pick(sel, _by_type(srcs, DocType.HELLODATA_LISTINGS),
                         lambda s: (s.parts_in_file == 1, s.data.get("row_count", 0)), "HelloData listings", "submarket")
    sel.comps = sorted(_by_type(srcs, DocType.HELLODATA_COMPS), key=lambda s: s.data.get("source") != "sheet")
    sel.costar_excel = _pick(sel, _by_type(srcs, DocType.COSTAR_SUBMARKET_EXCEL), lambda s: (len(s.data.get("series", [])),), "CoStar table", "submarket")
    sel.costar_pdf = _pick(sel, _by_type(srcs, DocType.COSTAR_SUBMARKET_PDF), lambda s: (s.data.get("report_date") or "",), "CoStar report", "submarket")
    sel.rent_chart = _pick(sel, _by_type(srcs, DocType.RENT_CHART), lambda s: (len(s.data.get("months", [])),), "Rent chart", "rent_trend")
    sel.capital_calls = _pick(sel, _by_type(srcs, DocType.SLATE_CAPITAL_CALLS), lambda s: (len(s.data.get("calls", [])),), "Capital calls", "capital")
    sel.distributions = _pick(sel, _by_type(srcs, DocType.SLATE_DISTRIBUTIONS), lambda s: (len(s.data.get("distributions", [])),), "Distributions", "capital")
    return sel
