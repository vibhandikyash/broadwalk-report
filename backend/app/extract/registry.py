"""DocType -> extractor. Add a new document type by adding a classifier signature and one entry here."""
from __future__ import annotations

from typing import Callable

from ..classify.classifier import DocType, Part
from . import (costar_excel, costar_pdf, hellodata_comps, hellodata_listings, rent_chart, slate, yardi_balance_sheet,
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
}


def run_extractor(part: Part) -> Extraction:
    fn = EXTRACTORS.get(part.doc_type)
    if fn is None:
        raise ExtractionError(f"No extractor for document type '{part.doc_type}'")
    return fn(part)
