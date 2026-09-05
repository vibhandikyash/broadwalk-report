from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .. import assets, db
from ..consolidate.completeness import evaluate
from ..report.render import render_html
from ..workers import jobs
from ..workers.pool import pool
from .projects import project_or_404

router = APIRouter(tags=["report"])
# The preview is same-origin with the app; the policy keeps it inert even if some markup slipped past escaping.
PREVIEW_CSP = "default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data:; form-action 'none'; base-uri 'none'"


def report_public(r: dict) -> dict:
    return {"id": r["id"], "project_id": r["project_id"], "version": r["version"], "status": r["status"], "error": r["error"],
            "created_at": r["created_at"], "has_pdf": bool(r.get("pdf_path")), "complete": r.get("complete"), "gap_count": r.get("gap_count")}


def report_or_404(pid: str, rid: str) -> dict:
    r = db.get_report(rid)
    if r is None or r["project_id"] != pid:
        raise HTTPException(404, "Report not found")
    return r


@router.get("/projects/{pid}/report/preview", response_class=HTMLResponse)
def preview(pid: str) -> HTMLResponse:
    project = project_or_404(pid)
    try:
        data, issues, _row = jobs.load_effective(pid)
    except LookupError as e:
        raise HTTPException(409, str(e)) from e
    gaps = evaluate(data, issues).gap_count
    return HTMLResponse(render_html(data, project, assets=assets.current_assets(pid), draft_gaps=gaps), headers={"Content-Security-Policy": PREVIEW_CSP})


@router.post("/projects/{pid}/reports", status_code=202)
def create_report(pid: str) -> dict:
    """Queue a new version. The reviewed data is snapshotted here, at request time, so later edits never leak into it."""
    project_or_404(pid)
    try:
        data, issues, _row = jobs.load_effective(pid)
    except LookupError as e:
        raise HTTPException(409, str(e)) from e
    comp = evaluate(data, issues)
    r = db.create_report(pid, snapshot=data.model_dump(), complete=comp.complete, gap_count=comp.gap_count)
    assets.copy_for_version(pid, jobs.report_dir(pid), r["version"])
    pool.submit(f"report:{r['id']}", jobs.generate_report, r["id"])
    return report_public(db.get_report(r["id"]))


@router.get("/projects/{pid}/reports")
def list_reports(pid: str) -> list[dict]:
    project_or_404(pid)
    return [report_public(r) for r in db.list_reports(pid)]


@router.get("/projects/{pid}/reports/{rid}")
def get_report(pid: str, rid: str) -> dict:
    return report_public(report_or_404(pid, rid))


@router.get("/projects/{pid}/reports/{rid}/snapshot")
def report_snapshot(pid: str, rid: str) -> JSONResponse:
    """The exact reviewed data this version was rendered from."""
    r = report_or_404(pid, rid)
    if not r.get("snapshot"):
        raise HTTPException(404, "This version has no stored snapshot")
    return JSONResponse(r["snapshot"])


@router.get("/projects/{pid}/reports/{rid}/download")
def download_report(pid: str, rid: str) -> FileResponse:
    r = report_or_404(pid, rid)
    if r["status"] != "done" or not r.get("pdf_path"):
        raise HTTPException(409, r.get("error") or "The PDF is not ready yet")
    project = project_or_404(pid)
    stem = re.sub(r"[^A-Za-z0-9]+", "-", project["name"]).strip("-").lower() or "report"
    suffix = "-draft" if r.get("gap_count") else ""  # a structurally generated but incomplete report is named as a draft
    return FileResponse(r["pdf_path"], media_type="application/pdf", filename=f"{stem}-v{r['version']}{suffix}.pdf")
