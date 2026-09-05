# backend/tests/test_api_files.py
from fastapi.testclient import TestClient

from app.main import app
from app.workers.pool import pool
from tests.helpers import BUDGET_ROWS, LTO_ROWS, make_xlsx, rent_roll_rows


def test_project_and_file_lifecycle(tmp_path):
    xlsx = make_xlsx(tmp_path / "fin.xlsx", {"Report1": BUDGET_ROWS, "RR": rent_roll_rows("06/30/2026", 306, 338, 90.53, 14), "LTO": LTO_ROWS})
    with TestClient(app) as client:
        assert client.get("/api/doc-types").json()[0]["key"] == "yardi_budget_comparison"
        p = client.post("/api/projects", json={"name": "  Boardwalk 2Q26 "}).json()
        assert p["name"] == "Boardwalk 2Q26" and client.get("/api/projects").json()[0]["id"] == p["id"]
        assert client.get(f"/api/projects/{p['id']}").json()["stage"] == "upload"
        with xlsx.open("rb") as fh:
            r = client.post(f"/api/projects/{p['id']}/files", files=[("files", ("fin.xlsx", fh, "application/octet-stream")),
                                                                     ("files", ("notes.docx", b"hello", "application/octet-stream"))])
        assert r.status_code == 201
        recs = r.json()
        assert recs[0]["status"] in ("queued", "processing", "processed") and recs[1]["status"] == "unsupported"
        assert "extractions" not in recs[0]
        assert pool.wait_idle(90)
        detail = client.get(f"/api/projects/{p['id']}").json()  # consolidation happens inside the jobs: no polling needed
        assert detail["stage"] == "review" and detail["report_built"] is True, {k: detail[k] for k in ("stage", "report_built", "processing")} | {"files": [(f["original_filename"], f["status"], f["error"]) for f in detail["files"]]}
        good = next(f for f in detail["files"] if f["original_filename"] == "fin.xlsx")
        assert good["status"] == "processed" and [x["doc_type"] for x in good["parts"]][0] == "yardi_budget_comparison"
        ex = client.get(f"/api/projects/{p['id']}/files/{good['id']}/extraction").json()
        assert len(ex["extractions"]) == 3
        assert client.patch(f"/api/projects/{p['id']}/files/{good['id']}", json={"ignored": True}).json()["ignored"] is True
        assert client.patch(f"/api/projects/{p['id']}/files/{good['id']}", json={"ignored": False, "doc_type_override": "nope"}).status_code == 422
        r = client.post(f"/api/projects/{p['id']}/files/{good['id']}/reprocess")
        assert r.status_code == 200 and pool.wait_idle(90)
        bad = next(f for f in detail["files"] if f["original_filename"] == "notes.docx")
        assert client.post(f"/api/projects/{p['id']}/files/{bad['id']}/reprocess").status_code == 409
        assert client.delete(f"/api/projects/{p['id']}/files/{bad['id']}").status_code == 204
        assert len(client.get(f"/api/projects/{p['id']}/files").json()) == 1
        assert client.delete(f"/api/projects/{p['id']}").status_code == 204
        assert client.get(f"/api/projects/{p['id']}").status_code == 404


def test_upload_rejects_oversize(tmp_path, monkeypatch):
    from app.api import files as files_api
    monkeypatch.setattr(files_api, "_upload_limit", lambda: 5)
    with TestClient(app) as client:
        p = client.post("/api/projects", json={"name": "P"}).json()
        r = client.post(f"/api/projects/{p['id']}/files", files=[("files", ("big.xlsx", b"x" * 10, "application/octet-stream"))])
        assert r.status_code == 413
