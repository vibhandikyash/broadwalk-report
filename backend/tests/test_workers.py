# backend/tests/test_workers.py
import time

from app import db
from app.classify.classifier import DocType
from app.workers import jobs
from app.workers.pool import Pool
from tests.helpers import BUDGET_ROWS, LTO_ROWS, make_xlsx, rent_roll_rows


def setup_module(module):
    db.init_db()


def test_pool_runs_jobs_once_per_key_and_reports_idle():
    pool = Pool(workers=2)
    seen = []
    assert pool.submit("k1", lambda: seen.append(1)) is True
    assert pool.submit("k2", lambda: (time.sleep(0.2), seen.append(2))) is True
    assert pool.submit("k2", lambda: seen.append(3)) is False  # already running
    assert pool.wait_idle(5) and sorted(seen) == [1, 2]
    pool.submit("boom", lambda: 1 / 0)  # exceptions are logged, never raised
    assert pool.wait_idle(5)
    pool.shutdown()


def test_process_file_extracts_and_builds_report_data(tmp_path):
    p = db.create_project("W")
    good = make_xlsx(tmp_path / "fin.xlsx", {"Report1": BUDGET_ROWS, "RR": rent_roll_rows("06/30/2026", 306, 338, 90.53, 14), "LTO": LTO_ROWS})
    fid = db.new_id()
    db.add_file(p["id"], fid, "fin.xlsx", str(good), ".xlsx", good.stat().st_size)
    jobs.process_file(fid)
    f = db.get_file(fid)
    assert f["status"] == "processed" and f["error"] is None
    assert [x["doc_type"] for x in f["parts"]] == [DocType.YARDI_BUDGET_COMPARISON, DocType.YARDI_RENT_ROLL, DocType.YARDI_LEASE_TRADE_OUT]
    assert len(f["extractions"]) == 3 and f["processed_at"]
    rd = db.get_report_data(p["id"])
    assert rd["built_at"] and rd["data"]["sections"]["property"]["fields"]["units"]["value"] == 338
    data, issues, row = jobs.load_effective(p["id"])
    assert data.value("financials.tables.lines.rows.noi.ptd_actual") == 550 and any(i.severity == "warning" for i in issues)


def test_process_file_failure_modes(tmp_path):
    p = db.create_project("W2")
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not a workbook")
    fid = db.new_id()
    db.add_file(p["id"], fid, "bad.xlsx", str(bad), ".xlsx", 14)
    jobs.process_file(fid)
    assert db.get_file(fid)["status"] == "failed" and "Could not read" in db.get_file(fid)["error"]
    odd = make_xlsx(tmp_path / "odd.xlsx", {"S": [["hello"], ["world", 1]]})
    fid2 = db.new_id()
    db.add_file(p["id"], fid2, "odd.xlsx", str(odd), ".xlsx", odd.stat().st_size)
    jobs.process_file(fid2)
    f2 = db.get_file(fid2)
    assert f2["status"] == "unrecognized" and f2["parts"][0]["doc_type"] == "unknown" and "No recognised report" in f2["error"]
    assert db.get_report_data(p["id"])["built_at"]  # consolidation still ran, with errors flagged


def test_override_doc_type_and_recover_stuck(tmp_path):
    p = db.create_project("W3")
    path = make_xlsx(tmp_path / "x.xlsx", {"Sheet": rent_roll_rows("03/31/2026", 310, 338, 91.71, 34)})
    fid = db.new_id()
    db.add_file(p["id"], fid, "x.xlsx", str(path), ".xlsx", 10)
    db.update_file(fid, doc_type_override=DocType.YARDI_LEASE_TRADE_OUT, status="processing")
    jobs.recover_stuck_files()
    assert jobs.pool.wait_idle(10)
    f = db.get_file(fid)
    assert f["status"] == "failed" and f["parts"][0]["doc_type"] == DocType.YARDI_LEASE_TRADE_OUT
    assert f["parts"][0]["warnings"] and "Extraction failed" in f["parts"][0]["warnings"][0]
    assert "extraction failed for every part" in f["error"]
