# backend/tests/test_builder.py
from app.classify.classifier import DocType
from app.consolidate.builder import _comp_entries, apply_overrides, build
from app.consolidate.select import Selection, Src
from app.extract.registry import run_extractor
from tests.helpers import (BALANCE_ROWS, BUDGET_ROWS, CAPITAL_CALLS_TEXT, COMPS_ROWS, COSTAR_PDF_TEXT, COSTAR_ROWS,
                           DISTRIBUTIONS_TEXT, LISTINGS_ROWS, LTO_ROWS, RENT_CHART_ROWS, pdf_part, rent_roll_rows,
                           schedule_rows, sheet_part)

JUN = {"BWK.A1": 1172.47, "BWK.B0": 1331.04, "BWK.B1": 1370.84, "BWK.S1": 1108.31, "TOTAL": 1250.5}
MAR = {"BWK.A1": 1205.1, "BWK.B0": 1357.95, "BWK.B1": 1356.5, "BWK.S1": 1099.72, "TOTAL": 1346.33}


def file_of(fid: str, filename: str, *parts) -> dict:
    exs = [run_extractor(p).model_dump() for p in parts]
    return {"id": fid, "original_filename": filename, "status": "processed", "ignored": False,
            "parts": [{"doc_type": p.doc_type} for p in parts], "extractions": exs}


def sample_files() -> list[dict]:
    return [
        file_of("f1", "financials.xlsx", sheet_part(BUDGET_ROWS, DocType.YARDI_BUDGET_COMPARISON, file_id="f1", filename="financials.xlsx")),
        file_of("f2", "bs.xlsx", sheet_part(BALANCE_ROWS, DocType.YARDI_BALANCE_SHEET, file_id="f2", filename="bs.xlsx")),
        file_of("f3", "rr-jun.xlsx", sheet_part(rent_roll_rows("06/30/2026", 306, 338, 90.53, 14), DocType.YARDI_RENT_ROLL, file_id="f3", filename="rr-jun.xlsx")),
        file_of("f4", "rr-mar.xlsx", sheet_part(rent_roll_rows("03/31/2026", 310, 338, 91.71, 34), DocType.YARDI_RENT_ROLL, file_id="f4", filename="rr-mar.xlsx")),
        file_of("f5", "sch-jun.xlsx", sheet_part(schedule_rows("06/30/2026", JUN), DocType.YARDI_MARKET_RENT_SCHEDULE, file_id="f5", filename="sch-jun.xlsx")),
        file_of("f6", "sch-mar.xlsx", sheet_part(schedule_rows("03/31/2026", MAR), DocType.YARDI_MARKET_RENT_SCHEDULE, file_id="f6", filename="sch-mar.xlsx")),
        file_of("f7", "lto.xlsx", sheet_part(LTO_ROWS, DocType.YARDI_LEASE_TRADE_OUT, file_id="f7", filename="lto.xlsx")),
        file_of("f8", "listings.xlsx", sheet_part(LISTINGS_ROWS, DocType.HELLODATA_LISTINGS, file_id="f8", filename="listings.xlsx")),
        file_of("f9", "comps.xlsx", sheet_part(COMPS_ROWS, DocType.HELLODATA_COMPS, file_id="f9", filename="comps.xlsx")),
        file_of("f10", "costar.xlsx", sheet_part(COSTAR_ROWS, DocType.COSTAR_SUBMARKET_EXCEL, file_id="f10", filename="costar.xlsx")),
        file_of("f11", "costar.pdf", pdf_part(COSTAR_PDF_TEXT, DocType.COSTAR_SUBMARKET_PDF, file_id="f11", filename="costar.pdf")),
        file_of("f12", "chart.xlsx", sheet_part(RENT_CHART_ROWS, DocType.RENT_CHART, file_id="f12", filename="chart.xlsx")),
        file_of("f13", "calls.pdf", pdf_part(CAPITAL_CALLS_TEXT, DocType.SLATE_CAPITAL_CALLS, file_id="f13", filename="calls.pdf")),
        file_of("f14", "dists.pdf", pdf_part(DISTRIBUTIONS_TEXT, DocType.SLATE_DISTRIBUTIONS, file_id="f14", filename="dists.pdf")),
    ]


def test_build_end_to_end():
    data, notes = build({"id": "p1", "name": "Boardwalk"}, sample_files())
    v = data.value
    assert data.meta["period"]["quarter_label"] == "2Q26" and not [n for n in notes if n["severity"] == "error"]
    # property
    assert v("property.fields.name") == "The Boardwalk" and v("property.fields.units") == 338
    assert v("property.fields.year_built") == 1973 and v("property.fields.acquired_date") == "2025-07-30"
    assert v("property.fields.address") == "4637 Deleon Street" and v("property.fields.city_state") == "Fort Myers, FL"
    assert v("property.fields.zip") == "33907" and v("property.fields.submarket") == "Western Lee County"
    assert v("property.fields.prepared_by") == "ZMR Capital" and v("property.fields.avg_unit_sf") == 760
    assert v("property.fields.quarter_label") == "2Q26" and data.field("property.fields.site_acres").status == "missing"
    assert v("property.fields.description") == (
        "The Boardwalk is a 338-unit multifamily community located in Fort Myers, FL. "
        "The property was built in 1973 and acquired in July 2025."
    )
    assert data.field("property.fields.description").status == "derived"
    assert data.field("property.fields.name").source.filename == "rr-jun.xlsx"
    # capital
    pp = data.field("capital.fields.purchase_price")
    assert pp.value == 48000000 and pp.status == "conflict" and pp.alternatives[0].value == 38100000
    assert v("capital.fields.equity_invested") == 14259605.94 and v("capital.fields.quarter_contributions") == 0.0
    assert v("capital.fields.distributions_itd") == 0.0 and abs(v("capital.fields.price_per_unit") - 48000000 / 338) < 1e-6
    assert v("capital.fields.contributions_note") == "No capital called this quarter"
    # financing
    assert v("financing.fields.loan_amount") == 36519000 and v("financing.fields.interest_monthly") == 159161.98
    assert data.field("financing.fields.interest_monthly").status == "inferred"
    assert abs(v("financing.fields.implied_rate") - 0.0523) < 1e-4 and v("financing.fields.borrower") == "The Boardwalk Owner, LLC"
    assert data.field("financing.fields.lender").status == "missing"
    # financials
    fin = "financials.tables.lines.rows"
    assert v(f"{fin}.total_revenue.ptd_actual") == 1000 and v(f"{fin}.total_revenue.ptd_var") == 46
    assert v(f"{fin}.payroll.ptd_var") == -10 and v(f"{fin}.concessions.ptd_actual") == -50
    assert v(f"{fin}.net_cash_flow.ptd_var") == 36 and v(f"{fin}.property_taxes.ptd_actual") == 100
    assert v(f"{fin}.debt_service.ptd_actual") == 300 and v(f"{fin}.total_opex.ytd_actual") == 900
    assert data.field(f"{fin}.gpr.ptd_actual").source.locator == "sheet 'Report1' rows 8"
    # capex
    cap = "capex.tables.lines"
    assert set(data.table(cap).rows) == {"plumbing_water_heaters", "paint", "roof"}
    assert v(f"{cap}.rows.plumbing_water_heaters.ptd_actual") == 33 and v(f"{cap}.rows.plumbing_water_heaters.ytd_budget") == 31
    assert v(f"{cap}.totals.ptd_actual") == 61 and v(f"{cap}.totals.ytd_actual") == 98 and v("capex.fields.source_total_ptd") == 61
    assert v("commentary.fields.capex_var") == -29
    # in-place rent
    ipr = "in_place_rent.tables.by_floor_plan"
    assert list(data.table(ipr).rows) == ["0br", "1br", "2br"]
    assert v(f"{ipr}.rows.1br.current_rent") == 1172.47 and v(f"{ipr}.rows.1br.prior_rent") == 1205.1
    assert abs(v(f"{ipr}.rows.2br.current_rent") - 1342.497) < 0.01 and v(f"{ipr}.rows.2br.units") == 76
    assert abs(v(f"{ipr}.rows.1br.variance") + 32.63) < 1e-6 and v(f"{ipr}.rows.2br.type") == "2 BR · 1-2 BA"
    assert v(f"{ipr}.totals.current_rent") == 1250.5 and v(f"{ipr}.totals.units") == 139
    # occupancy and trade-out
    assert abs(v("occupancy.fields.current_pct") - 0.9053) < 1e-9 and abs(v("occupancy.fields.prior_pct") - 0.9171) < 1e-9
    assert v("occupancy.fields.change_bps") == -118 and v("occupancy.fields.future_applicants") == 14
    nl = "occupancy.tables.new_leases"
    assert list(data.table(nl).rows) == ["bwk-s1", "bwk-a1"]
    assert v(f"{nl}.rows.bwk-a1.count") == 2 and v(f"{nl}.rows.bwk-a1.avg_prior") == 1250 and v(f"{nl}.rows.bwk-a1.lto") == -200
    assert v(f"{nl}.totals.count") == 3 and v("occupancy.fields.new_lease_count") == 3 and v("occupancy.fields.renewal_count") == 2
    assert v("occupancy.tables.renewals.rows.bwk-a1.avg_current") == 1425
    # submarket
    assert abs(v("submarket.fields.vacancy") - 0.16339) < 1e-4 and abs(v("submarket.fields.prior_vacancy") - 0.14712) < 1e-4
    assert abs(v("submarket.fields.rent_growth_yoy") + 0.05424) < 1e-4 and v("submarket.fields.under_construction") == 0
    assert v("submarket.fields.submarket_name") == "Western Lee County"
    comps = "submarket.tables.comps"
    assert list(data.table(comps).rows) == ["the-boardwalk", "the-ashlar"]
    assert data.table(comps).row_meta["the-boardwalk"]["subject"] is True
    assert abs(v(f"{comps}.rows.the-boardwalk.leased_pct") - 0.9053) < 1e-9 and v(f"{comps}.rows.the-boardwalk.units") == 338
    assert v(f"{comps}.rows.the-ashlar.asking_rent") == 1700 and v(f"{comps}.rows.the-ashlar.concession") == 100
    assert abs(v(f"{comps}.rows.the-ashlar.leased_pct") - 2 / 3) < 1e-9 and v(f"{comps}.rows.the-ashlar.vintage") == 1998
    assert v(f"{comps}.totals.asking_rent") == 1700
    # rent trend and status
    assert list(data.table("rent_trend.tables.monthly").rows) == ["2025-07", "2025-08"]
    assert v("rent_trend.fields.subject_name") == "The Boardwalk"
    assert v("status.fields.collections_recovered") == 7 and v("status.fields.bad_debt_writeoff") == -10
    assert v("status.fields.next_quarter_label") == "3Q26"


def test_future_completion_under_recent_deliveries_is_retained_but_not_reported():
    pdf_text = COSTAR_PDF_TEXT.replace(
        "2330 Union St",
        "Future Community\n2    105    1    Sep 2026    Sep 2027\n2330 Union St",
    )
    part = pdf_part(pdf_text, DocType.COSTAR_SUBMARKET_PDF, file_id="f11", filename="costar.pdf")
    extraction = run_extractor(part)
    assert any(project["name"] == "Future Community" for project in extraction.data["construction_projects"])
    files = [file for file in sample_files() if file["id"] != "f11"] + [file_of("f11", "costar.pdf", part)]

    data, notes = build({"id": "p", "name": "P"}, files)

    assert data.value("submarket.fields.recent_deliveries") == "Montage at Midtown (321 units, Jun 2026)"
    assert any("Future Community" in note["message"] and "excluded" in note["message"] for note in notes)


def test_build_with_only_financials_flags_missing_but_does_not_fail():
    data, notes = build({"id": "p", "name": "P"}, sample_files()[:1])
    assert data.value("financials.tables.lines.rows.noi.ptd_actual") == 550
    assert data.field("property.fields.units").status == "missing"
    assert any(n["severity"] == "error" and "Property name" in n["message"] for n in notes)
    assert data.table("submarket.tables.comps").rows == {} and data.table("in_place_rent.tables.by_floor_plan").rows == {}


def test_comp_summary_metadata_matches_listing_by_street_address_when_names_differ():
    listing = Src("listing", "listing.xlsx", DocType.HELLODATA_LISTINGS.value, "sheet 'Listings'", {
        "properties": {"Fountains at Forestwood": {
            "address": "1735 Brantley Road", "asking_n": 1, "asking_sum": 1500,
        }},
    })
    summary = Src("summary", "summary.xlsx", DocType.HELLODATA_COMPS.value, "sheet 'Rent Comps'", {
        "source": "sheet",
        "comps": [{
            "name": "39 Acres", "address": "1735 Brantley Road, Fort Myers, FL 33907",
            "units": 397, "year_built": 1985, "row": 3,
        }],
    })

    entries, extras = _comp_entries(Selection(listings=listing, comps=[summary]))

    matched = entries["fountains-at-forestwood"]["summaries"][0][0]
    assert matched["units"] == 397 and matched["year_built"] == 1985
    assert extras == []


def test_apply_overrides_fields_rows_deletions_and_ai_drafts():
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    stale = apply_overrides(data, {
        "fields": {"financing.fields.lender": "Fannie Mae", "capital.fields.purchase_price": 38100000, "gone.fields.x": 1},
        "rows": {"underwriting.tables.budget": {"manual_1": {"category": "Amenity Upkeep", "section": "value_add", "original_budget": 75000, "spent_to_date": 0}}},
        "deleted_rows": {"submarket.tables.comps": ["the-ashlar"]},
        "ai_drafts": {"commentary.fields.takeaway": "Revenue finished below budget."},
    })
    assert stale == ["gone.fields.x"]
    assert data.value("financing.fields.lender") == "Fannie Mae" and data.value("capital.fields.purchase_price") == 38100000
    row = data.table("underwriting.tables.budget").rows["manual_1"]
    assert row["category"].value == "Amenity Upkeep" and row["category"].status == "manual" and row["pct_spent"].status == "derived"
    assert "the-ashlar" not in data.table("submarket.tables.comps").rows
    tk = data.field("commentary.fields.takeaway")
    assert tk.value == "Revenue finished below budget." and tk.status == "ai_draft"
    from app.consolidate.calc import recompute
    recompute(data)
    assert data.value("underwriting.tables.budget.totals.original_budget") == 75000 and data.value("underwriting.tables.budget.rows.manual_1.pct_spent") == 0
    assert abs(data.value("capital.fields.price_per_unit") - 38100000 / 338) < 1e-6
