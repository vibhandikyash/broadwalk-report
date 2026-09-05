# Real World Generalization Validation Design

## Purpose

This validation suite determines whether the report generator works because it understands the supported document families or because it was tuned to The Boardwalk example. It uses new property identities, reporting periods, values, filenames, sheet names, file groupings, and source availability. The expected results are declared independently from the application and are never copied from its output.

The suite is diagnostic. It adds fixtures, an oracle, a runner, tests, and evidence. It does not change extraction or report-generation behavior. If a scenario exposes an application defect, the run records the failure for a separate product fix.

## Validation Scenarios

### Harbor Point 3Q26 Complete Dataset

Harbor Point is a 264-unit property reporting the quarter ended September 30, 2026. Its sources cover the full supported workflow: Yardi budget comparison, balance sheet, current and prior rent rolls, current and prior market rent schedules, lease trade-out, HelloData listings and rent comps, CoStar history, rent trend history, Slate capital calls, and Slate distributions.

Variation from the development dataset includes unrelated filenames, descriptive rather than default sheet names, multiple supported reports in each workbook, different unit types, different values, a nonzero capital call, a nonzero distribution, and a different reporting quarter.

Pass criteria:

- The property identity, reporting period, unit count, occupancy, financial totals, loan amount, equity, rent values, leasing totals, CoStar metrics, and capital activity equal the independent oracle.
- All source files finish in an expected terminal state.
- Reviewer-only fields can be corrected and preserved in a version snapshot.
- A ten-page PDF contains Harbor Point values and no Boardwalk identity.

### Pine Ridge 4Q26 Sparse Dataset

Pine Ridge is a 412-unit property reporting the quarter ended December 31, 2026. It deliberately omits balance-sheet, Slate, and rent-trend sources. It includes current and prior operational data, financials, leasing, and market data with extra leading rows, alternate date forms, percentage strings, and harmless note sheets.

Pass criteria:

- Available facts are extracted accurately despite the structural variations.
- Unavailable report inputs remain missing or are flagged; they are not populated with Boardwalk values.
- The project reaches review without a project-wide failure.
- Explicit reviewer corrections make report generation possible without re-uploading.
- The PDF contains Pine Ridge data and does not contain Harbor Point or Boardwalk identities.

### Lakeside Commons 1Q27 Conflict Dataset

Lakeside Commons is a 196-unit property reporting the quarter ended March 31, 2027. It includes a current financial export, an older populated export, a duplicate current export, a rent roll for a different property, a scanned PDF, reordered financial columns, inserted rows and columns, and an extra unrelated sheet.

Pass criteria:

- The current reporting period wins over the older export.
- Duplicate candidates are reported without corrupting totals.
- The unrelated property is set aside and never contaminates the report.
- The scanned PDF receives the `needs_ocr` status.
- Conflicts and source-selection issues remain visible to the reviewer.
- After corrections, the generated PDF and immutable snapshot contain only Lakeside Commons data.

## Fixture Structure

Each scenario lives under `validation/real_world/scenarios/<scenario>/`:

```text
expected.json
sources/
  operations.xlsx
  leasing.xlsx
  market.xlsx
  capital-calls.pdf              optional
  distributions.pdf             optional
  additional decoys             scenario-specific
```

The XLSX files are real Open XML workbooks authored with typed numbers, dates, and percentages. Their formatting is intentionally modest because they emulate exported operating reports, not presentation workbooks. Source PDFs contain selectable text unless the scenario explicitly calls for an image-only scan.

## Independent Oracle

Each `expected.json` contains:

- scenario and property metadata;
- expected terminal status by source file;
- scalar report paths with exact values or numeric tolerances;
- table-cell paths with exact values or numeric tolerances;
- expected warnings and errors;
- reviewer corrections to apply through the public API;
- required and forbidden PDF text;
- expected page count.

The runner compares the API response to this file. It must not update expected values from application output. Changes to an oracle require a human-readable explanation in version control.

## Test Harness

`backend/tests/test_real_world_scenarios.py` parametrizes all scenario directories and executes the public workflow:

1. Create a project.
2. Upload every source through the API.
3. Wait for processing to become idle.
4. Assert file statuses and project stage.
5. Flatten structured fields and table cells by their public paths.
6. Compare extracted and derived values to the independent oracle.
7. Assert required issue messages and absence of forbidden property names.
8. Submit reviewer corrections through the batch correction endpoint.
9. Generate a report version.
10. Download and inspect its PDF and JSON snapshot.
11. Confirm the version is immutable after a later correction.

`validation/real_world/run_validation.py` uses the same harness and writes durable evidence under `validation/real_world/results/<scenario>/`: the generated PDF, reviewed-data snapshot, per-scenario JSON result, and an aggregate summary.

## Evidence and Verification

Automated evidence includes source status, asserted data paths, issue checks, correction results, report status, page count, required text, forbidden text, and snapshot checks. A scenario passes only if all mandatory checks pass; missing assertions cannot be represented as success.

Every generated PDF is rendered to PNG and visually inspected for missing glyphs, clipping, overlap, unreadable tables, and footer continuity. Representative sheets from every workbook are rendered and checked for visible content, correct types, and legible headers.

The final generalization result distinguishes:

- application passes;
- application limitation exposed;
- fixture or oracle defect;
- environmental failure such as unavailable Chromium.

## Boundaries

- Synthetic data is fictional and contains no personal information.
- The suite does not claim to predict every hidden evaluation dataset.
- It tests the currently supported Yardi, HelloData, CoStar, and Slate document families.
- OCR remains a deliberate negative-path test, not a newly implemented feature.
- Existing unrelated worktree changes are preserved and excluded from this suite's commits.
