# backend/tests/test_document.py
import datetime as dt

from app.readers.document import Sheet, is_number, norm, to_date, to_number


def test_to_number_variants():
    assert to_number("1,234.5") == 1234.5
    assert to_number("(1,234)") == -1234
    assert to_number("$48,000") == 48000
    assert to_number("91.71%") == 91.71
    assert to_number("N/A") is None and to_number(None) is None and to_number(True) is None
    assert to_number(12) == 12.0 and to_number("abc") is None


def test_is_number():
    assert is_number(5) and is_number("1,234") and is_number("(12.5)")
    assert not is_number("4000-0000") and not is_number("Total") and not is_number(None) and not is_number(False)


def test_to_date_variants():
    assert to_date("06/30/2026") == dt.date(2026, 6, 30)
    assert to_date(dt.datetime(2026, 4, 1, 5)) == dt.date(2026, 4, 1)
    assert to_date("Jul-25") == dt.date(2025, 7, 1)
    assert to_date("2026-04") == dt.date(2026, 4, 1)
    assert to_date("not a date") is None


def test_norm_collapses_whitespace():
    assert norm("  PTD   Actual ") == "ptd actual" and norm(None) == ""


def test_header_block_joins_multirow_headers_and_skips_blank_rows():
    rows = [
        ["Rent Roll"], ["The Boardwalk (45726)"], [None],
        ["Summary Groups", None, "Square", "# Of", "% Unit"],
        [None, None, "Footage", "Units", "Occupancy"],
        ["Occupied Units", None, "258,734.00", 310, 91.71],
    ]
    sh = Sheet("Report1", rows)
    start, k, headers = sh.header_block(["summary groups", "# of"], max_rows=3)
    assert (start, k) == (3, 2)
    assert Sheet.col(headers, r"# of units") == 3 and Sheet.col(headers, r"% unit occupancy") == 4
    assert sh.has_numbers(5) and not sh.has_numbers(4)


def test_header_block_requires_token_on_start_row():
    rows = [["Book = Accrual"], [None, None, "Balance", "Beginning", "Net"], [None, None, "Current Period", "Balance", "Change"], ["1000-0000", "Cash", 5, 4, 1]]
    sh = Sheet("R", rows)
    start, k, headers = sh.header_block(["balance", "beginning"], max_rows=2)
    assert (start, k) == (1, 2) and Sheet.col(headers, r"change") == 4


def test_label_column_skips_gl_codes_and_find():
    sh = Sheet("R", [["4000-0000", "  Gross Potential Rent", 5], ["4001-0000", "  Loss to Lease", 6]])
    assert sh.label_column(0) == 1
    assert sh.find(r"loss to lease") == (1, 1, "  Loss to Lease")
    assert sh.find(r"nothing") is None
