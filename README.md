# Investor Report Generator

Turns a folder of property source files (Yardi, HelloData, CoStar and Slate exports) into a quarterly LP investor report.
Upload files, review every extracted value with its source, correct what is wrong or missing, generate the PDF, edit, regenerate.

## Prerequisites

- Python 3.12 or newer (3.13 tested)
- Node.js 22.12 or newer and npm 10 or newer (22.16 with npm 10.9 tested; with nvm: `nvm use 22`; Node 18 is too old for Angular 21)
- Chromium for PDF rendering, installed once by Playwright during setup
- No cloud services. AI narrative drafting is optional (an Anthropic API key or a local Claude Code login).

## Quick start

```bash
scripts/run.sh setup        # venv, locked Python deps, Chromium, npm ci, .env from .env.example
scripts/run.sh start        # backend on http://localhost:8000 and the Angular app on http://localhost:4200
scripts/run.sh reset-data   # wipes ONLY runtime data (uploads, database, generated reports); code and dependencies stay
```

`scripts/check.sh` runs every automated check (see "Verification" below).

## Backend setup, step by step

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.lock                        # the tested, pinned set; requirements*.txt hold the ranges
python -m playwright install chromium                   # one-time, about 150 MB, needed for PDF output
python -m pip check
cp ../.env.example ../.env                              # edit if you want another data folder, port or workers
uvicorn app.main:app --reload --port 8000
```

`GET http://localhost:8000/api/health` reports whether the PDF renderer and an AI provider are available.

## Frontend setup, step by step

```bash
cd frontend
npm ci
npm start                    # Angular dev server on http://localhost:4200, proxies /api to the backend port
```

## Environment variables (`.env` at the repository root)

| Variable | Default | Purpose |
|---|---|---|
| `APP_DATA_DIR` | `backend/data` | SQLite database, uploaded files, generated reports. A relative path is taken from the repository root whichever directory the backend is started from; absolute paths work too |
| `APP_WORKERS` | `3` | Parallel file-processing threads |
| `APP_MAX_UPLOAD_MB` | `50` | Per-file upload limit |
| `APP_CORS_ORIGINS` | `http://localhost:4200` | Allowed browser origins |
| `BACKEND_PORT` | `8000` | Port the Angular dev proxy forwards `/api` to. If 8000 is busy, set this and start uvicorn with the same `--port` (`scripts/run.sh start` does both) |
| `NARRATIVE_PROVIDER` | `auto` | `api` (Anthropic SDK with an API key), `agent-sdk` (Claude Agent SDK on the local Claude Code login), `mock` (deterministic drafts built only from the structured figures; for tests and offline demonstrations), `off`. `auto` picks `api` when a key is set, else `agent-sdk` when that package is installed |
| `ANTHROPIC_API_KEY` | unset | Enables the `api` provider |
| `ANTHROPIC_MODEL` | unset | Model override. `api` defaults to `claude-opus-5`; `agent-sdk` defaults to the Claude Code CLI's configured model |

## External services

| Service | Purpose | Variable | Credentials |
|---|---|---|---|
| Anthropic Claude API (`api` provider) | Drafts narrative paragraphs from the structured, reviewed numbers. Optional; the app is fully functional without it. | `ANTHROPIC_API_KEY` | The user supplies their own key in `.env`. |
| Claude Agent SDK (`agent-sdk` provider) | Same drafting through the bundled Claude Code CLI, using whatever that CLI is logged in with. Meant for a developer's own machine; per Anthropic's terms a distributed product must use the API-key provider. | none (`pip install -r backend/requirements-llm.txt`, then log in with `claude`) | The CLI's own credentials; the app stores nothing. One call per narrative field, no tools, no settings or CLAUDE.md loaded. |

Nothing else leaves the machine. Playwright's Chromium is downloaded once at setup time.

## Using the application

1. **Create a report**: Projects page, enter a name, Create.
2. **Upload source files**: Files page, drop or pick `.xlsx` / `.xlsm` / `.pdf` files (any names, any order; the drop zone is keyboard operable). Every file gets a status:
   `queued`, `processing`, `processed`, `failed` (corrupt or unreadable), `unsupported` (file type), `not recognised` (readable but no known report inside; not used until you set its type), `needs OCR` (image-only PDF; no text layer).
   One bad file never blocks the others, and a project with nothing usable still reaches the review screen with the problems listed.
   Optional report images (cover photo, logo) are uploaded on the same page and embedded in the PDF.
3. **Review extracted data**: Review page. Left: report sections in page order with a count of items needing attention. Every value shows a status chip (extracted, derived, edited, AI draft, missing, conflict) and a "source" button naming the file, sheet or page, and row it came from. "Needs attention" filters to missing and conflicting values. Issues are listed per section; selecting one jumps to its section.
4. **Correct data**: type into any editable field or table cell and Save. Every batch is validated before anything is stored: unknown paths, calculated fields, wrong types (text in a number, a percent above 100%, a malformed date, negative unit counts) are refused with a message and nothing from that batch is saved. Percentages are entered as percents in the UI and stored as fractions. Derived values recompute immediately. Conflicts show the alternatives; pick one. The underwriting budget, comp set and rent-trend tables accept new rows. "Reset" restores the extracted value; "Stored corrections" lists every saved correction and can reset any of them, or everything.
5. **Check completeness**: the Review page's "Report completeness" panel and `GET /projects/{id}/completeness` list every item a finished investor report still needs, page by page (see "Structural versus complete" below). Each item jumps to its section.
6. **Generate the report**: Report page shows a live HTML preview. Generate PDF snapshots the reviewed data at that moment and renders it; versions are immutable, each with a downloadable PDF and its data snapshot (JSON). A version generated while items are outstanding is a **draft**: it is marked as such on the cover and in every footer, downloads as `...-draft.pdf`, and carries `complete: false` with its `gap_count` in the API and the versions list. If a page would overflow its fixed box, the version fails with the page, section and amount instead of producing a clipped PDF.
7. **Regenerate**: edit on the Review page and press Generate again. Uploads are not reprocessed; earlier versions do not change.

### Structural versus complete

Two different statements, kept apart on purpose:

- **Structural**: files were ingested, every supported value was extracted, and a ten-page PDF renders without overflow. This always works, whatever is missing, so a reviewer can preview a partly reviewed report at any time.
- **Complete**: every value and table a finished investor report needs has been reviewed and populated. One specification, `backend/app/consolidate/completeness.py`, decides this; the review screen, the API, the version record and the draft marker all read from it. The requirements, by page: property identity and facts (2), current and prior in-place rent (2), capital summary and business plan (3), at least one underwriting row (3), the rent trend (3), financing terms and commentary (4), the core financial lines with no reconciliation warning (6), capital projects (7), submarket KPIs and a usable comp set (8), current and prior occupancy plus leasing rows or a reviewed no-activity statement (9), at least one status item and one goal (10), and the narratives on pages 2, 5, 7, 8 and 9.

A genuine zero (a Slate export stating no calls, or a reviewer entering 0) satisfies a requirement; an empty value does not. An empty leasing table counts as "no activity" only when the reviewer fills the no-activity statement on the Occupancy section; otherwise it is missing. Reviewer text, extracted values and AI drafts all count as populated; the number of drafts still awaiting review is reported separately. Missing values that the specification requires are warnings on the review screen (naming their page); other missing values are informational.

The fields that no supported export contains, and therefore always need a reviewer, are: acquisition date (when no CoStar sale record is supplied), submarket and market names (when no CoStar PDF is supplied), building class, site acres, hold period, description, business plan summary, the underwriting rows and their period note, the loan terms other than principal, monthly interest and reserve balance, the outlook and financing commentary, the rent-trend caption, status items and goals, and the no-activity statement when leasing tables are empty.

### Where files are

| What | Where (`APP_DATA_DIR` defaults to `backend/data`) |
|---|---|
| Database | `APP_DATA_DIR/app.db` |
| Uploaded source files | `APP_DATA_DIR/projects/<project id>/uploads/` |
| Cover photo and logo | `APP_DATA_DIR/projects/<project id>/assets/` |
| Report versions | `APP_DATA_DIR/projects/<project id>/reports/report-v<N>.pdf`, `.html`, `.json` (the snapshot), plus the images frozen for that version |
| Sample deliverable | `deliverables/` (the Boardwalk 2Q26 report, its reviewed-data snapshot and a note on how they were produced) |

`scripts/run.sh reset-data` removes only `projects/` and `app.db` (plus its journal files) inside `APP_DATA_DIR`. It refuses the filesystem root, your home folder, the repository and any folder that holds neither `app.db` nor `projects/`.

Setting a file's document type manually: if a file was not recognised, pick its type in the Files page dropdown and it is re-processed (refused with a message while the file is still processing). "Include" unticked excludes a file from the report data without deleting it, useful when two exports overlap (for example two HelloData comp sets) or when a file turns out to describe another property.

## Developer notes

### Architecture

```
Upload → readers (xlsx/pdf → Document) → classifier (content signatures → DocType per sheet/PDF)
      → extractors (DocType → typed JSON payload with row/page provenance)
      → select (choose between overlapping sources, check they describe one property, rank Slate exports by date)
      → builder (consolidate into ReportData: sections of Fields and Tables, alternatives on disagreement)
      → calc.recompute (derived values) → validate (missing / conflict / reconciliation / date checks)
      → review UI (corrections validated and stored as overrides, applied on every read)
      → version snapshot → Jinja HTML template → layout check → Chromium PDF
```

Files are processed by an in-process thread pool; each file is an isolated job. Every terminal transition (processed, failed,
unsupported, not recognised, needs OCR, excluded, deleted) calls one project-level completion check, which consolidates
once no file is queued or processing. The check is idempotent and serialised per project, so it is also called after an
upload batch and on a project read, and jobs left mid-flight by a restart (files, report versions, narrative drafting) are
re-queued at startup. Per-file extraction payloads, the consolidated data, the user's overrides and the report versions
(with their snapshots) are stored in SQLite (`app.db`).

### Extraction strategy

- Every document is located by **content**, never by filename: a Yardi Budget Comparison is a sheet whose header says "Budget Comparison" with Actual/Budget columns; a rent roll is a sheet with a "Summary Groups" block; HelloData listings are a sheet with Property Name / Asking Rent / Effective Rent columns, and so on (`classify/classifier.py`).
- Inside a document, values are located by **header and label text**. Multi-row headers are joined; Yardi's leading-space indentation is used to track section hierarchy so capital lines can be told apart from operating lines. Column order does not matter and optional columns may be absent.
- The financial table maps canonical rows (Gross Potential Rent, Payroll, NOI ...) to source lines through regex patterns in `backend/config/pl_mapping.toml`; capital-project regrouping lives in `capex_mapping.toml`. Both are editable without touching code.
- Derived values (variances, weighted averages, per-unit figures, comp averages) are computed from inputs, so a corrected input updates everything that depends on it.
- Every extracted value keeps `{file, sheet or page, row}` provenance, shown in the UI as the "source" of the value.
- Values that appear in more than one file (unit count, year built, submarket vacancy, purchase price, Slate totals of the same date) are compared; a material difference becomes a `conflict` with the alternatives attached, for the reviewer to settle.

### Generalization strategy

- Nothing keys on filenames, sheet names, cell coordinates, unit-type codes or GL account numbers.
- Multiple candidate sources for the same section are ranked deterministically (the Budget Comparison with YTD columns over a monthly one; the listings export that contains the subject property over one that does not; the most recent Slate export by its print date, so an older, populated capital-call list never replaces a current "no capital calls" export). The alternatives are listed as issues and the user can exclude a file to switch.
- Sources that name a different property (from a Yardi title such as "Lakeside Villas (99001)") are set aside with an error instead of being merged; names read heuristically from a text column only raise a warning.
- Missing files degrade gracefully: the section's fields become `missing` and editable; the rest of the report still generates.
- Percentages are normalised to fractions however the source expresses them (91.71, 0.9171 or "91.71%"); dates are parsed from several formats; extra sheets and pages that match nothing are ignored and reported.
- The dataset integration test (`tests/test_dataset.py`) is opt-in and asserts totals, not layout, on the supplied files and on a mutated copy (random file names, renamed sheets, inserted rows and columns, reordered and dropped columns, extra sheets, alternate date and percent spellings, a duplicated export, an unrelated property's rent roll and an image-only PDF).

### Corrections, snapshots and safety

- A correction batch is resolved against the current data (path must exist, target must not be calculated), coerced to the field's kind with semantic rules (occupancy in 0-1, counts and prices non-negative, four-digit years, text length limits), applied to an in-memory copy, recomputed, validated, serialised and rendered to HTML, and only then persisted in one statement. Any failure returns `422` and stores nothing.
- Stored corrections that no longer fit (a hand-edited database, an older build) are ignored on read with an issue, so the review screen and generation keep working; `POST /projects/{id}/report-data/overrides/reset` (the "Stored corrections" panel) removes them without loading the effective data.
- Report versions snapshot the reviewed data at request time; version numbers are allocated inside an immediate transaction and are unique.
- Before printing, every page is measured in Chromium; if content overflows the fixed page box the version fails with page, section, amount and a hint. Each page's footer sits in normal flow at the end of its content, so a clipped page would also lose its "NN / 10" marker in the PDF text.
- Chart text is XML-escaped and all other report content goes through Jinja autoescaping; the preview is served with a strict Content-Security-Policy and shown in a sandboxed iframe.

### Accessibility

Interactive controls are real buttons and links with accessible names, the workflow stepper marks the current step with `aria-current`, status changes (uploads, processing, saves, drafting, generation) are announced through live regions, errors are alerts that receive focus, the file drop zone is keyboard operable with a visible focus ring, tables carry captions and row headers, and the layout reflows to a single column below 820 px (also checked at 375 px in the browser test).

### Known limitations

- Loan terms, the original underwriting budget, property description facts (acreage, class, hold period) and status-update narratives are not present in any supplied source file. They are manual fields flagged as missing until a reviewer enters them; the sample deliverable carries values entered from the client's own example report.
- The rent trend chart needs the pre-built rent chart workbook for a full 12-month history; without it the chart is computed from whatever months the LTO and HelloData listings cover.
- Comp unit counts and vintages come from a HelloData comp summary when one is supplied; the unit-level listings export does not contain them.
- Image-only (scanned) PDFs get the `needs OCR` status; no OCR is implemented.
- Tables that do not fit a page are refused rather than continued on an extra page; the report keeps the reference's ten-page format.
- Comparable properties appear whenever any supported data names them (the listings export or the HelloData comp sheet define the set; the one-page comp PDF only enriches matching rows, or defines the set when it is the only source). Cells with no source stay empty and editable, averages use available values only, and the footnote states per column whether the average is unit-weighted or simple.
- The optional AI drafting sends section values (not files) to Claude, through an API key or the local Claude Code login. Drafts are marked `AI draft` with their provenance and must be reviewed. Each draft remembers the figures it was written from: when a reviewer later changes one of those figures the draft is flagged as out of date, and the next drafting run replaces flagged and empty drafts only, never reviewer text. Drafting never invents property events, repair status, lender actions or goals; those stay reviewer-supplied.
- Only what the supported exports contain is extracted. Loan documents, the original underwriting, property photos and logos, qualitative status updates and next-quarter goals are entered by the reviewer (photos and logos through the image slots on the Files page).
- No authentication or multi-user support; single local user by design.

### Next steps (another 40 hours)

1. OCR for scanned PDFs (Tesseract) behind the same reader interface.
2. A loan-document extractor (term sheet PDF) feeding the financing page.
3. Per-sheet document type overrides for multi-sheet workbooks.
4. Side-by-side source viewer on the review screen (open the sheet at the row the value came from).
5. Continuation pages for long tables, with renumbered footers.
6. A mapping editor in the UI for `pl_mapping.toml` / `capex_mapping.toml`.
7. Snapshot tests of the rendered HTML per section.

## Verification

```bash
TEST_DATASET_DIR="/path/to/SOURCE FILES" scripts/check.sh            # everything below except the browser test
TEST_DATASET_DIR="/path/to/SOURCE FILES" UI_E2E_URL=http://localhost:4200 scripts/check.sh --e2e   # also the browser test
# TEST_DATASET_DIR must be the folder that holds only the source files; a check that cannot run is named as skipped in the last line

# or individually
cd backend && pytest                                                        # unit, API, reliability, corrections, render tests
TEST_DATASET_DIR="/path/to/SOURCE FILES" pytest tests/test_dataset.py -v    # the supplied files plus the mutated copy
pytest tests/test_real_world_scenarios.py -v                               # four independent property packages (see validation/real_world/README.md)
python ../validation/real_world/run_validation.py                          # the same scenarios with preserved evidence and the assessment matrix
python -m pip_audit -r requirements.lock                                    # Python dependency vulnerabilities
cd ../frontend && npx ng test --watch=false && npx ng build && npm audit --audit-level=high
cd ../backend && UI_E2E_URL=http://localhost:4200 TEST_DATASET_DIR="/path/to/SOURCE FILES" pytest tests/test_ui_e2e.py -v
LLM_LIVE=1 pytest tests/test_narrative.py -v                               # optional: one real drafting call on the configured provider
python ../scripts/check_pdf.py ../deliverables/boardwalk-2q26-investor-report.pdf --expect "Fannie Mae"   # structure, fonts, and a PDFium raster check that every word draws
```

Tests that need Chromium skip themselves when it is not installed. The reliability suite repeats a mixed
supported / unsupported / corrupt upload batch 100 times and requires consolidation every time without polling.

The report embeds Source Serif 4 and JetBrains Mono (SIL Open Font License, licences in `backend/app/report/static/fonts/`).
