# Implementation status

Snapshot taken on 2026-09-07 at the first push to GitHub. Code state: commit `c580797` plus the documentation
commit that follows it. This file says what exists, how it was verified, and what is still wrong, weak or
missing. Read it together with `CHANGELOG.md` (how the code got here) and `validation/real_world/ASSESSMENT.md`
(the scored verdict with its evidence).

## 1. What is implemented

### Ingestion

- Upload any number of `.xlsx`, `.xlsm` and `.pdf` files in any order and under any name. Each file is an
  isolated job in an in-process thread pool; one bad file never blocks the others.
- Readers turn workbooks and text PDFs into a common `Document` (sheets or pages, rows of cells).
- A content-signature classifier recognises twelve document types across four export families: Yardi (budget
  comparison, balance sheet, rent roll, market rent schedule, lease trade-out), HelloData (listings, comp
  summary), CoStar (submarket Excel and PDF), the rent chart workbook, and Slate (capital calls, distributions).
  Nothing keys on filenames, sheet names or cell coordinates.
- File statuses: `queued`, `processing`, `processed`, `failed`, `unsupported`, `unrecognized`, `needs_ocr`.
  A reviewer can set the type of an unrecognised file by hand, exclude a file without deleting it, or delete it.
- Cover photo and logo upload through an asset API; images are frozen per report version.

### Extraction and consolidation

- One extractor per document type, each producing a typed payload with `{file, sheet or page, row}` provenance
  on every value.
- Source selection ranks overlapping exports deterministically (YTD budget comparison over monthly, the listings
  export containing the subject over one that does not, the latest Slate export by print date) and sets aside
  sources that name another property.
- The builder consolidates everything into `ReportData`: twelve sections in page order, each with fields and
  tables, alternatives attached wherever two sources disagree.
- Derived values (variances, weighted averages, per-unit figures, comp averages, quarter changes) recompute from
  inputs, so a corrected input updates everything downstream.
- Validation produces issues with severities: conflicts, reconciliation mismatches, date problems, and missing
  values (warnings when the completeness specification requires them, informational otherwise).
- Comparable rows come from whichever source defines the comp set; rows without rents are kept with empty
  editable cells; averages use available values with the method stated in the footnote.

### Review and correction

- Every value shows a status chip (extracted, derived, edited, AI draft, missing, conflict) and a source button.
- Corrections are typed and atomic: a batch is validated, coerced, recomputed, validated again, serialised and
  rendered in memory before one persist; any failure returns 422 and stores nothing.
- Rows can be added to the underwriting budget, comp set and rent-trend tables; rows can be deleted.
- Stored corrections are listed and can be reset one at a time or all at once, even when the data cannot load.
- A completeness panel lists every item a finished report still needs, page by page, each jumping to its section.

### Narratives

- Providers: Anthropic API (`api`), Claude Agent SDK on the local Claude Code login (`agent-sdk`), a
  deterministic `mock` for tests and demonstrations, or `off`.
- Drafting fills only empty fields from structured values, never invents property events, and never overwrites
  reviewer text. Each draft stores a hash of the figures it used and is flagged stale when those figures change.

### Report generation

- Live HTML preview served with a strict Content-Security-Policy in a sandboxed iframe.
- Immutable versions: each snapshots the reviewed data at request time, keeps its own PDF, HTML, JSON snapshot
  and frozen images. Version numbers are unique under an immediate transaction.
- Ten fixed pages at 720 x 404.88 pt with Source Serif 4 and JetBrains Mono embedded, no Type 3 fonts.
- Every page is measured in Chromium before printing; an overflowing page fails the version with page, section
  and amount instead of clipping.
- Versions generated with outstanding items are drafts: DRAFT marker on the cover and every footer, `-draft.pdf`
  download name, `complete: false` and `gap_count` in the API.

### Operations

- SQLite with WAL, JSON columns, migrations on start; restart re-queues interrupted jobs.
- `scripts/run.sh` for setup, start and a guarded runtime-data reset; `scripts/check.sh` for every automated
  check; `scripts/check_pdf.py` for structure, font and raster checks on any generated PDF.

## 2. How it was verified

Final full run of `scripts/check.sh --e2e` at `c580797`:

| Check | Result |
|---|---|
| Backend unit, API, reliability, corrections, render and scenario tests | 146 passed, 4 skipped (opt-in live checks) |
| Supplied Boardwalk dataset plus a mutated copy | 2 passed |
| pip-audit on the lock file | no known vulnerabilities |
| Angular unit tests (vitest) | 35 passed in 6 files |
| Angular production build | passed |
| npm audit (high) | 0 vulnerabilities |
| Browser end-to-end (Playwright against the running app) | 1 passed |
| Sample deliverable PDF structure and raster check | OK |

Validation runner (`validation/real_world/run_validation.py`), same commit:

| Scenario | Classification | Gaps | Drafts | Result |
|---|---|---:|---:|---|
| Riverbend Station 4Q25 | complete | 0 | 12 | pass, complete version, no draft marker, image on pages 1 and 2 |
| Harbor Point 3Q26 | structural | 40 | 0 | pass, exact gap set and warnings, draft marker everywhere |
| Pine Ridge 4Q26 | structural | 42 | 0 | pass, three partial comps kept with correct averages |
| Lakeside Commons 1Q27 | structural | 43 | 0 | pass, duplicate export, decoy property and OCR file isolated |

All 40 rendered pages were inspected by eye. Evidence lives under `validation/real_world/results/`.

Readiness score in `ASSESSMENT.md`: **90/100**. The score reflects a suite that proves the workflow on four
synthetic properties and one real dataset. It does not claim live-provider coverage, and one end-to-end flake
(below) remains unexplained.

## 3. Known flaws

These are defects or weaknesses in what exists, as opposed to features that were never built.

1. **Unexplained end-to-end flake.** On 2026-09-05 one full run failed the browser test on its processed-file
   count after four seconds, although the assertion carried a two-minute timeout and the backend had processed
   every file. Two immediate re-runs passed. The cause was not found. Treat a single failure of
   `tests/test_ui_e2e.py` as suspect and re-run before investigating the app.
2. **Legend layout is estimated, not measured.** The chart wraps its legend using 6.2 px per character. That is
   conservative for the fonts in use, but a very long series name could still be wider than estimated. A
   measured layout would need text metrics in the renderer.
3. **The overflow guard only sees page boxes.** It catches content that runs past a page. It cannot see text
   clipped inside an SVG or a container with hidden overflow, which is how the legend defect slipped through
   until visual inspection. Page images from the validation runner are the safety net for this class of bug.
4. **Equal same-period sources have no tie-breaker.** Two exports of identical date and completeness leave the
   choice to the reviewer, who excludes one. The application flags the pair but does not pick.
5. **Property-name heuristics.** A Yardi title such as "Lakeside Villas (99001)" is authoritative; a name read
   from a text column only raises a warning. A decoy file with no title and a matching layout would merge.
6. **Comp metadata depends on the summary sheet.** Unit counts and vintages of comparables come from the
   HelloData comp summary; the listings export alone leaves those cells empty until a reviewer fills them, and
   the averages are then simple rather than unit-weighted (the footnote says so).
7. **Parts of the Boardwalk sample are hand-entered.** Loan terms, the underwriting budget, property facts, the
   business plan, status items and goals do not exist in any supplied export. They were typed in from the
   client's example report, as a reviewer would. The sample proves the workflow, not extraction of those values.
8. **The Boardwalk narratives came from a live provider.** They were drafted by the API provider and reviewed;
   they cannot be regenerated deterministically. The validation suite uses the mock provider for that reason.
9. **Live AI providers are not exercised automatically.** `LLM_LIVE=1` runs one real call by hand. Prose quality
   from a live model is unmeasured.
10. **Three validation fixtures need an external runtime to regenerate.** Harbor Point, Pine Ridge and Lakeside
    were generated with a Codex-bundled workbook tool; their workbooks are committed, so the tests run anywhere,
    but changing those fixtures needs that tool. Riverbend regenerates with the backend virtualenv alone.
11. **Percent and date parsing are heuristics.** Values like `91.71`, `0.9171` and `91.71%` are normalised by
    magnitude and format; an export that reports a fraction above 1 for a real percentage would be misread and
    would surface only as a range conflict or a visibly wrong number on the review screen.
12. **Long tables are refused, not continued.** A quarter with more capital lines or comparables than a page
    holds fails generation with the overflow message. There is no continuation page.

## 4. Known limitations (by design or out of scope)

- No OCR: image-only PDFs are isolated with `needs_ocr`.
- Only the four supported export families are extracted. An unrelated accounting schema needs a new extractor
  or mapping; `pl_mapping.toml` and `capex_mapping.toml` cover label variations, not new layouts.
- No loan-document extractor: financing terms beyond principal, monthly interest and reserve balance are manual.
- Always-manual fields: acquisition date without a CoStar sale record, submarket and market names without a
  CoStar PDF, building class, site acres, hold period, description, business plan, underwriting rows and their
  period note, most loan terms, outlooks and financing commentary, rent-trend caption, status items, goals, and
  the no-activity statement when leasing tables are empty. The suite proves a reviewer can complete all of them.
- Single local user: no authentication, no roles, no audit trail beyond stored corrections and version snapshots.
- SQLite and an in-process thread pool: fine for one reviewer on one machine, not for a shared server.
- The `agent-sdk` provider is a developer convenience on a personal login; a distributed product must use the
  API-key provider.
- The rent-trend chart needs the pre-built rent chart workbook for a full twelve-month history.

## 5. Environment quirks worth knowing

- If port 8000 is busy, set `BACKEND_PORT` in `.env`; `scripts/run.sh start` and the Angular proxy both read it.
- The Angular dev server occasionally dies on macOS during long sessions; restart it before the browser test.
- A checkout path containing `)` breaks vitest's glob; `frontend/vitest.config.mts` escapes it.
- npm 10.9 cannot add new dependencies in this checkout (an arborist bug); `npx npm@11 install <pkg>` works and
  `npm ci` is unaffected.
- `scripts/check.sh --e2e` refuses to start without `TEST_DATASET_DIR` (the folder that holds only the source
  exports) and `UI_E2E_URL`; the pip-audit step can take several minutes on a cold cache.

## 6. Documentation debt

- `CLAUDE_CODE_HANDOFF.md` is the first audit's brief (72/100 at `f17c999`). Everything it asked for has been
  done or superseded; it is kept as history, not as a task list.
- `docs/implementation-plan.md` is the original build plan and predates most of the design decisions in
  `docs/superpowers/specs/`.
- Test coverage is not measured; the suite is organised by behaviour, not by line coverage.

## 7. What would raise the score

1. A measured legend and a raster-diff check per page against a golden image, to close the SVG-clipping class.
2. OCR behind the reader interface, so scanned PDFs join the workflow.
3. A loan-document extractor for the financing page.
4. A recorded live-provider run in CI with a replay fixture, so prose quality is at least regression-tested.
5. Continuation pages with renumbered footers for long tables.
6. A deterministic tie-breaker for equal same-period sources, with the choice shown as a conflict.
