# backend/tests/test_api_report_data.py
from fastapi.testclient import TestClient

from app.main import app
from app.workers.pool import pool
from tests.helpers import (BALANCE_ROWS, BUDGET_ROWS, COMPS_ROWS, COSTAR_ROWS, LISTINGS_ROWS, LTO_ROWS, RENT_CHART_ROWS, make_xlsx,
                           rent_roll_rows, schedule_rows)

RENTS = {"BWK.A1": 1172.47, "BWK.B0": 1331.04, "BWK.B1": 1370.84, "BWK.S1": 1108.31, "TOTAL": 1250.5}


def upload_all(client, pid, tmp_path):
    xlsx = make_xlsx(tmp_path / "all.xlsx", {
        "Fin": BUDGET_ROWS, "BS": BALANCE_ROWS, "RR": rent_roll_rows("06/30/2026", 306, 338, 90.53, 14),
        "RR0": rent_roll_rows("03/31/2026", 310, 338, 91.71, 34), "Sch": schedule_rows("06/30/2026", RENTS), "LTO": LTO_ROWS,
        "HD": LISTINGS_ROWS, "Comps": COMPS_ROWS, "CoStar": COSTAR_ROWS, "Chart": RENT_CHART_ROWS})
    with xlsx.open("rb") as fh:
        assert client.post(f"/api/projects/{pid}/files", files=[("files", ("all.xlsx", fh, "application/octet-stream"))]).status_code == 201
    assert pool.wait_idle(90)


def test_report_data_read_patch_rows_and_rebuild(tmp_path):
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "RD"}).json()["id"]
        assert client.get(f"/api/projects/{pid}/report-data").status_code == 409
        upload_all(client, pid, tmp_path)
        ui = client.get(f"/api/projects/{pid}/report-data").json()
        keys = [s["key"] for s in ui["sections"]]
        assert keys == ["property", "in_place_rent", "capital", "underwriting", "rent_trend", "financing", "financials", "commentary", "capex", "submarket", "occupancy", "status"]
        prop = next(s for s in ui["sections"] if s["key"] == "property")
        units = next(f for f in prop["fields"] if f["key"] == "units")
        assert units["effective"] == 338 and units["status"] == "extracted" and units["source"]["locator"].startswith("sheet 'RR'")
        assert ui["summary"]["missing"] > 0 and ui["built_at"]
        fin = next(t for s in ui["sections"] if s["key"] == "financials" for t in s["tables"])
        noi = next(r for r in fin["rows"] if r["key"] == "noi")
        assert next(c for c in noi["cells"] if c["key"] == "ptd_var")["readonly"] is True
        body = {"changes": [{"path": "financing.fields.lender", "value": "Fannie Mae"},
                            {"path": "financials.tables.lines.rows.total_revenue.ptd_actual", "value": 1100}],
                "add_rows": [{"table": "underwriting.tables.budget", "values": {"category": "Amenity Upkeep", "section": "value_add", "original_budget": 75000, "spent_to_date": 0}}],
                "delete_rows": [{"table": "submarket.tables.comps", "key": "the-ashlar"}]}
        ui = client.patch(f"/api/projects/{pid}/report-data", json=body).json()
        financing = next(s for s in ui["sections"] if s["key"] == "financing")
        lender = next(f for f in financing["fields"] if f["key"] == "lender")
        assert lender["effective"] == "Fannie Mae" and lender["status"] == "manual"
        fin = next(t for s in ui["sections"] if s["key"] == "financials" for t in s["tables"])
        rev = next(r for r in fin["rows"] if r["key"] == "total_revenue")
        assert next(c for c in rev["cells"] if c["key"] == "ptd_var")["effective"] == 146
        assert any("does not equal the sum" in i["message"] for i in ui["issues"])
        uw = next(t for s in ui["sections"] if s["key"] == "underwriting" for t in s["tables"])
        assert uw["rows"][0]["manual"] is True and next(c for c in uw["totals"] if c["key"] == "original_budget")["effective"] == 75000
        comps = next(t for s in ui["sections"] if s["key"] == "submarket" for t in s["tables"])
        assert [r["key"] for r in comps["rows"]] == ["the-boardwalk"]
        # clearing an override restores the extracted value; rebuild keeps the remaining overrides
        ui = client.patch(f"/api/projects/{pid}/report-data", json={"changes": [{"path": "financials.tables.lines.rows.total_revenue.ptd_actual", "value": None}]}).json()
        fin = next(t for s in ui["sections"] if s["key"] == "financials" for t in s["tables"])
        rev = next(r for r in fin["rows"] if r["key"] == "total_revenue")
        assert next(c for c in rev["cells"] if c["key"] == "ptd_actual")["effective"] == 1000
        ui = client.post(f"/api/projects/{pid}/report-data/rebuild").json()
        financing = next(s for s in ui["sections"] if s["key"] == "financing")
        assert next(f for f in financing["fields"] if f["key"] == "lender")["effective"] == "Fannie Mae"



def test_completeness_endpoint_and_summary_track_the_review(tmp_path):
    from app.consolidate.completeness import fill_gaps_for_test
    from app.workers import jobs

    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "Cmp"}).json()["id"]
        upload_all(client, pid, tmp_path)
        c = client.get(f"/api/projects/{pid}/completeness").json()
        assert c["complete"] is False and c["gap_count"] == len(c["gaps"]) > 10
        assert {"path", "label", "page", "group", "reason"} <= set(c["gaps"][0]) and any(g["page"] == 4 for g in c["gaps"])
        assert any(not g["complete"] for g in c["groups"]) and c["ai_drafts_pending"] == 0
        ui = client.get(f"/api/projects/{pid}/report-data").json()
        assert ui["summary"]["completeness"]["gap_count"] == c["gap_count"] and ui["summary"]["completeness"]["complete"] is False
        v1 = client.post(f"/api/projects/{pid}/reports").json()
        assert v1["complete"] is False and v1["gap_count"] == c["gap_count"]
        # fill every gap through the public correction API, as a reviewer would
        data, _issues, _row = jobs.load_effective(pid)
        ov = fill_gaps_for_test(data)
        body = {"changes": [{"path": k, "value": v} for k, v in ov["fields"].items()],
                "add_rows": [{"table": tp, "key": rk, "values": vals} for tp, rows in ov["rows"].items() for rk, vals in rows.items()]}
        assert client.patch(f"/api/projects/{pid}/report-data", json=body).status_code == 200
        c = client.get(f"/api/projects/{pid}/completeness").json()
        assert c["complete"] is True and c["gap_count"] == 0, [g["path"] for g in c["gaps"]]
        v2 = client.post(f"/api/projects/{pid}/reports").json()
        assert v2["complete"] is True and v2["gap_count"] == 0
        assert client.get(f"/api/projects/{pid}/reports").json()[0]["complete"] is True
        assert pool.wait_idle(180)
        from app.report.render import chromium_available

        if chromium_available():
            d1 = client.get(f"/api/projects/{pid}/reports/{v1['id']}/download")
            d2 = client.get(f"/api/projects/{pid}/reports/{v2['id']}/download")
            assert d1.status_code == 200 and "-v1-draft.pdf" in d1.headers["content-disposition"]
            assert d2.status_code == 200 and "-v2.pdf" in d2.headers["content-disposition"] and "draft" not in d2.headers["content-disposition"]
            import pdfplumber

            with pdfplumber.open(__import__("io").BytesIO(d1.content)) as doc:
                text = "\n".join(p.extract_text() or "" for p in doc.pages)
            assert text.count("DRAFT") >= 10, "every page of an incomplete report is marked"
            with pdfplumber.open(__import__("io").BytesIO(d2.content)) as doc:
                assert "DRAFT" not in "\n".join(p.extract_text() or "" for p in doc.pages)
