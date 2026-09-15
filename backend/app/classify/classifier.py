"""Content-based document classification: one Part per xlsx sheet, one Part per PDF.

Signatures are substrings of the normalised head of the sheet (first 25 rows) or of the PDF text.
`must` substrings all have to appear; each `any_of` hit raises confidence. Filenames are never used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..readers.document import Document, Page, Sheet, norm


class DocType(str, Enum):
    YARDI_BUDGET_COMPARISON = "yardi_budget_comparison"
    ANNUAL_FINANCIAL_STATEMENT = "annual_financial_statement"
    YARDI_BALANCE_SHEET = "yardi_balance_sheet"
    YARDI_RENT_ROLL = "yardi_rent_roll"
    YARDI_MARKET_RENT_SCHEDULE = "yardi_market_rent_schedule"
    YARDI_LEASE_TRADE_OUT = "yardi_lease_trade_out"
    HELLODATA_LISTINGS = "hellodata_listings"
    HELLODATA_COMPS = "hellodata_comps"
    COSTAR_SUBMARKET_EXCEL = "costar_submarket_excel"
    COSTAR_SUBMARKET_PDF = "costar_submarket_pdf"
    RENT_CHART = "rent_chart"
    SLATE_CAPITAL_CALLS = "slate_capital_calls"
    SLATE_DISTRIBUTIONS = "slate_distributions"
    MANAGEMENT_MEMO = "management_memo"
    LOAN_SUMMARY = "loan_summary"
    CAPITAL_PROJECTS = "capital_projects"
    UNDERWRITING_PLAN = "underwriting_plan"
    UNKNOWN = "unknown"


DOC_TYPE_LABELS: dict[DocType, str] = {
    DocType.YARDI_BUDGET_COMPARISON: "Yardi Budget Comparison (P&L and capital)",
    DocType.ANNUAL_FINANCIAL_STATEMENT: "Annual financial statement",
    DocType.YARDI_BALANCE_SHEET: "Yardi Balance Sheet",
    DocType.YARDI_RENT_ROLL: "Yardi Rent Roll summary (occupancy)",
    DocType.YARDI_MARKET_RENT_SCHEDULE: "Yardi Market Rent Schedule (rent by unit type)",
    DocType.YARDI_LEASE_TRADE_OUT: "Yardi Lease Trade-Out (renewals / move-ins)",
    DocType.HELLODATA_LISTINGS: "HelloData unit-level listings",
    DocType.HELLODATA_COMPS: "HelloData comp set summary",
    DocType.COSTAR_SUBMARKET_EXCEL: "CoStar submarket data table",
    DocType.COSTAR_SUBMARKET_PDF: "CoStar submarket report (PDF)",
    DocType.RENT_CHART: "Rent trend chart workbook",
    DocType.SLATE_CAPITAL_CALLS: "Slate capital calls",
    DocType.SLATE_DISTRIBUTIONS: "Slate distributions",
    DocType.MANAGEMENT_MEMO: "Asset management memorandum",
    DocType.LOAN_SUMMARY: "Loan servicing summary",
    DocType.CAPITAL_PROJECTS: "Capital project register",
    DocType.UNDERWRITING_PLAN: "Original underwriting plan",
    DocType.UNKNOWN: "Unrecognized",
}

Signature = tuple[DocType, list[str], list[str]]

SHEET_SIGNATURES: list[Signature] = [
    (DocType.ANNUAL_FINANCIAL_STATEMENT, ["annual statement", "eoy"], ["period", "revenue", "expense"]),
    (DocType.YARDI_BUDGET_COMPARISON, ["budget comparison"], ["ptd actual", "ytd actual", "mtd actual", "% var", "annual"]),
    (DocType.YARDI_BALANCE_SHEET, ["balance sheet"], ["beginning", "net change", "total assets", "current period"]),
    (DocType.YARDI_RENT_ROLL, ["rent roll", "summary groups"], ["% unit occupancy", "occupied units", "future residents", "# of units"]),
    (DocType.YARDI_MARKET_RENT_SCHEDULE, ["market rent schedule"], ["unit type", "occupied units", "average resident rent", "sq ft"]),
    (DocType.YARDI_LEASE_TRADE_OUT, ["resident name", "lease rent"], ["lease renewals", "move ins", "renewal start", "previous lease term", "effective rent"]),
    (DocType.HELLODATA_LISTINGS, ["property name", "asking rent", "effective rent", "leased date"], ["first listed", "days on mkt", "floorplan", "active listing"]),
    (DocType.HELLODATA_COMPS, ["rent comps", "yr built"], ["# units", "leased %", "similarity", "exposure"]),
    (DocType.COSTAR_SUBMARKET_EXCEL, ["period", "vacancy rate", "market asking rent"], ["inventory units", "under constr", "market cap rate", "absorp"]),
    (DocType.RENT_CHART, ["gross psf", "effective psf", "lease count"], ["comp set", "t12", "month"]),
]

PDF_SIGNATURES: list[Signature] = [
    (DocType.COSTAR_SUBMARKET_PDF, ["submarket report", "costar"], ["vacancy rate", "asking rent", "sale comparables", "key indicators"]),
    (DocType.HELLODATA_COMPS, ["rents by unit type"], ["ner", "concession", "# leased", "hellodata"]),
    (DocType.SLATE_CAPITAL_CALLS, ["new capital call"], ["total called", "callable capital", "no capital calls yet", "contributed"]),
    (DocType.SLATE_DISTRIBUTIONS, ["new distribution"], ["no distributions yet", "gross amount", "net amount", "settled"]),
    (DocType.MANAGEMENT_MEMO, ["asset manager", "quarter"], ["property facts", "approved hold", "operating update", "goals"]),
    (DocType.LOAN_SUMMARY, ["loan", "principal"], ["interest rate", "maturity", "amortization", "servicer"]),
]

MIN_CONFIDENCE = 0.6


@dataclass
class Part:
    """One classified unit of a file: a sheet (xlsx) or the whole document (pdf)."""

    doc_type: str
    confidence: float
    locator: str
    file_id: str
    filename: str
    sheet: Sheet | None = None
    pages: list[Page] = field(default_factory=list)
    created: str | None = None

    def to_json(self) -> dict:
        return {"doc_type": self.doc_type, "confidence": round(self.confidence, 2), "locator": self.locator}


def score(text: str, must: list[str], any_of: list[str]) -> float:
    if not all(m in text for m in must):
        return 0.0
    hits = sum(1 for a in any_of if a in text)
    return 0.6 + 0.4 * hits / max(len(any_of), 1)


def best_match(text: str, signatures: list[Signature]) -> tuple[DocType, float]:
    ranked = sorted(((score(text, must, anyof), t) for t, must, anyof in signatures), key=lambda x: -x[0])
    conf, t = ranked[0]
    return (t, conf) if conf >= MIN_CONFIDENCE else (DocType.UNKNOWN, conf)


def classify(doc: Document) -> list[Part]:
    parts: list[Part] = []
    if doc.kind == "xlsx":
        for sh in doc.sheets:
            text = norm(sh.head_text(100))
            t, conf = best_match(text, SHEET_SIGNATURES)
            if t == DocType.UNKNOWN:
                if all(x in text for x in ("account", "description", "ptd actual")):
                    t, conf = DocType.YARDI_BUDGET_COMPARISON, 0.75
                elif all(x in text for x in ("balance sheet", "account", "description", "current period")):
                    t, conf = DocType.YARDI_BALANCE_SHEET, 0.75
                elif all(x in text for x in ("as of", "unit type", "# of units", "average resident rent")):
                    t, conf = DocType.YARDI_MARKET_RENT_SCHEDULE, 0.8
                elif "rent roll" in text and "as of" in text and sh.header_block(
                    ["summary groups", "# of"], max_rows=3, search_rows=sh.nrows
                ) is not None:
                    t, conf = DocType.YARDI_RENT_ROLL, 0.8
                elif all(x in text for x in ("as of", "# of units", "occupied units", "vacant units")):
                    t, conf = DocType.YARDI_RENT_ROLL, 0.8
                elif all(x in text for x in ("lease id", "property name", "event type", "lease rent")):
                    t, conf = DocType.YARDI_LEASE_TRADE_OUT, 0.8
                elif all(x in text for x in ("project id", "capital category", "quarter actual")):
                    t, conf = DocType.CAPITAL_PROJECTS, 0.8
                elif all(x in text for x in ("program", "category", "original budget")):
                    t, conf = DocType.UNDERWRITING_PLAN, 0.8
            parts.append(Part(t.value, conf, f"sheet '{sh.name}'", doc.file_id, doc.filename, sheet=sh))
    else:
        normal = norm(doc.text[:30000])
        t, conf = best_match(normal, PDF_SIGNATURES)
        ocr_pages = [str(page.number) for page in doc.pages if page.ocr]
        locator = f"pages 1-{len(doc.pages)}"
        if ocr_pages:
            locator += f"; Gemini vision OCR pages {', '.join(ocr_pages)}"
        if "investor cash activity statement" in normal and "capital calls" in normal:
            parts.append(Part(DocType.SLATE_CAPITAL_CALLS.value, 0.9, locator, doc.file_id, doc.filename, pages=doc.pages, created=doc.created))
            if "distributions" in normal:
                parts.append(Part(DocType.SLATE_DISTRIBUTIONS.value, 0.9, locator, doc.file_id, doc.filename, pages=doc.pages, created=doc.created))
        else:
            parts.append(Part(t.value, conf, locator, doc.file_id, doc.filename, pages=doc.pages, created=doc.created))
    return parts
