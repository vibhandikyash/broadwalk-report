# Real World Generalization Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove whether the reporting application generalizes beyond the Boardwalk example by creating independent, realistic source packages, processing them through the public upload/review/report workflow, and preserving machine-readable and visual evidence.

**Architecture:** Keep validation assets isolated under `validation/real_world`. A deterministic fixture builder creates business-style XLSX/PDF inputs, independent JSON manifests define expected outcomes, and a Python harness drives the FastAPI application only through its public HTTP interface. Pytest exercises the same harness, while a CLI runner preserves generated PDFs, snapshots, API evidence, and an aggregate result summary.

**Tech Stack:** Python 3.11, FastAPI TestClient, pytest, pypdf, reportlab/Pillow, Node.js, `@oai/artifact-tool`, JSON.

---

## Task 1: Establish the Validation Contract

**Files:**

- Create: `backend/tests/test_real_world_scenarios.py`
- Create: `validation/__init__.py`
- Create: `validation/real_world/__init__.py`
- Create: `validation/real_world/README.md`

- [ ] Add a discovery test that requires exactly these scenario identifiers: `harbor_point_3q26`, `pine_ridge_4q26`, and `lakeside_commons_1q27`.
- [ ] Add a module-contract test that requires `validation.real_world.harness` to expose `discover_scenarios` and `run_scenario`.
- [ ] Run `pytest -q backend/tests/test_real_world_scenarios.py` and confirm the new tests fail because the scenario assets and harness do not yet exist.
- [ ] Add package markers and a README that documents prerequisites, fixture regeneration, CLI execution, output locations, scenario intent, and the rule that expected manifests are independent test oracles.

## Task 2: Define Independent Expected Results

**Files:**

- Create: `validation/real_world/scenarios/harbor_point_3q26/expected.json`
- Create: `validation/real_world/scenarios/pine_ridge_4q26/expected.json`
- Create: `validation/real_world/scenarios/lakeside_commons_1q27/expected.json`

- [ ] Define each property identity, reporting period, source-file expectations, required review issues, expected extracted/corrected field values, prohibited decoy identities, and report assertions.
- [ ] Include numerical tolerances for ratios and rates instead of string-format-dependent comparisons.
- [ ] Make Harbor Point a complete alternate-property case with all major data sources.
- [ ] Make Pine Ridge a sparse-but-valid case that deliberately needs manual corrections for unavailable fields.
- [ ] Make Lakeside Commons a conflict case containing stale duplicates, an unrelated-property decoy, and an image-only document expected to require OCR.
- [ ] Keep all expected values literal in JSON; do not import or derive them from fixture-builder constants.

## Task 3: Build Five Realistic Spreadsheet Sources

**Files:**

- Create: `validation/real_world/build_fixtures.mjs`
- Create: `validation/real_world/.gitignore`
- Generate: `validation/real_world/scenarios/harbor_point_3q26/sources/2026_Q3_reporting_export.xlsx`
- Generate: `validation/real_world/scenarios/pine_ridge_4q26/sources/Property_Ops_December.xlsx`
- Generate: `validation/real_world/scenarios/lakeside_commons_1q27/sources/Current_Quarter_Pack.xlsx`
- Generate: `validation/real_world/scenarios/lakeside_commons_1q27/sources/Archive_Export.xlsx`
- Generate: `validation/real_world/scenarios/lakeside_commons_1q27/sources/Regional_Support.xlsx`

- [ ] Use `@oai/artifact-tool` for workbook creation and verification.
- [ ] Vary sheet order, leading blank rows, file names, property sizes, dates, rent schedules, budget values, and comparable-property sets so the sources do not mimic the original sample’s exact layout.
- [ ] Include the supported operational domains needed by the application: budget, balance sheet where applicable, rent roll, rent schedule, leases/turnovers, listings, comparables, market metrics, and rent history.
- [ ] Put old-period duplicate data in `Archive_Export.xlsx` and unrelated-property data in `Regional_Support.xlsx` to test selection and contamination resistance.
- [ ] Inspect key ranges and scan all five workbooks for formula errors.
- [ ] Render representative sheets from every workbook and visually verify that the source files are readable and structurally realistic.

## Task 4: Build Four PDF Sources

**Files:**

- Create: `validation/real_world/build_source_pdfs.py`
- Generate: `validation/real_world/scenarios/harbor_point_3q26/sources/capital_calls_2026Q3.pdf`
- Generate: `validation/real_world/scenarios/harbor_point_3q26/sources/cash_distributions_2026Q3.pdf`
- Generate: `validation/real_world/scenarios/lakeside_commons_1q27/sources/capital_activity.pdf`
- Generate: `validation/real_world/scenarios/lakeside_commons_1q27/sources/scanned_vendor_report.pdf`

- [ ] Create text PDFs with varied labels and layouts for valid capital-call/distribution extraction.
- [ ] Create the vendor report as an image-only PDF with no text layer to exercise the documented OCR-required path.
- [ ] Extract text from every source PDF and assert the first three contain their expected identity/value markers while the scan has no extractable text.
- [ ] Render and visually inspect every page of every source PDF.

## Task 5: Implement the Public-Workflow Harness

**Files:**

- Create: `validation/real_world/harness.py`
- Modify: `backend/tests/test_real_world_scenarios.py`

- [ ] Implement scenario discovery from manifest directories, with deterministic sorting and clear validation errors.
- [ ] Create a dataset via HTTP, upload all manifest-listed files via HTTP, wait for application background work, and collect file status/issue evidence.
- [ ] Flatten the dataset API’s structured fields/cells into stable paths and compare expected values with configurable numerical tolerances.
- [ ] Apply only manifest-declared manual corrections through the batch correction endpoint and verify corrected values through a fresh dataset response.
- [ ] Generate a report through HTTP, wait for completion, download the PDF and JSON snapshot, and preserve the report metadata.
- [ ] Assert page count, required report text, forbidden decoy identities, file status expectations, issue fragments, and correction persistence.
- [ ] Apply a later dataset correction and prove the previously generated report snapshot remains immutable.
- [ ] Write a per-scenario `result.json` containing inputs, observed values, mismatches, warnings, file evidence, report evidence, and pass/fail status.
- [ ] Ensure the harness reports validation failures without mutating application code or silently relaxing expected results.

## Task 6: Add Parametric End-to-End Tests

**Files:**

- Modify: `backend/tests/test_real_world_scenarios.py`

- [ ] Parameterize one end-to-end test across all three manifests.
- [ ] Use isolated temporary data roots and output directories so test runs cannot depend on or alter checked-in application state.
- [ ] Assert each scenario completes the entire ingestion, review/correction, report-generation, snapshot, and PDF-download lifecycle.
- [ ] Add focused tests for missing-manifest validation and tolerance-aware comparison helpers.
- [ ] Run the new file alone and fix only harness/fixture defects until all new tests pass.

## Task 7: Add a Repeatable CLI Validation Runner

**Files:**

- Create: `validation/real_world/run_validation.py`
- Generate: `validation/real_world/results/summary.json`
- Generate: `validation/real_world/results/harbor_point_3q26/report.pdf`
- Generate: `validation/real_world/results/harbor_point_3q26/snapshot.json`
- Generate: `validation/real_world/results/harbor_point_3q26/result.json`
- Generate: `validation/real_world/results/pine_ridge_4q26/report.pdf`
- Generate: `validation/real_world/results/pine_ridge_4q26/snapshot.json`
- Generate: `validation/real_world/results/pine_ridge_4q26/result.json`
- Generate: `validation/real_world/results/lakeside_commons_1q27/report.pdf`
- Generate: `validation/real_world/results/lakeside_commons_1q27/snapshot.json`
- Generate: `validation/real_world/results/lakeside_commons_1q27/result.json`

- [ ] Add CLI flags for scenario selection and output location, with all scenarios selected by default.
- [ ] Start each scenario from isolated storage while preserving all final evidence in the requested output directory.
- [ ] Emit a concise console result and a detailed aggregate JSON summary.
- [ ] Exit nonzero if any expected value, contamination check, workflow stage, or report assertion fails.
- [ ] Run the CLI across all scenarios and preserve its reports and evidence.

## Task 8: Verify Report Content and Visual Quality

**Files:**

- Inspect: `validation/real_world/results/*/report.pdf`
- Inspect: `validation/real_world/results/*/snapshot.json`
- Inspect: `validation/real_world/results/*/result.json`

- [ ] Extract text and page counts from every generated report.
- [ ] Confirm the requested property/period identifiers appear and all forbidden decoy identities are absent.
- [ ] Render every report page to PNG contact sheets and visually inspect for clipping, overlap, missing glyphs, blank pages, and implausible values.
- [ ] Compare report text and snapshot values against independent manifests rather than fixture-generation code.
- [ ] Correct fixture or harness defects and rerun until failures represent application behavior rather than test infrastructure.

## Task 9: Run Full Regression and Publish the Generalization Assessment

**Files:**

- Modify only if evidence requires clarification: `validation/real_world/README.md`
- Preserve: `validation/real_world/results/summary.json`

- [ ] Run the complete backend test suite.
- [ ] Run the frontend typecheck/build/check workflow and the repository’s documented end-to-end check command.
- [ ] Re-run the real-world CLI after the full suite to capture fresh final evidence.
- [ ] Record exact pass/fail totals, scenario-specific defects, hardcoding findings, and confidence limits in the aggregate summary.
- [ ] Score generalization separately for extraction, conflict handling, sparse-input resilience, correction workflow, report correctness, and visual quality.
- [ ] Verify the working tree and ensure no unrelated in-progress files were staged, overwritten, or reformatted.
- [ ] Deliver clickable paths to every generated workbook, source PDF, report PDF, manifest, and summary with a concise final verdict.
