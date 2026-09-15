# backend/tests/test_extract_costar.py
from app.classify.classifier import DocType
from app.extract.costar_excel import extract as extract_excel
from app.extract.costar_pdf import extract as extract_pdf, parse_costar_text
from tests.helpers import COSTAR_PDF_TEXT, COSTAR_ROWS, pdf_part, sheet_part


def test_costar_excel_series():
    d = extract_excel(sheet_part(COSTAR_ROWS, DocType.COSTAR_SUBMARKET_EXCEL)).data
    s = d["series"]
    assert [x["period"] for x in s] == ["2026 Q3 QTD", "2026 Q2", "2026 Q1", "2025 Q4"]
    q2 = s[1]
    assert (q2["year"], q2["quarter"], q2["flag"]) == (2026, 2, "") and s[0]["flag"] == "QTD"
    assert abs(q2["vacancy"] - 0.16339) < 1e-4 and abs(q2["asking_rent"] - 1555.1) < 0.01
    assert abs(q2["rent_growth"] + 0.05424) < 1e-4 and q2["under_construction"] == 0 and q2["uc_pct"] == 0
    assert q2["absorption_12m"] == 406 and q2["row"] == 2 and abs(q2["cap_rate"] - 0.061) < 1e-9


def test_costar_pdf_parsing():
    d = parse_costar_text(COSTAR_PDF_TEXT.split("\f"))
    assert d["submarket"] == "Western Lee County" and d["market"] == "Fort Myers" and d["state"] == "FL"
    assert d["report_date"] == "2026-07-21" and d["licensed_to"] == "ZMR Capital"
    assert d["overview"] == {"delivered_12m": 674, "absorption_12m": 449, "vacancy": 0.159, "rent_growth_12m": -0.044}
    assert d["key_stats"]["inventory"] == 9571 and d["key_stats"]["asking_rent"] == 1564 and d["key_stats"]["under_construction"] == 0
    assert d["trends"]["vacancy"]["peak"] == 0.163 and d["trends"]["vacancy"]["peak_when"] == "2026 Q2"
    assert d["trends"]["asking_rent_growth"]["trough"] == -0.084
    sale = d["sales"][1]
    assert sale["name"] == "The Boardwalk" and sale["year_built"] == 1973 and sale["units"] == 338
    assert sale["sale_date"] == "2025-07-30" and sale["price"] == 38100000 and sale["price_per_unit"] == 112721
    assert d["deliveries"][0] == {"name": "Montage at Midtown", "units": 321, "stories": 4, "start": "Apr 2024", "complete": "Jun 2026", "page": 3}
    ex = extract_pdf(pdf_part(COSTAR_PDF_TEXT, DocType.COSTAR_SUBMARKET_PDF))
    assert ex.data["submarket"] == "Western Lee County"


def test_construction_rows_keep_their_headings_across_pages():
    pages = [
        "\n".join([
            "Construction", "RECENT DELIVERIES", "Property Name/Address Rating Units Stories Start Complete",
            "Completed Community", "1 100 2 Jan 2025 May 2026",
            "UNDER CONSTRUCTION", "Building Community Jan 2027", "1 200 3 Feb 2025",
        ]),
        "\n".join([
            "Construction", "Another Building Community Feb 2027", "2 150 2 Mar 2025",
            "PROPOSED", "Planned Community", "1 105 1 Sep 2026 Sep 2027",
        ]),
        "\n".join(["Sales Past 12 Months", "Unclassified Community", "1 90 2 Jan 2025 May 2026"]),
    ]

    data = parse_costar_text(pages)

    assert [project["name"] for project in data["deliveries"]] == ["Completed Community"]
    assert [(project["name"], project["category"], project["page"])
            for project in data["construction_projects"]] == [
                ("Completed Community", "recent_deliveries", 1),
                ("Building Community", "under_construction", 1),
                ("Another Building Community", "under_construction", 2),
                ("Planned Community", "proposed", 2),
            ]
    assert data["construction_projects"][1]["complete"] == "Jan 2027"
