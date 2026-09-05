# Investor Report Generator

Turns a folder of property source files (Yardi, HelloData, CoStar, Slate exports) into a quarterly LP investor report.
Upload files, review every extracted value with its source, correct what is wrong or missing, generate the PDF, edit, regenerate.

## Prerequisites

- Python 3.12 or newer
- Node.js 22 LTS and npm 10 (with nvm: `nvm use 22` before `npm start`; Node 18 is too old for Angular 21)
- Chromium for PDF rendering (installed once by Playwright, see below)
- No cloud services are required. AI narrative drafting is optional and needs an Anthropic API key.

## Backend setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt                     # or requirements.txt without test/LLM extras;
                                                        # requirements-llm.txt adds the optional drafting providers
python -m playwright install chromium                   # one-time, ~150 MB, needed for PDF output
cp ../.env.example ../.env                              # edit if you want a different data folder or workers
uvicorn app.main:app --reload --port 8000
```

`GET http://localhost:8000/api/health` reports whether the PDF renderer and the LLM are available.

## Frontend setup

```bash
cd frontend
npm install
npm start                                               # Angular dev server on http://localhost:4200, proxies /api to the backend port
```

## Environment variables (`.env` at the repo root)

| Variable | Default | Purpose |
|---|---|---|
| `APP_DATA_DIR` | `backend/data` | SQLite database, uploaded files, generated reports |
| `APP_WORKERS` | `3` | Parallel file-processing threads |
| `APP_MAX_UPLOAD_MB` | `50` | Per-file upload limit |
| `APP_CORS_ORIGINS` | `http://localhost:4200` | Allowed browser origins |
| `BACKEND_PORT` | `8000` | Port the Angular dev proxy forwards `/api` to. If 8000 is busy, set this and start uvicorn with the same `--port` |
| `NARRATIVE_PROVIDER` | `auto` | `api` (Anthropic SDK with an API key), `agent-sdk` (Claude Agent SDK on the local Claude Code login), `off`. `auto` picks `api` when a key is set, else `agent-sdk` when the package is installed |
| `ANTHROPIC_API_KEY` | unset | Enables the `api` provider |
| `ANTHROPIC_MODEL` | unset | Model override. `api` defaults to `claude-opus-5`; `agent-sdk` defaults to the Claude Code CLI's configured model |

## External services

| Service | Purpose | Variable | Credentials |
|---|---|---|---|
| Anthropic Claude API (`api` provider) | Drafts narrative paragraphs from the structured, reviewed numbers. Optional; the app is fully functional without it. | `ANTHROPIC_API_KEY` | The user supplies their own key in `.env`. Requests are made with server-side refusal fallbacks enabled (`fallbacks: "default"`). |
| Claude Agent SDK (`agent-sdk` provider) | Same drafting, through the bundled Claude Code CLI, so it uses whatever that CLI is logged in with. Intended for a developer's own machine that already has a Claude Code login; per Anthropic's terms, a distributed product must use the API-key provider. | none (`pip install -r backend/requirements-llm.txt`, then `claude` login) | Nothing is stored by the app; the CLI's own credentials are used. One call per narrative field, no tools, no settings or CLAUDE.md loaded. |

Nothing else leaves the machine. Playwright's Chromium is downloaded once at setup time.

## Using the application

1. **Create a report**: Projects page, enter a name, Create.
2. **Upload source files**: Files page, drop or pick `.xlsx` / `.pdf` files (any names, any order). Each file shows a status: queued, processing, processed, failed, unsupported, and the report types detected inside it. One bad file never blocks the others.
3. **Review extracted data**: Review page. Left: report sections in page order. Every value shows a status chip (extracted, derived, manual, AI draft, missing, conflict) and a "source" button with the file, sheet or page, and row it came from. "Needs attention" filters to missing and conflicting values.
4. **Correct data**: type in any editable field or table cell and Save. Derived values recompute immediately. Conflicts show the alternatives; pick one. Tables such as the underwriting budget and the comp set accept new rows. "Reset" restores the extracted value.
5. **Generate the report**: Report page shows a live HTML preview. Generate PDF creates a new version; download it from the versions list.
6. **Regenerate**: edit on the Review page and press Generate again. Uploads are not reprocessed; edits are kept.

Generated files live under `APP_DATA_DIR/projects/<project id>/reports/report-v<N>.pdf` (and `.html`).

Setting a file's document type manually: if a file was not recognised, pick its type in the Files page dropdown and it is re-processed. "Exclude" removes a file from the report data without deleting it (useful when two exports overlap, for example two HelloData comp sets).

## Developer notes

### Architecture

```
Upload → readers (xlsx/pdf → Document) → classifier (content signatures → DocType per sheet/PDF)
      → extractors (DocType → typed JSON payload with row/page provenance)
      → builder (select sources, consolidate into ReportData: sections of Fields and Tables)
      → calc.recompute (derived values) → validate (missing / conflict / reconciliation issues)
      → review UI (edits stored as overrides, applied on every read)
      → Jinja HTML template → Chromium PDF
```

Files are processed by an in-process thread pool; each file is an isolated job. When the last file finishes, consolidation runs automatically. Per-file extraction payloads, the consolidated data, the user's overrides and the report versions are stored in SQLite (`app.db`).

### Extraction strategy

- Every document is located by **content**, never by filename: a Yardi Budget Comparison is a sheet whose header says "Budget Comparison" with Actual/Budget columns; a rent roll is a sheet with a "Summary Groups" block; HelloData listings are a sheet with Property Name / Asking Rent / Effective Rent columns, and so on (`classify/classifier.py`).
- Inside a document, values are located by **header and label text**. Multi-row headers are joined; Yardi's leading-space indentation is used to track section hierarchy so capital lines can be told apart from operating lines.
- The financial table maps canonical rows (Gross Potential Rent, Payroll, NOI ...) to source lines through regex patterns in `backend/config/pl_mapping.toml`; capital-project regrouping lives in `capex_mapping.toml`. Both are editable without touching code.
- Derived values (variances, weighted averages, per-unit figures, comp averages) are computed from inputs, so a corrected input updates everything that depends on it.
- Every extracted value keeps `{file, sheet or page, row}` provenance, shown in the UI as the "source" of the value.

### Generalization strategy

- Nothing keys on filenames, sheet names, cell coordinates, unit-type codes or GL account numbers.
- Multiple candidate sources for the same section are ranked deterministically (for example the Budget Comparison with YTD columns wins over a monthly one; a standalone HelloData export wins over the same sheet inside a full report), the alternatives are listed as issues, and the user can exclude a file to switch.
- Missing files degrade gracefully: the section's fields become `missing` and editable; the rest of the report still generates.
- Percentages are normalised to fractions regardless of how the source expresses them; dates are parsed from several formats.
- The dataset integration test (`tests/test_dataset.py`) is opt-in and asserts totals, not layout.

### Known limitations

- Loan terms, the original underwriting budget, property description facts (acreage, class, hold period) and status-update narratives are not present in any supplied source file. They are manual fields flagged as missing.
- The rent trend chart needs the pre-built rent chart workbook for a full 12-month history; without it the chart is computed from whatever months the LTO and HelloData listings cover.
- Comp unit counts and vintages come from a HelloData comp summary when one is supplied; the unit-level listings export does not contain them.
- Image-only (scanned) PDFs are reported as unsupported; no OCR is implemented.
- The frontend has no unit tests; it is covered by the browser end-to-end test below.
- The optional AI drafting sends section values (not files) to Claude, through an API key or the local Claude Code login. Drafts are marked `AI draft` and must be reviewed.
- No authentication or multi-user support; single local user by design.

### Next steps (another 40 hours)

1. OCR for scanned PDFs (Tesseract) behind the same reader interface.
2. A loan-document extractor (term sheet PDF) feeding the financing page.
3. Per-sheet document type overrides for multi-sheet workbooks.
4. Side-by-side source viewer on the review screen (open the sheet at the row the value came from).
5. Property photo and logo upload slots for the cover page.
6. A mapping editor in the UI for `pl_mapping.toml` / `capex_mapping.toml`.
7. Snapshot tests of the rendered HTML per section.

## Running the tests

```bash
cd backend && pytest -q                                                    # unit and API tests (synthetic data)
TEST_DATASET_DIR="/path/to/SOURCE FILES" pytest tests/test_dataset.py -v   # optional: the real files, plus a mutated copy
                                                                           # (random names, renamed sheets, shifted rows/columns)
UI_E2E_URL=http://localhost:4200 TEST_DATASET_DIR="/path/to/SOURCE FILES" pytest tests/test_ui_e2e.py -v
LLM_LIVE=1 pytest tests/test_narrative.py -v                              # optional: one real drafting call on the configured provider
                                                                           # optional: drives the Angular app in headless Chromium
                                                                           # (upload, every Files-page control, edits, PDF); both servers must be running
```

The report embeds Source Serif 4 and JetBrains Mono (SIL Open Font License, licences in `backend/app/report/static/fonts/`).
