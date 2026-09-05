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
