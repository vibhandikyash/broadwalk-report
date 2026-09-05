"""Typed, atomic corrections: invalid input is rejected with 422 and never persisted."""
import math

import pytest
from fastapi.testclient import TestClient

from app import db
from app.consolidate.corrections import coerce
from app.main import app
from app.workers.pool import pool
from tests.test_api_report_data import upload_all


def test_coerce_accepts_documented_representations():
    assert coerce("money", "1,234.5") == 1234.5 and coerce("money", 7) == 7.0
    assert coerce("integer", 5.0) == 5 and isinstance(coerce("integer", "12"), int)
    assert coerce("percent", 0.905, "current_pct") == 0.905 and coerce("percent", -0.4) == -0.4
    assert coerce("date", "2026-06-30") == "2026-06-30" and coerce("date", "2026-06-30T00:00:00") == "2026-06-30"
    assert coerce("text", "  hi ") == "hi" and coerce("text", 1973) == "1973" and coerce("longtext", "x" * 5000)


@pytest.mark.parametrize("kind,value,key", [
    ("money", "abc", ""), ("money", float("nan"), ""), ("money", float("inf"), ""), ("money", True, ""), ("money", [1], ""),
    ("integer", 1.5, ""), ("integer", -3, "units"), ("integer", 973, "year_built"),
    ("percent", 90.5, ""), ("percent", "5%", ""), ("percent", 1.2, "current_pct"), ("percent", -0.1, "vacancy"),
    ("date", "06/30/2026", ""), ("date", "2026-13-01", ""), ("date", 20260630, ""),
    ("text", "x" * 501, ""), ("longtext", "x" * 5001, ""), ("text", {"a": 1}, ""), ("text", float("nan"), ""),
])
def test_coerce_rejects_bad_values(kind, value, key):
    with pytest.raises(ValueError):
        coerce(kind, value, key)


def _field(ui, section, key):
    return next(f for s in ui["sections"] if s["key"] == section for f in s["fields"] if f["key"] == key)


def _cell(ui, path):
    for s in ui["sections"]:
        for t in s["tables"]:
            for r in t["rows"]:
                for c in r["cells"]:
                    if c["path"] == path:
                        return c
            for c in t["totals"]:
                if c["path"] == path:
                    return c
    raise KeyError(path)


def test_invalid_corrections_return_422_and_persist_nothing(tmp_path):
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "C"}).json()["id"]
        upload_all(client, pid, tmp_path)
        url = f"/api/projects/{pid}/report-data"
        cases = [
            ({"changes": [{"path": "nope.fields.x", "value": 1}]}, "unknown field path"),
            ({"changes": [{"path": "commentary.fields.noi_actual", "value": 1}]}, "calculated"),
            ({"changes": [{"path": "financials.tables.lines.rows.noi.ptd_var", "value": 1}]}, "calculated"),
            ({"changes": [{"path": "capex.tables.lines.totals.ptd_actual", "value": 1}]}, "calculated"),
            ({"changes": [{"path": "property.fields.units", "value": "lots"}]}, "expected a number"),
            ({"changes": [{"path": "property.fields.units", "value": 12.5}]}, "whole number"),
            ({"changes": [{"path": "property.fields.units", "value": -4}]}, "negative"),
            ({"changes": [{"path": "occupancy.fields.current_pct", "value": 90.53}]}, "fractions"),
            ({"changes": [{"path": "occupancy.fields.current_pct", "value": 1.2}]}, "between 0 and 1"),
            ({"changes": [{"path": "financing.fields.rate", "value": "5.23%"}]}, "fractions"),
            ({"changes": [{"path": "financing.fields.effective_date", "value": "06/30/2026"}]}, "YYYY-MM-DD"),
            ({"changes": [{"path": "financing.fields.lender", "value": "x" * 600}]}, "longer than"),
            ({"changes": [{"path": "financing.fields.lender", "value": "Fannie Mae"}, {"path": "property.fields.units", "value": -1}]}, "negative"),
            ({"add_rows": [{"table": "financials.tables.lines", "values": {}}]}, "cannot be added"),
            ({"add_rows": [{"table": "underwriting.tables.budget", "values": {"pct_spent": 0.5}}]}, "calculated"),
            ({"add_rows": [{"table": "underwriting.tables.budget", "values": {"bogus": 1}}]}, "unknown column"),
            ({"add_rows": [{"table": "underwriting.tables.budget", "values": {"original_budget": "lots"}}]}, "expected a number"),
            ({"add_rows": [{"table": "underwriting.tables.budget", "key": "bad key!", "values": {}}]}, "row keys"),
            ({"delete_rows": [{"table": "financials.tables.lines", "key": "noi"}]}, "cannot be removed"),
            ({"delete_rows": [{"table": "submarket.tables.comps", "key": "nope"}]}, "unknown row"),
            ({"delete_rows": [{"table": "nope.tables.x", "key": "a"}]}, "unknown table"),
        ]
        for body, msg in cases:
            r = client.patch(url, json=body)
            assert r.status_code == 422 and msg in r.json()["detail"], (body, r.status_code, r.json())
        for raw in ('{"changes":[{"path":"property.fields.units","value":NaN}]}', '{"changes":[{"path":"property.fields.units","value":1e999}]}'):
            r = client.patch(url, content=raw, headers={"content-type": "application/json"})
            assert r.status_code == 422, raw
        assert client.get(f"{url}/overrides").json() == {}
        ui = client.get(url).json()
        assert _field(ui, "property", "units")["effective"] == 338 and _field(ui, "financing", "lender")["effective"] is None
        assert client.get(f"/api/projects/{pid}/report/preview").status_code == 200


def test_valid_edits_recompute_dependents_and_manual_rows_are_typed(tmp_path):
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "C2"}).json()["id"]
        upload_all(client, pid, tmp_path)
        url = f"/api/projects/{pid}/report-data"
        ui = client.patch(url, json={"changes": [
            {"path": "financials.tables.lines.rows.total_revenue.ptd_actual", "value": "1,100"},
            {"path": "occupancy.fields.current_pct", "value": 0.9},
            {"path": "financing.fields.effective_date", "value": "2025-08-01"},
            {"path": "financing.fields.maturity_date", "value": "2025-07-01"},
        ]}).json()
        assert _cell(ui, "financials.tables.lines.rows.total_revenue.ptd_var")["effective"] == 146
        assert _field(ui, "commentary", "revenue_actual")["effective"] == 1100 and _field(ui, "commentary", "revenue_var_pct")["effective"] == pytest.approx(146 / 954)
        assert _field(ui, "occupancy", "change_bps")["effective"] == round((0.9 - 0.9171) * 10000)
        assert any("Maturity date" in i["message"] and i["severity"] == "error" for i in ui["issues"])
        ui = client.patch(url, json={"add_rows": [{"table": "underwriting.tables.budget", "values": {"category": "Amenity", "section": "value_add", "original_budget": "75,000", "spent_to_date": 7500}}]}).json()
        uw = next(t for s in ui["sections"] if s["key"] == "underwriting" for t in s["tables"])
        row = uw["rows"][0]
        vals = {c["key"]: c["effective"] for c in row["cells"]}
        assert vals["original_budget"] == 75000 and isinstance(vals["original_budget"], float) and vals["pct_spent"] == pytest.approx(0.1)
        assert next(c["effective"] for c in uw["totals"] if c["key"] == "pct_spent") == pytest.approx(0.1)
        # a later cell edit on the manual row goes through the same typing
        r = client.patch(url, json={"changes": [{"path": f"underwriting.tables.budget.rows.{row['key']}.original_budget", "value": "abc"}]})
        assert r.status_code == 422
        ui = client.patch(url, json={"changes": [{"path": f"underwriting.tables.budget.rows.{row['key']}.original_budget", "value": 80000}]}).json()
        assert next(c["effective"] for c in uw["totals"] if c["key"] == "original_budget") == 75000
        uw = next(t for s in ui["sections"] if s["key"] == "underwriting" for t in s["tables"])
        assert next(c["effective"] for c in uw["totals"] if c["key"] == "original_budget") == 80000
        # a failed correction leaves review, preview and generation usable
        assert client.patch(url, json={"changes": [{"path": "property.fields.units", "value": "x"}]}).status_code == 422
        assert client.get(url).status_code == 200 and client.get(f"/api/projects/{pid}/report/preview").status_code == 200
        assert client.post(f"/api/projects/{pid}/reports").status_code == 202
        assert pool.wait_idle(120)


def test_legacy_invalid_overrides_are_ignored_and_resettable(tmp_path):
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "C3"}).json()["id"]
        upload_all(client, pid, tmp_path)
        url = f"/api/projects/{pid}/report-data"
        db.save_overrides(pid, {"fields": {"property.fields.units": "lots", "commentary.fields.noi_actual": 5, "financing.fields.lender": "Fannie Mae",
                                          "occupancy.fields.current_pct": float("nan")},
                                "rows": {"underwriting.tables.budget": {"m1": {"original_budget": "abc", "category": "Kept"}}, "bad.table": "junk"},
                                "ai_drafts": {"capex.fields.narrative": 12, "commentary.fields.takeaway": "A draft."}})
        r = client.get(url)
        assert r.status_code == 200
        ui = r.json()
        assert _field(ui, "property", "units")["effective"] == 338 and _field(ui, "financing", "lender")["effective"] == "Fannie Mae"
        assert _field(ui, "commentary", "takeaway")["effective"] == "A draft." and _field(ui, "capex", "narrative")["effective"] is None
        ignored = [i["message"] for i in ui["issues"] if "stored correction was ignored" in i["message"]]
        assert len(ignored) >= 4 and any("property.fields.units" in m for m in ignored)
        uw = next(t for s in ui["sections"] if s["key"] == "underwriting" for t in s["tables"])
        assert {c["key"]: c["effective"] for c in uw["rows"][0]["cells"]}["category"] == "Kept"
        assert client.get(f"/api/projects/{pid}/report/preview").status_code == 200
        assert client.post(f"/api/projects/{pid}/reports").status_code == 202
        assert pool.wait_idle(120)
        raw = client.get(f"{url}/overrides").json()
        assert raw["fields"]["property.fields.units"] == "lots"  # the raw store is untouched by reads
        left = client.post(f"{url}/overrides/reset", json={"paths": ["property.fields.units", "underwriting.tables.budget.rows.m1"]}).json()
        assert "property.fields.units" not in left["fields"] and left["fields"]["financing.fields.lender"] == "Fannie Mae"
        assert left["rows"]["underwriting.tables.budget"] == {}
        assert client.post(f"{url}/overrides/reset", json={"ai_drafts": True}).json().get("ai_drafts") is None
        client.patch(url, json={"delete_rows": [{"table": "submarket.tables.comps", "key": "the-ashlar"}]})
        assert client.get(f"{url}/overrides").json()["deleted_rows"] == {"submarket.tables.comps": ["the-ashlar"]}
        assert client.post(f"{url}/overrides/reset", json={"paths": ["submarket.tables.comps.deleted"]}).json()["deleted_rows"] == {}
        assert client.post(f"{url}/overrides/reset", json={}).json() == {}
        assert _field(client.get(url).json(), "financing", "lender")["effective"] is None
