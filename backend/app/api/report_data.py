from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field as PField

from .. import db
from ..workers import jobs
from .projects import project_or_404
from .serialize import to_ui

router = APIRouter(tags=["report-data"])


class Change(BaseModel):
    path: str
    value: Any = None


class AddRow(BaseModel):
    table: str
    key: str | None = None
    values: dict[str, Any] = PField(default_factory=dict)


class DeleteRow(BaseModel):
    table: str
    key: str


class PatchBody(BaseModel):
    changes: list[Change] = PField(default_factory=list)
    add_rows: list[AddRow] = PField(default_factory=list)
    delete_rows: list[DeleteRow] = PField(default_factory=list)


def ui_payload(pid: str) -> dict:
    try:
        data, issues, row = jobs.load_effective(pid)
    except LookupError as e:
        raise HTTPException(409, str(e)) from e
    return to_ui(data, issues, row)


@router.get("/projects/{pid}/report-data")
def get_report_data(pid: str) -> dict:
    project_or_404(pid)
    return ui_payload(pid)


@router.post("/projects/{pid}/report-data/rebuild")
def rebuild_report_data(pid: str) -> dict:
    project_or_404(pid)
    if any(f["status"] in ("queued", "processing") for f in db.list_files(pid)):
        raise HTTPException(409, "Files are still processing; wait for them to finish")
    jobs.build_report_data(pid)
    return ui_payload(pid)


@router.patch("/projects/{pid}/report-data")
def patch_report_data(pid: str, body: PatchBody) -> dict:
    project_or_404(pid)
    row = db.get_report_data(pid)
    if row is None or not row.get("data"):
        raise HTTPException(409, "Report data has not been built yet; upload and process files first")
    ov = row.get("overrides") or {}
    fields = ov.setdefault("fields", {})
    rows = ov.setdefault("rows", {})
    deleted = ov.setdefault("deleted_rows", {})
    for ch in body.changes:
        if ch.value is None or ch.value == "":
            fields.pop(ch.path, None)
        else:
            fields[ch.path] = ch.value
    for ar in body.add_rows:
        key = ar.key or f"manual-{db.new_id()[:6]}"
        rows.setdefault(ar.table, {})[key] = ar.values
        if key in deleted.get(ar.table, []):
            deleted[ar.table].remove(key)
    for dr in body.delete_rows:
        if dr.key in rows.get(dr.table, {}):
            rows[dr.table].pop(dr.key)
        else:
            deleted.setdefault(dr.table, [])
            if dr.key not in deleted[dr.table]:
                deleted[dr.table].append(dr.key)
        prefix = f"{dr.table}.rows.{dr.key}."
        for p in [p for p in fields if p.startswith(prefix)]:
            fields.pop(p)
    db.save_overrides(pid, ov)
    return ui_payload(pid)


@router.post("/projects/{pid}/narratives", status_code=202)
def draft_narratives(pid: str) -> dict:
    from ..config import settings
    from ..workers.pool import pool

    project_or_404(pid)
    if not settings.llm_enabled:
        raise HTTPException(503, "AI drafting is not configured: set ANTHROPIC_API_KEY in .env, or install claude-agent-sdk "
                                 "and log in to Claude Code, then restart the backend")
    row = db.get_report_data(pid)
    if row is None or not row.get("data"):
        raise HTTPException(409, "Report data has not been built yet")
    queued = pool.submit(f"narratives:{pid}", jobs.draft_narratives, pid)
    return {"status": "queued" if queued else "already_running"}
