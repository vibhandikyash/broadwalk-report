"""Choose which extraction feeds which section when several files could, and record the alternatives.

Also the place where cross-file identity is checked: sources that name a different property than
the rest of the upload are set aside with an error note instead of being consolidated silently.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from ..classify.classifier import DocType
from ..readers.document import norm


def names_match(a: str | None, b: str | None) -> bool:
    ka, kb = (re.sub(r"[^a-z0-9]", "", re.sub(r"^the\s+", "", norm(x))) for x in (a or "", b or ""))
    return bool(ka) and bool(kb) and (ka == kb or ka in kb or kb in ka)


PAGE_RE = re.compile(r"\bpage\s+(\d+)")


@dataclass
class Src:
    file_id: str
    filename: str
    doc_type: str
    locator: str
    data: dict
    parts_in_file: int = 1
    provenance: dict = field(default_factory=dict)  # from extract.registry.part_provenance

    def source(self, suffix: str = "", text: str = "") -> dict:
        return {"file_id": self.file_id, "filename": self.filename, "doc_type": self.doc_type,
                "locator": f"{self.locator} {suffix}".strip(), "text": text or None, **self.method(suffix)}

    def method(self, suffix: str = "") -> dict:
        """Whether the value behind `suffix` was read natively or recovered by OCR.

        When the suffix names a page, the answer is exact. When it does not and the file needed OCR
        anywhere, the value is reported as 'mixed' rather than claimed to be native.
        """
        ocr_pages = set((self.provenance or {}).get("ocr_pages") or [])
        if not ocr_pages:
            return {"method": "native", "ocr_confidence": None}
        confidence = (self.provenance or {}).get("ocr_confidence")
        page = PAGE_RE.search(suffix)
        if page:
            on_ocr_page = int(page.group(1)) in ocr_pages
            return {"method": "ocr" if on_ocr_page else "native", "ocr_confidence": confidence if on_ocr_page else None}
        return {"method": (self.provenance or {}).get("method") or "mixed", "ocr_confidence": confidence}


@dataclass
class Selection:
    budget: Src | None = None
    balance_sheet: Src | None = None
    balance_sheets: list[Src] = field(default_factory=list)
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
    capital_calls_all: list[Src] = field(default_factory=list)
    distributions_all: list[Src] = field(default_factory=list)
    management_memo: Src | None = None
    loan_summaries: list[Src] = field(default_factory=list)
    capital_projects: Src | None = None
    underwriting_plan: Src | None = None
    property_name: str | None = None
    excluded: list[Src] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)


def collect(files: list[dict]) -> list[Src]:
    out: list[Src] = []
    for f in files:
        if f.get("ignored") or f.get("status") != "processed":
            continue
        n_parts = len([p for p in (f.get("parts") or []) if p.get("doc_type") != DocType.UNKNOWN.value])  # a stray 'Notes' sheet does not count
        for ex in f.get("extractions") or []:
            prov = ex.get("provenance") or {}  # absent on extractions stored before provenance was recorded
            snapshots = ex["data"].get("_snapshots")
            if snapshots:
                out.extend(Src(f["id"], f["original_filename"], ex["doc_type"], ex["locator"], snapshot, n_parts, prov)
                           for snapshot in snapshots)
            else:
                out.append(Src(f["id"], f["original_filename"], ex["doc_type"], ex["locator"], ex["data"], n_parts, prov))
    return out


def _by_type(srcs: list[Src], t: DocType) -> list[Src]:
    return [s for s in srcs if s.doc_type == t.value]


def _period_end(s: Src) -> str:
    return (s.data.get("period") or {}).get("end") or ""


def _slate_key(rows_key: str) -> Callable[[Src], tuple]:
    """Newest export first: its print date, else the latest transaction it lists; row count only breaks ties."""
    return lambda s: (s.data.get("report_date") or s.data.get("latest_transaction") or "", len(s.data.get(rows_key, [])))


def _has_subject(s: Src, name: str | None) -> bool:
    """A listings export that includes the subject property can feed the comp table's subject row."""
    return bool(name) and any(names_match(n, name) for n in (s.data.get("properties") or {}))


def _pick(sel: Selection, cands: list[Src], key: Callable[[Src], tuple], label: str, path: str, why: str = "") -> Src | None:
    if not cands:
        return None
    ranked = sorted(cands, key=key, reverse=True)
    if len(ranked) > 1:
        others = "; ".join(f"{s.filename} ({s.locator})" for s in ranked[1:])
        sel.notes.append({"severity": "warning", "path": path,
                          "message": f"{label}: using {ranked[0].filename} ({ranked[0].locator}){why}. Also found: {others}. "
                                     "Exclude a file on the Files page to switch."})
    return ranked[0]


def _split_by_property(sel: Selection, srcs: list[Src]) -> list[Src]:
    """Keep the sources that agree on the property; set the rest aside with an error note."""
    named = [(s, s.data["property_name"]) for s in srcs if s.data.get("property_name")]
    if not named:
        return srcs
    groups: list[list[str]] = []
    for _, n in named:
        for g in groups:
            if names_match(g[0], n):
                g.append(n)
                break
        else:
            groups.append([n])
    reliable = {s.data["property_name"] for s, _ in named if s.data.get("property_ref")}  # names read from a 'Name (code)' title
    primary = max(groups, key=lambda g: (len(g), any(n in reliable for n in g)))
    sel.property_name = Counter(primary).most_common(1)[0][0]
    keep = []
    for s in srcs:
        n = s.data.get("property_name")
        if not n or names_match(n, sel.property_name):
            keep.append(s)
        elif s.data.get("property_ref"):  # a titled Yardi report about another property: never merge it
            sel.excluded.append(s)
            sel.notes.append({"severity": "error", "path": "property.fields.name",
                              "message": f"{s.filename} ({s.locator}) reports on '{n}', not '{sel.property_name}'; it was set aside. "
                                         "Remove or exclude it on the Files page if it does not belong to this report."})
        else:  # the name came from a heuristic (a text column), so keep the data but ask
            keep.append(s)
            sel.notes.append({"severity": "warning", "path": "property.fields.name",
                              "message": f"{s.filename} ({s.locator}) names '{n}' where '{sel.property_name}' was expected; it was still used. "
                                         "Exclude it on the Files page if it belongs to another property."})
    return keep


def select(srcs: list[Src]) -> Selection:
    sel = Selection()
    srcs = _split_by_property(sel, srcs)
    sel.budget = _pick(sel, _by_type(srcs, DocType.YARDI_BUDGET_COMPARISON),
                       lambda s: ("ytd_actual" in s.data.get("columns", []), _period_end(s)), "Financials source", "financials")
    sel.balance_sheets = _by_type(srcs, DocType.YARDI_BALANCE_SHEET)
    sel.balance_sheet = _pick(sel, sel.balance_sheets, lambda s: (_period_end(s),), "Balance sheet", "capital")
    sel.rent_rolls = sorted(_by_type(srcs, DocType.YARDI_RENT_ROLL), key=lambda s: s.data.get("as_of") or "")
    sel.schedules = sorted(_by_type(srcs, DocType.YARDI_MARKET_RENT_SCHEDULE), key=lambda s: s.data.get("as_of") or "")
    budget_end = _period_end(sel.budget) if sel.budget else ""
    ltos = _by_type(srcs, DocType.YARDI_LEASE_TRADE_OUT)
    sel.lto = _pick(sel, ltos,
                    lambda s: (_period_end(s) == budget_end, "renewals" in s.data.get("sections", {}), _period_end(s)),
                    "Lease trade-out source", "occupancy")
    if len(ltos) > 1:
        chosen = sel.lto
        assert chosen is not None
        merged = {"move_ins": {"rows": []}, "renewals": {"rows": []}, "transfers": {"rows": []}}
        seen: set[str] = set()
        for source in ltos:
            for section, content in source.data.get("sections", {}).items():
                target = section if section in merged else None
                if target is None:
                    continue
                for row in content.get("rows", []):
                    key = row.get("lease_id") or f"{row.get('unit')}|{row.get('start')}|{row.get('resident_name')}|{target}"
                    if key not in seen:
                        seen.add(key)
                        merged[target]["rows"].append(row)
        sel.lto = Src(chosen.file_id, chosen.filename, chosen.doc_type, "combined lease exports",
                      {**chosen.data, "sections": merged}, chosen.parts_in_file, chosen.provenance)
    sel.listings = _pick(sel, _by_type(srcs, DocType.HELLODATA_LISTINGS),
                         lambda s: (_has_subject(s, sel.property_name), s.parts_in_file == 1, s.data.get("row_count", 0)),
                         "HelloData listings", "submarket")
    sel.comps = sorted(_by_type(srcs, DocType.HELLODATA_COMPS), key=lambda s: s.data.get("source") != "sheet")
    sel.costar_excel = _pick(sel, _by_type(srcs, DocType.COSTAR_SUBMARKET_EXCEL), lambda s: (len(s.data.get("series", [])),), "CoStar table", "submarket")
    sel.costar_pdf = _pick(sel, _by_type(srcs, DocType.COSTAR_SUBMARKET_PDF), lambda s: (s.data.get("report_date") or "",), "CoStar report", "submarket")
    sel.rent_chart = _pick(sel, _by_type(srcs, DocType.RENT_CHART), lambda s: (len(s.data.get("months", [])),), "Rent chart", "rent_trend")
    sel.capital_calls_all = _by_type(srcs, DocType.SLATE_CAPITAL_CALLS)
    sel.distributions_all = _by_type(srcs, DocType.SLATE_DISTRIBUTIONS)
    sel.capital_calls = _pick(sel, sel.capital_calls_all, _slate_key("calls"), "Capital calls", "capital", why=", the most recent export")
    sel.distributions = _pick(sel, sel.distributions_all, _slate_key("distributions"), "Distributions", "capital", why=", the most recent export")
    sel.management_memo = _pick(sel, _by_type(srcs, DocType.MANAGEMENT_MEMO), lambda s: (len(s.data.get("text", "")),),
                                "Management memorandum", "property")
    sel.loan_summaries = _by_type(srcs, DocType.LOAN_SUMMARY)
    sel.capital_projects = _pick(sel, _by_type(srcs, DocType.CAPITAL_PROJECTS), lambda s: (_period_end(s),),
                                 "Capital projects", "capex")
    sel.underwriting_plan = _pick(sel, _by_type(srcs, DocType.UNDERWRITING_PLAN), lambda s: (len(s.data.get("rows", [])),),
                                  "Underwriting plan", "underwriting")
    return sel
