from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field as PField

from .. import assets, db
from ..consolidate.corrections import CorrectionError, apply_patch
from ..report.render import render_html
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


class ResetBody(BaseModel):
    paths: list[str] = PField(default_factory=list, description="Override paths or table paths to drop; empty = drop everything")
    ai_drafts: bool = False


def ui_payload(pid: str) -> dict:
    try:
        data, issues, row = jobs.load_effective(pid)
    except LookupError as e:
        raise HTTPException(409, str(e)) from e
    return to_ui(data, issues, row)


def _built_row(pid: str) -> dict:
    row = db.get_report_data(pid)
    if row is None or not row.get("data"):
        raise HTTPException(409, "Report data has not been built yet; upload and process files first")
    return row


@router.get("/projects/{pid}/report-data")
def get_report_data(pid: str) -> dict:
    project_or_404(pid)
    return ui_payload(pid)


@router.post("/projects/{pid}/report-data/rebuild")
def rebuild_report_data(pid: str) -> dict:
    project_or_404(pid)
    if any(f["status"] in jobs.ACTIVE for f in db.list_files(pid)):
        raise HTTPException(409, "Files are still processing; wait for them to finish")
    jobs.build_report_data(pid)
    return ui_payload(pid)


@router.patch("/projects/{pid}/report-data")
def patch_report_data(pid: str, body: PatchBody) -> dict:
    """Apply a batch of corrections atomically: every change is validated against the current data,
    the result is recomputed, validated, serialised and rendered in memory, and only then persisted."""
    project = project_or_404(pid)
    row = _built_row(pid)
    from ..models import ReportData

    base = ReportData.model_validate(row["data"])
    try:
        new_ov = apply_patch(base, row.get("overrides") or {}, body.changes, body.add_rows, body.delete_rows)
    except CorrectionError as e:
        raise HTTPException(422, e.args[0]) from None
    files = db.list_files(pid)
    try:
        data, issues = jobs.effective(row, new_ov, files)
        payload = to_ui(data, issues, {**row, "overrides": new_ov})
        render_html(data, project, assets=assets.current_assets(pid))  # render preparation must succeed before we keep the batch
    except Exception as e:  # noqa: BLE001 - nothing was persisted
        raise HTTPException(422, f"The corrections could not be applied: {type(e).__name__}: {e}") from None
    db.save_overrides(pid, new_ov)
    db.save_issues(pid, [i.model_dump() for i in issues])
    return payload


@router.get("/projects/{pid}/report-data/overrides")
def get_overrides(pid: str) -> dict:
    """The raw stored corrections, readable even when the effective data cannot be built."""
    project_or_404(pid)
    row = db.get_report_data(pid)
    return (row or {}).get("overrides") or {}


@router.post("/projects/{pid}/report-data/overrides/reset")
def reset_overrides(pid: str, body: ResetBody) -> dict:
    """Administrative recovery: drop stored corrections by path without loading the effective report."""
    project_or_404(pid)
    row = db.get_report_data(pid)
    ov = (row or {}).get("overrides") or {}
    if not body.paths and not body.ai_drafts:
        ov = {}
    else:
        for p in body.paths:
            if p.endswith(".deleted"):  # '<table>.deleted' restores every row removed from that table
                (ov.get("deleted_rows") or {}).pop(p[:-8], None)
                continue
            (ov.get("fields") or {}).pop(p, None)
            (ov.get("rows") or {}).pop(p, None)
            (ov.get("deleted_rows") or {}).pop(p, None)
            (ov.get("ai_drafts") or {}).pop(p, None)
            for tpath, trows in (ov.get("rows") or {}).items():  # '<table>.rows.<key>' drops one manual row
                if p.startswith(tpath + ".rows."):
                    trows.pop(p[len(tpath) + 6:], None)
        if body.ai_drafts:
            ov.pop("ai_drafts", None)
    db.save_overrides(pid, ov)
    return ov


@router.post("/projects/{pid}/narratives", status_code=202)
def draft_narratives(pid: str) -> dict:
    from ..config import settings
    from ..workers.pool import pool

    project_or_404(pid)
    if not settings.llm_enabled:
        raise HTTPException(503, "AI drafting is not configured: set ANTHROPIC_API_KEY in .env, or install claude-agent-sdk "
                                 "and log in to Claude Code, then restart the backend")
    _built_row(pid)
    queued = pool.submit(f"narratives:{pid}", jobs.draft_narratives, pid)
    return {"status": "queued" if queued else "already_running"}
