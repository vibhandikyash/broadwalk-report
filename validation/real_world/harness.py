"""Public-HTTP workflow harness for independent generalization scenarios.

Every scenario is `structural` (ingestion, extraction and a PDF work despite missing information; its
expected gaps and warnings are asserted exactly) or `complete` (after the manifest's reviewer corrections,
row additions, mock narratives and assets, the completeness specification reports no gap, the version is
marked complete, and every page of the PDF carries the expected content). A ten-page PDF alone never passes.
"""
from __future__ import annotations

import io
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from . import pdf_checks

ROOT = Path(__file__).resolve().parent
SCENARIO_ROOT = ROOT / "scenarios"
CLASSIFICATIONS = ("structural", "complete")


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    directory: Path
    manifest: dict[str, Any]

    @property
    def classification(self) -> str:
        return self.manifest["classification"]


def discover_scenarios(root: Path = SCENARIO_ROOT) -> list[Scenario]:
    scenarios: list[Scenario] = []
    for manifest_path in sorted(root.glob("*/expected.json")):
        manifest = json.loads(manifest_path.read_text())
        scenario_id = str(manifest.get("id") or "")
        if scenario_id != manifest_path.parent.name:
            raise ValueError(f"{manifest_path}: id must match its directory name")
        sources = manifest.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"{manifest_path}: sources must be a non-empty list")
        if manifest.get("classification") not in CLASSIFICATIONS:
            raise ValueError(f"{manifest_path}: classification must be one of {CLASSIFICATIONS}")
        scenarios.append(Scenario(scenario_id, manifest_path.parent, manifest))
    return scenarios


def flatten_ui(payload: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for section in payload.get("sections", []):
        for field in section.get("fields", []):
            values[field["path"]] = field.get("effective")
        for table in section.get("tables", []):
            for row in table.get("rows", []):
                for cell in row.get("cells", []):
                    values[cell["path"]] = cell.get("effective")
            for cell in table.get("totals", []):
                values[cell["path"]] = cell.get("effective")
    return values


def ui_fields(payload: dict[str, Any]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for section in payload.get("sections", []):
        for field in section.get("fields", []):
            out[field["path"]] = field
        for table in section.get("tables", []):
            for row in table.get("rows", []):
                for cell in row.get("cells", []):
                    out[cell["path"]] = cell
    return out


def flatten_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    eff = lambda f: f.get("override") if f.get("override") is not None else f.get("value")  # noqa: E731
    for sk, section in snapshot.get("sections", {}).items():
        for fk, field in section.get("fields", {}).items():
            values[f"{sk}.fields.{fk}"] = eff(field)
        for tk, table in section.get("tables", {}).items():
            for rk, row in table.get("rows", {}).items():
                for ck, field in row.items():
                    values[f"{sk}.tables.{tk}.rows.{rk}.{ck}"] = eff(field)
            for ck, field in table.get("totals", {}).items():
                values[f"{sk}.tables.{tk}.totals.{ck}"] = eff(field)
    return values


def value_mismatch(actual: Any, expectation: dict[str, Any]) -> str | None:
    expected = expectation.get("value")
    tolerance = expectation.get("tolerance", 0)
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            return f"expected numeric {expected!r}, observed {actual!r}"
        if not math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=float(tolerance)):
            return f"expected {expected!r} +/- {tolerance!r}, observed {actual!r}"
    elif actual != expected:
        return f"expected {expected!r}, observed {actual!r}"
    return None


def _expect_values(observed: dict[str, Any], expected: dict[str, dict[str, Any]], failures: list[str], prefix: str) -> None:
    for field_path, expectation in expected.items():
        if field_path not in observed:
            failures.append(f"{prefix} {field_path}: path is absent")
            continue
        if mismatch := value_mismatch(observed[field_path], expectation):
            failures.append(f"{prefix} {field_path}: {mismatch}")


def _response_json(response, expected_status: int, failures: list[str], label: str) -> Any:
    if response.status_code != expected_status:
        failures.append(f"{label}: HTTP {response.status_code}, expected {expected_status}: {response.text[:500]}")
        return None
    try:
        return response.json()
    except Exception as exc:  # noqa: BLE001 - evidence should retain malformed HTTP responses
        failures.append(f"{label}: response was not JSON ({type(exc).__name__}: {exc})")
        return None


def _issues_text(payload: dict[str, Any]) -> str:
    return "\n".join(str(issue.get("message") or "") for issue in payload.get("issues", []))


def _file_evidence(detail: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"name": f.get("original_filename"), "status": f.get("status"), "error": f.get("error"), "parts": f.get("parts") or []} for f in detail.get("files", [])]


def _effective_corpus(values: dict[str, Any]) -> str:
    return json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)


def _png(color: tuple[int, int, int]) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (640, 360), color).save(buf, "PNG")
    return buf.getvalue()


def _wait_narratives(client, project_id: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    seen_running = False
    while time.monotonic() < deadline:
        ui = client.get(f"/api/projects/{project_id}/report-data").json()
        status = ui.get("narrative_status")
        if status == "running":
            seen_running = True
        elif status in ("done", "failed") and (seen_running or status == "done"):
            return ui
        time.sleep(0.5)
    return client.get(f"/api/projects/{project_id}/report-data").json()


def provenance_matrix(snapshot: dict[str, Any], expected_gaps: set[str], observed_gaps: set[str]) -> dict[str, Any]:
    """Per page: how each value came to be. A missing value is unexpected only when the completeness
    specification reports it as a gap that the scenario did not declare; everything else missing is
    intentional (a declared gap) or optional."""
    pages: dict[int, dict[str, int]] = {}
    for sk, section in snapshot.get("sections", {}).items():
        page = int(section.get("page") or 0)
        counts = pages.setdefault(page, {"extracted": 0, "derived": 0, "corrected": 0, "drafted": 0, "missing_intentional": 0, "missing_unexpected": 0, "conflict": 0})

        def tally(path: str, f: dict) -> None:
            value = f.get("override") if f.get("override") is not None else f.get("value")
            status = f.get("status")
            if f.get("override") is not None:
                counts["corrected"] += 1
            elif status == "ai_draft":
                counts["drafted"] += 1
            elif status == "derived":
                counts["derived" if value not in (None, "") else "missing_intentional"] += 1
            elif status == "conflict":
                counts["conflict"] += 1
            elif value not in (None, ""):
                counts["extracted"] += 1
            elif path in observed_gaps and path not in expected_gaps:
                counts["missing_unexpected"] += 1
            else:
                counts["missing_intentional"] += 1

        for fk, f in section.get("fields", {}).items():
            tally(f"{sk}.fields.{fk}", f)
        for tk, table in section.get("tables", {}).items():
            for rk, row in table.get("rows", {}).items():
                for ck, f in row.items():
                    tally(f"{sk}.tables.{tk}.rows.{rk}.{ck}", f)
    return {str(k): v for k, v in sorted(pages.items())}


def run_scenario(client, scenario: Scenario | Path, output_dir: Path, timeout: float = 240) -> dict[str, Any]:
    """Run one scenario through upload, review/correction, narratives, assets, completeness, report and snapshot APIs."""
    from app.workers.pool import pool

    if isinstance(scenario, Path):
        scenario = Scenario(scenario.name, scenario, json.loads((scenario / "expected.json").read_text()))
    manifest = scenario.manifest
    classification = manifest["classification"]
    scenario_output = output_dir / scenario.scenario_id
    scenario_output.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    warnings: list[str] = []
    result: dict[str, Any] = {"scenario": scenario.scenario_id, "classification": classification, "description": manifest.get("description"),
                              "passed": False, "failures": failures, "warnings": warnings, "files": [], "observed_values": {}, "report": {}, "completeness": {}}
    expected_gaps = set(manifest.get("expected_gaps", []))
    try:
        created = _response_json(client.post("/api/projects", json={"name": manifest["project_name"]}), 201, failures, "create project")
        if not created:
            raise RuntimeError("project creation failed")
        project_id = created["id"]
        result["project_id"] = project_id
        api = f"/api/projects/{project_id}"

        # 1. upload every source through the API
        source_dir = scenario.directory / "sources"
        for source in manifest["sources"]:
            source_path = source_dir / source["name"]
            upload_name = source.get("upload_as") or source_path.name
            if not source_path.is_file():
                failures.append(f"source is missing: {source_path}")
                continue
            with source_path.open("rb") as handle:
                response = client.post(f"{api}/files", files=[("files", (upload_name, handle, "application/octet-stream"))])
            _response_json(response, 201, failures, f"upload {upload_name}")
        if failures:
            raise RuntimeError("one or more source uploads failed")
        if not pool.wait_idle(timeout):
            failures.append(f"ingestion did not become idle within {timeout:g} seconds")
            raise RuntimeError("ingestion timeout")
        detail = _response_json(client.get(api), 200, failures, "load project") or {}
        result["stage_after_ingestion"] = detail.get("stage")
        result["files"] = _file_evidence(detail)
        files_by_name = {item.get("original_filename"): item for item in detail.get("files", [])}
        for source in manifest["sources"]:
            upload_name = source.get("upload_as") or source["name"]
            observed_file = files_by_name.get(upload_name)
            if observed_file is None:
                failures.append(f"file record is missing for {upload_name}")
            elif observed_file.get("status") != source["status"]:
                failures.append(f"{upload_name}: expected status {source['status']!r}, observed {observed_file.get('status')!r}")

        # 2. extracted values and issues before any correction
        ui = _response_json(client.get(f"{api}/report-data"), 200, failures, "load report data") or {}
        before = flatten_ui(ui)
        result["observed_values"]["before_corrections"] = {path: before.get(path) for path in manifest.get("expected_values", {})}
        _expect_values(before, manifest.get("expected_values", {}), failures, "before corrections")
        _expect_values(before, manifest.get("expected_before_corrections_only", {}), failures, "before corrections")  # values a correction will change
        issue_text = _issues_text(ui)
        result["issues_before_corrections"] = ui.get("issues", [])
        for fragment in manifest.get("issues_contains", []):
            if fragment.casefold() not in issue_text.casefold():
                failures.append(f"expected issue fragment was absent: {fragment!r}")
        for tpath, n in manifest.get("expected_table_rows", {}).items():
            rows = [t for s in ui.get("sections", []) for t in s.get("tables", []) if t["path"] == tpath]
            observed = len(rows[0]["rows"]) if rows else None
            if observed != n:
                failures.append(f"table {tpath}: expected {n} rows, observed {observed}")

        # 3. corrections that must be refused, and must change nothing
        for bad in manifest.get("invalid_corrections", []):
            r = client.patch(f"{api}/report-data", json={"changes": [{"path": bad["path"], "value": bad["value"]}]})
            if r.status_code != 422:
                failures.append(f"invalid correction {bad['path']}={bad['value']!r} returned HTTP {r.status_code}, expected 422")
        if manifest.get("invalid_corrections"):
            after_bad = flatten_ui(client.get(f"{api}/report-data").json())
            if after_bad != before:
                failures.append("a refused correction changed the effective data")

        # 4. report images through the asset API
        assets = manifest.get("assets") or {}
        for kind, spec in assets.items():
            if kind not in ("cover", "logo"):
                continue
            content = _png((52, 92, 130)) if spec == "generated" else (source_dir / spec).read_bytes()
            r = client.put(f"{api}/assets/{kind}", files={"file": (f"{kind}.png", content, "image/png")})
            _response_json(r, 200, failures, f"upload {kind} image")

        # 5. reviewer corrections and manual rows through the batch correction API
        corrections = manifest.get("corrections", [])
        additions = manifest.get("row_additions", [])
        if corrections or additions:
            body = {"changes": corrections, "add_rows": [{"table": a["table"], "key": a.get("key"), "values": a["values"]} for a in additions]}
            ui = _response_json(client.patch(f"{api}/report-data", json=body), 200, failures, "apply corrections") or ui
        after = flatten_ui(ui)
        fields = ui_fields(ui)
        for c in corrections:
            f = fields.get(c["path"])
            if f is not None and c.get("value") not in (None, "") and f.get("status") != "manual":
                failures.append(f"corrected field {c['path']} has status {f.get('status')!r}, expected 'manual'")
        result["observed_values"]["after_corrections"] = {path: after.get(path) for path in manifest.get("expected_after_corrections", {})}
        _expect_values(after, manifest.get("expected_after_corrections", {}), failures, "after corrections")

        # 6. reset restores the extracted value, then the correction is re-applied
        reset = manifest.get("reset_check")
        if reset:
            path = reset["path"]
            _response_json(client.post(f"{api}/report-data/overrides/reset", json={"paths": [path]}), 200, failures, "reset override")
            reverted = flatten_ui(client.get(f"{api}/report-data").json()).get(path)
            expected_reverted = reset.get("expect")
            if reverted != expected_reverted:
                failures.append(f"reset {path}: expected {expected_reverted!r} after reset, observed {reverted!r}")
            original = next((c for c in corrections if c["path"] == path), None)
            if original:
                ui = _response_json(client.patch(f"{api}/report-data", json={"changes": [original]}), 200, failures, "re-apply correction") or ui

        # 7. narratives through the drafting workflow (mock provider: deterministic, offline)
        drafted: list[str] = []
        if manifest.get("narratives") == "mock":
            empty_before = [p for p, f in ui_fields(ui).items() if f.get("kind") == "longtext" and f.get("effective") in (None, "")]
            r = client.post(f"{api}/narratives")
            _response_json(r, 202, failures, "start narrative drafting")
            ui = _wait_narratives(client, project_id, timeout)
            if ui.get("narrative_status") != "done":
                failures.append(f"narrative drafting ended with status {ui.get('narrative_status')!r}: {ui.get('narrative_error')}")
            fields = ui_fields(ui)
            for path in manifest.get("expected_drafts", []):
                f = fields.get(path) or {}
                if f.get("status") != "ai_draft" or not f.get("effective"):
                    failures.append(f"expected an AI draft at {path}, observed status {f.get('status')!r}")
                elif "Drafted by AI" not in ((f.get("source") or {}).get("text") or ""):
                    failures.append(f"draft at {path} lacks AI provenance")
                else:
                    drafted.append(path)
            for c in corrections:  # reviewer text is never overwritten by drafting
                f = fields.get(c["path"])
                if f is not None and c.get("value") not in (None, "") and f.get("effective") != c["value"]:
                    failures.append(f"drafting changed reviewer text at {c['path']}")
            after = flatten_ui(ui)
        result["drafted"] = drafted

        # 8. completeness before generation
        comp = _response_json(client.get(f"{api}/completeness"), 200, failures, "load completeness") or {}
        result["completeness"] = comp
        observed_gaps = {g["path"] for g in comp.get("gaps", [])}
        summary = ui.get("summary", {})
        if classification == "complete":
            if not comp.get("complete"):
                failures.append(f"complete scenario has {comp.get('gap_count')} gap(s): {sorted(observed_gaps)}")
            if summary.get("conflicts"):
                failures.append(f"complete scenario has {summary['conflicts']} unresolved conflict(s)")
            if expected_gaps:
                failures.append("a complete scenario must not declare expected_gaps")
        else:
            if "expected_gaps" not in manifest:
                failures.append("structural scenario must declare expected_gaps")
            if observed_gaps != expected_gaps:
                failures.append(f"gaps differ from the oracle: unexpected {sorted(observed_gaps - expected_gaps)}; missing {sorted(expected_gaps - observed_gaps)}")
        if "expected_warning_paths" in manifest:
            observed_warn = {i["path"] for i in ui.get("issues", []) if i.get("severity") == "warning" and i.get("path")}
            expected_warn = set(manifest["expected_warning_paths"])
            if observed_warn != expected_warn:
                failures.append(f"warning paths differ from the oracle: unexpected {sorted(observed_warn - expected_warn)}; missing {sorted(expected_warn - observed_warn)}")
        elif classification == "complete":
            unexpected = [i for i in ui.get("issues", []) if i.get("severity") in ("warning", "error")]
            if unexpected:
                failures.append(f"complete scenario still reports {len(unexpected)} warning/error issue(s): {[i['message'][:80] for i in unexpected][:5]}")

        # 9. generate, snapshot, download
        report_record = _response_json(client.post(f"{api}/reports"), 202, failures, "create report")
        if not report_record:
            raise RuntimeError("report creation failed")
        report_id = report_record["id"]
        if bool(report_record.get("complete")) != (classification == "complete"):
            failures.append(f"version complete flag is {report_record.get('complete')!r} for a {classification} scenario")
        snapshot = _response_json(client.get(f"{api}/reports/{report_id}/snapshot"), 200, failures, "download report snapshot") or {}
        snapshot_path = scenario_output / "snapshot.json"
        snapshot_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        snapshot_values = flatten_snapshot(snapshot)
        _expect_values(snapshot_values, manifest.get("expected_values", {}), failures, "snapshot")
        _expect_values(snapshot_values, manifest.get("expected_after_corrections", {}), failures, "snapshot")
        for path in drafted:
            if not snapshot_values.get(path):
                failures.append(f"snapshot lost the draft at {path}")
        if not pool.wait_idle(timeout):
            failures.append(f"report generation did not become idle within {timeout:g} seconds")
            raise RuntimeError("report timeout")
        report_record = _response_json(client.get(f"{api}/reports/{report_id}"), 200, failures, "load report") or {}
        result["report"] = dict(report_record)
        pdf_path = scenario_output / "report.pdf"
        if report_record.get("status") != "done":
            failures.append(f"report status is {report_record.get('status')!r}: {report_record.get('error')}")
        else:
            download = client.get(f"{api}/reports/{report_id}/download")
            if download.status_code != 200:
                failures.append(f"download report: HTTP {download.status_code}: {download.text[:500]}")
            else:
                pdf_path.write_bytes(download.content)
                disposition = download.headers.get("content-disposition", "")
                if (classification == "complete") == ("-draft" in disposition):
                    failures.append(f"download name {disposition!r} does not match the {classification} classification")
                _check_pdf(manifest, classification, pdf_path, scenario_output, after, snapshot_values, bool(assets.get("cover")), failures, result)

        # 10. immutability: later edits and asset replacements never change a saved version
        immutable = manifest.get("immutability_patch")
        if immutable:
            _response_json(client.patch(f"{api}/report-data", json={"changes": [immutable]}), 200, failures, "apply post-report immutability correction")
            persisted = _response_json(client.get(f"{api}/reports/{report_id}/snapshot"), 200, failures, "reload report snapshot")
            if persisted != snapshot:
                failures.append("saved report snapshot changed after a later dataset correction")
        if assets.get("cover") and assets.get("freeze_check") and pdf_path.exists():
            first_digest = pdf_checks.first_image_digest(pdf_path, 0)
            _response_json(client.put(f"{api}/assets/cover", files={"file": ("cover2.png", _png((200, 40, 40)), "image/png")}), 200, failures, "replace cover image")
            v2 = _response_json(client.post(f"{api}/reports"), 202, failures, "create second version") or {}
            if not pool.wait_idle(timeout):
                failures.append("second version did not finish")
            again = client.get(f"{api}/reports/{report_id}/download")
            if again.status_code == 200 and again.content != pdf_path.read_bytes():
                failures.append("version 1 PDF bytes changed after the cover image was replaced")
            d2 = client.get(f"{api}/reports/{v2.get('id')}/download")
            if d2.status_code == 200:
                second = scenario_output / "report-v2.pdf"
                second.write_bytes(d2.content)
                if pdf_checks.first_image_digest(second, 0) == first_digest:
                    failures.append("version 2 did not pick up the replaced cover image")
                if pdf_checks.first_image_digest(pdf_path, 0) != first_digest:
                    failures.append("version 1 lost its frozen cover image")
            else:
                failures.append(f"second version download: HTTP {d2.status_code}")

        final_detail = _response_json(client.get(api), 200, failures, "load final project") or {}
        result["stage_after_report"] = final_detail.get("stage")
        result["provenance"] = provenance_matrix(snapshot, expected_gaps, observed_gaps)
        files = result["files"]
        result["file_summary"] = {s: sum(1 for f in files if f["status"] == s) for s in ("processed", "unrecognized", "unsupported", "needs_ocr", "failed")}
        (scenario_output / "completeness.json").write_text(json.dumps({"classification": classification, "completeness": comp, "expected_gaps": sorted(expected_gaps),
                                                                        "provenance_by_page": result["provenance"], "drafted": drafted, "file_summary": result["file_summary"]},
                                                                       indent=2, sort_keys=True) + "\n")
    except Exception as exc:  # noqa: BLE001 - retain partial evidence for every failed scenario
        message = f"workflow exception: {type(exc).__name__}: {exc}"
        if message not in failures:
            failures.append(message)

    result["passed"] = not failures
    (scenario_output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return result


def _check_pdf(manifest, classification, pdf_path: Path, out: Path, after: dict, snapshot_values: dict, has_cover: bool, failures: list[str], result: dict) -> None:
    texts = pdf_checks.page_texts(pdf_path)
    pdf_text = "\n".join(texts)
    report_expectation = manifest.get("report", {})
    expected_pages = report_expectation.get("page_count", 10)
    if len(texts) != expected_pages:
        failures.append(f"report page count: expected {expected_pages}, observed {len(texts)}")
    for fragment in report_expectation.get("text_contains", []):
        if fragment.casefold() not in pdf_text.casefold():
            failures.append(f"report PDF is missing text: {fragment!r}")
    for page_no, fragments in (report_expectation.get("pages") or {}).items():
        page_text = texts[int(page_no) - 1] if int(page_no) <= len(texts) else ""
        for fragment in fragments:
            if fragment.casefold() not in page_text.casefold():
                failures.append(f"page {page_no} is missing text: {fragment!r}")
    corpus = _effective_corpus(after) + _effective_corpus(snapshot_values)
    for forbidden in manifest.get("forbidden_text", []):
        if forbidden.casefold() in pdf_text.casefold():
            failures.append(f"report PDF contains forbidden identity: {forbidden!r}")
        if forbidden.casefold() in corpus.casefold():
            failures.append(f"effective report data contains forbidden identity: {forbidden!r}")
    if classification == "complete":
        failures.extend(pdf_checks.heading_problems(texts))
        if "DRAFT" in pdf_text:
            failures.append("a complete report must not carry the draft marker")
        name, quarter = manifest.get("report_identity", (None, None)) if isinstance(manifest.get("report_identity"), list) else (None, None)
        if name and quarter:
            for i, t in enumerate(texts[1:], start=2):
                if name.casefold() not in t.casefold() or quarter.casefold() not in t.casefold():
                    failures.append(f"page {i} does not carry the property name and quarter")
    elif "DRAFT" not in pdf_text:
        failures.append("a structural (incomplete) report must carry the draft marker")
    images = pdf_checks.image_counts(pdf_path)
    if has_cover:
        if images[0] < 1 or images[1] < 1:
            failures.append(f"uploaded cover image missing from page 1 or 2 (images per page {images[:2]})")
    elif images[0] != 0:
        failures.append("a scenario without an image should render the placeholder, not an embedded image")
    failures.extend(pdf_checks.structural_problems(pdf_path, expected_pages))
    pages = pdf_checks.render_pages(pdf_path, out / "pages")
    result["report"].update({"page_count": len(texts), "pdf_path": str(pdf_path), "images_per_page": images, "page_images": [str(p) for p in pages],
                             "pdf_text_excerpt": pdf_text[:2000]})


def run_many(client, scenarios: Iterable[Scenario], output_dir: Path, timeout: float = 240) -> list[dict[str, Any]]:
    return [run_scenario(client, scenario, output_dir, timeout=timeout) for scenario in scenarios]
