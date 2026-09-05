# Production-Readiness Remediation Plan

Design: `docs/superpowers/specs/2026-09-05-production-readiness-remediation-design.md`. Every task is test-first: write the failing test, run it, implement, run it green.

## Traceability

| Requirement | Tasks | Tests |
|---|---|---|
| 1 Preserve partial comp rows and correct totals | T1 | `test_comps.py` (metadata-only, mixed, subject plus comps, missing asking, missing effective, missing units, totals, workbook names and sheet positions) |
| 2 Structural versus complete validation | T2, T3, T4, T8 | `test_completeness.py`, `test_api_completeness` in `test_api_report_data.py`, `test_render_html.py` draft marker, frontend specs |
| 3 Complete non-Boardwalk scenario | T9, T10 | `test_real_world_scenarios.py` (riverbend complete) |
| 4 Strengthen existing scenarios | T10 | exact gaps and warning paths per manifest |
| 5 PDF acceptance | T7, T10 | per-page checks, images, raster, page PNG evidence |
| 6 Narrative behaviour | T5 | `test_narrative.py` mock provider, staleness, PDF presence |
| 7 Manual completion | T10 | harness correction, add_rows, reset, snapshot assertions |
| 8 Report assets | T6, T7 | `test_api_assets.py`, harness image checks |
| 9 Honest limitations | T11 | README, validation README |
| 10 Release reporting | T7, T11 | `assessment.md`, `completeness.json`, `ASSESSMENT.md` |
| Regression | T12 | full suites, dataset forbidden strings, deliverable regenerated complete |

## T1 Comparable rows

Files: `backend/app/consolidate/builder.py` (`_submarket`), `backend/app/consolidate/calc.py` (comp totals and footnote), `backend/tests/test_comps.py` (new), `backend/tests/test_calc.py`.

- [ ] Tests: union of listings and summary properties; metadata-only row kept with missing rents; leased % fallbacks; totals ignore missing, weight only when every contributing comp has units, subject excluded; footnote names weighting per column; comps sheet found in another workbook name and sheet position.
- [ ] Implement union consolidation with per-cell provenance; per-column weighting; footnote text.
- [ ] Boardwalk dataset test still passes (Ashlar asking 1,719, comp averages unchanged where inputs unchanged).

## T2 Completeness specification

Files: `backend/app/consolidate/completeness.py` (new), `backend/app/consolidate/builder.py` (no-activity note field), `backend/tests/test_completeness.py` (new).

- [ ] Tests: sample data has gaps for every manual group; filling them through overrides yields `complete`; zero versus missing for capital; leasing rows versus note versus missing; optional fields never gaps; AI drafts count as populated but are counted as pending.
- [ ] Implement `REQUIREMENTS`, `evaluate(data, issues) -> Completeness`, `is_required(path)`.

## T3 Issues and API

Files: `backend/app/consolidate/validate.py`, `backend/app/api/serialize.py`, `backend/app/api/report_data.py`, `backend/app/api/report.py`, `backend/app/db.py`, `backend/app/workers/jobs.py`, `backend/tests/test_validate.py`, `backend/tests/test_api_report_data.py`, `backend/tests/test_api_report.py`.

- [ ] Tests: missing required field is a warning naming its page, optional is info; `GET /completeness`; `summary.completeness`; report version carries `complete`/`gap_count`; draft download filename.
- [ ] Implement severity from the specification; endpoint; version columns with migration; filename.

## T4 Draft marker in the rendered report

Files: `backend/app/report/render.py`, `backend/app/report/templates/report.html`, `backend/app/report/static/report.css`, `backend/tests/test_render_html.py`, `backend/tests/test_render_pdf.py`.

- [ ] Tests: incomplete snapshot renders `DRAFT · N items outstanding` in footers and on the cover; complete snapshot has no marker; ten pages still fit.
- [ ] Implement `render_html(..., completeness=...)`; `generate_report` passes the stored gap count.

## T5 Narrative mock provider and staleness

Files: `backend/app/config.py`, `backend/app/services/narrative.py`, `backend/app/consolidate/builder.py` (`apply_overrides`), `backend/app/workers/jobs.py`, `backend/tests/test_narrative.py`.

- [ ] Tests: `NARRATIVE_PROVIDER=mock` resolves; mock drafts only empty fields, uses payload values, invents no figure (every number in a draft exists in the payload), never overwrites reviewer text; stored basis; changing a reviewed value flags the draft stale and the next drafting run replaces it; draft text appears in rendered HTML with `ai_draft` provenance.
- [ ] Implement.

## T6 Assets API coverage

Files: `backend/tests/test_api_assets.py` (new).

- [ ] Tests: upload cover and logo, preview embeds data URIs, version 1 freezes the image, replacing the asset leaves version 1's frozen file unchanged and version 2 uses the new one, delete restores the placeholder, wrong type refused.

## T7 Harness and evidence

Files: `validation/real_world/harness.py`, `validation/real_world/pdf_checks.py` (new), `validation/real_world/run_validation.py`, `validation/real_world/README.md`, `backend/tests/test_real_world_scenarios.py`.

- [ ] Manifest schema: `classification`, `expected_gaps`, `expected_warning_paths`, `narratives`, `assets`, `row_additions`, `reset_check`, `report.pages`, `report.headings`.
- [ ] Steps: completeness before generation, narratives, assets, row additions, reset, per-page checks, image checks, raster check, page PNGs, provenance matrix, `completeness.json`.
- [ ] Runner: `assessment.md` with page-by-page matrix per report; mock provider enabled; evidence layout documented.

## T8 Frontend

Files: `frontend/src/app/core/models.ts`, `api.service.ts`, `pages/review/review.component.ts`, `pages/report/report.component.ts`, specs, `testing/fixtures.ts`.

- [ ] Tests: completeness panel lists gaps and jumps; report badge, draft button label, draft version chip.
- [ ] Implement.

## T9 Riverbend Station scenario

Files: `validation/real_world/build_riverbend.py` (new), `validation/real_world/scenarios/riverbend_station_4q25/expected.json`, generated sources.

- [ ] Build three workbooks with shuffled sheets and unfamiliar names, two Slate PDFs (Chromium), oracle values computed independently and written literally.
- [ ] Manifest: corrections for every manual field, underwriting rows, mock narratives, assets, per-page expectations, forbidden identities.

## T10 Scenario manifests and tests

- [ ] Classify Harbor Point, Pine Ridge, Lakeside as structural with exact `expected_gaps` and `expected_warning_paths`; keep their conditions.
- [ ] Riverbend complete: no gaps, no conflicts, all page checks, images, narratives.
- [ ] Test parametrisation asserts by classification; no test passes on page count alone.

## T11 Documentation

- [ ] README: structural versus complete, completeness endpoint and panel, mock provider, draft marker, manual-field list, limitations.
- [ ] `validation/real_world/README.md` and `ASSESSMENT.md` rewritten from evidence.

## T12 Regression and release

- [ ] Boardwalk deliverable regenerated as `complete`; dataset test asserts no alternate-property identity.
- [ ] Full backend suite, dataset tests, frontend tests and build, browser E2E, validation runner, page inspection.
- [ ] Commit in logical steps; working tree clean.
