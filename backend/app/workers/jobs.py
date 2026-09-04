"""Job functions: process one file, consolidate a project, load the effective report data.

Report rendering (generate_report) is added in Task 25 and AI drafting (draft_narratives) in Task 26.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .. import db
from ..classify.classifier import DocType, classify
from ..consolidate import validate
from ..consolidate.builder import apply_overrides, build
from ..consolidate.calc import recompute
from ..extract.registry import run_extractor
from ..models import Issue, ReportData
from ..readers.registry import UnsupportedFileType, read_document
from .pool import pool

log = logging.getLogger(__name__)
ACTIVE = ("queued", "processing")


def process_file(file_id: str) -> None:
    f = db.get_file(file_id)
    if f is None:
        return
    project_id = f["project_id"]
    db.update_file(file_id, status="processing", error=None)
    try:
        doc = read_document(Path(f["stored_path"]), file_id, f["original_filename"])
    except UnsupportedFileType as e:
        db.update_file(file_id, status="unsupported", error=str(e), processed_at=db.now())
        rebuild_if_idle(project_id)
        return
    except Exception as e:  # noqa: BLE001 - corrupt or unreadable file
        log.exception("read failed for %s", f["original_filename"])
        db.update_file(file_id, status="failed", error=f"Could not read file: {e}", processed_at=db.now())
        rebuild_if_idle(project_id)
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
        error = "No recognised report found in this file; it is not used. Set the document type manually if it should be."
    elif not extractions:
        error = "Recognised, but extraction failed for every part: " + "; ".join(w for p in parts_json for w in p["warnings"])
    else:
        error = None
    db.update_file(file_id, status="processed" if extractions or not recognised else "failed", error=error,
                   parts=parts_json, extractions=extractions, processed_at=db.now())
    rebuild_if_idle(project_id)


def rebuild_if_idle(project_id: str) -> None:
    if any(x["status"] in ACTIVE for x in db.list_files(project_id)):
        return
    build_report_data(project_id)


def build_report_data(project_id: str) -> ReportData:
    project = db.get_project(project_id)
    if project is None:
        raise KeyError(project_id)
    files = db.list_files(project_id)
    data, notes = build(project, files)
    db.save_report_data(project_id, data.model_dump(), notes)
    return data


def load_effective(project_id: str) -> tuple[ReportData, list[Issue], dict]:
    """Base data + overrides + recompute + validation. Cheap enough to run on every read."""
    row = db.get_report_data(project_id)
    if row is None or not row.get("data"):
        raise LookupError("Report data has not been built yet; upload and process files first")
    data = ReportData.model_validate(row["data"])
    stale = apply_overrides(data, row.get("overrides") or {})
    recompute(data)
    issues = validate.run(data, row.get("notes") or [], db.list_files(project_id))
    issues += [Issue(path=p, severity="info", message=f"An earlier edit to '{p}' no longer applies (the row or field disappeared after re-processing)") for p in stale]
    db.save_issues(project_id, [i.model_dump() for i in issues])
    return data, issues, row


def recover_stuck_files() -> None:
    """On startup, re-queue files that were mid-flight when the server last stopped."""
    for p in db.list_projects():
        for f in db.list_files(p["id"]):
            if f["status"] in ACTIVE:
                db.update_file(f["id"], status="queued")
                pool.submit(f"file:{f['id']}", process_file, f["id"])


def generate_report(report_id: str) -> None:
    """Render the current effective data to HTML and PDF for one report version."""
    from ..config import settings
    from ..report.render import render_html, render_pdf

    r = db.get_report(report_id)
    if r is None:
        return
    db.update_report(report_id, status="rendering", error=None)
    try:
        project = db.get_project(r["project_id"])
        data, _issues, _row = load_effective(r["project_id"])
        out_dir = settings.data_dir / "projects" / r["project_id"] / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / f"report-v{r['version']}.html"
        pdf_path = out_dir / f"report-v{r['version']}.pdf"
        html_path.write_text(render_html(data, project))
        db.update_report(report_id, html_path=str(html_path))
        render_pdf(html_path, pdf_path)
        db.update_report(report_id, status="done", pdf_path=str(pdf_path))
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
        ov = row.get("overrides") or {}
        ov.setdefault("ai_drafts", {}).update(drafts)
        db.save_overrides(project_id, ov)
        db.set_narrative(project_id, "done", None if drafts else "Nothing to draft: every narrative field already has text, or the data was insufficient")
    except Exception as e:  # noqa: BLE001 - shown to the user on the review screen
        log.exception("narrative drafting failed")
        db.set_narrative(project_id, "failed", f"{type(e).__name__}: {e}")
