#!/usr/bin/env python3
"""Build the Riverbend Station 4Q25 source package: three workbooks with unfamiliar names and shuffled sheets,
two Slate-style PDFs printed by Chromium, and a deterministic property photo. Pure Python: openpyxl, Playwright,
Pillow. The expected values in expected.json are written by hand from the figures below, not exported from here.

Run from the repository root with the backend virtualenv:  backend/.venv/bin/python validation/real_world/build_riverbend.py
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import openpyxl
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OUT = HERE / "scenarios" / "riverbend_station_4q25" / "sources"

NAME, CODE = "Riverbend Station", "64008"
ADDRESS = "2450 Riverbend Drive, Denver, CO 80216"
TYPES = [  # label, code, units, occupied now, occupied prior, sqft, market rent, resident rent now (prior = now - 30)
    ("0 Bedroom 1 Bathroom", "RB.S1", 28, 26, 25, 560, 1395, 1340),
    ("1 Bedroom 1 Bathroom", "RB.A1", 96, 90, 88, 720, 1620, 1555),
    ("2 Bedroom 2 Bathroom", "RB.B2", 84, 78, 77, 1015, 2010, 1930),
    ("3 Bedroom 2 Bathroom", "RB.C2", 20, 18, 17, 1230, 2380, 2265),
]
UNITS = sum(t[2] for t in TYPES)            # 228
OCC_NOW = sum(t[3] for t in TYPES)          # 212
OCC_PRIOR = sum(t[4] for t in TYPES)        # 207


def fin_row(code, label, a, b, ytd=4):
    """PTD actual/budget, variance, % var, YTD (four quarters of the same run rate), annual budget."""
    var = a - b
    pct = round(var / abs(b) * 100, 2) if b else "N/A"
    return [code, label, a, b, var, pct, a * ytd, b * ytd, var * ytd, pct, b * 4]


def budget_rows():
    r = fin_row
    return [
        [f"Property =  {CODE} {CODE}con"], ["Budget Comparison"], ["Period = Oct 2025-Dec 2025"], ["Book = Accrual ; Tree = rp-cashflow"],
        [None, None, " PTD Actual ", " PTD Budget ", " Variance ", " % Var ", " YTD Actual ", " YTD Budget ", " Variance ", " % Var ", " Annual "],
        ["3998-0000", "    REVENUE"], ["3999-0000", "      Rental Income"],
        r("4000-0000", "        Gross Potential Rent", 1262000, 1240000), r("4001-0000", "        Loss/Gain to Lease", 38000, 45000),
        r("4004-0000", "        Less:Concessions", -21000, -18000), r("4006-0000", "        Less:  Vacancy", -88000, -95000),
        r("4016-0000", "        Pet Rent", 6500, 6000), r("4060-0000", "        NET RENTAL INCOME", 1197500, 1178000),
        ["4080-9999", "  UTILITY INCOME"], r("4081-0005", "        Water Income", 118000, 112000), r("4081-0100", "        TOTAL UTILITY INCOME", 118000, 112000),
        ["4400-0000", "  OTHER INCOME"], r("4407-0050", "        Less:Write Off Bad Debt", -9000, -7000), r("4407-0055", "        Former Resident Collections", 4000, 3000),
        r("4407-0060", "        Fee Income", 44500, 45000), r("4699-0000", "        TOTAL OTHER INCOME", 39500, 41000),
        r("4999-0000", "            TOTAL REVENUE", 1355000, 1331000),
        ["5000-0000", "    EXPENSES"], ["5019-0000", "  PAYROLL"], r("5020-0000", "        Manager Salaries", 172000, 168000), r("5055-0000", "          TOTAL PAYROLL", 172000, 168000),
        ["5056-0000", "  GENERAL & ADMINISTRATIVE"], r("5056-1000", "          TOTAL GENERAL & ADMINISTRATIVE", 41000, 38500),
        ["5095-0000", "  MARKETING"], r("5108-0000", "          TOTAL MARKETING", 24000, 26000),
        ["5200-0000", "  REPAIRS & MAINTENANCE"], r("5215-0000", "          TOTAL REPAIRS & MAINTENANCE", 58000, 52000),
        ["5299-0000", "  UTILITIES"], r("5310-0000", "        Water & Wastewater", 176000, 170000), r("5399-0000", "          TOTAL UTILITIES", 176000, 170000),
        ["5460-0000", "  MANAGEMENT FEES"], r("5465-0000", "          TOTAL MANAGEMENT FEES", 40650, 39930),
        ["5499-0000", "  TAXES"], r("5500-0000", "        Property Taxes", 158000, 158000), r("5515-0000", "          TOTAL TAXES", 158000, 158000),
        ["5519-9999", "  INSURANCE"], r("5520-0000", "        Insurance", 72000, 86000), r("5520-0010", "          TOTAL INSURANCE", 72000, 86000),
        r("6500-0000", "            TOTAL EXPENSES", 741650, 738430), r("6700-0000", "            NET OPERATING INCOME/(LOSS)", 613350, 592570),
        ["6800-0000", "  DEBT SERVICE"], r("6801-0000", "        Interest Expense-1st Lien", 404550, 404550), r("6810-0000", "          TOTAL DEBT SERVICE", 404550, 404550),
        r("7000-0000", "            NET INCOME/(LOSS) AFTER DS", 208800, 188020),
        [None, "    INTERIOR RENOVATIONS"],
        r("7100-0016", "        Plumbing Replacement", 27500, 30000), r("7100-0020", "        HVAC Additions", 19000, 22000),
        r("7100-0009", "        Paint", 12500, 10000), r("7100-0011", "        Flooring - Carpet & Vinyl", 15000, 12000),
        r(None, "          TOTAL INTERIOR RENOVATIONS", 74000, 74000),
        [None, "    EXTERIOR RENOVATIONS"],
        r("7200-0002", "        Roof", 0, 15000), r("7200-0031", "        Landscape Additions", 8000, 9000),
        r(None, "          TOTAL EXTERIOR RENOVATIONS", 8000, 24000),
        [None, None, 82000, 98000, None, None, 328000, 392000],
    ]


def balance_rows():
    return [
        [f"Property =  {CODE} {CODE}con"], ["Balance Sheet (With Period Change)"], ["Period = Oct 2025-Dec 2025"], ["Book = Accrual ; Tree = ysi_bs"],
        [None, None, "Balance", "Beginning", "Net"], [None, None, "Current Period", "Balance", "Change"],
        ["0999-0000", "                                         ASSETS"],
        ["1000-0100", "        Cash - Operating", 512400.5, 488210.25, 24190.25],
        ["1250-0000", "        Capital Improvements Escrow", 265000, 250000, 15000],
        ["1500-0000", "        Land", 6200000, 6200000, 0], ["1500-0021", "        Building", 34300000, 34300000, 0],
        ["1500-0029", "          Total Building", 40500000, 40500000, 0],
        ["1500-0041", "        Furniture, Fixtures & Equipment", 500000, 500000, 0], ["1500-0049", "          Total Furniture & Fixtures", 500000, 500000, 0],
        ["1995-0000", "                   TOTAL ASSETS", 41777400.5, 41738210.25, 39190.25],
        ["1997-0000", "     LIABILITIES"], ["2139-0001", "        Accrued Interest", 134850, 134850, 0],
        ["2310-0000", "        Mortgage Payable", 31000000, 31000000, 0], ["2310-0020", "          TOTAL MORTGAGE PAYABLE", 31000000, 31000000, 0],
        ["2999-0000", "     EQUITY"], ["3015-0000", "        Owner Contributions", 12900000, 12550000, 350000],
        ["3994-0000", "              TOTAL EQUITY", 10642550.5, 10603360.25, 39190.25],
    ]


def rent_roll_rows(as_of: str, occupied: int, future: int):
    pct = occupied / UNITS * 100
    market = sum(t[2] * t[6] for t in TYPES)
    actual = sum(t[3 if occupied == OCC_NOW else 4] * (t[7] if occupied == OCC_NOW else t[7] - 30) for t in TYPES)
    sqft = sum(t[2] * t[5] for t in TYPES)
    return [
        ["Rent Roll"], [f"{NAME} ({CODE})"], [f"As Of = {as_of}"], [None],
        ["Property", "State", "Total", "Name", "Market", "Resident", "Deposit", "Average", "Average", "Average", "Balance"],
        [None, None, "Units", None, "Rent", "Rent", None, "Market", "Resident", "Deposit"], [None, None, None, None, None, None, None, "Rent", "Rent"],
        [CODE, "CO", UNITS, NAME, market, actual, 118500, round(market / UNITS, 2), round(actual / occupied, 2), 519.74, -21870.4],
        [None, None, UNITS, "Total", market, actual, 118500, round(market / UNITS, 2), round(actual / occupied, 2), 519.74, -21870.4],
        [None],
        ["Summary Groups", None, "Square", "Market", "Actual", "Security", "Other", "# Of", "% Unit", "% Sqft", "Balance"],
        [None, None, "Footage", "Rent", "Rent", "Deposit", "Deposits", "Units", "Occupancy", "Occupied"],
        ["Current/Notice/Vacant Residents", None, sqft, market, actual, 118500, -500, UNITS, pct, pct, -20100.15],
        ["Future Residents/Applicants", None, future * 720, future * 1620, 0, 0, 0, future, None, None, -1770.25],
        ["Occupied Units", None, occupied * 812, round(market * occupied / UNITS), None, None, None, occupied, pct, pct],
        ["Total Non Rev Units", None, 0, 0, None, None, None, 0, 0, 0],
        ["Total Vacant Units", None, (UNITS - occupied) * 812, round(market * (UNITS - occupied) / UNITS), None, None, None, UNITS - occupied, 100 - pct, 100 - pct],
        ["Totals:", None, sqft, market, actual, 118500, -500, UNITS, 100, 100, -21870.4],
    ]


def schedule_rows(as_of: str, prior: bool):
    rows = [["Market Rent Schedule"], [f"{NAME} ({CODE})"], [f"As Of = {as_of}"],
            ["Unit Type", "Units", "Unit Type", "Unit Type", "Total", "Total Unit", "Average", "Occupied", "Average"],
            [None, None, "Rent", "Sq Ft", "Unit Type", "Rent", "Unit Rent", "Units", "Resident Rent"], [None, None, None, None, "Rent"]]
    tot_units = tot_occ = tot_rent = wr = ws = 0
    for label, code, units, occ_now, occ_prior, sqft, market, resident in TYPES:
        occ = occ_prior if prior else occ_now
        res = resident - 30 if prior else resident
        rows.append([f"{label} ({code})", units, market, sqft, units * market, units * market, market, occ, res])
        tot_units += units; tot_occ += occ; tot_rent += units * market; wr += occ * res; ws += units * sqft
    rows.append(["Grand Total", tot_units, round(tot_rent / tot_units, 2), round(ws / tot_units, 2), tot_rent, tot_rent, round(tot_rent / tot_units, 2), tot_occ, round(wr / tot_occ, 2)])
    return rows


LTO = {  # kind, unit type, sqft, unit, date, market, current, prior
    "renewals": [("RB.A1", 720, "R-118", dt.datetime(2025, 10, 12), 1620, 1575, 1540), ("RB.B2", 1015, "R-231", dt.datetime(2025, 11, 3), 2010, 1950, 1905),
                 ("RB.S1", 560, "R-014", dt.datetime(2025, 12, 1), 1395, 1355, 1330)],
    "move_ins": [("RB.A1", 720, "R-127", dt.datetime(2025, 10, 20), 1620, 1540, 1580), ("RB.A1", 720, "R-142", dt.datetime(2025, 11, 18), 1620, 1560, 1600),
                 ("RB.B2", 1015, "R-244", dt.datetime(2025, 12, 5), 2010, 1890, 1940), ("RB.C2", 1230, "R-309", dt.datetime(2025, 12, 19), 2380, 2250, 2300)],
}


def lto_rows():
    group = [None, None, None, None, None, "New Lease Term", None, None, None, None, None, None, None, None, None, "Previous Lease Term"]
    header = [None, "Resident Name", "Unit Type", "Sqft", "Unit", "Renewal Start", "Lease Term", "Market Rent", "Lease Rent", "Up-Front Concessions", "Total Recurring Concessions",
              "Total Concessions", "# Months Free", "Effective Rent", "EFF Rent PSF", "Lease Rent", "Total Concessions", "Lease Term", "Effective Rent", "Eff Rent PSF", "Rent Change", "% Change", "Eff Rent % Change"]
    move_header = list(header); move_header[5] = "Lease Start"

    def rec(i, kind, r):
        ut, sqft, unit, date, market, cur, prior = r
        return [NAME, f"Resident {kind[0].upper()}{i}", ut + "   ", sqft, unit, date, 12, market, cur, 0, 0, 0, 0, cur, round(cur / sqft, 2), prior, 0, 12, prior, round(prior / sqft, 2), cur - prior, round((cur - prior) / prior, 4), round((cur - prior) / prior, 4)]

    rows = [[None, "Lease Renewals"], [None, "Leases Expiring between 2025-10-01 and 2025-12-31"], [None], group, header]
    rows += [rec(i, "renewals", r) for i, r in enumerate(LTO["renewals"], 1)]
    rows += [[None, "Averages for Riverbend Station"], [None], [None, "Move Ins"], [None, "Move In between 2025-10-01 and 2025-12-31"], [None], group, move_header]
    rows += [rec(i, "move_ins", r) for i, r in enumerate(LTO["move_ins"], 1)]
    return rows


LISTINGS = {  # name, address, listings (plan, unit, beds, baths, sqft, first listed, leased date, active, dom, asking, effective)
    NAME: (ADDRESS, [("A1", "127", 1, 1, 720, dt.datetime(2025, 9, 20), dt.datetime(2025, 10, 20), False, 30, 1650, 1580),
                     ("B2", "244", 2, 2, 1015, dt.datetime(2025, 11, 10), dt.datetime(2025, 12, 5), False, 25, 2040, 1960),
                     ("S1", "021", 0, 1, 560, dt.datetime(2025, 12, 1), None, True, 30, 1420, 1420)]),
    "Platte Street Lofts": ("1600 Platte Street, Denver, CO 80202", [("L1", "402", 1, 1, 745, dt.datetime(2025, 10, 2), dt.datetime(2025, 10, 28), False, 26, 1795, 1720),
                                                                      ("L2", "518", 2, 2, 1040, dt.datetime(2025, 11, 6), dt.datetime(2025, 12, 12), False, 36, 2180, 2100)]),
    "Union Yard Flats": ("3100 Brighton Boulevard, Denver, CO 80216", [("U1", "210", 1, 1, 700, dt.datetime(2025, 10, 15), dt.datetime(2025, 11, 20), False, 36, 1690, 1640),
                                                                       ("U1", "315", 1, 1, 700, dt.datetime(2025, 12, 8), None, True, 23, 1760, 1690)]),
}


def listings_rows():
    rows = [[None], [None, "Unit-Level Data"],
            [None, "Property Name", "Address", "Floorplan Name", "Unit #", "Floor #", "Beds", "Baths", "Partial Baths", "Sqft", "First Listed", "Leased Date", "Active Listing?", "Days on Mkt", "Asking Rent", "Asking PSF", "Effective Rent", "Effective PSF"]]
    for name, (addr, items) in LISTINGS.items():
        for plan, unit, beds, baths, sqft, listed, leased, active, dom, ask, eff in items:
            rows.append([None, name, addr, plan, unit, None, beds, baths, None, sqft, listed, leased, active, dom, ask, round(ask / sqft, 2), eff, round(eff / sqft, 2)])
    return rows


COMPS = [(NAME, ADDRESS, "--", "--", 0.7, 1997, 228, 3, 812, 0.93, 0.07), ("Platte Street Lofts", "1600 Platte Street, Denver, CO 80202", 0.9, 1.8, 0.8, 2008, 312, 5, 845, 0.955, 0.05),
         ("Union Yard Flats", "3100 Brighton Boulevard, Denver, CO 80216", 0.87, 0.9, 0.7, 2001, 204, 3, 790, 0.925, 0.08),
         ("Brighton Walk", "3600 Brighton Boulevard, Denver, CO 80216", 0.83, 1.2, 0.75, 2015, 176, 4, 860, 0.94, 0.06)]


def comps_rows():
    return [[None], [None, "Rent Comps", None, None, None, None, None, None, None, None, None, None, "30-Day Avg Rents"],
            [None, "Property", "Address", "Similarity", "Dist. (mi)", "Quality", "Yr Built", "# Units", "Stories", "Avg Sqft", "Leased %", "Exposure %", "Studio", "1BR"],
            *[[None, *c, None, None] for c in COMPS], [None, "Comp Average", "--", 0.87, 1.3, 0.75, 2008, 230.7, 4, 831.7, 0.94, 0.063, None, None]]


COSTAR = [["Period", "Asset Value", "Vacancy Rate", "Market Asking Rent/Unit", "Annual Rent Growth", "Inventory Units", "Under Constr Units", "Under Constr % of Inventory", "12 Mo Absorp Units", "Market Sale Price/Unit", "12 Mo Sales Vol", "12 Mo Sales Vol Growth", "Market Cap Rate"],
          ["2026 Q1 QTD", 4212000000, 0.072, 1861.5, 0.019, 24640, 610, 0.0248, 320, 236000, 402000000, 4.1, 0.052],
          ["2025 Q4", 4198000000, 0.074, 1855, 0.021, 24600, 640, 0.026, 310, 234500, 398000000, 3.8, 0.052],
          ["2025 Q3", 4150000000, 0.078, 1842, 0.018, 24410, 700, 0.0287, 285, 231000, 371000000, 2.2, 0.053],
          ["2025 Q2", 4110000000, 0.081, 1830, 0.015, 24300, 760, 0.0313, 260, 229000, 355000000, 1.5, 0.054]]


def chart_rows():
    rows = [[f"{NAME} vs. Denver Comp Set"], ["January 2025 - December 2025"], ["Rent chart only considers new leases"], [None],
            ["Month", f"{NAME} / Lease Count", f"{NAME} / Gross PSF", f"{NAME} / Effective PSF", "Denver Comp Set / Lease Count", "Denver Comp Set / Gross PSF", "Denver Comp Set / Effective PSF"]]
    for m in range(12):
        rows.append([dt.datetime(2025, m + 1, 1), 5 + (m % 4), round(2.05 + 0.012 * m, 4), round(1.96 + 0.011 * m, 4), 14 + (m % 5), round(2.18 + 0.009 * m, 4), round(2.09 + 0.008 * m, 4)])
    rows += [["T12 Total / SF-Wtd", 66, 2.12, 2.02, 190, 2.23, 2.13], [None], ["Methodology"], ["Source: Yardi LTO report; 12-month+ term new leases; HelloData leased listings for the comp set."]]
    return rows


def save(path: Path, sheets: dict[str, list[list]]) -> None:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def print_pdf(path: Path, title: str, lines: list[str]) -> None:
    from playwright.sync_api import sync_playwright

    body = "".join(f"<p style='font-family:Menlo,monospace;font-size:11pt;margin:0 0 6pt'>{line}</p>" for line in lines)
    html = f"<html><head><title>{title}</title></head><body style='padding:40px'><h2 style='font-family:Helvetica'>{title}</h2>{body}</body></html>"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html)
            page.pdf(path=str(path), format="Letter")
        finally:
            browser.close()


def photo(path: Path) -> None:
    img = Image.new("RGB", (960, 540), (52, 92, 130))
    d = ImageDraw.Draw(img)
    for i, color in enumerate(((78, 118, 156), (108, 142, 176), (188, 170, 130))):
        d.rectangle((60 + i * 280, 200 + i * 40, 300 + i * 280, 480), fill=color)
    d.rectangle((0, 470, 960, 540), fill=(60, 110, 70))
    d.text((40, 30), "Riverbend Station validation photo", fill=(255, 255, 255))
    img.save(path, "PNG")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    save(OUT / "FY25-Q4 ops bundle (rev2).xlsx", {
        "Notes": [["Prepared for the quarterly package"], ["Internal use", "n/a", 42]],
        "Unit Mix Dec": schedule_rows("12/31/2025", prior=False),
        "P&L Q4": budget_rows(),
        "Rent Roll Dec": rent_roll_rows("12/31/2025", OCC_NOW, 6),
        "Unit Mix Sep": schedule_rows("09/30/2025", prior=True),
        "Rent Roll Sep": rent_roll_rows("09/30/2025", OCC_PRIOR, 9),
    })
    save(OUT / "bal+leasing_export.xlsx", {"Trade-Outs": lto_rows(), "Balance Sheet": balance_rows(), "Junk Sheet": [["hello"], ["world", 1]]})
    save(OUT / "market data 12-2025.xlsx", {"Rent Chart": chart_rows(), "Comps": comps_rows(), "Listings": listings_rows(), "CoStar": COSTAR})
    print_pdf(OUT / "slate-cc-2025-12.pdf", "Capital Calls", [
        "Back to Entities", f"{NAME} Owner, LLC (Slate)    Active", "Asset SPV", "Transactions", "Capital Calls    New Capital Call", "1 record",
        "Total Called    $12,900,000.00    100%    Callable Capital    $0", "Title    Due Date    From    To    Total Called    Contributed    Progress",
        "4Q25 Capital Improvements    11/10/2025    Settled    $350,000.00    $350,000.00    100%"])
    print_pdf(OUT / "slate-dist-2025-12.pdf", "Distributions", [
        "Back to Entities", f"{NAME} Owner, LLC (Slate)    Active", "Transactions", "Distributions    New Distribution", "1 record",
        "Gross Amount    Net Amount", "Title    Period    Date    Classes    From    To    Settled",
        "4Q25 Operating Distribution    12/15/2025    Settled    $180,000.00    $180,000.00"])
    photo(OUT / "riverbend-photo.png")
    print("wrote", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
