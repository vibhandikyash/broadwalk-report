# backend/tests/test_dataset.py
import os
from pathlib import Path

import pytest

DATASET = os.getenv("TEST_DATASET_DIR")
pytestmark = pytest.mark.skipif(not DATASET, reason="set TEST_DATASET_DIR to the folder holding the real source files")


def test_real_dataset_end_to_end():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.workers.pool import pool

    paths = sorted(p for p in Path(DATASET).rglob("*") if p.suffix.lower() in (".xlsx", ".pdf") and not p.name.startswith("~$"))
    assert paths, "no source files found"
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "dataset"}).json()["id"]
        for p in paths:
            with p.open("rb") as fh:
                assert client.post(f"/api/projects/{pid}/files", files=[("files", (p.name, fh, "application/octet-stream"))]).status_code == 201
        assert pool.wait_idle(180)
        detail = client.get(f"/api/projects/{pid}").json()
        bad = [(f["original_filename"], f["status"], f["error"]) for f in detail["files"] if f["status"] not in ("processed", "unsupported")]
        assert not bad, bad
        ui = client.get(f"/api/projects/{pid}/report-data").json()
        v = {f["path"]: f["effective"] for s in ui["sections"] for f in s["fields"]}
        cells = {c["path"]: c["effective"] for s in ui["sections"] for t in s["tables"] for r in t["rows"] for c in r["cells"]}
        cells.update({c["path"]: c["effective"] for s in ui["sections"] for t in s["tables"] for c in t["totals"]})
        assert v["property.fields.name"] == "The Boardwalk" and v["property.fields.units"] == 338
        assert v["property.fields.year_built"] == 1973 and v["property.fields.acquired_date"] == "2025-07-30"
        assert v["capital.fields.purchase_price"] == 48000000 and abs(v["capital.fields.equity_invested"] - 14259605.94) < 1
        assert abs(v["financing.fields.implied_rate"] - 0.0523) < 1e-4 and v["financing.fields.loan_amount"] == 36519000
        assert abs(cells["financials.tables.lines.rows.noi.ptd_actual"] - 636105.69) < 1
        assert abs(cells["financials.tables.lines.rows.total_revenue.ytd_actual"] - 2826719.16) < 1
        assert abs(cells["financials.tables.lines.rows.concessions.ptd_actual"] + 53131.05) < 1
        assert abs(cells["financials.tables.lines.rows.net_cash_flow.ptd_var"] + 134365.64) < 1
        assert abs(cells["capex.tables.lines.totals.ptd_actual"] - 241077.37) < 1 and abs(v["capex.fields.source_total_ptd"] - 241077.37) < 1
        assert abs(cells["capex.tables.lines.rows.plumbing_water_heaters.ptd_actual"] - 80252.75) < 1
        assert abs(cells["in_place_rent.tables.by_floor_plan.totals.current_rent"] - 1323.98) < 0.01
        assert abs(cells["in_place_rent.tables.by_floor_plan.rows.0br.current_rent"] - 1074.1) < 0.5
        assert abs(v["occupancy.fields.current_pct"] - 0.9053) < 1e-4 and v["occupancy.fields.change_bps"] == -118
        assert cells["occupancy.tables.new_leases.totals.count"] == 38 and abs(cells["occupancy.tables.new_leases.totals.lto_pct"] + 0.1762) < 1e-3
        assert cells["occupancy.tables.renewals.totals.count"] == 25
        assert abs(v["submarket.fields.vacancy"] - 0.1634) < 1e-3 and abs(v["submarket.fields.prior_vacancy"] - 0.1471) < 1e-3
        assert abs(cells["submarket.tables.comps.rows.the-ashlar.asking_rent"] - 1719) < 1
        assert abs(cells["submarket.tables.comps.rows.the-boardwalk.asking_rent"] - 1303) < 1
        assert v["submarket.fields.submarket_name"] == "Western Lee County" and v["property.fields.prepared_by"] == "ZMR Capital"
        assert not [i for i in ui["issues"] if i["severity"] == "error"], [i["message"] for i in ui["issues"] if i["severity"] == "error"]
