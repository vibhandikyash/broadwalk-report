"""Public-HTTP workflow harness for independent generalization scenarios."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pypdfium2 as pdfium


ROOT = Path(__file__).resolve().parent
SCENARIO_ROOT = ROOT / "scenarios"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    directory: Path
    manifest: dict[str, Any]


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


def flatten_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for section_key, section in snapshot.get("sections", {}).items():
        for field_key, field in section.get("fields", {}).items():
            values[f"{section_key}.fields.{field_key}"] = field.get("override") if field.get("override") is not None else field.get("value")
        for table_key, table in section.get("tables", {}).items():
            for row_key, row in table.get("rows", {}).items():
                for column_key, field in row.items():
                    values[f"{section_key}.tables.{table_key}.rows.{row_key}.{column_key}"] = field.get("override") if field.get("override") is not None else field.get("value")
            for column_key, field in table.get("totals", {}).items():
                values[f"{section_key}.tables.{table_key}.totals.{column_key}"] = field.get("override") if field.get("override") is not None else field.get("value")
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
    return [
        {
            "name": item.get("original_filename"),
            "status": item.get("status"),
            "error": item.get("error"),
            "parts": item.get("parts") or [],
        }
        for item in detail.get("files", [])
    ]


def _pdf_evidence(pdf_path: Path) -> tuple[int, str]:
    document = pdfium.PdfDocument(str(pdf_path))
    text = []
    for page in document:
        text_page = page.get_textpage()
        text.append(text_page.get_text_range())
        text_page.close()
        page.close()
    page_count = len(document)
    document.close()
    return page_count, "\n".join(text)


def _effective_corpus(values: dict[str, Any]) -> str:
    return json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)


def run_scenario(client, scenario: Scenario | Path, output_dir: Path, timeout: float = 240) -> dict[str, Any]:
    """Run one scenario through upload, review/correction, report, and immutable snapshot APIs."""
    from app.workers.pool import pool

    if isinstance(scenario, Path):
        manifest_path = scenario / "expected.json"
        scenario = Scenario(scenario.name, scenario, json.loads(manifest_path.read_text()))
    manifest = scenario.manifest
    scenario_output = output_dir / scenario.scenario_id
    scenario_output.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    warnings: list[str] = []
    result: dict[str, Any] = {
        "scenario": scenario.scenario_id,
        "description": manifest.get("description"),
        "passed": False,
        "failures": failures,
        "warnings": warnings,
        "files": [],
        "observed_values": {},
        "report": {},
    }

    try:
        created = _response_json(client.post("/api/projects", json={"name": manifest["project_name"]}), 201, failures, "create project")
        if not created:
            raise RuntimeError("project creation failed")
        project_id = created["id"]
        result["project_id"] = project_id

        source_dir = scenario.directory / "sources"
        for source in manifest["sources"]:
            source_path = source_dir / source["name"]
            upload_name = source.get("upload_as") or source_path.name
            if not source_path.is_file():
                failures.append(f"source is missing: {source_path}")
                continue
            with source_path.open("rb") as handle:
                response = client.post(
                    f"/api/projects/{project_id}/files",
                    files=[("files", (upload_name, handle, "application/octet-stream"))],
                )
            _response_json(response, 201, failures, f"upload {upload_name}")
        if failures:
            raise RuntimeError("one or more source uploads failed")
        if not pool.wait_idle(timeout):
            failures.append(f"ingestion did not become idle within {timeout:g} seconds")
            raise RuntimeError("ingestion timeout")

        detail = _response_json(client.get(f"/api/projects/{project_id}"), 200, failures, "load project") or {}
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

        ui = _response_json(client.get(f"/api/projects/{project_id}/report-data"), 200, failures, "load report data") or {}
        before = flatten_ui(ui)
        result["observed_values"]["before_corrections"] = {path: before.get(path) for path in manifest.get("expected_values", {})}
        _expect_values(before, manifest.get("expected_values", {}), failures, "before corrections")
        issue_text = _issues_text(ui)
        result["issues_before_corrections"] = ui.get("issues", [])
        for fragment in manifest.get("issues_contains", []):
            if fragment.casefold() not in issue_text.casefold():
                failures.append(f"expected issue fragment was absent: {fragment!r}")

        corrections = manifest.get("corrections", [])
        if corrections:
            ui = _response_json(
                client.patch(f"/api/projects/{project_id}/report-data", json={"changes": corrections}),
                200,
                failures,
                "apply corrections",
            ) or ui
        after = flatten_ui(ui)
        result["observed_values"]["after_corrections"] = {path: after.get(path) for path in manifest.get("expected_after_corrections", {})}
        _expect_values(after, manifest.get("expected_after_corrections", {}), failures, "after corrections")

        report_record = _response_json(client.post(f"/api/projects/{project_id}/reports"), 202, failures, "create report")
        if not report_record:
            raise RuntimeError("report creation failed")
        report_id = report_record["id"]
        snapshot_response = client.get(f"/api/projects/{project_id}/reports/{report_id}/snapshot")
        snapshot = _response_json(snapshot_response, 200, failures, "download report snapshot") or {}
        snapshot_path = scenario_output / "snapshot.json"
        snapshot_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        snapshot_values = flatten_snapshot(snapshot)
        _expect_values(snapshot_values, manifest.get("expected_values", {}), failures, "snapshot")
        _expect_values(snapshot_values, manifest.get("expected_after_corrections", {}), failures, "snapshot")

        if not pool.wait_idle(timeout):
            failures.append(f"report generation did not become idle within {timeout:g} seconds")
            raise RuntimeError("report timeout")
        report_record = _response_json(client.get(f"/api/projects/{project_id}/reports/{report_id}"), 200, failures, "load report") or {}
        result["report"] = report_record
        if report_record.get("status") != "done":
            failures.append(f"report status is {report_record.get('status')!r}: {report_record.get('error')}")
        else:
            download = client.get(f"/api/projects/{project_id}/reports/{report_id}/download")
            if download.status_code != 200:
                failures.append(f"download report: HTTP {download.status_code}: {download.text[:500]}")
            else:
                pdf_path = scenario_output / "report.pdf"
                pdf_path.write_bytes(download.content)
                page_count, pdf_text = _pdf_evidence(pdf_path)
                report_expectation = manifest.get("report", {})
                expected_pages = report_expectation.get("page_count")
                if expected_pages is not None and page_count != expected_pages:
                    failures.append(f"report page count: expected {expected_pages}, observed {page_count}")
                for fragment in report_expectation.get("text_contains", []):
                    if fragment.casefold() not in pdf_text.casefold():
                        failures.append(f"report PDF is missing text: {fragment!r}")
                effective_corpus = _effective_corpus(after)
                for forbidden in manifest.get("forbidden_text", []):
                    if forbidden.casefold() in pdf_text.casefold():
                        failures.append(f"report PDF contains forbidden identity: {forbidden!r}")
                    if forbidden.casefold() in effective_corpus.casefold():
                        failures.append(f"effective report data contains forbidden identity: {forbidden!r}")
                result["report"].update({
                    "page_count": page_count,
                    "pdf_text": pdf_text,
                    "pdf_path": str(pdf_path),
                    "snapshot_path": str(snapshot_path),
                })

        immutable = manifest.get("immutability_patch")
        if immutable:
            patched = client.patch(f"/api/projects/{project_id}/report-data", json={"changes": [immutable]})
            _response_json(patched, 200, failures, "apply post-report immutability correction")
            persisted = _response_json(client.get(f"/api/projects/{project_id}/reports/{report_id}/snapshot"), 200, failures, "reload report snapshot")
            if persisted != snapshot:
                failures.append("saved report snapshot changed after a later dataset correction")

        final_detail = _response_json(client.get(f"/api/projects/{project_id}"), 200, failures, "load final project") or {}
        result["stage_after_report"] = final_detail.get("stage")
    except Exception as exc:  # noqa: BLE001 - retain partial evidence for every failed scenario
        message = f"workflow exception: {type(exc).__name__}: {exc}"
        if message not in failures:
            failures.append(message)

    result["passed"] = not failures
    (scenario_output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return result


def run_many(client, scenarios: Iterable[Scenario], output_dir: Path, timeout: float = 240) -> list[dict[str, Any]]:
    return [run_scenario(client, scenario, output_dir, timeout=timeout) for scenario in scenarios]
