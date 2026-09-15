# backend/tests/test_extract_yardi_rent_roll.py
import pytest

from app.classify.classifier import DocType
from app.extract.base import ExtractionError
from app.extract.yardi_rent_roll import extract
from tests.helpers import rent_roll_rows, sheet_part


def test_rent_roll_summary():
    d = extract(sheet_part(rent_roll_rows("06/30/2026", 306, 338, 90.53, 14), DocType.YARDI_RENT_ROLL)).data
    assert d["as_of"] == "2026-06-30" and d["property_name"] == "The Boardwalk" and d["property_ref"] == "45726"
    assert d["total_units"] == 338 and d["occupied_units"] == 306 and d["vacant_units"] == 32
    assert d["future_applicants"] == 14 and abs(d["occupancy_pct"] - 0.9053) < 1e-9
    assert d["avg_market_rent"] == 1317.72 and d["avg_resident_rent"] == 1325.13
    assert d["prov"]["occupied_row"] == 14


def test_rent_roll_without_summary_block_raises():
    with pytest.raises(ExtractionError):
        extract(sheet_part([["Rent Roll"], ["Nothing", 1]], DocType.YARDI_RENT_ROLL))


def test_summary_at_end_of_detailed_rent_roll():
    rows = [["Rent Roll"], ["As Of = 03/31/2026"]] + [["unit", i] for i in range(150)]
    rows += [["Summary Groups", None, "# Of Units", "% Unit Occupancy"],
             ["Occupied Units", None, 198, 82.5], ["Total Vacant Units", None, 42],
             ["Totals:", None, 240]]
    data = extract(sheet_part(rows, DocType.YARDI_RENT_ROLL)).data
    assert data["as_of"] == "2026-03-31" and data["occupied_units"] == 198
    assert data["total_units"] == 240 and data["occupancy_pct"] == 0.825


def test_inconsistent_summary_counts_raise():
    rows = [["Rent Roll"], ["As Of = 03/31/2026"], ["Summary Groups", "# Of Units"],
            ["Occupied Units", 250], ["Totals:", 240]]
    with pytest.raises(ExtractionError, match="inconsistent"):
        extract(sheet_part(rows, DocType.YARDI_RENT_ROLL))
