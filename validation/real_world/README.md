# Real-world validation

This suite checks that the application works on properties and source packages that are independent of the
Boardwalk example, and it distinguishes a report that merely renders from one that is finished.

## Classifications

- **structural**: the package is ingested, supported values are extracted and a ten-page PDF renders while
  optional information stays missing by design. The manifest lists the exact completeness gaps
  (`expected_gaps`) and warning paths (`expected_warning_paths`) the application must report; any new gap or
  warning fails the test, and the PDF must carry the draft marker.
- **complete**: after the manifest's reviewer corrections, manual rows, mock narratives and images, the
  completeness specification reports no gap, no conflict remains, the version is marked complete, every page
  carries its expected headings and content, the uploaded image is embedded, and the PDF passes the raster,
  font and overflow checks.

## Scenarios

| Scenario | Classification | What it exercises |
|---|---|---|
| `riverbend_station_4q25` | complete | A 228-unit Denver property, quarter ended 2025-12-31: every supported export family across three workbooks with unfamiliar names and shuffled sheets, Slate capital-call and distribution PDFs, a property photo and logo through the asset API, four underwriting rows through the correction API, corrections for every manual field, refused invalid corrections, a reset check, twelve mock narrative drafts, per-page PDF content, image freezing across versions and snapshot immutability |
| `harbor_point_3q26` | structural | Complete operational data in one opaque workbook plus two Slate PDFs; financing terms, property facts, narratives, underwriting and status content stay open |
| `pine_ridge_4q26` | structural | Sparse package: no balance sheet, Slate or rent-comp rents; capital and loan facts entered through corrections; comp rows keep their units, vintage and leased % |
| `lakeside_commons_1q27` | structural | Conflicts: a stale duplicate export, a rent roll for another property (set aside), an image-only PDF (`needs_ocr`), no leasing report (empty tables stay "missing" without the no-activity statement) |

Each `expected.json` is an independent oracle: its values are literal and are never copied from application output.

## Regenerate inputs

Harbor Point, Pine Ridge and Lakeside were generated with `build_fixtures.mjs` (needs the `@oai/artifact-tool`
runtime; the generated workbooks are committed) and `build_source_pdfs.py` (needs `reportlab`). Riverbend
Station uses only the backend virtualenv:

```bash
backend/.venv/bin/python validation/real_world/build_riverbend.py
```

## Run

From the repository root, with the backend virtualenv:

```bash
backend/.venv/bin/python validation/real_world/run_validation.py        # all scenarios, evidence under results/
cd backend && pytest tests/test_real_world_scenarios.py -v            # the same harness under pytest
```

Narratives are drafted by the deterministic `mock` provider, so no key, network access or login is involved.

## Evidence layout

```
results/
  summary.json                 pass/fail, classification, gap count and drafted count per scenario
  assessment.md                generated: scenario table plus a per-page provenance matrix for every report
  <scenario>/
    report.pdf                 the generated version (report-v2.pdf when the image freeze check ran)
    snapshot.json              the immutable reviewed-data snapshot of that version
    completeness.json          classification, completeness result, expected gaps, provenance by page, file summary
    result.json                every observed value, issue, failure and report check
    pages/page-NN.png          every page rendered with PDFium for visual inspection
```

The provenance matrix counts, per page, values that were extracted, derived, entered through reviewer
corrections, drafted by the mock provider, missing intentionally (a declared gap or an optional field), missing
unexpectedly, or in conflict. `ASSESSMENT.md` next to this file is the human-written verdict.
