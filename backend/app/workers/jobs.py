"""Job functions: process one file, consolidate a project, load the effective report data, render a
report version from its snapshot, draft narratives. Every terminal file transition ends in
rebuild_if_idle(), the single project-level completion check.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from .. import assets, db
from ..classify.classifier import DocType, classify
from ..consolidate import corrections, validate
from ..consolidate.builder import apply_overrides, build
from ..consolidate.calc import recompute
from ..extract.registry import run_extractor
from ..models import Issue, ReportData
from ..readers.pdf_reader import NoTextError
from ..readers.registry import UnsupportedFileType, read_document
from .pool import pool

log = logging.getLogger(__name__)
ACTIVE = ("queued", "processing")
_build_locks: dict[str, threading.Lock] = {}
_build_locks_guard = threading.Lock()


def _build_lock(project_id: str) -> threading.Lock:
    with _build_locks_guard:
        return _build_locks.setdefault(project_id, threading.Lock())


def process_file(file_id: str) -> None:
    f = db.get_file(file_id)
    if f is None:
        return
    db.update_file(file_id, status="processing", error=None)
    try:
        _process(f)
    except Exception as e:  # noqa: BLE001 - a crash must leave the file terminal, never stuck in 'processing'
        log.exception("processing failed for %s", f["original_filename"])
        db.update_file(file_id, status="failed", error=f"Processing failed: {type(e).__name__}: {e}", processed_at=db.now())
    latest = db.get_file(file_id)
    if latest and latest.get("doc_type_override") != f.get("doc_type_override"):
        process_file(file_id)  # the type was changed while this run was in flight: run once more with the new type
        return
    rebuild_if_idle(f["project_id"])


def _process(f: dict) -> None:
    file_id = f["id"]
    try:
        doc = read_document(Path(f["stored_path"]), file_id, f["original_filename"])
    except UnsupportedFileType as e:
        db.update_file(file_id, status="unsupported", error=str(e), processed_at=db.now())
        return
    except NoTextError as e:
        db.update_file(file_id, status="needs_ocr", processed_at=db.now(),
                       error=f"{e} Export a text-based PDF from the source system, or enter the values on the Review page.")
        return
    except Exception as e:  # noqa: BLE001 - corrupt or unreadable file
        log.warning("read failed for %s: %s", f["original_filename"], e)
        db.update_file(file_id, status="failed", error=f"Could not read file: {e}", processed_at=db.now())
        return
    parts = classify(doc)
    if f.get("doc_type_override") and len(parts) == 1:
        parts[0].doc_type, parts[0].confidence = f["doc_type_override"], 1.0
    extractions, parts_json = [], []
    for part in parts:
        pj = {**part.to_json(), "warnings": []}
        if part.doc_type != DocType.UNKNOWN.value:
            try:
                ex = run_extractor(part)
                extractions.append(ex.model_dump())
                pj["warnings"] = list(ex.warnings)
            except Exception as e:  # noqa: BLE001 - one part failing must not fail the file
                log.warning("extraction failed for %s %s: %s", f["original_filename"], part.locator, e)
                pj["warnings"] = [f"Extraction failed: {e}"]
        parts_json.append(pj)
    recognised = [p for p in parts_json if p["doc_type"] != DocType.UNKNOWN.value]
    if not recognised:
        status, error = "unrecognized", "No recognised report found in this file, so it is not used. Set the document type manually if it should be."
    elif not extractions:
        status, error = "failed", "Recognised, but extraction failed for every part: " + "; ".join(w for p in parts_json for w in p["warnings"])
    else:
        status, error = "processed", None
    db.update_file(file_id, status=status, error=error, parts=parts_json, extractions=extractions, processed_at=db.now())


def rebuild_if_idle(project_id: str) -> None:
    """Project-level completion check: consolidate once no file is queued or processing.

    Idempotent and serialised per project, so it is safe to call from every transition, the upload
    handler and a project read; the worst case is one redundant build.
    """
    with _build_lock(project_id):
        if db.get_project(project_id) is None:
            return
        files = db.list_files(project_id)
        if any(x["status"] in ACTIVE for x in files):
            return
        _build(project_id, files)


def build_report_data(project_id: str) -> ReportData:
    project = db.get_project(project_id)
    if project is None:
        raise KeyError(project_id)
    with _build_lock(project_id):
        return _build(project_id, db.list_files(project_id))


def _build(project_id: str, files: list[dict]) -> ReportData:
    project = db.get_project(project_id)
    if project is None:
        raise KeyError(project_id)
    data, notes = build(project, files)
    db.save_report_data(project_id, data.model_dump(), notes)
    return data


def effective(row: dict, overrides: dict | None, files: list[dict]) -> tuple[ReportData, list[Issue]]:
    """Base data + (sanitised) overrides + recompute + validation, without touching the database."""
    data = ReportData.model_validate(row["data"])
    clean, dropped = corrections.sanitize(data, row.get("overrides") or {} if overrides is None else overrides)
    stale = apply_overrides(data, clean)
    recompute(data)
    issues = validate.run(data, row.get("notes") or [], files)
    issues += [Issue(path=p, severity="info", message=f"An earlier edit to '{p}' no longer applies (the row or field disappeared after re-processing)") for p in stale]
    issues += [Issue(path=d.split(":", 1)[0], severity="warning",
                     message=f"A stored correction was ignored because it no longer fits its field ({d}). Reset it under Corrections if it keeps appearing.") for d in dropped]
    return data, issues


def load_effective(project_id: str) -> tuple[ReportData, list[Issue], dict]:
    """Effective report data for a project; also refreshes the stored issue list."""
    row = db.get_report_data(project_id)
    if row is None or not row.get("data"):
        raise LookupError("Report data has not been built yet; upload and process files first")
    data, issues = effective(row, None, db.list_files(project_id))
    db.save_issues(project_id, [i.model_dump() for i in issues])
    return data, issues, row


def recover_stuck_files() -> None:
    """On startup, re-queue files, report versions and narrative runs that were mid-flight when the server last stopped."""
    for p in db.list_projects():
        for f in db.list_files(p["id"]):
            if f["status"] in ACTIVE:
                db.update_file(f["id"], status="queued")
                pool.submit(f"file:{f['id']}", process_file, f["id"])
        for r in db.list_reports(p["id"]):
            if r["status"] in ("queued", "rendering"):
                db.update_report(r["id"], status="queued")
                pool.submit(f"report:{r['id']}", generate_report, r["id"])
        rd = db.get_report_data(p["id"])
        if rd and rd.get("narrative_status") == "running":
            from ..config import settings

            if settings.llm_enabled:
                pool.submit(f"narratives:{p['id']}", draft_narratives, p["id"])
            else:
                db.set_narrative(p["id"], "failed", "Drafting was interrupted by a restart and no AI provider is configured now")
        rebuild_if_idle(p["id"])


def report_dir(project_id: str) -> Path:
    from ..config import settings

    out = settings.data_dir / "projects" / project_id / "reports"
    out.mkdir(parents=True, exist_ok=True)
    return out


def generate_report(report_id: str) -> None:
    """Render one report version to HTML and PDF from the snapshot taken when it was requested."""
    from ..report.render import LayoutOverflow, render_html, render_pdf

    r = db.get_report(report_id)
    if r is None:
        return
    db.update_report(report_id, status="rendering", error=None)
    try:
        project = db.get_project(r["project_id"])
        if r.get("snapshot"):
            data = ReportData.model_validate(r["snapshot"])
        else:  # a version queued by an older build without snapshots
            data, _issues, _row = load_effective(r["project_id"])
            db.update_report(report_id, snapshot=data.model_dump())
        out_dir = report_dir(r["project_id"])
        stem = f"report-v{r['version']}"
        (out_dir / f"{stem}.json").write_text(json.dumps(data.model_dump(), indent=1, default=str))
        html_path, pdf_path = out_dir / f"{stem}.html", out_dir / f"{stem}.pdf"
        html_path.write_text(render_html(data, project, assets=assets.version_assets(out_dir, r["version"])))
        db.update_report(report_id, html_path=str(html_path))
        render_pdf(html_path, pdf_path)
        db.update_report(report_id, status="done", pdf_path=str(pdf_path))
    except LayoutOverflow as e:
        log.warning("report %s rejected: %s", report_id, e)
        db.update_report(report_id, status="failed", error=str(e))
    except Exception as e:  # noqa: BLE001 - surface the failure on the version row
        log.exception("report render failed for %s", report_id)
        db.update_report(report_id, status="failed",
                         error=f"{type(e).__name__}: {e}. If Chromium is missing run: python -m playwright install chromium")


def draft_narratives(project_id: str) -> None:
    """Draft empty narrative fields with the LLM and store them as ai_drafts in the overrides."""
    from ..services.narrative import draft_all

    db.set_narrative(project_id, "running", None)
    try:
        data, _issues, row = load_effective(project_id)
        drafts = draft_all(data)
        ov = (db.get_report_data(project_id) or {}).get("overrides") or {}  # re-read: the reviewer may have saved meanwhile
        ov.setdefault("ai_drafts", {}).update(drafts)
        db.save_overrides(project_id, ov)
        db.set_narrative(project_id, "done", None if drafts else "Nothing to draft: every narrative field already has text, or the data was insufficient")
    except Exception as e:  # noqa: BLE001 - shown to the user on the review screen
        log.exception("narrative drafting failed")
        db.set_narrative(project_id, "failed", f"{type(e).__name__}: {e}")
