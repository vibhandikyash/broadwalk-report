"""SQLite persistence. One short-lived connection per call; JSON columns are decoded on read."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  original_filename TEXT NOT NULL,
  stored_path TEXT NOT NULL,
  ext TEXT NOT NULL,
  size INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  error TEXT,
  parts TEXT NOT NULL DEFAULT '[]',
  extractions TEXT NOT NULL DEFAULT '[]',
  doc_type_override TEXT,
  ignored INTEGER NOT NULL DEFAULT 0,
  uploaded_at TEXT NOT NULL,
  processed_at TEXT
);
CREATE TABLE IF NOT EXISTS report_data (
  project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
  data TEXT,
  overrides TEXT NOT NULL DEFAULT '{}',
  issues TEXT NOT NULL DEFAULT '[]',
  notes TEXT NOT NULL DEFAULT '[]',
  built_at TEXT,
  narrative_status TEXT,
  narrative_error TEXT
);
CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  error TEXT,
  html_path TEXT,
  pdf_path TEXT,
  created_at TEXT NOT NULL,
  snapshot TEXT,
  complete INTEGER,
  gap_count INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS reports_project_version ON reports(project_id, version);
"""

JSON_COLS = {"parts", "extractions", "data", "overrides", "issues", "notes", "snapshot"}
REPORT_COLS = "id, project_id, version, status, error, html_path, pdf_path, created_at, complete, gap_count"
BOOL_COLS = {"ignored", "complete"}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def init_db() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        cols = {r["name"] for r in con.execute("PRAGMA table_info(reports)").fetchall()}
        for col, decl in (("snapshot", "TEXT"), ("complete", "INTEGER"), ("gap_count", "INTEGER")):
            if cols and col not in cols:  # database from a build before versions carried snapshots or completeness
                con.execute(f"ALTER TABLE reports ADD COLUMN {col} {decl}")
        con.executescript(SCHEMA)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(settings.db_path, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _decode(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in JSON_COLS:
        if k in d and isinstance(d[k], str):
            d[k] = json.loads(d[k])
    for k in BOOL_COLS:
        if k in d and d[k] is not None:
            d[k] = bool(d[k])
    return d


def _encode(cols: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in cols.items():
        if k in JSON_COLS and not isinstance(v, str):
            v = json.dumps(v, default=str)
        if k in BOOL_COLS:
            v = int(bool(v))
        out[k] = v
    return out


def _update(table: str, id_col: str, id_val: str, **cols: Any) -> None:
    if not cols:
        return
    enc = _encode(cols)
    sets = ", ".join(f"{k} = ?" for k in enc)
    with connect() as con:
        con.execute(f"UPDATE {table} SET {sets} WHERE {id_col} = ?", [*enc.values(), id_val])


# ---------- projects ----------
def create_project(name: str) -> dict:
    pid, ts = new_id(), now()
    with connect() as con:
        con.execute("INSERT INTO projects VALUES (?,?,?,?)", (pid, name, ts, ts))
    return get_project(pid)  # type: ignore[return-value]


def get_project(pid: str) -> dict | None:
    with connect() as con:
        return _decode(con.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone())


def list_projects() -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT p.*, (SELECT COUNT(*) FROM files f WHERE f.project_id = p.id) AS file_count "
            "FROM projects p ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
    return [_decode(r) for r in rows]  # type: ignore[misc]


def touch_project(pid: str) -> None:
    _update("projects", "id", pid, updated_at=now())


def delete_project(pid: str) -> None:
    with connect() as con:
        con.execute("DELETE FROM projects WHERE id = ?", (pid,))


# ---------- files ----------
def add_file(project_id: str, file_id: str, original_filename: str, stored_path: str, ext: str, size: int,
             status: str = "queued", error: str | None = None) -> dict:
    with connect() as con:
        con.execute(
            "INSERT INTO files (id, project_id, original_filename, stored_path, ext, size, uploaded_at, status, error, processed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (file_id, project_id, original_filename, stored_path, ext, size, now(), status, error,
             now() if status != "queued" else None),
        )
    touch_project(project_id)
    return get_file(file_id)  # type: ignore[return-value]


def get_file(fid: str) -> dict | None:
    with connect() as con:
        return _decode(con.execute("SELECT * FROM files WHERE id = ?", (fid,)).fetchone())


def list_files(project_id: str) -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT * FROM files WHERE project_id = ? ORDER BY uploaded_at, id", (project_id,)).fetchall()
    return [_decode(r) for r in rows]  # type: ignore[misc]


def update_file(fid: str, **cols: Any) -> None:
    _update("files", "id", fid, **cols)


def delete_file(fid: str) -> None:
    with connect() as con:
        con.execute("DELETE FROM files WHERE id = ?", (fid,))


# ---------- report data ----------
def get_report_data(project_id: str) -> dict | None:
    with connect() as con:
        return _decode(con.execute("SELECT * FROM report_data WHERE project_id = ?", (project_id,)).fetchone())


def save_report_data(project_id: str, data: dict, notes: list) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO report_data (project_id, data, notes, built_at) VALUES (?,?,?,?) "
            "ON CONFLICT(project_id) DO UPDATE SET data = excluded.data, notes = excluded.notes, built_at = excluded.built_at",
            (project_id, json.dumps(data, default=str), json.dumps(notes, default=str), now()),
        )
    touch_project(project_id)


def save_overrides(project_id: str, overrides: dict) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO report_data (project_id, overrides) VALUES (?,?) "
            "ON CONFLICT(project_id) DO UPDATE SET overrides = excluded.overrides",
            (project_id, json.dumps(overrides, default=str)),
        )
    touch_project(project_id)


def save_issues(project_id: str, issues: list) -> None:
    _update("report_data", "project_id", project_id, issues=issues)


def set_narrative(project_id: str, status: str | None, error: str | None = None) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO report_data (project_id, narrative_status, narrative_error) VALUES (?,?,?) "
            "ON CONFLICT(project_id) DO UPDATE SET narrative_status = excluded.narrative_status, "
            "narrative_error = excluded.narrative_error",
            (project_id, status, error),
        )


# ---------- reports ----------
def create_report(project_id: str, snapshot: dict | None = None, complete: bool | None = None, gap_count: int | None = None) -> dict:
    """New queued version. BEGIN IMMEDIATE serialises the read-then-insert so concurrent requests get distinct numbers."""
    rid = new_id()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        ver = con.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM reports WHERE project_id = ?", (project_id,)).fetchone()[0]
        con.execute(
            "INSERT INTO reports (id, project_id, version, status, created_at, snapshot, complete, gap_count) VALUES (?,?,?,?,?,?,?,?)",
            (rid, project_id, ver, "queued", now(), json.dumps(snapshot, default=str) if snapshot is not None else None,
             None if complete is None else int(complete), gap_count),
        )
    return get_report(rid)  # type: ignore[return-value]


def update_report(rid: str, **cols: Any) -> None:
    _update("reports", "id", rid, **cols)


def get_report(rid: str) -> dict | None:
    with connect() as con:
        return _decode(con.execute("SELECT * FROM reports WHERE id = ?", (rid,)).fetchone())


def list_reports(project_id: str) -> list[dict]:
    with connect() as con:
        rows = con.execute(f"SELECT {REPORT_COLS} FROM reports WHERE project_id = ? ORDER BY version DESC", (project_id,)).fetchall()
    return [_decode(r) for r in rows]  # type: ignore[misc]
