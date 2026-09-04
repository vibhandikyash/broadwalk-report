# backend/tests/test_api_report.py
from fastapi.testclient import TestClient

from app.main import app
from app.workers.pool import pool
from tests.test_api_report_data import upload_all


def test_preview_generate_and_download(tmp_path):
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "R"}).json()["id"]
        assert client.get(f"/api/projects/{pid}/report/preview").status_code == 409
        assert client.post(f"/api/projects/{pid}/reports").status_code == 409
        upload_all(client, pid, tmp_path)
        html = client.get(f"/api/projects/{pid}/report/preview")
        assert html.status_code == 200 and "The Boardwalk" in html.text and html.headers["content-type"].startswith("text/html")
        r = client.post(f"/api/projects/{pid}/reports")
        assert r.status_code == 202 and r.json()["version"] == 1 and r.json()["status"] in ("queued", "rendering", "done", "failed")
        rid = r.json()["id"]
        assert pool.wait_idle(120)
        rep = client.get(f"/api/projects/{pid}/reports/{rid}").json()
        if client.get("/api/health").json()["pdf_renderer"]:
            assert rep["status"] == "done" and rep["has_pdf"] is True, rep["error"]
            dl = client.get(f"/api/projects/{pid}/reports/{rid}/download")
            assert dl.status_code == 200 and dl.headers["content-type"] == "application/pdf" and dl.content[:4] == b"%PDF"
        else:
            assert rep["status"] == "failed" and rep["error"]
            assert client.get(f"/api/projects/{pid}/reports/{rid}/download").status_code == 409
        r2 = client.post(f"/api/projects/{pid}/reports").json()
        assert r2["version"] == 2 and [x["version"] for x in client.get(f"/api/projects/{pid}/reports").json()] == [2, 1]
        assert pool.wait_idle(120)
        assert client.get(f"/api/projects/{pid}").json()["stage"] in ("generated", "review")
