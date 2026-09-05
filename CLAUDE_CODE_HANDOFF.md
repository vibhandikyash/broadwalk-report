# Claude Code Handoff: Investor Report Generator Hardening

## Mission

Continue from the current Claude implementation and make it a reliable, complete local application that satisfies every requirement in:

- `../Test Project Requirements - The Boardwalk.docx`
- `../OUTPUT-FILE-Boardwalk-2Q26 Quarterly Investor Reporting.pdf`
- `README.md`
- `docs/implementation-plan.md`

Work autonomously. Consult the requirements and existing documentation whenever a decision is unclear. Do not stop after planning: implement the changes, run the complete test suite, exercise the application end to end, and inspect every generated PDF page before declaring completion.

The implementation must remain local-first, using Angular/TypeScript for the frontend and Python/FastAPI for the backend. Do not add unnecessary cloud infrastructure, authentication, billing, or multi-tenant functionality.

## Starting point

Audited commit: `f17c999`

Overall audit result: **72/100 — strongest of the two implementations, but not release-ready.**

The current implementation has a strong architecture, structured report model, broad source extraction, persisted corrections, row editing, source provenance, and a report structurally close to the reference. The remaining work is concentrated around correctness, job reliability, PDF overflow, security, accessibility, testing, and final report completeness.

## Non-negotiable engineering rules

1. Do not hardcode Boardwalk filenames, sheet names, row numbers, property values, or local absolute paths in production code.
2. Treat the supplied data as one example dataset, not a fixed template.
3. Preserve extracted source provenance and manual overrides separately.
4. Never invent missing property, financing, underwriting, or narrative information.
5. Missing or uncertain values must be visible and manually correctable.
6. Invalid corrections must never be persisted.
7. A failed or unsupported file must not prevent other files from processing or the project from reaching review.
8. Generated reports must never silently omit or clip content.
9. A generated version must be an immutable snapshot of the reviewed data at the moment generation is requested.
10. Keep changes focused. Extend the existing architecture rather than replacing it without evidence.
11. Do not weaken assertions, increase timeouts to conceal races, or skip failing tests.
12. Do not claim success until all automated and manual acceptance checks below have passed.

## Priority 0: release blockers

### 1. Make corrections typed, validated, atomic, and recoverable

Current risk:

- `backend/app/api/report_data.py` accepts `Any` for every correction.
- It does not consistently validate that a path exists, that the field is editable, or that the value matches the field's declared kind.
- Overrides are saved before recalculation finishes.
- A malformed numeric correction can return HTTP 500 while remaining persisted, poisoning future review, preview, and generation requests.
- Derived and read-only fields can be targeted through the API even if the UI disables them.

Required implementation:

1. Resolve every requested path against the current `ReportData` before writing anything.
2. Return HTTP 422 for unknown paths.
3. Return HTTP 422 for derived/read-only fields and derived table cells.
4. Coerce values according to `Field.kind`:
   - `money` and `number`: finite decimal/float only.
   - `integer`: finite whole number only.
   - `percent`: accept one documented representation and enforce a valid domain.
   - `date`: valid ISO date only.
   - `text` and `longtext`: strings with reasonable length limits.
5. Add semantic constraints where applicable:
   - occupancy and rates must be within their valid ranges;
   - units, lease counts, square feet, periods, and monetary counts that cannot be negative must reject negative values;
   - date relationships such as maturity after effective date should produce a validation issue.
6. Apply the complete batch to an in-memory copy.
7. Recompute all derived values.
8. Run validation and verify serialization/render preparation succeeds.
9. Persist the complete correction batch in one SQLite transaction only after all checks pass.
10. On failure, persist nothing.
11. Add an administrative recovery path that can remove a malformed legacy override without first loading the poisoned effective report.
12. Ensure manual row additions and deletions receive the same path, type, and transaction validation.

Required tests:

- Unknown field path returns 422 and changes nothing.
- Read-only/derived field edit returns 422 and changes nothing.
- Invalid number, integer, percent, date, `NaN`, and infinity return 422.
- A batch with one invalid change persists none of its changes.
- A valid input edit recomputes every dependent value.
- A failed correction does not break subsequent report-data, preview, or generation requests.
- Manual row values are typed and totals recompute correctly.
- Legacy invalid overrides can be safely reset.

Primary files:

- `backend/app/api/report_data.py`
- `backend/app/models.py`
- `backend/app/consolidate/builder.py`
- `backend/app/consolidate/calc.py`
- `backend/app/db.py`

### 2. Fix upload, processing, and recovery races

Current risk:

- File records are created and worker jobs are submitted while the multipart batch is still being handled.
- A supported file can finish while a later unsupported file still has its initial `queued` state.
- The worker then declines to consolidate because it sees an active file; the unsupported branch changes state without triggering consolidation.
- The project can remain in `processing` indefinitely with no running job.
- Increasing test timeouts does not repair this race.
- Report and narrative jobs left in active states are not recovered after restart.
- A document-type override submitted during active processing can persist without being applied.

Required implementation:

1. Save all uploaded file records and determine supported/unsupported state before submitting any worker.
2. Only after the complete batch is durable, enqueue supported files.
3. Use one project-level completion/coordinator operation that determines when every file is terminal.
4. Make consolidation idempotent and safe when invoked more than once.
5. Every transition to `processed`, `failed`, `unsupported`, or excluded must trigger or schedule the same completion check.
6. Ensure a project with only unsupported/failed/unrecognized files reaches a stable review state with visible issues.
7. Recover files, reports, and narrative jobs left queued/running/rendering after process restart.
8. Either disable document-type changes while a file is active or guarantee a subsequent job applies the new override.
9. Make keyed worker submission and status transitions thread-safe.
10. Ensure project stage reflects persisted work, not merely the existence of a report row.

Required tests:

- Repeat a mixed supported/unsupported batch at least 100 times; every run must consolidate.
- Supported + corrupt + unsupported files must reach review with isolated file statuses.
- Unsupported-only and corrupt-only projects must not stay in processing.
- Multiple simultaneous uploads must not lose consolidation.
- Changing a type override during processing must either return 409 or reliably reprocess with the new value.
- Restart recovery tests for file, report, and narrative jobs.
- Duplicate generation requests must receive unique versions without a race.

Primary files:

- `backend/app/api/files.py`
- `backend/app/workers/jobs.py`
- `backend/app/workers/pool.py`
- `backend/app/main.py`
- `backend/app/db.py`

### 3. Prevent silent PDF clipping or data loss

Current risk:

- Report pages use fixed dimensions and `overflow: hidden`.
- Tables and narrative sections have unbounded content.
- Long content can disappear while report generation still reports success.

Required implementation:

1. Render the HTML in Chromium before printing.
2. Measure every `.page` element using both `scrollHeight` and `clientHeight`.
3. Detect horizontal and vertical overflow.
4. If overflow exists, reject generation with a clear error containing:
   - page number;
   - section name;
   - overflow direction and approximate amount;
   - suggested correction when possible.
5. Where appropriate, add explicit continuation-page or density rules for tables, but do not silently shrink text below a readable size.
6. Confirm all expected section-ending markers appear in extracted PDF text.
7. Keep the intended ten-page primary format for the supplied reviewed dataset.
8. Ensure a failed render leaves a failed version record and does not expose a partial PDF as downloadable.

Required tests:

- Very long status and narrative text must be rejected or fully preserved.
- Excess underwriting, comp, capex, new-lease, and renewal rows must be rejected or paginated without loss.
- Both vertical and horizontal overflow are detected.
- A normal reviewed Boardwalk report remains exactly ten pages at 720 × 404.88 points.
- PDF text contains unique markers placed at the end of every page's content.

Primary files:

- `backend/app/report/render.py`
- `backend/app/report/static/report.css`
- `backend/app/report/templates/report.html`

### 4. Remove the stored-XSS path in the report preview

Current risk:

- Chart series names can originate from uploaded or edited data.
- `backend/app/report/chart.py` inserts those names into SVG markup without XML escaping.
- The finished SVG is rendered with Jinja's `safe` filter in the same-origin preview.

Required implementation:

1. XML-escape all dynamic SVG text and attribute content.
2. Prefer constructing SVG from safe primitives instead of string concatenation where practical.
3. Continue using Jinja autoescaping for ordinary report content.
4. Add adversarial tests containing closing tags, event handlers, scripts, quotes, and entity sequences.
5. Verify the resulting preview contains text only and no executable node or handler.

Primary files:

- `backend/app/report/chart.py`
- `backend/app/report/render.py`
- `backend/app/report/templates/report.html`

## Priority 1: extraction and consolidation accuracy

### Period-aware source selection

Capital-call and distribution candidates must be ranked by reporting period/report date, not by row count. A populated older report must never override a current zero-activity report.

Add tests for:

- current zero activity versus older populated activity;
- multiple current-period documents with conflicting totals;
- undated documents;
- files uploaded in every order.

Primary files:

- `backend/app/consolidate/select.py`
- `backend/app/consolidate/builder.py`

### Cross-file identity and reconciliation

1. Extract property identity wherever the source provides it.
2. Prevent silent consolidation of different properties.
3. Surface alternatives and source references for conflicting financial, occupancy, rent, debt, and market values.
4. Add materiality-aware reconciliation issues.
5. Require user resolution for conflicts that can materially change the report.

### Generalization tests

Retain the new randomized/shifted dataset test and extend it to cover:

- the supplied rent-chart workbook rather than dropping it;
- reordered multi-row headers;
- missing optional columns;
- extra leading/trailing rows and columns;
- renamed files and sheets;
- alternate date and percentage representations;
- extra irrelevant sheets and pages;
- image-only PDFs with a clear OCR-required status;
- duplicated same-period sources;
- an unrelated property's report in the same upload batch.

Do not make fixtures pass by adding dataset-specific coordinates or names.

### File status semantics

Do not label an unrecognized and unused file as successfully processed. Use an explicit state such as `unrecognized` or `unused`, show it distinctly in the UI, and explain the manual type-override option.

## Priority 1: report accuracy and completeness

Generate a new verified report from the current code. The existing runtime `report-v6.pdf` is not acceptable as the final handoff because it contains incorrect and incomplete reviewed content.

### Mandatory factual correction

- The lender must be **Fannie Mae**, not Freddie Mac.

### Complete or explicitly review these areas

- property description, site size, class, hold period, and location;
- full original underwriting budget;
- financing borrower, original and current balance, effective date, maturity, term, amortization, interest-only period, prepayment, reserves, escrow, and recourse;
- financial and capital commentary;
- operating status and next-quarter goals;
- all reference financial rows and variance directions;
- capital annual budget and period/YTD values;
- comp units, vintage, leased percentage, asking rent, effective rent, and concession;
- new-lease and renewal counts, rents, trade-out dollars, percentages, and square feet.

Values absent from the source files must remain clearly marked for manual review until a reviewer enters them. Do not encode the reference values as production defaults.

### Visual verification

1. Use the newly committed Source Serif 4 and JetBrains Mono fonts and verify they are embedded in the PDF.
2. Compare all ten pages against the reference at full resolution.
3. Confirm there are no clipped headers, footers, labels, tables, or narratives.
4. Confirm page numbering and section ordering match the primary reference structure.
5. Improve hierarchy, whitespace, table density, and narrative balance where the current pages are visibly sparse.
6. Add property/logo imagery only through a reusable upload/configuration mechanism; do not hardcode Boardwalk assets.
7. Produce a clearly identified final sample PDF in a deliberate output/deliverables folder.
8. Store or document the exact reviewed-data snapshot and commit used to create it.

## Priority 1: frontend quality and accessibility

### Testing

The repository currently has no Angular unit-test target. The opt-in Playwright E2E test is valuable but is not a replacement for focused component and service tests.

Required work:

1. Add a working Angular test target.
2. Add tests for the API service, projects page, upload states, review edits, reset behavior, conflict selection, row insertion/deletion, generation states, and error handling.
3. Keep the full browser E2E test and run it automatically in CI or the documented acceptance command.
4. Add a failed-backend/load-state test for every route.
5. Test narrow viewport behavior.

### Accessibility

Meet a defensible WCAG 2.2 AA baseline:

- turn clickable issue `<div>` elements into keyboard-operable buttons or links;
- provide accessible names and roles for all interactive controls;
- add `aria-current` to the active workflow step;
- use live regions for uploads, processing, saves, validation errors, narrative drafting, and report generation;
- replace CSS-only disabled anchors with genuinely disabled controls or guarded navigation;
- preserve visible keyboard focus on the file picker/drop zone;
- correct small-text contrast failures;
- add responsive reflow for narrow screens and 200–400% zoom;
- provide useful focus movement after validation failures and section jumps.

## Priority 2: reproducibility and documentation

1. Lock Python dependencies to a tested set of versions. Preserve the npm lockfile.
2. Correct the `.env` example and README so `APP_DATA_DIR` resolves consistently regardless of launch directory.
3. Provide one reliable clean-start command or script for local evaluation.
4. Document how to clear only application runtime data safely.
5. Document all generated-file locations.
6. Ensure no developer-machine absolute paths, credentials, or test-specific values are committed.
7. Add automated checks for:
   - Python tests and static checks;
   - Angular unit tests and production build;
   - full browser E2E;
   - supplied and mutated dataset tests;
   - dependency vulnerabilities;
   - PDF page count, dimensions, embedded fonts, overflow, and expected text.

## Suggested 40-hour allocation

| Workstream | Hours |
|---|---:|
| Typed, transactional correction system | 7 |
| Upload races, job recovery, version snapshot integrity | 6 |
| PDF overflow detection and layout handling | 6 |
| Extraction selection, reconciliation, and mutation coverage | 6 |
| Final report completion and visual QA | 5 |
| Angular tests and accessibility | 5 |
| Security and dependency reproducibility | 2 |
| Clean-install end-to-end acceptance run | 3 |
| **Total** | **40** |

## Required verification commands

Adapt paths and ports as necessary, but the final handoff must show equivalent successful evidence.

```bash
# Backend: clean environment
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pip check
pytest -q

# Real and mutated dataset checks
TEST_DATASET_DIR="../../SOURCE FILES" pytest tests/test_dataset.py -v

# Frontend
cd ../frontend
npm ci
npm test -- --watch=false
npm run build
npm audit --audit-level=high

# Running application browser test
cd ../backend
UI_E2E_URL=http://localhost:4200 \
TEST_DATASET_DIR="../../SOURCE FILES" \
pytest tests/test_ui_e2e.py -v

# Generated PDF structure
pdfinfo /path/to/final-report.pdf
pdffonts /path/to/final-report.pdf
pdftotext -layout /path/to/final-report.pdf -
```

Also perform a manual browser walkthrough:

1. Create a new project.
2. Upload all supplied files plus one unsupported and one corrupt file.
3. Observe visible processing progress and isolated failures.
4. Inspect extraction source details.
5. Resolve a conflict.
6. Correct scalar fields and table cells.
7. Add and delete a manual underwriting row.
8. Confirm derived values recompute.
9. Generate and download version 1.
10. Make further edits without re-uploading or reprocessing.
11. Generate and download version 2.
12. Confirm version 1 is unchanged and version 2 contains the corrections.
13. Restart the backend during processing and generation and verify recovery.
14. Render every PDF page to an image and inspect it at full size.

## Definition of done

Do not mark the work complete until all of the following are true:

- [ ] Invalid corrections return a clear 4xx response and never alter persisted state.
- [ ] Derived/read-only fields cannot be overridden through the API.
- [ ] A failed correction cannot make the review screen or report generation unusable.
- [ ] Mixed file batches complete reliably in at least 100 repeated concurrency runs.
- [ ] Unsupported, corrupt, and unrecognized files are isolated and clearly represented.
- [ ] Restart tests recover file, report, and narrative work.
- [ ] Report-version creation is concurrency-safe and snapshots reviewed data at request time.
- [ ] No generated PDF can succeed while content is clipped or omitted.
- [ ] Crafted uploaded or edited text cannot inject active HTML/SVG into the preview.
- [ ] Period-aware selection prevents older Slate activity from replacing current zero activity.
- [ ] Cross-property and material numeric conflicts are surfaced for review.
- [ ] The complete supplied dataset and expanded mutated fixtures pass without dataset-specific production logic.
- [ ] Angular unit tests, backend tests, browser E2E, production build, and dependency checks all pass.
- [ ] Accessibility issues listed above are fixed and tested.
- [ ] A clean machine can be set up using only the repository documentation.
- [ ] The final PDF uses the intended fonts and has ten pages at the reference dimensions.
- [ ] The final PDF contains Fannie Mae and all reviewed required content.
- [ ] Every page has been visually compared with the reference, with no clipping or blank unintended regions.
- [ ] The final sample PDF and its reviewed-data snapshot are clearly delivered.

## Final handoff format

When finished, report:

1. the commit reviewed;
2. a concise list of implemented fixes;
3. every verification command and its exact result;
4. any intentionally unresolved limitation and why it is acceptable under the requirements;
5. the final PDF path;
6. the reviewed-data snapshot path;
7. confirmation that all ten pages were visually inspected;
8. confirmation that no source requirement was knowingly omitted.
