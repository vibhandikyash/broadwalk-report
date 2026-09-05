"""Upload, processing, recovery and versioning under contention. No sleeps that could hide a race."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.report.render import chromium_available
from app.workers import jobs
from app.workers.pool import pool
from tests.helpers import BUDGET_ROWS, LTO_ROWS, make_xlsx, rent_roll_rows


def _small(tmp_path):
    return make_xlsx(tmp_path / "fin.xlsx", {"Report1": BUDGET_ROWS, "RR": rent_roll_rows("06/30/2026", 306, 338, 90.53, 14)})


def _batch(good: bytes):
    return [("files", ("fin.xlsx", good, "application/octet-stream")), ("files", ("notes.docx", b"hello", "application/octet-stream")),
            ("files", ("bad.xlsx", b"not a workbook", "application/octet-stream"))]


def test_mixed_batches_consolidate_every_time(tmp_path):
    good = _small(tmp_path).read_bytes()
    with TestClient(app) as client:
        for i in range(100):
            pid = client.post("/api/projects", json={"name": f"batch {i}"}).json()["id"]
            assert client.post(f"/api/projects/{pid}/files", files=_batch(good)).status_code == 201
            assert pool.wait_idle(60)
            detail = client.get(f"/api/projects/{pid}").json()  # no polling: consolidation must already be done
            statuses = {f["original_filename"]: f["status"] for f in detail["files"]}
            assert statuses == {"fin.xlsx": "processed", "notes.docx": "unsupported", "bad.xlsx": "failed"}, (i, detail["files"])
            assert detail["stage"] == "review" and detail["report_built"], (i, detail["stage"])
            client.delete(f"/api/projects/{pid}")


def test_projects_with_only_unusable_files_reach_review_with_issues(tmp_path):
    with TestClient(app) as client:
        for name, files in (("unsupported only", [("files", ("a.docx", b"x", "application/octet-stream")), ("files", ("b.txt", b"y", "text/plain"))]),
                            ("corrupt only", [("files", ("a.xlsx", b"junk", "application/octet-stream")), ("files", ("b.pdf", b"%PDF-junk", "application/pdf"))]),
                            ("unrecognised only", [("files", ("odd.xlsx", make_xlsx(tmp_path / "odd.xlsx", {"S": [["hello"], ["world", 1]]}).read_bytes(), "application/octet-stream"))])):
            pid = client.post("/api/projects", json={"name": name}).json()["id"]
            assert client.post(f"/api/projects/{pid}/files", files=files).status_code == 201
            assert pool.wait_idle(60)
            detail = client.get(f"/api/projects/{pid}").json()
            assert detail["stage"] == "review" and detail["report_built"], (name, detail)
            assert all(f["status"] in ("unsupported", "failed", "unrecognized") and f["error"] for f in detail["files"]), detail["files"]
            ui = client.get(f"/api/projects/{pid}/report-data").json()
            assert ui["summary"]["errors"] >= 1 and any(f["original_filename"].split(".")[0] in i["message"] for f in detail["files"] for i in ui["issues"])


def test_scanned_pdf_gets_needs_ocr_status(tmp_path):
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument.new()
    pdf.new_page(400, 300)  # a blank page: no text layer at all
    path = tmp_path / "scan.pdf"
    pdf.save(path)
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "scan"}).json()["id"]
        with path.open("rb") as fh:
            assert client.post(f"/api/projects/{pid}/files", files=[("files", ("scan.pdf", fh, "application/pdf"))]).status_code == 201
        assert pool.wait_idle(60)
        f = client.get(f"/api/projects/{pid}/files").json()[0]
        assert f["status"] == "needs_ocr" and "OCR" in f["error"]
        assert client.get(f"/api/projects/{pid}").json()["stage"] == "review"


def test_simultaneous_uploads_to_one_project_all_consolidate(tmp_path):
    good = _small(tmp_path).read_bytes()
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "parallel"}).json()["id"]
        results = []

        def upload(n):
            c = TestClient(app)  # no lifespan: shares the running app and pool
            results.append(c.post(f"/api/projects/{pid}/files", files=_batch(good)).status_code)
        threads = [threading.Thread(target=upload, args=(n,)) for n in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results == [201] * 6 and pool.wait_idle(120)
        detail = client.get(f"/api/projects/{pid}").json()
        assert len(detail["files"]) == 18 and detail["stage"] == "review" and detail["report_built"]
        assert sum(f["status"] == "processed" for f in detail["files"]) == 6


def test_type_override_during_processing_is_refused_then_applied(tmp_path, monkeypatch):
    real = jobs.read_document

    def slow(*a, **k):
        time.sleep(1.5)
        return real(*a, **k)
    monkeypatch.setattr(jobs, "read_document", slow)
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "override"}).json()["id"]
        with _small(tmp_path).open("rb") as fh:
            fid = client.post(f"/api/projects/{pid}/files", files=[("files", ("fin.xlsx", fh, "application/octet-stream"))]).json()[0]["id"]
        r = client.patch(f"/api/projects/{pid}/files/{fid}", json={"doc_type_override": "yardi_rent_roll"})
        assert r.status_code == 409 and "still processing" in r.json()["detail"]
        assert client.post(f"/api/projects/{pid}/files/{fid}/reprocess").status_code == 409
        assert client.delete(f"/api/projects/{pid}/files/{fid}").status_code == 409
        assert pool.wait_idle(60)
        assert client.get(f"/api/projects/{pid}").json()["stage"] == "review"
        monkeypatch.setattr(jobs, "read_document", real)
        f = client.patch(f"/api/projects/{pid}/files/{fid}", json={"doc_type_override": "yardi_rent_roll"}).json()
        assert f["status"] == "queued" and f["doc_type_override"] == "yardi_rent_roll"
        assert pool.wait_idle(60)
        f = client.get(f"/api/projects/{pid}/files").json()[0]
        assert f["status"] == "processed" and f["doc_type_override"] == "yardi_rent_roll"  # multi-sheet: override kept, auto-detect per sheet


def test_override_changed_mid_run_is_applied_by_a_second_pass(tmp_path, monkeypatch):
    """The tiny window after the API's 'is it running' check: the job re-runs itself when the type changed under it."""
    path = make_xlsx(tmp_path / "x.xlsx", {"Sheet": rent_roll_rows("03/31/2026", 310, 338, 91.71, 34)})
    p = db.create_project("midrun")
    fid = db.new_id()
    db.add_file(p["id"], fid, "x.xlsx", str(path), ".xlsx", 10)
    real = jobs.read_document

    def flip(*a, **k):
        monkeypatch.setattr(jobs, "read_document", real)
        db.update_file(fid, doc_type_override="yardi_lease_trade_out")
        return real(*a, **k)
    monkeypatch.setattr(jobs, "read_document", flip)
    jobs.process_file(fid)
    f = db.get_file(fid)
    assert f["status"] == "failed" and f["parts"][0]["doc_type"] == "yardi_lease_trade_out"


def test_restart_recovers_files_reports_and_narratives(tmp_path, monkeypatch):
    import dataclasses

    import app.config as cfg
    monkeypatch.setattr(cfg, "settings", dataclasses.replace(cfg.settings, narrative_provider="off"))  # never call a live model here
    path = _small(tmp_path)
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "restart"}).json()["id"]
        with path.open("rb") as fh:
            fid = client.post(f"/api/projects/{pid}/files", files=[("files", ("fin.xlsx", fh, "application/octet-stream"))]).json()[0]["id"]
        assert pool.wait_idle(60)
        rid = client.post(f"/api/projects/{pid}/reports").json()["id"]
        assert pool.wait_idle(120)
    # simulate a crash: everything left mid-flight
    db.update_file(fid, status="processing")
    db.update_report(rid, status="rendering", pdf_path=None)
    db.set_narrative(pid, "running", None)
    with TestClient(app) as client:  # lifespan runs the recovery
        assert pool.wait_idle(120)
        detail = client.get(f"/api/projects/{pid}").json()
        assert detail["files"][0]["status"] == "processed" and detail["stage"] in ("review", "generated")
        rep = client.get(f"/api/projects/{pid}/reports/{rid}").json()
        assert rep["status"] == ("done" if chromium_available() else "failed") and rep["status"] != "rendering"
        rd = client.get(f"/api/projects/{pid}/report-data").json()
        assert rd["narrative_status"] == "failed" and "restart" in rd["narrative_error"]
    # with a provider configured the drafting job is re-queued instead
    monkeypatch.setattr(cfg, "settings", dataclasses.replace(cfg.settings, narrative_provider="api", anthropic_api_key="test-key"))
    ran = []
    monkeypatch.setattr(jobs, "draft_narratives", lambda p: (ran.append(p), db.set_narrative(p, "done", None)))
    db.set_narrative(pid, "running", None)
    with TestClient(app) as client:
        assert pool.wait_idle(60)
        assert ran == [pid] and client.get(f"/api/projects/{pid}/report-data").json()["narrative_status"] == "done"


def test_concurrent_version_numbers_are_unique():
    p = db.create_project("versions")
    with ThreadPoolExecutor(max_workers=8) as ex:
        versions = sorted(r["version"] for r in ex.map(lambda _: db.create_report(p["id"]), range(24)))
    assert versions == list(range(1, 25))


def test_versions_snapshot_reviewed_data_at_request_time(tmp_path):
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "snap"}).json()["id"]
        with _small(tmp_path).open("rb") as fh:
            client.post(f"/api/projects/{pid}/files", files=[("files", ("fin.xlsx", fh, "application/octet-stream"))])
        assert pool.wait_idle(60)
        client.patch(f"/api/projects/{pid}/report-data", json={"changes": [{"path": "financing.fields.lender", "value": "Freddie Mac"}]})
        v1 = client.post(f"/api/projects/{pid}/reports").json()
        client.patch(f"/api/projects/{pid}/report-data", json={"changes": [{"path": "financing.fields.lender", "value": "Fannie Mae"}]})
        v2 = client.post(f"/api/projects/{pid}/reports").json()
        assert (v1["version"], v2["version"]) == (1, 2)
        s1 = client.get(f"/api/projects/{pid}/reports/{v1['id']}/snapshot").json()
        s2 = client.get(f"/api/projects/{pid}/reports/{v2['id']}/snapshot").json()
        assert s1["sections"]["financing"]["fields"]["lender"]["override"] == "Freddie Mac"
        assert s2["sections"]["financing"]["fields"]["lender"]["override"] == "Fannie Mae"
        assert pool.wait_idle(180)
        if chromium_available():
            import pdfplumber

            for v, lender in ((v1, "Freddie Mac"), (v2, "Fannie Mae")):
                r = client.get(f"/api/projects/{pid}/reports/{v['id']}/download")
                assert r.status_code == 200
                out = tmp_path / f"v{v['version']}.pdf"
                out.write_bytes(r.content)
                with pdfplumber.open(out) as doc:
                    assert lender in doc.pages[3].extract_text()
