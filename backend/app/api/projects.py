from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field as PField

from .. import assets, db
from ..config import settings
from ..workers.pool import pool

router = APIRouter(tags=["projects"])
ACTIVE = ("queued", "processing")


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
    if any(f["status"] in ACTIVE for f in files):
        return "processing"
    if not (rd and rd.get("built_at")):
        return "processing"
    return "generated" if any(r["status"] == "done" for r in reports) else "review"


def project_detail(pid: str) -> dict:
    from ..workers import jobs

    p = project_or_404(pid)
    files = db.list_files(pid)
    rd = db.get_report_data(pid)
    if files and not any(f["status"] in ACTIVE for f in files) and not (rd and rd.get("built_at")):
        jobs.rebuild_if_idle(pid)  # every file is terminal but nothing consolidated: self-heal on read
        rd = db.get_report_data(pid)
    reports = db.list_reports(pid)
    return {**p, "files": [file_public(f) for f in files], "reports": reports, "stage": _stage(files, rd, reports),
            "report_built": bool(rd and rd.get("built_at")), "assets": assets.present(pid),
            "processing": [f["id"] for f in files if pool.is_running(f"file:{f['id']}")]}


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn) -> dict:
    return db.create_project(body.name.strip())


def project_summary(row: dict) -> dict:
    """A project as the index shows it: where it has got to, and what is waiting.

    The stage follows the same rules as _stage above, from the counts the list query already returns,
    so the index costs one query rather than a full read per project.
    """
    built = bool(row.get("built_at"))
    version = row.get("latest_version")
    if not row.get("file_count"):
        stage = "upload"
    elif row.get("files_active") or not built:
        stage = "processing"
    else:
        stage = "generated" if version else "review"
    return {"id": row["id"], "name": row["name"], "created_at": row["created_at"], "updated_at": row["updated_at"],
            "file_count": row.get("file_count") or 0, "files_attention": row.get("files_attention") or 0,
            "stage": stage, "report_built": built, "latest_version": version,
            "latest_gap_count": row.get("latest_gap_count")}


@router.get("/projects")
def list_projects() -> list[dict]:
    return [project_summary(r) for r in db.list_projects()]


@router.get("/projects/{pid}")
def get_project(pid: str) -> dict:
    return project_detail(pid)


@router.delete("/projects/{pid}", status_code=204)
def delete_project(pid: str) -> None:
    project_or_404(pid)
    db.delete_project(pid)
    shutil.rmtree(settings.data_dir / "projects" / pid, ignore_errors=True)


@router.put("/projects/{pid}/assets/{kind}")
async def put_asset(pid: str, kind: str, file: UploadFile = File(...)) -> dict:
    """Cover photo or logo for the report (png, jpg or webp)."""
    project_or_404(pid)
    if kind not in assets.KINDS:
        raise HTTPException(404, f"Unknown asset '{kind}'; use one of {', '.join(assets.KINDS)}")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in assets.IMAGE_TYPES:
        raise HTTPException(422, f"Unsupported image type '{suffix}'. Use png, jpg or webp")
    content = await file.read(assets.MAX_BYTES + 1)
    if len(content) > assets.MAX_BYTES:
        raise HTTPException(413, f"Images are limited to {assets.MAX_BYTES // (1024 * 1024)} MB")
    assets.save(pid, kind, suffix, content)
    db.touch_project(pid)
    return assets.present(pid)


@router.get("/projects/{pid}/assets/{kind}")
def get_asset(pid: str, kind: str) -> FileResponse:
    project_or_404(pid)
    p = assets.find(pid, kind) if kind in assets.KINDS else None
    if p is None:
        raise HTTPException(404, "No such image")
    return FileResponse(p, media_type=assets.IMAGE_TYPES[p.suffix.lower()])


@router.delete("/projects/{pid}/assets/{kind}")
def delete_asset(pid: str, kind: str) -> dict:
    project_or_404(pid)
    if kind not in assets.KINDS:
        raise HTTPException(404, "No such image")
    assets.remove(pid, kind)
    db.touch_project(pid)
    return assets.present(pid)
