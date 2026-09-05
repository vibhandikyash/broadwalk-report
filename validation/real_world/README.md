# Real-world generalization validation

This suite checks whether the application works on properties and source packages that are independent of the Boardwalk example. It deliberately exercises different file names, sheet order, property sizes, periods, missing inputs, duplicate periods, an unrelated-property decoy, and an image-only PDF.

## Scenarios

- `harbor_point_3q26`: complete alternate-property package covering every supported spreadsheet domain plus capital calls and distributions.
- `pine_ridge_4q26`: sparse but valid package; unavailable capital and financing values are entered through the normal correction API before report generation.
- `lakeside_commons_1q27`: conflicting package with a stale/duplicate export, a different-property rent roll, and a scan that must be flagged for OCR.

Each `expected.json` is an independent test oracle. Its values are intentionally literal and are not imported from `build_fixtures.mjs`.

## Regenerate inputs

The workbook builder uses the bundled `@oai/artifact-tool` runtime. Point `node_modules` in this directory at the bundled package folder, then run:

```bash
node validation/real_world/build_fixtures.mjs
python3 validation/real_world/build_source_pdfs.py
```

## Run

From the repository root:

```bash
python3 validation/real_world/run_validation.py
pytest -q backend/tests/test_real_world_scenarios.py
```

The CLI writes one report PDF, immutable snapshot, and detailed result per scenario under `validation/real_world/results`, plus `summary.json`. It exits nonzero when any independently expected value, workflow stage, contamination check, or report assertion fails.
