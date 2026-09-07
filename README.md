# Investor Report Generator

Turns a folder of property source files (Yardi, HelloData, CoStar and Slate exports) into a ten-page quarterly LP
investor report. Upload the files, review every extracted value with the file, sheet and row it came from, correct
what is wrong or missing, let the optional AI draft the narrative paragraphs from the reviewed numbers, generate
an immutable PDF version, edit, regenerate.

Local-first by design: a FastAPI backend with SQLite, an Angular 21 frontend, and Playwright's Chromium for the
PDF. Nothing leaves the machine unless you enable AI drafting with your own key.

Status: feature-complete for the brief, verified on the supplied Boardwalk dataset and on four independent
property packages. See `STATUS.md` for what is implemented and what is still weak, `CHANGELOG.md` for the
history, and `validation/real_world/ASSESSMENT.md` for the scored verdict (90/100) with its evidence.

## Contents

1. [What it produces](#what-it-produces)
2. [How it works](#how-it-works)
3. [Repository layout](#repository-layout)
4. [Prerequisites](#prerequisites)
5. [Quick start](#quick-start)
6. [Configuration](#configuration)
7. [Using the application](#using-the-application)
8. [Structural versus complete](#structural-versus-complete)
9. [Supported source documents](#supported-source-documents)
10. [API reference](#api-reference)
11. [Data model](#data-model)
12. [Where files are](#where-files-are)
13. [Developer notes](#developer-notes)
14. [Verification](#verification)
15. [Real-world validation suite](#real-world-validation-suite)
16. [Sample deliverable](#sample-deliverable)
17. [Documentation index](#documentation-index)
18. [Known limitations](#known-limitations)
19. [Next steps](#next-steps)
20. [Licences and data](#licences-and-data)

## What it produces

A ten-page 16:9 PDF (720 x 404.88 pt) that follows the structure of the client's reference report:

| Page | Section | Main sources |
|---:|---|---|
| 1 | Cover: property, location, units, vintage, acquisition, purchase price, preparer, cover photo | rent roll, balance sheet, CoStar, reviewer |
| 2 | Property Description: facts, in-place rent by unit type with quarter-over-quarter change | market rent schedule, rent roll, reviewer |
| 3 | Property Summary and Business Plan: capital summary, underwriting budget, rent-trend chart | balance sheet, Slate, rent chart workbook, reviewer |
| 4 | Financing Overview: loan terms, phases, prepayment, reserves | balance sheet, reviewer |
| 5 | Financial and Capital Commentary: takeaway, revenue, expenses, NOI, outlooks | derived from page 6 and 7, AI draft or reviewer |
| 6 | Financial Performance: quarter and year-to-date actual versus budget | Yardi budget comparison |
| 7 | Capital Projects: line items, quarter and year-to-date, annual budget | Yardi budget comparison (capital section) |
| 8 | Submarket Comparison: vacancy, asking rent, construction, comp set table | CoStar, HelloData listings and comps |
| 9 | Occupancy and Leasing: occupancy, new leases and renewals by floor plan | rent roll, lease trade-out |
| 10 | Status Update and next-quarter Goals | reviewer |

Every version is an immutable snapshot with its PDF, HTML and JSON data. A version generated while required items
are still missing is a **draft**, marked on every page and named `...-draft.pdf`.

## How it works

```
Upload → readers (xlsx/pdf → Document) → classifier (content signatures → DocType per sheet/PDF)
      → extractors (DocType → typed JSON payload with row/page provenance)
      → select (choose between overlapping sources, check they describe one property, rank Slate exports by date)
      → builder (consolidate into ReportData: sections of Fields and Tables, alternatives on disagreement)
      → calc.recompute (derived values) → validate (missing / conflict / reconciliation / date checks)
      → completeness (structural versus complete, gaps by page)
      → review UI (corrections validated and stored as overrides, applied on every read)
      → narratives (optional drafts from the structured values, with a basis hash)
      → version snapshot → Jinja HTML template → layout check → Chromium PDF
```

Four rules hold everywhere:

- **Provenance.** Every extracted value keeps the file, sheet or page, and row it came from, and shows it in the UI.
- **Nothing invented.** Values that no source contains stay visibly missing and editable. The AI drafts only from
  reviewed numbers and never writes property events, lender actions or goals.
- **Corrections are separate from extraction.** Reviewer edits are stored as overrides and applied on every read,
  so the original extraction is never lost and any correction can be reset.
- **Versions are immutable.** Generation snapshots the reviewed data at that moment; later edits and image
  replacements never change an existing version.

## Repository layout

```
backend/
  app/
    readers/        xlsx and pdf readers producing a common Document
    classify/       content-signature classifier and DocType
    extract/        one extractor per document type, all with provenance
    consolidate/    select, builder, calc, validate, corrections, completeness, mapping
    report/         Jinja template, CSS, embedded fonts, SVG chart, formatters, Chromium renderer
    services/       narrative drafting (api, agent-sdk, mock)
    workers/        thread pool and job coordination
    api/            FastAPI routers (projects, files, report-data, report) and serialisation
    db.py           SQLite schema, migrations and access
    config.py       settings from the environment and .env
  config/           pl_mapping.toml and capex_mapping.toml (label patterns, editable without code)
  tests/            pytest suite (unit, API, reliability, corrections, render, dataset, scenarios, browser)
  requirements*.txt / requirements.lock
frontend/
  src/app/
    core/           API service and models
    pages/          projects, files, review (field and table editors), report
    shared/         stepper, status chip
    testing/        fixtures for the specs
  vitest.config.mts, proxy configuration, package.json
validation/real_world/
  scenarios/        four independent property packages with expected.json oracles
  harness.py, pdf_checks.py, run_validation.py, build_riverbend.py
  results/          generated evidence: PDFs, snapshots, completeness, page images, assessment
  README.md, ASSESSMENT.md
scripts/            run.sh (setup, start, reset-data), check.sh (every check), check_pdf.py
deliverables/       the Boardwalk 2Q26 sample report, its reviewed-data snapshot and a note on how it was produced
docs/               implementation plan, design documents and task plans
CHANGELOG.md, STATUS.md, CLAUDE_CODE_HANDOFF.md, .env.example
```

## Prerequisites

- Python 3.12 or newer (3.13 tested).
- Node.js 22.12 or newer and npm 10 or newer (22.16 with npm 10.9 tested; with nvm: `nvm use 22`). Node 18 is
  too old for Angular 21.
- Chromium for PDF rendering, installed once by Playwright during setup (about 150 MB).
- No cloud services. AI narrative drafting is optional and needs either an Anthropic API key or a local Claude
  Code login.

## Quick start

```bash
scripts/run.sh setup        # venv, locked Python deps, Chromium, npm ci, .env from .env.example
scripts/run.sh start        # backend on http://localhost:8000 and the Angular app on http://localhost:4200
scripts/run.sh reset-data   # wipes ONLY runtime data (uploads, database, generated reports); code and dependencies stay
```

Open http://localhost:4200. `GET http://localhost:8000/api/health` reports whether the PDF renderer and an AI
provider are available. If port 8000 is taken on your machine, set `BACKEND_PORT` in `.env` before starting;
both the backend and the Angular proxy read it.

### Backend, step by step

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.lock                        # the tested, pinned set; requirements*.txt hold the ranges
python -m playwright install chromium                   # one-time, needed for PDF output
python -m pip check
cp ../.env.example ../.env                              # edit if you want another data folder, port or workers
uvicorn app.main:app --reload --port 8000
```

`requirements.txt` holds the runtime ranges, `requirements-dev.txt` adds pytest, httpx and pip-audit,
`requirements-llm.txt` adds the optional drafting providers. `requirements.lock` pins all of them plus the PDF
checking tools (pypdfium2, pdfplumber, Pillow) used by the scripts and the validation suite.

### Frontend, step by step

```bash
cd frontend
npm ci
npm start                    # Angular dev server on http://localhost:4200, proxies /api to the backend port
```

## Configuration

Environment variables, read from the process environment first and then from `.env` at the repository root:

| Variable | Default | Purpose |
|---|---|---|
| `APP_DATA_DIR` | `backend/data` | SQLite database, uploaded files, generated reports. A relative path is taken from the repository root whichever directory the backend is started from; absolute paths work too |
| `APP_WORKERS` | `3` | Parallel file-processing threads |
| `APP_MAX_UPLOAD_MB` | `50` | Per-file upload limit |
| `APP_CORS_ORIGINS` | `http://localhost:4200` | Allowed browser origins |
| `BACKEND_PORT` | `8000` | Port the backend listens on and the Angular dev proxy forwards `/api` to |
| `NARRATIVE_PROVIDER` | `auto` | `api` (Anthropic SDK with an API key), `agent-sdk` (Claude Agent SDK on the local Claude Code login), `mock` (deterministic drafts built only from the structured figures; for tests and offline demonstrations), `off`. `auto` picks `api` when a key is set, else `agent-sdk` when that package is installed, else nothing |
| `ANTHROPIC_API_KEY` | unset | Enables the `api` provider |
| `ANTHROPIC_MODEL` | unset | Model override. `api` defaults to `claude-opus-5`; `agent-sdk` defaults to the Claude Code CLI's configured model |

### External services

| Service | Purpose | Variable | Credentials |
|---|---|---|---|
| Anthropic Claude API (`api` provider) | Drafts narrative paragraphs from the structured, reviewed numbers. Optional; the app is fully functional without it. | `ANTHROPIC_API_KEY` | Your own key in `.env`. |
| Claude Agent SDK (`agent-sdk` provider) | Same drafting through the bundled Claude Code CLI, using whatever that CLI is logged in with. Meant for a developer's own machine; per Anthropic's terms a distributed product must use the API-key provider. | none (`pip install -r backend/requirements-llm.txt`, then log in with `claude`) | The CLI's own credentials; the app stores nothing. One call per narrative field, no tools, no settings or CLAUDE.md loaded. |

Nothing else leaves the machine. Playwright's Chromium is downloaded once at setup time.

## Using the application

1. **Create a report.** Projects page, enter a name, Create.
2. **Upload source files.** Files page, drop or pick `.xlsx` / `.xlsm` / `.pdf` files (any names, any order; the
   drop zone is keyboard operable). Every file gets a status: `queued`, `processing`, `processed`, `failed`
   (corrupt or unreadable), `unsupported` (file type), `not recognised` (readable but no known report inside; not
   used until you set its type), `needs OCR` (image-only PDF). One bad file never blocks the others, and a
   project with nothing usable still reaches the review screen with the problems listed. Optional report images
   (cover photo, logo) are uploaded on the same page and embedded in the PDF.
3. **Review extracted data.** Review page. Left: report sections in page order with a count of items needing
   attention. Every value shows a status chip (extracted, derived, edited, AI draft, missing, conflict) and a
   "source" button naming the file, sheet or page, and row it came from. "Needs attention" filters to missing and
   conflicting values. Issues are listed per section; selecting one jumps to its section.
4. **Correct data.** Type into any editable field or table cell and Save. Every batch is validated before
   anything is stored: unknown paths, calculated fields, wrong types (text in a number, a percent above 100%, a
   malformed date, negative unit counts) are refused with a message and nothing from that batch is saved.
   Percentages are entered as percents and stored as fractions. Derived values recompute immediately. Conflicts
   show the alternatives; pick one. The underwriting budget, comp set and rent-trend tables accept new rows.
   "Reset" restores the extracted value; "Stored corrections" lists every saved correction and can reset any of
   them, or everything.
5. **Draft narratives (optional).** With a provider configured, "Draft narratives" fills the empty narrative
   fields from the section's reviewed numbers. Drafts carry the `AI draft` status, remember the figures they were
   written from, and are flagged when those figures change. Reviewer text is never overwritten.
6. **Check completeness.** The Review page's "Report completeness" panel and `GET /projects/{id}/completeness`
   list every item a finished investor report still needs, page by page. Each item jumps to its section.
7. **Generate the report.** Report page shows a live HTML preview. Generate PDF snapshots the reviewed data at
   that moment and renders it; versions are immutable, each with a downloadable PDF and its data snapshot. A
   version generated while items are outstanding is a draft (see below). If a page would overflow its fixed box,
   the version fails with the page, section and amount instead of producing a clipped PDF.
8. **Regenerate.** Edit on the Review page and press Generate again. Uploads are not reprocessed; earlier
   versions do not change.

Setting a file's document type manually: if a file was not recognised, pick its type in the Files page dropdown
and it is re-processed (refused with a message while the file is still processing). "Include" unticked excludes
a file from the report data without deleting it, useful when two exports overlap (for example two HelloData comp
sets) or when a file turns out to describe another property.

## Structural versus complete

Two different statements, kept apart on purpose:

- **Structural**: files were ingested, every supported value was extracted, and a ten-page PDF renders without
  overflow. This always works, whatever is missing, so a reviewer can preview a partly reviewed report at any time.
- **Complete**: every value and table a finished investor report needs has been reviewed and populated. One
  specification, `backend/app/consolidate/completeness.py`, decides this; the review screen, the API, the version
  record and the draft marker all read from it.

Requirements by page: property identity and facts (2), current and prior in-place rent (2), capital summary and
business plan (3), at least one underwriting row (3), the rent trend (3), financing terms and commentary (4), the
core financial lines with no reconciliation warning (6), capital projects (7), submarket KPIs and a usable comp
set (8), current and prior occupancy plus leasing rows or a reviewed no-activity statement (9), at least one
status item and one goal (10), and the narratives on pages 2, 5, 7, 8 and 9.

A genuine zero (a Slate export stating no calls, or a reviewer entering 0) satisfies a requirement; an empty
value does not. An empty leasing table counts as "no activity" only when the reviewer fills the no-activity
statement on the Occupancy section; otherwise it is missing. Reviewer text, extracted values and AI drafts all
count as populated; the number of drafts still awaiting review is reported separately. Missing values that the
specification requires are warnings on the review screen (naming their page); other missing values are
informational.

The fields that no supported export contains, and therefore always need a reviewer: acquisition date (when no
CoStar sale record is supplied), submarket and market names (when no CoStar PDF is supplied), building class,
site acres, hold period, description, business plan summary, the underwriting rows and their period note, the
loan terms other than principal, monthly interest and reserve balance, the outlook and financing commentary,
the rent-trend caption, status items and goals, and the no-activity statement when leasing tables are empty.

A version generated while gaps remain is a **draft**: DRAFT with the outstanding count on the cover and in
every footer, a `...-draft.pdf` download name, `complete: false` and `gap_count` in the API and the versions
list. Complete versions carry no marker.

## Supported source documents

Recognised by content, never by filename or sheet name:

| Document type | Recognised by (content signature) | Feeds |
|---|---|---|
| Yardi Budget Comparison | "Budget Comparison" with PTD/YTD actual, % var and annual columns | pages 5, 6, 7 |
| Yardi Balance Sheet | "Balance Sheet" with beginning, net change, total assets and current period columns | pages 1, 3, 4 |
| Yardi Rent Roll summary | "Rent Roll" with a "Summary Groups" block (% unit occupancy, occupied units, future residents) | pages 1, 2, 8, 9 |
| Yardi Market Rent Schedule | "Market Rent Schedule" with unit type, occupied units, average resident rent and sq ft | page 2 |
| Yardi Lease Trade-Out | resident name and lease rent columns with renewal and move-in sections | page 9; the page 3 trend when no rent chart workbook exists |
| HelloData listings export | Property Name, Asking Rent, Effective Rent and Leased Date columns per unit | page 8; the page 3 trend when no rent chart workbook exists |
| HelloData comp summary | a "Rent Comps" sheet with Yr Built, # units and leased %, or the one-page "Rents by unit type" PDF | page 8 |
| CoStar submarket Excel | period rows with vacancy rate, market asking rent, inventory and under-construction units | page 8 |
| CoStar submarket PDF | a CoStar "Submarket Report" with key indicators and sale comparables | pages 1, 2, 8 |
| Rent chart workbook | gross PSF, effective PSF and lease count by month for the subject and the comp set | page 3 |
| Slate capital calls | a "New capital call" statement, or its "no capital calls yet" form; exports are ranked by print date | page 3 |
| Slate distributions | a "New distribution" statement, or its "no distributions yet" form; exports are ranked by print date | page 3 |

Anything else that reads is `not recognised` (and can be typed by hand); image-only PDFs are `needs OCR`;
other file types are `unsupported`.

## API reference

All routes are under `/api`. Responses are JSON unless noted.

| Method and path | Purpose |
|---|---|
| `GET /health` | Renderer and AI-provider availability |
| `GET /projects`, `POST /projects` | List projects, create one |
| `GET /projects/{pid}`, `DELETE /projects/{pid}` | Project with its files, stage and summary; delete everything under it |
| `GET /doc-types` | The document types a reviewer can assign by hand |
| `POST /projects/{pid}/files` | Upload one or more files; every record is saved before any job starts |
| `GET /projects/{pid}/files` | File list with statuses and errors |
| `PATCH /projects/{pid}/files/{fid}` | Set the document type or the include flag |
| `POST /projects/{pid}/files/{fid}/reprocess` | Re-run extraction for one file |
| `GET /projects/{pid}/files/{fid}/extraction` | The raw extraction payload of one file, with provenance |
| `DELETE /projects/{pid}/files/{fid}` | Remove a file and its extraction |
| `PUT`, `GET`, `DELETE /projects/{pid}/assets/{kind}` | Cover photo or logo (`cover`, `logo`) |
| `GET /projects/{pid}/report-data` | The effective report data: sections, fields, tables, issues, summary and completeness |
| `PATCH /projects/{pid}/report-data` | A batch of corrections, row additions and deletions; 422 with nothing stored on any error |
| `GET /projects/{pid}/report-data/overrides` | The stored corrections |
| `POST /projects/{pid}/report-data/overrides/reset` | Remove some or all stored corrections without loading the report |
| `POST /projects/{pid}/report-data/rebuild` | Re-consolidate from the stored extractions |
| `POST /projects/{pid}/narratives` | Draft the empty or stale narrative fields with the configured provider |
| `GET /projects/{pid}/completeness` | Gaps by page, gap count, complete flag, drafts pending |
| `GET /projects/{pid}/report/preview` | The HTML preview (strict Content-Security-Policy) |
| `POST /projects/{pid}/reports` | Generate a version (202 Accepted; the job snapshots, checks layout and renders) |
| `GET /projects/{pid}/reports`, `GET /projects/{pid}/reports/{rid}` | Versions with `complete`, `gap_count`, status and error |
| `GET /projects/{pid}/reports/{rid}/download` | The PDF (`-draft` suffix in the name when gaps remained) |
| `GET /projects/{pid}/reports/{rid}/snapshot` | The immutable reviewed-data snapshot of that version |

## Data model

- **ReportData** holds twelve sections in page order: `property`, `in_place_rent`, `capital`, `underwriting`,
  `rent_trend`, `financing`, `financials`, `commentary`, `capex`, `submarket`, `occupancy`, `status`. A section
  has fields and tables; a table has rows, columns and totals.
- **Paths** address every value: `section.fields.name`, `section.tables.table.rows.row.column`,
  `section.tables.table.totals.column`. Corrections, issues, gaps and drafts all use them.
- **Field** carries a kind (money, number, percent, date, text, longtext, integer), the extracted value with its
  source, alternatives when sources disagree, an override when a reviewer corrected it, and a status chip derived
  from those.
- **Overrides** are stored per project as `{fields, rows, deleted_rows, ai_drafts}` and applied on every read.
  Drafts are `{text, basis}` where `basis` is a hash of the figures the draft was written from.
- **Versions** store the snapshot of the effective data, the PDF path, `complete` and `gap_count`.
- **SQLite tables**: `projects`, `files` (status, type, include flag, extraction payload), `report_data`
  (consolidated data and overrides), `reports` (versions). WAL mode, JSON columns, migrations on start.

## Where files are

| What | Where (`APP_DATA_DIR` defaults to `backend/data`) |
|---|---|
| Database | `APP_DATA_DIR/app.db` |
| Uploaded source files | `APP_DATA_DIR/projects/<project id>/uploads/` |
| Cover photo and logo | `APP_DATA_DIR/projects/<project id>/assets/` |
| Report versions | `APP_DATA_DIR/projects/<project id>/reports/report-v<N>.pdf`, `.html`, `.json` (the snapshot), plus the images frozen for that version |
| Sample deliverable | `deliverables/` |

`scripts/run.sh reset-data` removes only `projects/` and `app.db` (plus its journal files) inside
`APP_DATA_DIR`. It refuses the filesystem root, your home folder, the repository and any folder that holds neither
`app.db` nor `projects/`.

## Developer notes

### Job coordination

Files are processed by an in-process thread pool; each file is an isolated job. Every terminal transition
(processed, failed, unsupported, not recognised, needs OCR, excluded, deleted) calls one project-level completion
check, which consolidates once no file is queued or processing. The check is idempotent and serialised per
project, so it is also called after an upload batch and on a project read, and jobs left mid-flight by a restart
(files, report versions, narrative drafting) are re-queued at startup.

### Extraction strategy

- Every document is located by **content**: a Yardi Budget Comparison is a sheet whose header says "Budget
  Comparison" with Actual/Budget columns; a rent roll is a sheet with a "Summary Groups" block; HelloData
  listings are a sheet with Property Name / Asking Rent / Effective Rent columns, and so on
  (`classify/classifier.py`).
- Inside a document, values are located by **header and label text**. Multi-row headers are joined; Yardi's
  leading-space indentation tracks section hierarchy so capital lines can be told apart from operating lines.
  Column order does not matter and optional columns may be absent.
- The financial table maps canonical rows (Gross Potential Rent, Payroll, NOI and so on) to source lines through
  regex patterns in `backend/config/pl_mapping.toml`; capital-project regrouping lives in `capex_mapping.toml`.
  Both are editable without touching code.
- Values that appear in more than one file (unit count, year built, submarket vacancy, purchase price, Slate
  totals of the same date) are compared; a material difference becomes a `conflict` with the alternatives
  attached, for the reviewer to settle.

### Generalisation strategy

- Nothing keys on filenames, sheet names, cell coordinates, unit-type codes or GL account numbers.
- Multiple candidate sources for the same section are ranked deterministically (the Budget Comparison with YTD
  columns over a monthly one; the listings export that contains the subject property over one that does not;
  the most recent Slate export by its print date). The alternatives are listed as issues and the user can
  exclude a file to switch.
- Sources that name a different property (from a Yardi title such as "Lakeside Villas (99001)") are set aside
  with an error instead of being merged; names read heuristically from a text column only raise a warning.
- Missing files degrade gracefully: the section's fields become `missing` and editable; the rest of the report
  still generates.
- Percentages are normalised to fractions however the source expresses them (91.71, 0.9171 or "91.71%"); dates
  are parsed from several formats; extra sheets and pages that match nothing are ignored and reported.
- Comparable properties: the listings export defines the comp set; the HelloData comp sheet defines it only when
  there is no listings export; the one-page comp PDF defines it only when it is the only source and otherwise
  enriches matching rows. Cells with no source stay empty and editable, averages use available values only, and
  the footnote states per column whether the average is unit-weighted or simple.

### Corrections, snapshots and safety

- A correction batch is resolved against the current data (path must exist, target must not be calculated),
  coerced to the field's kind with semantic rules (occupancy in 0-1, counts and prices non-negative, four-digit
  years, text length limits), applied to an in-memory copy, recomputed, validated, serialised and rendered to
  HTML, and only then persisted in one statement. Any failure returns 422 and stores nothing.
- Stored corrections that no longer fit (a hand-edited database, an older build) are ignored on read with an
  issue, so the review screen and generation keep working; the reset endpoint removes them without loading the
  effective data.
- Report versions snapshot the reviewed data at request time; version numbers are allocated inside an immediate
  transaction and are unique.
- Before printing, every page is measured in Chromium; if content overflows the fixed page box the version fails
  with page, section, amount and a hint. Each page's footer sits in normal flow at the end of its content, so a
  clipped page would also lose its "NN / 10" marker in the PDF text.
- Chart text is XML-escaped and all other report content goes through Jinja autoescaping; the preview is served
  with a strict Content-Security-Policy and shown in a sandboxed iframe.

### Narratives

- The provider is resolved from settings at call time: `api`, `agent-sdk`, `mock` or none.
- The payload for each narrative field is the section's structured values, rounded the way the report prints
  them. Drafting only fills fields that are empty or flagged stale.
- Each draft is stored as `{text, basis}`; `basis` is a hash of the payload. When a later correction changes one
  of the figures, the effective data flags the draft as out of date with a warning, and the next run replaces it.
- The mock provider writes a deterministic paragraph that names the figures it used, so tests can assert that no
  number outside the payload appears.

### PDF rendering

- Jinja template `backend/app/report/templates/report.html` with `static/report.css`; Source Serif 4 and
  JetBrains Mono are embedded from `static/fonts/`. Font synthesis is disabled so Chromium never emits Type 3
  glyph outlines.
- The rent-trend chart is a dependency-free SVG (`report/chart.py`); its legend wraps onto extra rows when the
  series names are long, and each extra row grows the canvas rather than covering the axis.
- `scripts/check_pdf.py <pdf> --expect "<text>"` verifies page count, page size, embedded fonts, the absence
  of Type 3 fonts, the end-of-page footer markers and expected text, and rasterises every page with PDFium to
  confirm that every extracted word draws.

### Accessibility

Interactive controls are real buttons and links with accessible names, the workflow stepper marks the current
step with `aria-current`, status changes (uploads, processing, saves, drafting, generation) are announced through
live regions, errors are alerts that receive focus, the file drop zone is keyboard operable with a visible focus
ring, tables carry captions and row headers, and the layout reflows to a single column below 820 px (also
checked at 375 px in the browser test).

### Frontend

Angular 21 (zoneless, signals, standalone components, lazy routes), vitest 4 with jsdom 28 for the specs. The
dev server proxies `/api` to `BACKEND_PORT`. Note for this checkout: a path containing `)` breaks vitest's
default glob, which `vitest.config.mts` escapes; and npm 10.9 cannot add new dependencies here (use
`npx npm@11 install <pkg>`), while `npm ci` works.

## Verification

```bash
TEST_DATASET_DIR="/path/to/SOURCE FILES" scripts/check.sh            # everything below except the browser test
TEST_DATASET_DIR="/path/to/SOURCE FILES" UI_E2E_URL=http://localhost:4200 scripts/check.sh --e2e   # also the browser test
# TEST_DATASET_DIR must be the folder that holds only the source files; a check that cannot run is named as skipped in the last line

# or individually
cd backend && pytest                                                        # unit, API, reliability, corrections, render, scenario tests
TEST_DATASET_DIR="/path/to/SOURCE FILES" pytest tests/test_dataset.py -v    # the supplied files plus the mutated copy
pytest tests/test_real_world_scenarios.py -v                               # four independent property packages
python ../validation/real_world/run_validation.py                          # the same scenarios with preserved evidence and the assessment matrix
python -m pip_audit -r requirements.lock                                    # Python dependency vulnerabilities
cd ../frontend && npx ng test --watch=false && npx ng build && npm audit --audit-level=high
cd ../backend && UI_E2E_URL=http://localhost:4200 TEST_DATASET_DIR="/path/to/SOURCE FILES" pytest tests/test_ui_e2e.py -v
LLM_LIVE=1 pytest tests/test_narrative.py -v                               # optional: one real drafting call on the configured provider
python ../scripts/check_pdf.py ../deliverables/boardwalk-2q26-investor-report.pdf --expect "Fannie Mae"
```

What the suites cover:

| Suite | Covers |
|---|---|
| Backend unit and API (`backend/tests`) | readers, classifier, every extractor, selection and mapping, builder, calculations, validation, completeness, comps, corrections, database, workers, reliability (100 mixed upload batches, concurrency, restart), narrative providers and staleness, HTML and PDF rendering, scripts, all API routers |
| Dataset (`test_dataset.py`, opt-in) | totals on the supplied Boardwalk files and on a mutated copy: random names, renamed sheets, inserted rows and columns, reordered and dropped columns, extra sheets, alternate date and percent spellings, a duplicated export, an unrelated property's rent roll, an image-only PDF |
| Scenarios (`test_real_world_scenarios.py`) | the four validation packages through the public API, including reversed upload order |
| Browser (`test_ui_e2e.py`, opt-in) | create, upload with an unsupported and a corrupt file, corrections, a refused invalid edit, manual rows, images, drafts, generation, download, version immutability, narrow layout |
| Frontend specs | API service, projects, files, review, report, stepper, including failed-backend states |

Totals at commit `c580797`: backend 146 passed and 4 skipped (opt-in live checks), dataset 2, frontend 35,
browser 1, validation runner 4 of 4, sample PDF check OK, pip-audit and npm audit clean. Tests that need
Chromium skip themselves when it is not installed.

## Real-world validation suite

`validation/real_world/` proves the application on properties that have nothing to do with the Boardwalk. Each
scenario is a source package plus an `expected.json` written by hand, never copied from application output.

| Scenario | Classification | What it exercises |
|---|---|---|
| Riverbend Station 4Q25 | complete | Every export family across three workbooks with unfamiliar names and shuffled sheets, two Slate PDFs, a photo and logo, 90 pre-correction values, refused invalid corrections, a reset, four underwriting rows and one manual comparable, twelve mock drafts, image freezing across versions, snapshot immutability, every page's headings and content |
| Harbor Point 3Q26 | structural | Complete operational data in one opaque workbook plus two Slate PDFs; 40 exact gaps stay open by design |
| Pine Ridge 4Q26 | structural | Sparse package with no balance sheet, Slate or rent-comp rents; 42 gaps; comps keep units, vintage and leased % |
| Lakeside Commons 1Q27 | structural | A stale duplicate export, a rent roll for another property, an image-only PDF, no leasing report; 43 gaps |

The runner writes, per scenario, the PDF, the snapshot, `completeness.json`, `result.json` and one PNG per
page, plus `summary.json` and a generated `assessment.md` with a per-page provenance matrix (extracted, derived,
corrected, drafted, missing intentionally, missing unexpectedly, conflicts). `ASSESSMENT.md` is the human
verdict. See `validation/real_world/README.md` for regeneration and the evidence layout.

## Sample deliverable

`deliverables/boardwalk-2q26-investor-report.pdf` is the Boardwalk 2Q26 report generated from all 17 supplied
source files, and `boardwalk-2q26-reviewed-data.json` is the exact snapshot it was rendered from, including every
extracted value with its source, every reviewer correction and the AI drafts. `deliverables/README.md` records
how it was produced, which values a reviewer entered by hand from the client's example, which conflicts were
settled and which commit rendered it.

## Documentation index

| Document | What it is |
|---|---|
| `README.md` | This file |
| `CHANGELOG.md` | Every change, by phase and commit |
| `STATUS.md` | What is implemented, verification totals, known flaws, limitations, environment quirks |
| `validation/real_world/ASSESSMENT.md` | The scored verdict (90/100) with its evidence and limitations |
| `validation/real_world/README.md` | The validation suite: classifications, scenarios, regeneration, evidence layout |
| `deliverables/README.md` | How the Boardwalk sample was produced |
| `docs/superpowers/specs/2026-09-05-production-readiness-remediation-design.md` | Design of the completeness specification, comparable rules, narratives and the validation suite |
| `docs/superpowers/plans/2026-09-05-production-readiness-remediation.md` | The traced task plan for that design |
| `docs/superpowers/specs/2026-09-05-real-world-generalization-validation-design.md` and its plan | The earlier validation design |
| `docs/implementation-plan.md` | The original build plan (historical) |
| `CLAUDE_CODE_HANDOFF.md` | The first audit brief, 72/100 at `f17c999` (historical; everything in it has been done or superseded) |

## Known limitations

The short list; `STATUS.md` has the full one with the flaws that were found and not yet fixed.

- Loan terms, the original underwriting budget, property facts (acreage, class, hold period), the business plan,
  status updates and goals are not present in any supported export. They are manual fields flagged as missing
  until a reviewer enters them.
- Image-only (scanned) PDFs get the `needs OCR` status; no OCR is implemented.
- Only the supported export families are extracted; an unrelated schema needs a new extractor or mapping.
- Two same-period sources of identical completeness have no tie-breaker; the reviewer excludes one.
- Tables that do not fit a page are refused rather than continued on an extra page.
- Live AI providers are not exercised by the automated suite; the mock provider proves the workflow.
- No authentication or multi-user support; single local user by design.

## Next steps

1. OCR for scanned PDFs behind the same reader interface.
2. A loan-document extractor (term sheet PDF) feeding the financing page.
3. Continuation pages for long tables, with renumbered footers.
4. A measured chart legend and a per-page raster comparison against golden images.
5. Per-sheet document type overrides for multi-sheet workbooks.
6. A side-by-side source viewer on the review screen.
7. A mapping editor in the UI for `pl_mapping.toml` and `capex_mapping.toml`.
8. A recorded live-provider run with a replay fixture.

## Licences and data

The report embeds Source Serif 4 and JetBrains Mono under the SIL Open Font License; the licences are in
`backend/app/report/static/fonts/`. The repository contains the Boardwalk sample report and its reviewed data,
which describe a real property; keep the repository private unless that is intended. The raw source exports
are not part of the repository; the dataset tests read them from `TEST_DATASET_DIR`.
