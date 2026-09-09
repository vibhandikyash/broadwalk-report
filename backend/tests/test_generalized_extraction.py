from app.classify.classifier import DocType, classify
from app.extract.generalized import extract_loan_summary, extract_management_memo
from app.extract.hellodata_comps import extract as extract_comps
from app.extract.yardi_lto import extract as extract_lto
from app.extract.yardi_rent_roll import extract as extract_rent_roll
from app.extract.yardi_rent_schedule import extract as extract_rent_schedule
from app.readers.document import Document, Page

from tests.helpers import pdf_part, sheet_part


def test_ocr_management_memo_uses_the_normal_classification_and_extraction_path():
    text = (
        "Asset manager quarterly memorandum | Cedar Quay ApartmentsProperty facts"
        "Cedar Quay Apartments is a synthetic 84-unit community. "
        "Acquired 2027-10-15 for $12,600,000; contributed equity $4,600,000. "
        "Approved hold: four years. Reach 95% physical occupancy."
        " Quarter-end operating update: The pool gate repair was completed on 2028-03-15. "
        "Approved next-quarter goals: Reach 96% physical occupancy; complete exterior painting."
    )
    document = Document("f1", "scan.pdf", "pdf", pages=[Page(1, text, ocr=True, ocr_confidence=0.99)])

    part = classify(document)[0]
    result = extract_management_memo(part)

    assert part.doc_type == DocType.MANAGEMENT_MEMO
    assert result.data["property_name"] == "Cedar Quay Apartments"
    assert result.data["units"] == 84
    assert result.data["hold_period_years"] == 4
    assert result.data["purchase_price"] == 12_600_000
    assert result.data["business_plan_summary"] == "Approved hold period is 4 years."
    assert result.data["status_items"][0]["title"] == "The Pool Gate Repair"
    assert result.data["goal_items"][0]["title"] == "Occupancy"
    assert result.data["goal_items"][1]["title"] == "Project delivery"


def test_generic_date_keyed_rent_and_occupancy_tables_return_snapshots():
    schedule = sheet_part([
        ["Market rent schedule"], ["Cedar Quay Apartments (cq84)"],
        ["As of", "Unit Type", "# of Units", "Sq Ft", "Average Resident Rent", "Market Rent"],
        ["2027-12-31", "S0", 24, 480, 980, 1080],
        ["2028-03-31", "S0", 24, 480, 960, 1060],
    ], DocType.YARDI_MARKET_RENT_SCHEDULE)
    occupancy = sheet_part([
        ["Rent Roll - Summary Groups"], ["Cedar Quay Apartments (cq84)"],
        ["As of", "# of Units", "Occupied Units", "Vacant Units"],
        ["2027-12-31", 84, 76, 8], ["2028-03-31", 84, 72, 12],
    ], DocType.YARDI_RENT_ROLL)

    rents = extract_rent_schedule(schedule).data["_snapshots"]
    occupied = extract_rent_roll(occupancy).data["_snapshots"]

    assert [row["as_of"] for row in rents] == ["2027-12-31", "2028-03-31"]
    assert rents[1]["total"]["avg_resident_rent"] == 960
    assert occupied[1]["occupied_units"] == 72
    assert occupied[1]["occupancy_pct"] == 72 / 84


def test_generic_lease_event_table_maps_event_types_and_period():
    part = sheet_part([
        ["Lease activity"], ["Cedar Quay Apartments (cq84)"],
        ["Period = 2028-01-01 - 2028-03-31"],
        ["Lease ID", "Property Name", "Event Type", "Unit", "Unit Type", "Resident Name", "Lease Start",
         "Previous Lease Rent", "Lease Rent", "Effective Rent", "Sq Ft", "Lease Term Months"],
        ["N-1", "Cedar Quay Apartments", "New", "101", "A1", "A", "2028-02-01", 1200, 1250, 1230, 690, 12],
        ["R-1", "Cedar Quay Apartments", "Renewal", "102", "A1", "B", "2028-03-01", 1200, 1240, 1220, 690, 12],
    ], DocType.YARDI_LEASE_TRADE_OUT)

    result = extract_lto(part).data

    assert result["period"] == {"start": "2028-01-01", "end": "2028-03-31"}
    assert result["sections"]["move_ins"]["rows"][0]["lease_id"] == "N-1"
    assert result["sections"]["renewals"]["rows"][0]["lease_id"] == "R-1"


def test_generic_loan_summary_extracts_explicit_terms():
    part = pdf_part(
        "Loan servicing summary | Cedar Quay Apartments\nProperty: Cedar Quay Apartments. "
        "Principal at 2028-03-31: $8,000,000. Fixed annual interest rate 6.00%. "
        "Term 48 months from 2027-11-01; maturity 2031-11-01. Interest only through 2029-10-31. "
        "Current monthly interest-only payment $40,000.00. Then 30-year amortization; monthly P&I; $47,964.04. "
        "Prepayment: yield maintenance until 2029-10-31. Replacement reserve $2,000 monthly. "
        "Repairs escrow: $125,000.",
        DocType.LOAN_SUMMARY,
    )

    result = extract_loan_summary(part).data

    assert result["property_name"] == "Cedar Quay Apartments"
    assert result["loan_amount"] == 8_000_000
    assert result["rate"] == 0.06
    assert result["rate_type"] == "Fixed"
    assert result["io_through"] == "2029-10-31"
    assert result["io_months"] == 24
    assert result["pi_monthly"] == 47_964.04
    assert result["prepayment"] == "yield maintenance until 2029-10-31"
    assert result["replacement_reserve_monthly"] == 2_000
    assert result["repairs_escrow"] == 125_000


def test_comp_summary_prefers_explicit_rents_and_derives_leased_percentage():
    part = sheet_part([
        ["Peer property summary"],
        ["Property", "Address", "Units", "Leased Units", "Asking Rent", "Effective Rent"],
        ["Maple Court", "1 Main St", 100, 94, 1_550, 1_510],
    ], DocType.HELLODATA_COMPS)

    result = extract_comps(part).data["comps"][0]

    assert result["asking_rent"] == 1_550
    assert result["effective_rent"] == 1_510
    assert result["leased_pct"] == 0.94
