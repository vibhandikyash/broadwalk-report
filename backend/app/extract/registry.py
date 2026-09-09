"""DocType -> extractor. Add a new document type by adding a classifier signature and one entry here."""
from __future__ import annotations

from typing import Callable

from ..classify.classifier import DocType, Part
from . import (costar_excel, costar_pdf, generalized, hellodata_comps, hellodata_listings, rent_chart, slate, yardi_balance_sheet,
               yardi_budget, yardi_lto, yardi_rent_roll, yardi_rent_schedule)
from .base import Extraction, ExtractionError

EXTRACTORS: dict[str, Callable[[Part], Extraction]] = {
    DocType.YARDI_BUDGET_COMPARISON.value: yardi_budget.extract,
    DocType.YARDI_BALANCE_SHEET.value: yardi_balance_sheet.extract,
    DocType.YARDI_RENT_ROLL.value: yardi_rent_roll.extract,
    DocType.YARDI_MARKET_RENT_SCHEDULE.value: yardi_rent_schedule.extract,
    DocType.YARDI_LEASE_TRADE_OUT.value: yardi_lto.extract,
    DocType.HELLODATA_LISTINGS.value: hellodata_listings.extract,
    DocType.HELLODATA_COMPS.value: hellodata_comps.extract,
    DocType.COSTAR_SUBMARKET_EXCEL.value: costar_excel.extract,
    DocType.COSTAR_SUBMARKET_PDF.value: costar_pdf.extract,
    DocType.RENT_CHART.value: rent_chart.extract,
    DocType.SLATE_CAPITAL_CALLS.value: slate.extract_capital_calls,
    DocType.SLATE_DISTRIBUTIONS.value: slate.extract_distributions,
    DocType.MANAGEMENT_MEMO.value: generalized.extract_management_memo,
    DocType.LOAN_SUMMARY.value: generalized.extract_loan_summary,
    DocType.CAPITAL_PROJECTS.value: generalized.extract_capital_projects,
    DocType.UNDERWRITING_PLAN.value: generalized.extract_underwriting_plan,
}


def part_provenance(part: Part) -> dict:
    """How the text of this part was obtained, so every value it yields can say so on the report.

    A workbook sheet is always read natively. A PDF is 'ocr' when every page came back from vision
    OCR, 'mixed' when only some did, and 'native' when none did. `ocr_pages` lets a value that names
    a page be attributed exactly; the confidence is the lowest any OCR'd page reported.
    """
    if not part.pages:
        return {"kind": "xlsx", "method": "native", "ocr_pages": [], "ocr_confidence": None}
    ocr_pages = [p.number for p in part.pages if p.ocr]
    confidences = [p.ocr_confidence for p in part.pages if p.ocr and p.ocr_confidence is not None]
    method = "native" if not ocr_pages else ("ocr" if len(ocr_pages) == len(part.pages) else "mixed")
    return {"kind": "pdf", "method": method, "ocr_pages": ocr_pages,
            "ocr_confidence": min(confidences) if confidences else None}


def run_extractor(part: Part) -> Extraction:
    fn = EXTRACTORS.get(part.doc_type)
    if fn is None:
        raise ExtractionError(f"No extractor for document type '{part.doc_type}'")
    ex = fn(part)
    ex.provenance = part_provenance(part)
    return ex
