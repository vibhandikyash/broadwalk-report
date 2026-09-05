# backend/tests/test_db.py
from app import db


def setup_module(module):
    db.init_db()


def test_project_and_file_roundtrip():
    p = db.create_project("Boardwalk 2Q26")
    assert p["name"] == "Boardwalk 2Q26" and p["id"]
    fid = db.new_id()
    f = db.add_file(p["id"], fid, "a.xlsx", "/tmp/a.xlsx", ".xlsx", 123)
    assert f["status"] == "queued" and f["parts"] == [] and f["ignored"] is False
    db.update_file(fid, status="processed", parts=[{"doc_type": "x"}], extractions=[{"data": {"a": 1}}])
    f2 = db.get_file(fid)
    assert f2["status"] == "processed" and f2["parts"][0]["doc_type"] == "x"
    assert f2["extractions"][0]["data"]["a"] == 1
    assert next(x for x in db.list_projects() if x["id"] == p["id"])["file_count"] == 1
    db.delete_file(fid)
    assert db.list_files(p["id"]) == []


def test_report_data_upsert_keeps_overrides():
    p = db.create_project("P")
    assert db.get_report_data(p["id"]) is None
    db.save_report_data(p["id"], {"sections": {}}, notes=[{"m": 1}])
    db.save_overrides(p["id"], {"fields": {"a.fields.b": 5}})
    db.save_report_data(p["id"], {"sections": {"x": {}}}, notes=[])
    row = db.get_report_data(p["id"])
    assert row["overrides"] == {"fields": {"a.fields.b": 5}}
    assert row["data"] == {"sections": {"x": {}}}
    assert row["built_at"]


def test_report_versions_increment():
    p = db.create_project("P")
    r1 = db.create_report(p["id"])
    r2 = db.create_report(p["id"])
    assert (r1["version"], r2["version"]) == (1, 2)
    db.update_report(r2["id"], status="done", pdf_path="/x.pdf")
    assert db.get_report(r2["id"])["status"] == "done"
    assert [r["version"] for r in db.list_reports(p["id"])] == [2, 1]
