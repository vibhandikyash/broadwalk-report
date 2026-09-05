from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import db
from ..classify.classifier import DOC_TYPE_LABELS, DocType
from ..config import settings
from ..readers.registry import SUPPORTED_EXTENSIONS
from ..workers import jobs
from ..workers.pool import pool
from .projects import file_public, project_or_404

router = APIRouter(tags=["files"])
CHUNK = 1024 * 1024
NOT_REPROCESSABLE = ("unsupported",)


class FilePatch(BaseModel):
    ignored: bool | None = None
    doc_type_override: str | None = None
    clear_override: bool = False


def _upload_limit() -> int:
    return settings.max_upload_mb * 1024 * 1024


def file_or_404(pid: str, fid: str) -> dict:
    f = db.get_file(fid)
    if f is None or f["project_id"] != pid:
        raise HTTPException(404, "File not found")
    return f


def _job_key(fid: str) -> str:
    return f"file:{fid}"


@router.get("/doc-types")
def doc_types() -> list[dict]:
    return [{"key": t.value, "label": label} for t, label in DOC_TYPE_LABELS.items()]


@router.post("/projects/{pid}/files", status_code=201)
async def upload_files(pid: str, files: list[UploadFile] = File(...)) -> list[dict]:
    project_or_404(pid)
    saved: list[dict] = []
    for uf in files:  # phase 1: every record is durable, with its final supported/unsupported state, before any job starts
        name = Path(uf.filename or "upload").name
        ext = Path(name).suffix.lower()
        fid = db.new_id()
        dest = settings.data_dir / "projects" / pid / "uploads" / f"{fid}{ext}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with dest.open("wb") as fh:
            while chunk := await uf.read(CHUNK):
                size += len(chunk)
                if size > _upload_limit():
                    fh.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(413, f"{name} exceeds the {settings.max_upload_mb} MB upload limit")
                fh.write(chunk)
        if ext in SUPPORTED_EXTENSIONS:
            saved.append(db.add_file(pid, fid, name, str(dest), ext, size))
        else:
            saved.append(db.add_file(pid, fid, name, str(dest), ext, size, status="unsupported",
                                     error=f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"))
    for rec in saved:  # phase 2: enqueue
        if rec["status"] == "queued":
            pool.submit(_job_key(rec["id"]), jobs.process_file, rec["id"])
    jobs.rebuild_if_idle(pid)  # covers a batch with nothing to process, and jobs that finished before this line
    return [file_public(r) for r in saved]


@router.get("/projects/{pid}/files")
def list_files(pid: str) -> list[dict]:
    project_or_404(pid)
    return [file_public(f) for f in db.list_files(pid)]


@router.get("/projects/{pid}/files/{fid}/extraction")
def file_extraction(pid: str, fid: str) -> dict:
    f = file_or_404(pid, fid)
    return {"parts": f["parts"], "extractions": f["extractions"]}


def _queue(f: dict) -> None:
    if f["status"] in jobs.ACTIVE or pool.is_running(_job_key(f["id"])):
        raise HTTPException(409, f"{f['original_filename']} is still processing; try again when it has finished")
    db.update_file(f["id"], status="queued", error=None)
    pool.submit(_job_key(f["id"]), jobs.process_file, f["id"])


@router.patch("/projects/{pid}/files/{fid}")
def patch_file(pid: str, fid: str, body: FilePatch) -> dict:
    f = file_or_404(pid, fid)
    cols: dict = {}
    if body.ignored is not None:
        cols["ignored"] = body.ignored
    if body.clear_override:
        cols["doc_type_override"] = None
    elif body.doc_type_override is not None:
        if body.doc_type_override not in {t.value for t in DocType}:
            raise HTTPException(422, f"Unknown document type '{body.doc_type_override}'")
        cols["doc_type_override"] = body.doc_type_override
    retype = "doc_type_override" in cols and f["status"] not in NOT_REPROCESSABLE and cols["doc_type_override"] != f.get("doc_type_override")
    if retype and (f["status"] in jobs.ACTIVE or pool.is_running(_job_key(fid))):
        raise HTTPException(409, f"{f['original_filename']} is still processing; change its type when it has finished")
    db.update_file(fid, **cols)
    if retype:
        _queue(db.get_file(fid))
    else:
        jobs.rebuild_if_idle(pid)
    return file_public(db.get_file(fid))


@router.post("/projects/{pid}/files/{fid}/reprocess")
def reprocess_file(pid: str, fid: str) -> dict:
    f = file_or_404(pid, fid)
    if f["status"] in NOT_REPROCESSABLE:
        raise HTTPException(409, "Unsupported file types cannot be processed")
    _queue(f)
    return file_public(db.get_file(fid))


@router.delete("/projects/{pid}/files/{fid}", status_code=204)
def delete_file(pid: str, fid: str) -> None:
    f = file_or_404(pid, fid)
    if f["status"] in jobs.ACTIVE or pool.is_running(_job_key(fid)):
        raise HTTPException(409, f"{f['original_filename']} is still processing; remove it when it has finished")
    db.delete_file(fid)
    Path(f["stored_path"]).unlink(missing_ok=True)
    jobs.rebuild_if_idle(pid)
