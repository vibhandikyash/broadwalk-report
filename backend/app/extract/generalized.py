"""Extract explicit facts from ordinary management, loan and capital documents."""
from __future__ import annotations

import re
from datetime import date

from ..classify.classifier import Part
from ..readers.document import Sheet, norm, to_number
from .base import Extraction, ExtractionError
from .yardi_common import find_property, parse_period


def _text(part: Part) -> str:
    return "\n".join(page.text for page in part.pages)


def _money(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, re.I | re.S)
    return to_number(match.group(1)) if match else None


def _months_between(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
    months = (end_date.year - start_date.year) * 12 + end_date.month - start_date.month
    return months + (1 if end_date.day >= start_date.day else 0)


def _memo_items(text: str) -> tuple[list[dict], list[dict]]:
    status_items = []
    for sentence in re.findall(r"[^.!?]*(?:completed|finished|remaining|in progress|due\s+\d{4}-\d{2}-\d{2})[^.!?]*[.!?]?", text, re.I):
        body = re.sub(r"\s+", " ", sentence).strip(" .")
        if not body:
            continue
        subject = re.split(r"\b(?:was|were|is|are|remains?|due)\b", body, maxsplit=1, flags=re.I)[0]
        title = re.sub(r"^(?:quarter-end\s+)?(?:operating\s+)?update\s*", "", subject, flags=re.I).strip(" :-")
        status_items.append({"title": title.title() or "Operating update", "subtitle": None, "body": body + "."})

    goals = re.search(r"(?:approved\s+)?next[- ]quarter goals?\s*[:.-]?\s*(.+)", text, re.I | re.S)
    goal_items = []
    if goals:
        for clause in re.split(r"\s*;\s*|(?<=[.!?])\s+", goals.group(1)):
            body = re.sub(r"\s+", " ", clause).strip(" .")
            if not body:
                continue
            label = "Occupancy" if "occupancy" in body.lower() else "Renewals" if "renewal" in body.lower() else "Project delivery"
            goal_items.append({"title": label, "subtitle": None, "body": body + "."})
    return status_items[:3], goal_items[:3]


def extract_management_memo(part: Part) -> Extraction:
    text = _text(part)
    name_match = re.search(r"(?:memorandum\s*\|\s*|property:\s*)(.+?)(?:\r?\n|property facts|\.)", text, re.I)
    units_match = re.search(r"\b(\d[\d,]*)-unit\b", text, re.I)
    style_match = re.search(r"\b\d[\d,]*-unit\s+([a-z][a-z -]+?)\s+community\b", text, re.I)
    address_match = re.search(r"community at\s+(.+?)\.\s*Built in", text, re.I | re.S)
    built_match = re.search(r"\bBuilt in\s+(\d{4})\b", text, re.I)
    acres_match = re.search(r"\bon\s+(\d+(?:\.\d+)?)\s+acres\b", text, re.I)
    hold_match = re.search(r"approved hold:\s*(\w+|\d+)\s+years?", text, re.I)
    word_numbers = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                    "eight": 8, "nine": 9, "ten": 10}
    hold = None
    if hold_match:
        raw = hold_match.group(1).lower()
        hold = int(raw) if raw.isdigit() else word_numbers.get(raw)
    acquired = re.search(r"acquired\s+(\d{4}-\d{2}-\d{2})\s+for\s+\$([\d,]+)", text, re.I)
    installations = re.search(r"(\d+)\s+installations?\s+were completed", text, re.I)
    occupancy_goal = re.search(r"reach\s+(\d+(?:\.\d+)?)%\s+physical occupancy", text, re.I)
    renewal_goal = re.search(r"renewal increases? of\s+(\d+(?:\.\d+)?)%\s+to\s+(\d+(?:\.\d+)?)%", text, re.I)
    property_description = None
    description_match = re.search(r"property facts\s*(.+?)(?:acquisition and plan|\r?\nAcquisition)", text, re.I | re.S)
    if description_match:
        property_description = re.sub(r"\s+", " ", description_match.group(1)).strip()
    business_plan_parts = []
    if hold is not None:
        business_plan_parts.append(f"Approved hold period is {hold} years.")
    if re.search(r"washer/dryer program is active", text, re.I):
        detail = f"; {installations.group(1)} installations completed this quarter" if installations else ""
        business_plan_parts.append(f"The washer/dryer program is active{detail}.")
    status_items, goal_items = _memo_items(text)
    data = {
        "property_name": name_match.group(1).strip() if name_match else None,
        "units": to_number(units_match.group(1)) if units_match else None,
        "building_class": style_match.group(1).strip() if style_match else None,
        "address": re.sub(r"\s+", " ", address_match.group(1)).strip() if address_match else None,
        "year_built": int(built_match.group(1)) if built_match else None,
        "site_acres": float(acres_match.group(1)) if acres_match else None,
        "hold_period_years": hold,
        "acquired_date": acquired.group(1) if acquired else None,
        "purchase_price": to_number(acquired.group(2)) if acquired else None,
        "equity_invested": _money(text, r"contributed equity\s+\$([\d,]+)"),
        "washer_dryer_status": "active" if re.search(r"washer/dryer program is active", text, re.I) else None,
        "installations": int(installations.group(1)) if installations else None,
        "occupancy_goal": float(occupancy_goal.group(1)) / 100 if occupancy_goal else None,
        "renewal_goal": ([float(renewal_goal.group(1)) / 100, float(renewal_goal.group(2)) / 100]
                         if renewal_goal else None),
        "property_description": property_description,
        "business_plan_summary": " ".join(business_plan_parts) or None,
        "status_items": status_items,
        "goal_items": goal_items,
        "text": text,
    }
    if not any(value is not None for key, value in data.items() if key != "text"):
        raise ExtractionError("No explicit management facts found")
    return Extraction(doc_type=part.doc_type, locator=part.locator, data=data)


def extract_loan_summary(part: Part) -> Extraction:
    text = _text(part)
    name_match = re.search(r"property:\s*([^\n.]+)", text, re.I)
    principal = re.search(r"principal at\s+(\d{4}-\d{2}-\d{2}):\s*\$([\d,]+)", text, re.I | re.S)
    rate = re.search(r"(?:annual interest rate|interest rate)\s+(\d+(?:\.\d+)?)%", text, re.I)
    lender = re.search(r"lender:\s*([^;]+)", text, re.I)
    servicer = re.search(r"servicer:\s*([^.;]+)", text, re.I)
    effective = re.search(r"term\s+\d+\s+months from\s+(\d{4}-\d{2}-\d{2})", text, re.I)
    maturity = re.search(r"maturity\s+(\d{4}-\d{2}-\d{2})", text, re.I)
    io_through = re.search(r"interest\s+only\s+through\s+(\d{4}-\d{2}-\d{2})", text, re.I)
    term = re.search(r"term\s+(\d+)\s+months", text, re.I)
    amort = re.search(r"then\s+(\d+)-year amortization", text, re.I)
    io_payment = _money(text, r"monthly interest-only payment\s+\$([\d,]+(?:\.\d+)?)")
    pi_payment = _money(text, r"monthly\s+P&I;\s*\$([\d,]+(?:\.\d+)?)")
    rate_type = ("Fixed" if re.search(r"\bfixed\b.{0,40}\binterest rate\b", text, re.I | re.S) else
                 "Variable" if re.search(r"\b(?:variable|floating)\b.{0,40}\b(?:rate|interest)\b", text, re.I | re.S) else None)
    prepayment = re.search(r"prepayment\s*:\s*([^\n.]+)", text, re.I)
    replacement_reserve = _money(text, r"replacement reserve(?:\s+of|\s*:)?\s*\$([\d,]+(?:\.\d+)?)\s*(?:per month|monthly)")
    repairs_escrow = _money(text, r"(?:repairs?|repair) escrow(?:\s+of|\s*:)?\s*\$([\d,]+(?:\.\d+)?)")
    effective_value = effective.group(1) if effective else None
    io_value = io_through.group(1) if io_through else None
    data = {
        "property_name": name_match.group(1).strip() if name_match else None,
        "as_of": principal.group(1) if principal else None,
        "loan_amount": to_number(principal.group(2)) if principal else None,
        "rate": float(rate.group(1)) / 100 if rate else None,
        "rate_type": rate_type,
        "lender": lender.group(1).strip() if lender else None,
        "servicer": servicer.group(1).strip() if servicer else None,
        "effective_date": effective_value,
        "maturity_date": maturity.group(1) if maturity else None,
        "io_through": io_value,
        "io_months": _months_between(effective_value, io_value),
        "term_months": int(term.group(1)) if term else None,
        "amortization_months": int(amort.group(1)) * 12 if amort else None,
        "interest_monthly": io_payment,
        "pi_monthly": pi_payment,
        "recourse": "Non-recourse" if "non-recourse" in text.lower() else None,
        "prepayment": prepayment.group(1).strip() if prepayment else None,
        "replacement_reserve_monthly": replacement_reserve,
        "repairs_escrow": repairs_escrow,
    }
    if data["loan_amount"] is None and data["rate"] is None:
        raise ExtractionError("No explicit loan terms found")
    return Extraction(doc_type=part.doc_type, locator=part.locator, data=data)


def extract_capital_projects(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    hb = sh.header_block(["capital category", "quarter actual"], max_rows=1, search_rows=120)
    if hb is None:
        raise ExtractionError("Capital-project header not found")
    hrow, _, headers = hb
    columns = {
        "category": Sheet.col(headers, r"capital category"), "ptd_actual": Sheet.col(headers, r"quarter actual"),
        "ptd_budget": Sheet.col(headers, r"quarter budget"), "ytd_actual": Sheet.col(headers, r"ytd actual"),
        "ytd_budget": Sheet.col(headers, r"ytd budget"), "annual_budget": Sheet.col(headers, r"annual budget"),
    }
    rows = []
    for r in range(hrow + 1, sh.nrows):
        label = sh.text(r, columns["category"]) if columns["category"] is not None else ""
        if not label:
            continue
        values = {key: to_number(sh.cell(r, col)) if col is not None else None for key, col in columns.items() if key != "category"}
        if any(value is not None for value in values.values()):
            rows.append({"label": label, "row": r, "values": values})
    period = parse_period(sh.head_text(hrow))
    return Extraction(doc_type=part.doc_type, locator=part.locator,
                      data={"period": period, "property_name": find_property(sh, max_row=hrow)[0],
                            "property_ref": find_property(sh, max_row=hrow)[1], "lines": rows})


def extract_underwriting_plan(part: Part) -> Extraction:
    sh = part.sheet
    assert sh is not None
    hb = sh.header_block(["program", "original budget"], max_rows=1, search_rows=120)
    if hb is None:
        raise ExtractionError("Underwriting-plan header not found")
    hrow, _, headers = hb
    c_program = Sheet.col(headers, r"^program$")
    c_category = Sheet.col(headers, r"^category$")
    c_budget = Sheet.col(headers, r"original budget")
    c_spent = Sheet.col(headers, r"spent since|spent to date")
    rows = []
    for r in range(hrow + 1, sh.nrows):
        category = sh.text(r, c_category) if c_category is not None else ""
        budget = to_number(sh.cell(r, c_budget)) if c_budget is not None else None
        if category and budget is not None:
            rows.append({"program": sh.text(r, c_program) if c_program is not None else None, "category": category,
                         "original_budget": budget, "spent_to_date": to_number(sh.cell(r, c_spent)) if c_spent is not None else None,
                         "row": r})
    return Extraction(doc_type=part.doc_type, locator=part.locator,
                      data={"property_name": find_property(sh, max_row=hrow)[0],
                            "property_ref": find_property(sh, max_row=hrow)[1], "rows": rows})
