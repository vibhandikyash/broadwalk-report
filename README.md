# Investor Report Generator

A locally runnable application that turns property source files into a structured, reviewable quarterly investor report. A user creates a project, uploads Excel and PDF files, reviews the extracted data and its source, corrects missing or inaccurate values, and generates a downloadable PDF report.

The supplied Boardwalk files are treated as an example dataset rather than a fixed template. Extraction is based on document content, labels, and table structure instead of exact filenames, file order, cell coordinates, or known values.

## Prerequisites

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/) for the Python environment and dependencies
- Node.js 22.12 or newer
- npm 10 or newer
- Chromium installed through Playwright for PDF generation

The application runs locally. External APIs are optional and are used only for narrative drafting or OCR of PDF pages without usable text.

## Backend setup

From the repository root:

```powershell
Set-Location backend
uv venv
uv pip install -r requirements.lock
uv run playwright install chromium
Copy-Item ..\.env.example ..\.env
uv run uvicorn app.main:app --reload --port 8000
```

The backend is available at `http://localhost:8000`.

Configuration is read from environment variables and from `.env` at the repository root. The provided `.env.example` contains the available settings. Do not commit API credentials.

## Frontend setup

In another terminal, from the repository root:

```powershell
Set-Location frontend
npm ci
npm start
```

The Angular application is available at `http://localhost:4200` and proxies `/api` requests to the backend port.

## External APIs

External services are not required for the core local workflow.

| Service | Purpose | Environment variables | Credentials |
|---|---|---|---|
| Anthropic API | Optionally drafts narrative fields from structured report data | `NARRATIVE_PROVIDER=api`, `ANTHROPIC_API_KEY`, optional `ANTHROPIC_MODEL` | Add an Anthropic API key to the local `.env` file |
| Claude Agent SDK | Optionally drafts narrative fields using a local Claude Code login | `NARRATIVE_PROVIDER=agent-sdk` | Install the optional dependencies and authenticate through Claude Code |
| Google Gemini API | Optionally performs vision OCR on scanned or low-text PDF pages | `GEMINI_API_KEY`, optional `GEMINI_MODEL`, `OCR_DPI`, `OCR_TIMEOUT_SECONDS`, `OCR_MIN_TEXT_CHARS` | Add a Gemini API key to the local `.env` file |

When Gemini OCR is enabled, only PDF pages without enough machine-readable text are sent to the service. Without it, an image-only PDF is marked as needing OCR and remains available for review.

## Application usage

1. Open the Angular application and create a report project.
2. Upload the `.xlsx`, `.xlsm`, and `.pdf` source files associated with the project.
3. Wait while each file is processed. The Files screen shows its upload and processing status and any error.
4. Open the Review screen to inspect extracted fields and tables. Missing, conflicting, and questionable values are identified, and available source information includes the filename and a worksheet, row, page, section, or source-text locator.
5. Correct inaccurate values or enter missing information, then save the changes.
6. Generate the report from the reviewed structured data.
7. Download the generated PDF from the Report screen.
8. To revise a report, edit the structured data and generate another version without uploading or processing the source files again.

By default, application data is stored under `backend/data`:

| Data | Location |
|---|---|
| SQLite database | `backend/data/app.db` |
| Uploaded files | `backend/data/projects/<project-id>/uploads/` |
| Project assets | `backend/data/projects/<project-id>/assets/` |
| Generated PDF, HTML, and JSON snapshots | `backend/data/projects/<project-id>/reports/` |

`APP_DATA_DIR` can be used to select another local data directory.

## Standard and verbose reports

The `REPORT_PROVENANCE` environment parameter controls whether previews and newly generated report versions include verbose source-provenance pages.

For the standard client report, set the repository-root `.env` file to:

```env
REPORT_PROVENANCE=false
```

This is the default. The generated PDF contains the ten report pages and does not include the additional working papers.

For a verbose report, set:

```env
REPORT_PROVENANCE=true
```

Restart the backend after changing the parameter. A verbose report includes interleaved data-source pages and closing source summaries that explain:

- Whether each value was extracted, calculated, entered by a reviewer, produced through OCR, or not found.
- The source filename and available worksheet, row, page, section, or source-text locator.
- The inputs used for calculated values.
- Why a value is displayed as unavailable.
- Which uploaded files were used and how their text was obtained.

These verbose pages are working papers for verification and demonstration. They are not part of the formal investor report and are omitted from the standard client version. The parameter changes report presentation only; it does not change extraction, calculations, validation, corrections, or stored report data.

## Architecture

```text
Angular interface
    -> FastAPI API
    -> file readers
    -> content classification
    -> document-specific extraction
    -> structured ReportData model
    -> selection, calculation, and validation
    -> human review and stored corrections
    -> versioned HTML and PDF report generation
```

The Angular frontend manages project creation, uploads, processing status, review, corrections, and report downloads. The FastAPI backend stores project state in SQLite and runs file processing and report generation through an in-process worker pool.

Excel workbooks and PDFs are converted into a common document representation. The classifier identifies relevant worksheets or PDFs from their content. Document-specific extractors convert recognized material into typed payloads with source locators. The consolidation layer selects appropriate sources, checks property identity and reporting periods, and builds the report's fields and tables. Deterministic Python code performs calculations and validation.

Reviewer corrections are stored separately from extracted values and reapplied when report data is loaded. Generating a report creates an immutable snapshot, allowing another version to be generated after later corrections without altering earlier versions.

## Extraction strategy

Extraction is driven by the information required by the report.

- Excel files are read with `openpyxl`; PDFs are read with `pdfplumber`.
- PDF pages without usable text can be processed with optional Gemini vision OCR.
- Files are classified from content signatures rather than filenames or upload order.
- Individual extractors locate information using document headings, column labels, row labels, and section structure.
- Financial and capital rows are mapped to canonical report rows through configurable patterns in `backend/config/pl_mapping.toml` and `backend/config/capex_mapping.toml`.
- Values are normalized into typed fields such as money, numbers, percentages, dates, integers, and text.
- Calculated values, totals, variances, ratios, and weighted averages are produced by Python rather than inferred by an AI model.
- When multiple sources provide materially different values, the alternatives are retained as a conflict for human review.
- Information that cannot be found remains missing and editable; the application does not silently invent it.

The structured `ReportData` representation separates source files from the final report. Each field can retain its extracted value, type, status, source, conflicting alternatives, and reviewer override. This structure allows users to inspect and correct data and regenerate reports without manipulating the original documents.

## Generalization strategy

The application does not depend on exact filenames, sheet names, file ordering, cell coordinates, property names, unit-type codes, account numbers, or values from the Boardwalk dataset.

It supports variation by:

- Classifying documents from combinations of headings and expected semantic columns.
- Searching for headers and labels when rows or columns move.
- Joining multi-row headers and tolerating reordered or absent optional columns.
- Normalizing common date, percentage, currency, and accounting-number formats.
- Processing each file independently so one corrupt or unsupported file does not fail the project.
- Ranking overlapping sources deterministically and allowing a user to exclude an unsuitable file.
- Separating files that appear to describe a different property instead of silently combining them.
- Leaving unavailable information visibly missing so a reviewer can supply it.
- Allowing a reviewer to assign a document type when readable material is not classified automatically.

The implemented extractors support Yardi budget comparisons, balance sheets, rent rolls, market rent schedules and lease trade-out reports; HelloData listings and comp summaries; CoStar submarket spreadsheets and PDFs; rent-trend workbooks; Slate capital calls and distributions; management memoranda; loan summaries; capital-project registers; and underwriting plans.

## Included testing data

The `testing_data` directory contains four test packages. Each package includes its source documents and the PDF generated by this application.

### Original source files

`testing_data/original_source_files` contains the Boardwalk 2Q26 source package originally supplied for the project. It includes the Yardi, HelloData, CoStar, Slate, rent-trend, occupancy, leasing, and supporting files used during development.

`original_source_files_report_with_verbose.pdf` is the report generated from that original package.

### Renamed baseline

`testing_data/01_renamed_baseline` contains a generated variation of the Boardwalk package in which the source files use opaque names such as `packet_24504_09.xlsx`. The underlying business case remains the Boardwalk 2Q26 report.

This package tests that classification and extraction depend on document content rather than the original filenames, filename numbering, or upload order. It also retains realistic workbooks containing relevant and irrelevant sheets.

`01_renamed_baseline_report_with_verbose.pdf` is the report generated from this package.

### New property and layouts

`testing_data/02_new_property_and_layouts` is a synthetic package for Juniper Grove Apartments, a 120-unit property with a reporting period ending September 30, 2027.

It uses new property values, generic filenames, different worksheet names, and consolidated workbooks containing several document types. For example, one workbook contains operating results, capital-project spending, balances, and an approved plan, while other files contain leasing, rent, occupancy, market, comparable-property, cash-activity, management, and loan information.

This package tests whether the system can recognize the same business concepts when they appear for a different property and in layouts that differ from the original Boardwalk files.

`02_new_property_and_layouts_report_with_verbose.pdf` is the report generated from this package.

### Missing data, conflicts, and scanned content

`testing_data/03_missing_conflicts_and_scan` is a synthetic package for Cedar Quay Apartments, an 84-unit property with a reporting period ending March 31, 2028.

This package deliberately includes difficult conditions:

- Missing source information that must remain visibly unavailable.
- Multiple balance sheets and lease-activity exports that can overlap or disagree.
- A document describing another property that must not be consolidated into Cedar Quay.
- An irrelevant facilities notice that contains no report data.
- A scanned management memorandum without a machine-readable text layer.
- Separate operating, capital, market, comparable-property, occupancy, underwriting, cash-activity, and loan sources.

It tests conflict handling, source selection, property isolation, irrelevant-file handling, missing-value behavior, and optional OCR recovery.

`03_missing_conflicts_and_scan_report_with_verbose.pdf` is the report generated from this package.

All four PDFs in `testing_data` were generated with `REPORT_PROVENANCE=true`. They therefore contain verbose working-paper pages explaining how values were extracted, derived, calculated, corrected, or left missing. Those explanatory pages are included to demonstrate and verify the application's processing; they are not part of the formal report produced when `REPORT_PROVENANCE=false`.

## Error handling

Every uploaded file has its own processing state. Unsupported formats, corrupt files, extraction failures, missing information, OCR failures, and report-generation failures are shown to the user. A failure in one file does not unnecessarily stop other files from being processed.

Corrections are validated before they are stored. Derived fields cannot be overwritten directly, and invalid values are rejected. Before PDF generation, the renderer checks fixed report pages for overflow and reports the affected page instead of producing a clipped report.

## Known limitations

- Extraction supports known report families and semantic layouts; substantially different document schemas may require a new classifier signature, extractor, or mapping.
- Scanned PDFs require a Gemini API key for automatic OCR. OCR results may be uncertain and should be reviewed.
- Some report information is not present in the supported exports and must be entered by a reviewer.
- When equally suitable sources cover the same period, the application may require the reviewer to exclude one.
- Tables that exceed the fixed report-page capacity are rejected instead of automatically continuing onto another page.
- Optional live AI services are not exercised by the normal automated test suite.
- The application is designed for a single local user and does not include authentication, multi-tenant security, production deployment infrastructure, billing, enterprise permissions, production-scale observability, or a production-scale database.

## Next steps

With additional development time, the next improvements would be:

1. Add continuation pages for tables that exceed a fixed report page.
2. Add per-worksheet document-type overrides for mixed workbooks.
3. Add a side-by-side source viewer with PDF page images and OCR bounding boxes.
4. Add a UI for maintaining financial and capital mapping rules.
5. Expand extraction fixtures and validation against additional unseen document layouts.
6. Add recorded validation of the optional live narrative and OCR providers.
