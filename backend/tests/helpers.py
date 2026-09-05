"""Synthetic workbooks that mirror the layouts of the real Yardi/HelloData/CoStar exports."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import openpyxl

from app.classify.classifier import Part
from app.readers.document import Page, Sheet


def make_xlsx(path: Path, sheets: dict[str, list[list]]) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    wb.save(path)
    return path


def sheet_part(rows: list[list], doc_type: str, name: str = "Report1", file_id: str = "f1", filename: str = "file.xlsx") -> Part:
    return Part(doc_type, 1.0, f"sheet '{name}'", file_id, filename, sheet=Sheet(name, rows))


def pdf_part(text: str, doc_type: str, file_id: str = "p1", filename: str = "file.pdf") -> Part:
    pages = [Page(i + 1, t) for i, t in enumerate(text.split("\f"))]
    return Part(doc_type, 1.0, f"pages 1-{len(pages)}", file_id, filename, pages=pages)


BUDGET_ROWS = [
    ["Property =  45726 45726con"],
    ["Budget Comparison"],
    ["Period = Apr 2026-Jun 2026"],
    ["Book = Accrual ; Tree = rp-cashflow"],
    [None, None, " PTD Actual ", " PTD Budget ", " Variance ", " % Var ", " YTD Actual ", " YTD Budget ", " Variance ", " % Var ", " Annual "],
    ["3998-0000", "    REVENUE"],
    ["3999-0000", "      Rental Income"],
    ["4000-0000", "        Gross Potential Rent", 1000, 900, 100, 11.11, 2000, 1800, 200, 11.11, 3600],
    ["4001-0000", "        Loss/Gain to Lease", 10, 50, -40, -80, 20, 100, -80, -80, 200],
    ["4004-0000", "        Less:Concessions-Mthly", 1, 0, 1, "N/A", 1, 0, 1, "N/A", 0],
    ["4005-0000", "        Less:Concessions-One Time", -51, -10, -41, -410, -101, -20, -81, -405, -40],
    ["4006-0000", "        Less:  Vacancy", -100, -110, 10, 9.09, -200, -220, 20, 9.09, -440],
    ["4016-0000", "        Pet Rent", 5, 4, 1, 25, 10, 8, 2, 25, 16],
    ["4060-0000", "        NET RENTAL INCOME", 865, 834, 31, 3.72, 1730, 1668, 62, 3.72, 3336],
    ["4080-9999", "  UTILITY INCOME"],
    ["4081-0005", "        Water Income", 100, 90, 10, 11.11, 200, 180, 20, 11.11, 360],
    ["4081-0100", "        TOTAL UTILITY INCOME", 100, 90, 10, 11.11, 200, 180, 20, 11.11, 360],
    ["4400-0000", "  OTHER INCOME"],
    ["4407-0050", "        Less:Write Off Bad Debt", -10, -5, -5, -100, -20, -10, -10, -100, -20],
    ["4407-0055", "        Former Resident Collections", 7, 3, 4, 133, 14, 6, 8, 133, 12],
    ["4699-0000", "        TOTAL OTHER INCOME", 35, 30, 5, 16.67, 70, 60, 10, 16.67, 120],
    ["4999-0000", "            TOTAL REVENUE", 1000, 954, 46, 4.82, 2000, 1908, 92, 4.82, 3816],
    ["5000-0000", "    EXPENSES"],
    ["5019-0000", "  PAYROLL"],
    ["5020-0000", "        Manager Salaries", 100, 90, -10, -11.11, 200, 180, -20, -11.11, 360],
    ["5055-0000", "          TOTAL PAYROLL", 100, 90, -10, -11.11, 200, 180, -20, -11.11, 360],
    ["5056-0000", "  GENERAL & ADMINISTRATIVE"],
    ["5056-1000", "          TOTAL GENERAL & ADMINISTRATIVE", 20, 25, 5, 20, 40, 50, 10, 20, 100],
    ["5095-0000", "  MARKETING"],
    ["5108-0000", "          TOTAL MARKETING", 10, 10, 0, 0, 20, 20, 0, 0, 40],
    ["5200-0000", "  REPAIRS & MAINTENANCE"],
    ["5215-0000", "          TOTAL REPAIRS & MAINTENANCE", 30, 25, -5, -20, 60, 50, -10, -20, 100],
    ["5299-0000", "  UTILITIES"],
    ["5310-0000", "        Water & Wastewater", 120, 100, -20, -20, 240, 200, -40, -20, 400],
    ["5399-0000", "          TOTAL UTILITIES", 120, 100, -20, -20, 240, 200, -40, -20, 400],
    ["5460-0000", "  MANAGEMENT FEES"],
    ["5465-0000", "          TOTAL MANAGEMENT FEES", 30, 30, 0, 0, 60, 60, 0, 0, 120],
    ["5499-0000", "  TAXES"],
    ["5500-0000", "        Property Taxes", 100, 100, 0, 0, 200, 200, 0, 0, 400],
    ["5515-0000", "          TOTAL TAXES", 100, 100, 0, 0, 200, 200, 0, 0, 400],
    ["5519-9999", "  INSURANCE"],
    ["5520-0000", "        Insurance", 40, 60, 20, 33.33, 80, 120, 40, 33.33, 240],
    ["5520-0010", "          TOTAL INSURANCE", 40, 60, 20, 33.33, 80, 120, 40, 33.33, 240],
    ["6500-0000", "            TOTAL EXPENSES", 450, 440, -10, -2.27, 900, 880, -20, -2.27, 1760],
    ["6700-0000", "            NET OPERATING INCOME/(LOSS)", 550, 514, 36, 7, 1100, 1028, 72, 7, 2056],
    ["6800-0000", "  DEBT SERVICE"],
    ["6801-0000", "        Interest Expense-1st Lien", 300, 300, 0, 0, 600, 600, 0, 0, 1200],
    ["6810-0000", "          TOTAL DEBT SERVICE", 300, 300, 0, 0, 600, 600, 0, 0, 1200],
    ["7000-0000", "            NET INCOME/(LOSS) AFTER DS", 250, 214, 36, 16.82, 500, 428, 72, 16.82, 856],
    ["7001-0000", "    NON-OPERATING EXPENSES"],
    ["7004-0000", "        Legal Fees", 0, 5, 5, 100, 1, 10, 9, 90, 20],
    [None, " INTERIOR & EXTERIOR RENOVATIONS"],
    [None, "      INTERIOR RENOVATIONS"],
    ["7100-0009", "        Paint", 25, 15, -10, -66.67, 48, 38, -10, -26.32, 68],
    ["7100-0016", "        Plumbing Replacement", 20, 17, -3, -17.65, 27, 24, -3, -12.5, 72],
    [None, "          TOTAL INTERIOR RENOVATIONS", 45, 32, -13, -40.63, 75, 62, -13, -20.97, 140],
    [None, "        EXTERIOR RENOVATIONS"],
    ["7200-0000", "      ROOF"],
    ["7200-0002", "        Roof", 3, 0, -3, "N/A", 3, 0, -3, "N/A", 2],
    [None, "          TOTAL ROOF", 3, 0, -3, "N/A", 3, 0, -3, "N/A", 2],
    [None, "          TOTAL EXTERIOR RENOVATIONS", 3, 0, -3, "N/A", 3, 0, -3, "N/A", 2],
    ["7500-0000", "  LEASE UP COSTS"],
    ["7500-0003", "        Marketing & Promotion", 1, 0, -1, "N/A", 2, 1, -1, -100, 1],
    ["7800-0000", "  DEPR/AMORT EXPENSE"],
    ["7810-0065", "        Amortization - Loan Costs", 36, 0, -36, "N/A", 72, 0, -72, "N/A", 0],
    [None, "    NON-OPERATING ITEMS"],
    ["1800-0005", "        EXTERIOR IMPROVEMENTS"],
    ["1811-0005", "      PLUMBING"],
    ["1814-0000", "        Plumbing", -13, 0, -13, "N/A", -20, -7, -13, -185.7, -7],
    ["1820-0010", "          TOTAL PLUMBING", -13, 0, -13, "N/A", -20, -7, -13, -185.7, -7],
    [None, "     TOTAL NON-OPERATING ITEMS", -13, 0, -13, "N/A", -20, -7, -13, -185.7, -7],
    [None, None, 61, 32, None, None, 98, 69],
]

BALANCE_ROWS = [
    ["Property =  45726 45726con"],
    ["Balance Sheet (With Period Change)"],
    ["Period = Apr 2026-Jun 2026"],
    ["Book = Accrual ; Tree = ysi_bs"],
    [None, None, "Balance", "Beginning", "Net"],
    [None, None, "Current Period", "Balance", "Change"],
    ["0999-0000", "                                         ASSETS"],
    ["1000-0100", "        Cash - Operating", 371079.7, 317212.03, 53867.67],
    ["1500-0000", "        Land", 9504000, 9504000, 0],
    ["1500-0021", "        Building", 38016000, 38016000, 0],
    ["1500-0029", "          Total Building", 47520000, 47520000, 0],
    ["1500-0041", "        Furniture, Fixtures & Equipment", 480000, 480000, 0],
    ["1500-0049", "          Total Furniture & Fixtures", 480000, 480000, 0],
    ["1995-0000", "                   TOTAL ASSETS", 51612168.23, 51472851.8, 139316.43],
    ["1997-0000", "     LIABILITIES"],
    ["2139-0001", "        Accrued Interest", 159161.98, 164467.37, -5305.39],
    ["2310-0000", "        Mortgage Payable", 36519000, 36519000, 0],
    ["2310-0020", "          TOTAL MORTGAGE PAYABLE", 36519000, 36519000, 0],
    ["2999-0000", "     EQUITY"],
    ["3015-0000", "        Owner Contributions", 14259605.94, 14259605.94, 0],
    ["3994-0000", "              TOTAL EQUITY", 14076975.24, 14098813.12, -21837.88],
]


def rent_roll_rows(as_of: str, occupied: int, total: int, pct: float, future: int) -> list[list]:
    return [
        ["Rent Roll"], ["The Boardwalk (45726)"], [f"As Of = {as_of}"], [None],
        ["Property", "State", "Total", "Name", "Market", "Resident", "Deposit", "Average", "Average", "Average", "Balance"],
        [None, None, "Units", None, "Rent", "Rent", None, "Market", "Resident", "Deposit"],
        [None, None, None, None, None, None, None, "Rent", "Rent"],
        ["45726", "FL", total, "The Boardwalk", 445390, 405490, 268485.13, 1317.72, 1325.13, 877.4, -53332.85],
        [None, None, total, "Total", 445390, 405490, 268485.13, 1317.72, 1325.13, 877.4, -53332.85],
        [None],
        ["Summary Groups", None, "Square", "Market", "Actual", "Security", "Other", "# Of", "% Unit", "% Sqft", "Balance"],
        [None, None, "Footage", "Rent", "Rent", "Deposit", "Deposits", "Units", "Occupancy", "Occupied"],
        ["Current/Notice/Vacant Residents", None, "284,310.00", "445,390.00", "405,490.00", "268,485.13", "-1,000.00", total, pct, 90.14, "-48,937.14"],
        ["Future Residents/Applicants", None, "10,937.00", "17,594.00", "0.00", "0.00", "0.00", future, None, None, "-4,395.71"],
        ["Occupied Units", None, "256,289.00", "402,494.00", None, None, None, occupied, pct, 90.14],
        ["Total Non Rev Units", None, "0.00", "0.00", None, None, None, 0, "0.00", "0.00"],
        ["Total Vacant Units", None, "28,021.00", "42,896.00", None, None, None, total - occupied, 9.46, 9.85],
        ["Totals:", None, "284,310.00", "445,390.00", "405,490.00", "268,485.13", "-1,000.00", total, "100.00", "100.00", "-53,332.85"],
    ]


def schedule_rows(as_of: str, rents: dict[str, float]) -> list[list]:
    """rents: unit-type label -> average resident rent (occupied units fixed per type below)."""
    return [
        ["Market Rent Schedule"], ["The Boardwalk (45726)"], [f"As Of = {as_of}"],
        ["Unit Type", "Units", "Unit Type", "Unit Type", "Total", "Total Unit", "Average", "Occupied", "Average"],
        [None, None, "Rent", "Sq Ft", "Unit Type", "Rent", "Unit Rent", "Units", "Resident Rent"],
        [None, None, None, None, "Rent"],
        ["1 Bedroom 1 Bathroom (BWK.A1)", 40, 999, 657, 39960, 44690, 1117.25, 38, rents["BWK.A1"]],
        ["2 Bedroom 1 Bathroom (BWK.B0)", 52, 1215, 814, 63180, 70119, 1348.44, 47, rents["BWK.B0"]],
        ["2 Bedroom 2 Bathroom (BWK.B1)", 24, 1209, 875, 29016, 32771, 1365.45, 19, rents["BWK.B1"]],
        ["0 Bedroom 1 Bathroom (BWK.S1)", 23, 901, 550, 20723, 25353, 1102.3, 22, rents["BWK.S1"]],
        ["Grand Total", 338, 1100, 760, 152879, 172933, 1244.11, 306, rents["TOTAL"]],
    ]


LTO_ROWS = [
    [None, "Lease Renewals"],
    [None, "Leases Expiring between 2026-04-01 and 2026-06-30"],
    [None],
    [None, None, None, None, None, "New Lease Term", None, None, None, None, None, None, None, None, None, "Previous Lease Term"],
    [None, "Resident Name", "Unit Type", "Sqft", "Unit", "Renewal Start", "Lease Term", "Market Rent", "Lease Rent", "Up-Front Concessions", "Total Recurring Concessions", "Total Concessions", "# Months Free", "Effective Rent", "EFF Rent PSF", "Lease Rent", "Total Concessions", "Lease Term", "Effective Rent", "Eff Rent PSF", "Rent Change", "% Change", "Eff Rent % Change"],
    ["The Boardwalk", "A Renter", "BWK.A1   ", 657, "4715D125", dt.datetime(2026, 4, 22), 12, 1264, 1425, 1425, 0, 1425, 1, 1306.25, 1.99, 1405, 0, 12, 1405, 2.14, 20, 0.01, -0.07],
    [None, None, "Averages for BWK.A1   ", None, None, None, 12, 1264, 1425, 1425, 0, 1425, 1, 1306.25, 1.99, 1405, 0, 12, 1405, 2.14, 20, 0.01, -0.07],
    ["The Boardwalk", "B Renter", "BWK.S1   ", 550, "4640H240", dt.datetime(2026, 5, 1), 12, 986, 1055, 1055, 0, 1055, 1, 967.08, 1.76, 1035, 0, 12, 1035, 1.88, 20, 0.02, -0.07],
    [None, "Averages for The Boardwalk", None, None, None, None, 12, 1125, 1240, 1240, 0, 1240, 1, 1136.67, 1.88, 1220, 0, 12, 1220, 2.01, 20, 0.02, -0.07],
    [None],
    [None, "Move Ins"],
    [None, "Move In between 2026-04-01 and 2026-06-30"],
    [None],
    [None, None, None, None, None, "New Lease Term", None, None, None, None, None, None, None, None, None, "Previous Lease Term"],
    [None, "Resident Name", "Unit Type", "Sqft", "Unit", "Lease Start", "Lease Term", "Market Rent", "Lease Rent", "Up-Front Concessions", "Total Recurring Concessions", "Total Concessions", "# Months Free", "Effective Rent", "EFF Rent PSF", "Lease Rent", "Total Concessions", "Lease Term", "Effective Rent", "Eff Rent PSF", "Rent Change", "% Change", "Eff Rent % Change"],
    ["The Boardwalk", "C Renter", "BWK.A1   ", 657, "4715D130", dt.datetime(2026, 6, 26), 12, 1094, 1000, 0, 0, 0, 0, 1000, 1.52, 1200, 0, 12, 1200, 1.83, -200, -0.17, -0.17],
    ["The Boardwalk", "D Renter", "BWK.A1   ", 657, "4755B110", dt.datetime(2026, 4, 1), 15, 1219, 1100, 0, 0, 0, 0, 1100, 1.67, 1300, 0, 12, 1300, 1.98, -200, -0.15, -0.15],
    ["The Boardwalk", "E Renter", "BWK.S1   ", 550, "4654L165", dt.datetime(2026, 6, 6), 12, 1181, 900, 0, 0, 0, 0, 900, 1.64, 1000, 0, 12, 1000, 1.82, -100, -0.1, -0.1],
]

LISTINGS_ROWS = [
    [None],
    [None, "Unit-Level Data"],
    [None, "Property Name", "Address", "Floorplan Name", "Unit #", "Floor #", "Beds", "Baths", "Partial Baths", "Sqft", "First Listed", "Leased Date", "Active Listing?", "Days on Mkt", "Asking Rent", "Asking PSF", "Effective Rent", "Effective PSF"],
    [None, "The Boardwalk", "4637 Deleon Street, Fort Myers, FL 33907", "A1", "101", None, 1, 1, None, 657, dt.datetime(2026, 3, 1), dt.datetime(2026, 4, 10), False, 40, 1300, 1.98, 1300, 1.98],
    [None, "The Boardwalk", "4637 Deleon Street, Fort Myers, FL 33907", "A1", "102", None, 1, 1, None, 657, dt.datetime(2026, 5, 1), None, True, 60, 1200, 1.83, 1100, 1.67],
    [None, "The Ashlar", "1 Ashlar Way, Fort Myers, FL 33907", "B2", "201", None, 2, 2, None, 900, dt.datetime(2026, 2, 1), dt.datetime(2026, 5, 20), False, 108, 1800, 2.0, 1600, 1.78],
    [None, "The Ashlar", "1 Ashlar Way, Fort Myers, FL 33907", "B2", "202", None, 2, 2, None, 900, dt.datetime(2026, 2, 1), dt.datetime(2026, 6, 1), False, 120, 1600, 1.78, 1500, 1.67],
    [None, "The Ashlar", "1 Ashlar Way, Fort Myers, FL 33907", "B2", "203", None, 2, 2, None, 900, dt.datetime(2026, 6, 1), None, True, 30, 1700, 1.89, 1700, 1.89],
]

COMPS_ROWS = [
    [None],
    [None, "Rent Comps", None, None, None, None, None, None, None, None, None, None, "30-Day Avg Rents"],
    [None, "Property", "Address", "Similarity", "Dist. (mi)", "Quality", "Yr Built", "# Units", "Stories", "Avg Sqft", "Leased %", "Exposure %", "Studio", "1BR"],
    [None, "The Boardwalk", "4637 Deleon Street, Fort Myers, FL 33907", "--", "--", 0.68, 1973, 338, 2, 843.73, 0.9, 0.14, 1118.92, 1174.43],
    [None, "Comp Average", "--", 0.87, 1.9, 0.68, 1990.5, 298.2, 2.4, 911.27, 0.96, 0.06, None, 1222.11],
    [None, "The Ashlar", "1 Ashlar Way, Fort Myers, FL 33907", 0.93, 1.29, 0.68, 1998, 428, 2, 840.9, 0.94, 0.07, None, 1177.83],
]

COSTAR_ROWS = [
    ["Period", "Asset Value", "Vacancy Rate", "Market Asking Rent/Unit", "Annual Rent Growth", "Inventory Units", "Under Constr Units", "Under Constr % of Inventory", "12 Mo Absorp Units", "Market Sale Price/Unit", "12 Mo Sales Vol", "12 Mo Sales Vol Growth", "Market Cap Rate"],
    ["2026 Q3 QTD", 1669351601.81, 0.158960965, 1563.89, -0.0447, 9571, 0, 0, 449.6, 174417.68, 120625000, 6.94, 0.061],
    ["2026 Q2", 1666065327.07, 0.163390659, 1555.10427, -0.054240721, 9571, 0, 0, 406, 174074.32, 116325000, 6.66, 0.061],
    ["2026 Q1", 1664655603.69, 0.147119114, 1539.90268, -0.083991131, 9250, 321, 0.0347, 222, 173927.03, 119360000, 0.72, 0.061],
    ["2025 Q4", 1672689470.22, 0.151147114, 1543.05826, -0.07498583, 9250, 321, 0.0347, 350, 174766.43, 119360000, 0.7, 0.061],
]

RENT_CHART_ROWS = [
    ["The Boardwalk vs. HelloData Comp Set"],
    ["July 2025 – June 2026"],
    ["Rent chart only considers new leases"],
    [None],
    ["Month", "The Boardwalk / Lease Count", "The Boardwalk / Gross PSF", "The Boardwalk / Effective PSF", "Comp Set / Lease Count", "Comp Set / Gross PSF", "Comp Set / Effective PSF"],
    [dt.datetime(2025, 7, 1), 12, 1.83, 1.63, 42, 1.71, 1.5],
    [dt.datetime(2025, 8, 1), 18, 1.75, 1.58, 61, 1.62, 1.45],
    ["T12 Total / SF-Wtd", 30, 1.78, 1.6, 103, 1.66, 1.47],
    [None],
    ["Methodology"],
    ["Source: Yardi LTO report — 12-month+ term new leases."],
]

COSTAR_PDF_TEXT = """Multi-Family Submarket Report
Western Lee County
Fort Myers - FL USA
PREPARED BY
Megan Burrows
7/21/2026
© 2026 CoStar Group - Licensed to ZMR Capital - 473560
\fOverview
Western Lee County Multi-Family
12 Mo Delivered Units    12 Mo Absorption Units    Vacancy Rate    12 Mo Asking Rent Growth
674    449    15.9%    -4.4%
KEY INDICATORS
Current Quarter    Units    Vacancy Rate    Asking Rent    Effective Rent    Absorption    Delivered Units    Under Constr
Submarket    9,571    15.9%    $1,564    $1,399    42    0    0
Annual Trends    12 Month    Historical    Forecast    Peak    When    Trough    When
Vacancy    1.3% (YOY)    8.2%    11.9%    16.3%    2026 Q2    4.2%    2015 Q1
Asking Rent Growth    -4.4%    2.2%    1.4%    16.0%    2021 Q4    -8.4%    2026 Q1
\fConstruction
RECENT DELIVERIES
Property Name/Address    Rating    Units    Stories    Start    Complete    Developer/Owner
Montage at Midtown    Catalyst Capital Management
1    321    4    Apr 2024    Jun 2026
2330 Union St
\fSales Past 12 Months
RECENT SIGNIFICANT SALES
Property Name/Address    Rating    Yr Built    Units    Vacancy    Sale Date    Price    Price/Unit    Price/SF
West End at City Walk
1    -    2021    319    21.0%    10/29/2025    $71,550,000    $224,294    $287
2250 McGregor Blvd
The Boardwalk
2    -    1973    338    5.9%    7/30/2025    $38,100,000    $112,721    $129
4637 Deleon St
"""

CAPITAL_CALLS_TEXT = """Back to Entities
The Boardwalk Owner, LLC (Slate)    Active
Asset SPV
Transactions
Capital Calls    New Capital Call
Distributions
0 records
Total Called    $0    0%    Callable Capital    $0
Title    Due Date    From    To    Total Called    Contributed    Progress
No Capital Calls Yet
"""

DISTRIBUTIONS_TEXT = """Back to Entities
The Boardwalk Owner, LLC (Slate)    Active
Transactions
Distributions    New Distribution
0 records
Gross Amount    Net Amount
Title    Period    Date    Classes    From    To    Settled
No Distributions Yet
"""

HELLODATA_PDF_TEXT = """The Boardwalk
ZMR Capital
4/1/2026 - 6/30/2026
Rents by Unit Type
# Leased    # Active    Days on Mkt    Min SF    Avg SF    Max SF    Min Rent    Avg Rent    Max Rent    Avg PSF    NER    NER PSF    Concession %    Trend
The Boardwalk    34    45    52    500    841    1,130    $995    $1,314    $1,662    $1.56    $1,178    $1.40    10.4%    +23.9%
Westchase    0    3    328    702    945    1,143    $1,078    $1,289    $1,496    $1.36    $1,289    $1.36    0.0%    +2.2%
Comp Average    105    673    859    1,132    $1,124    $1,368    $1,728    $1.59    $1,172    $1.36    14.0%
"""
