from __future__ import annotations

import shutil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field as PField

from .. import db
from ..config import settings
from ..workers.pool import pool

router = APIRouter(tags=["projects"])


class ProjectIn(BaseModel):
    name: str = PField(min_length=1, max_length=200)


def file_public(f: dict) -> dict:
    """File record without the (large) extraction payload."""
    return {k: v for k, v in f.items() if k != "extractions"}


def project_or_404(pid: str) -> dict:
    p = db.get_project(pid)
    if p is None:
        raise HTTPException(404, "Project not found")
    return p


def _stage(files: list[dict], rd: dict | None, reports: list[dict]) -> str:
    if not files:
        return "upload"
    if any(f["status"] in ("queued", "processing") for f in files):
        return "processing"
    if any(r["status"] == "done" for r in reports):
        return "generated"
    return "review" if rd and rd.get("built_at") else "processing"


def project_detail(pid: str) -> dict:
    p = project_or_404(pid)
    files = db.list_files(pid)
    rd = db.get_report_data(pid)
    reports = db.list_reports(pid)
    return {**p, "files": [file_public(f) for f in files], "reports": reports, "stage": _stage(files, rd, reports),
            "report_built": bool(rd and rd.get("built_at")),
            "processing": [f["id"] for f in files if pool.is_running(f"file:{f['id']}")]}


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn) -> dict:
    return db.create_project(body.name.strip())


@router.get("/projects")
def list_projects() -> list[dict]:
    return db.list_projects()


@router.get("/projects/{pid}")
def get_project(pid: str) -> dict:
    return project_detail(pid)


@router.delete("/projects/{pid}", status_code=204)
def delete_project(pid: str) -> None:
    project_or_404(pid)
    db.delete_project(pid)
    shutil.rmtree(settings.data_dir / "projects" / pid, ignore_errors=True)
