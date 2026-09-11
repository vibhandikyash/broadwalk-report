# Investor Report Generator: Implementation Report

## Document scope

This document explains how the application is implemented and why its principal technical decisions were made.

Operational material is intentionally kept in `README.md`: prerequisites, installation, startup commands, environment configuration, user instructions, included test packages, known limitations, and future work are not repeated here.

## 1. Implementation objective

The implementation converts heterogeneous property documents into a report without coupling report generation directly to the uploaded files. Its central design is a sequence of explicit transformations:

```text
Stored upload
    -> neutral document
    -> classified document part
    -> typed extraction
    -> selected source
    -> ReportData
    -> effective reviewed data
    -> immutable report snapshot
    -> HTML and PDF
```

Each boundary produces data that can be inspected independently. This makes extraction errors distinguishable from consolidation, calculation, correction, or rendering errors.

## 2. Backend composition

The FastAPI backend is divided by responsibility:

| Module | Responsibility |
|---|---|
| `app/readers` | Convert physical Excel and PDF files into a neutral in-memory document |
| `app/classify` | Identify relevant document parts from their content |
| `app/extract` | Convert a classified part into a document-specific typed payload |
| `app/consolidate` | Select sources, build report data, calculate values, apply corrections, and validate |
| `app/report` | Transform effective report data into HTML and PDF |
| `app/workers` | Coordinate background file processing and report generation |
| `app/api` | Expose project, file, report-data, asset, and report operations |
| `app/services` | Isolate optional narrative and OCR integrations |
| `app/db.py` | Define and access local SQLite persistence |
| `app/models.py` | Define the shared report-domain models |

The Angular frontend consumes the API through a typed service. Page components correspond to stages of the workflow, while shared components render statuses and report previews. Frontend state is refreshed from persisted backend state rather than treated as the authoritative copy.

## 3. Neutral document layer

Readers deliberately stop before interpreting business meaning.

An Excel workbook becomes a `Document` containing `Sheet` objects. A sheet retains its name and raw cell rows. Loading uses formula results because extraction needs the values visible in the exported report rather than formula expressions.

A PDF becomes a `Document` containing numbered `Page` objects. Each page retains its text and records whether that text was obtained natively or through OCR. This allows later extraction code to operate on one representation regardless of how the text was recovered.

The reader registry owns extension dispatch. Unsupported formats fail at this boundary and do not enter classification.

## 4. Content classification

The classifier works on a document's content rather than its external name. It evaluates combinations of title phrases, headings, and characteristic columns and returns one or more classified parts.

This distinction matters for multi-sheet workbooks: a workbook is only a container, and individual sheets may represent different business reports. Each classified part therefore carries its own document type, confidence, locator, and link to the underlying sheet or pages.

Classification can return an unknown type without treating the file as corrupt. A readable but unknown document is a different condition from a file that could not be opened.

## 5. Extraction boundary

The extractor registry dispatches each recognized part to a specialized extractor. An extractor is responsible for the layout and vocabulary of one document family but returns a stable payload for downstream code.

Extractors locate data through semantic structure:

- Header detection establishes the columns present in a table.
- Label matching identifies relevant rows.
- Multi-row headers are combined before column matching.
- Indentation and section headings distinguish rows with similar labels in different accounting sections.
- Common number, currency, percentage, and date representations are normalized.
- Source rows and pages are retained with the extracted values.

The extraction boundary does not build the final report. It records what a particular source says in the vocabulary of that source family.

## 6. Source collection and selection

`consolidate/select.py` converts stored extraction payloads into source objects used by the builder. This layer handles questions that cannot be answered correctly inside an individual extractor because they depend on the entire project.

Its responsibilities include:

- Comparing property identities across files.
- Separating sources that describe another property.
- Ordering point-in-time reports by date.
- Choosing between overlapping exports.
- Preferring a source with the columns required by the target report.
- Retaining selection notes when an alternative source exists.

Selection is deterministic. Upload order does not decide which source wins.

## 7. ReportData construction

`consolidate/builder.py` creates the report-domain structure. It translates selected source payloads into report sections containing fields and tables.

A field contains:

- A report label
- A declared value kind
- An extracted value
- A status
- An optional source
- Optional conflicting alternatives
- An optional reviewer override
- An explanatory note

Tables contain declared columns, keyed rows, totals, and row metadata. Stable paths identify every editable or calculated location. The same paths are used by corrections, validation issues, completeness checks, narrative drafts, API serialization, and provenance.

The builder records conflicts rather than flattening materially different source values into a single unexplained answer.

## 8. Deterministic calculations

`consolidate/calc.py` is the numerical authority for derived report values. It calculates results after initial construction and again after reviewer overrides are applied.

Its operations include:

- Differences and percentage variances
- Table totals
- Ratios and per-unit values
- Weighted and unweighted averages
- Occupancy changes
- Lease trade-out amounts and percentages
- Capital and financial rollups
- Labels derived from the reporting period

Derived fields are marked separately from extracted fields and cannot be directly overridden. Recalculation from effective inputs prevents a correction from leaving dependent values stale.

Arithmetic remains outside templates. The renderer formats calculated values but does not establish their business result.

## 9. Corrections and effective data

Extraction results and reviewer changes are intentionally separate.

The database stores overrides against stable report paths. When effective data is requested, the backend:

1. Loads the stored base `ReportData`.
2. Sanitizes the stored override collection.
3. Applies field changes, added rows, and deleted rows.
4. Recomputes derived fields.
5. Runs validation.
6. Reports overrides whose target no longer exists.

A correction request is checked against an in-memory copy before persistence. Paths must exist, calculated fields cannot be edited, and values must satisfy the target field's type and semantic constraints. The batch is stored only after the complete candidate remains serializable and renderable.

This design preserves the source extraction, supports resetting a correction, and avoids requiring document reprocessing after an edit.

## 10. Validation and completeness

Validation and completeness answer different questions.

Validation detects data problems such as incompatible periods, conflicting sources, failed reconciliation, invalid values, and processing errors.

Completeness determines whether the fields and tables required for a finished report have been populated and reviewed. It produces page-oriented gaps and a total gap count. A structurally renderable report can therefore still be explicitly identified as incomplete.

Both operate on effective data after corrections and recalculation. The review interface and version metadata consume the same results, preventing different parts of the application from applying different definitions of completeness.

## 11. Persistence model

SQLite uses four primary tables:

| Table | Stored responsibility |
|---|---|
| `projects` | Project identity and timestamps |
| `files` | Upload metadata, processing state, classification, and extraction payload |
| `report_data` | Consolidated base data, overrides, issues, notes, and narrative state |
| `reports` | Version number, immutable snapshot, completeness, status, and output paths |

Structured columns are serialized as JSON at the database boundary and decoded when read. Connections enable foreign keys and write-ahead logging.

Report version numbers are allocated transactionally. Deleting a project cascades its database records, while filesystem cleanup is limited to that project's managed directory.

## 12. Worker coordination

File extraction and PDF generation are coordinated by an in-process thread pool.

Every uploaded file is persisted before processing begins. A terminal file transition triggers a project-level rebuild check. Consolidation occurs only when no file in that project remains queued or processing.

Project-level locks serialize rebuilds. This prevents concurrent file completions from writing competing consolidated results.

Startup recovery requeues work that was interrupted while a file, narrative run, or report version was active. Jobs are keyed so duplicate submissions do not create duplicate work.

## 13. Rendering and immutable versions

The rendering layer receives effective `ReportData`; it does not parse original source documents.

Jinja templates produce HTML using autoescaping. Report-specific formatters control the display of money, percentages, dates, counts, and unavailable values. A dependency-free SVG renderer produces the rent-trend chart.

Before a PDF is accepted, Playwright measures every fixed page in Chromium. Content that exceeds a page boundary raises a layout error rather than being clipped.

When generation is requested, the backend snapshots the effective reviewed data before queuing the renderer. Assets are also copied for that version. Consequently, later edits or asset replacements do not change an existing report version.

## 14. Provenance implementation

Provenance is carried with data rather than reconstructed at the end. An extracted field source can include a file identifier, filename, document type, locator, source text, extraction method, and OCR confidence.

For calculated values, `consolidate/provenance.py` describes the operation and its inputs. The report renderer uses these descriptions to build working-paper rows grouped by the body page on which each value appears.

The `REPORT_PROVENANCE` parameter is read once into `settings.report_provenance` when backend configuration is loaded. In `report/render.py`, a render call with no explicit override follows that setting:

```text
settings.report_provenance = false
    -> body pages are numbered directly
    -> no provenance sheets are assembled

settings.report_provenance = true
    -> provenance entries are assembled from ReportData
    -> entries are paginated into working-paper sheets
    -> those sheets are interleaved with their related body pages
    -> closing source-file and extraction-method sheets are added
    -> printed page numbers are recalculated
```

This switch exists entirely at the rendering boundary. It does not select another extraction path, mutate `ReportData`, change a formula, change validation, or alter reviewer corrections. The same immutable data snapshot can therefore be rendered with or without its explanatory working papers.

The operational instructions and intended use of the parameter are documented in `README.md`; this section records only its internal implementation.

## 15. Optional service isolation

Optional external processing is isolated behind service modules.

Vision OCR returns page text, confidence, blocks, and cache information to the PDF reader. The recovered page then follows the ordinary classifier and extractor path.

Narrative providers receive structured section data after extraction and calculation. Drafts are stored as overrides with a hash of the numerical basis used to create them. If those inputs change, the draft can be identified as stale.

Neither service is required by the calculation engine or renderer. Provider failures are surfaced through normal file or narrative status rather than embedded into the report silently.

## 16. Safety and reliability decisions

The implementation includes the following boundaries:

- Uploaded content is validated by extension and size.
- One file failure does not terminate processing for unrelated files.
- Missing source information remains missing.
- Extracted values retain traceability where the source permits it.
- Calculations are performed by deterministic code.
- Correction batches are validated before persistence.
- Template output is escaped.
- The HTML preview uses a restrictive Content Security Policy and sandboxed frame.
- XML text used in generated charts is escaped.
- Fixed-page overflow is rejected.
- Existing report versions are immutable.
- Secrets and environment-specific values remain outside application logic.

These choices concentrate reliability controls at transitions where untrusted files, mutable reviewer input, and generated output enter or leave the system.

## 17. Test structure

Backend tests exercise readers, classification, extractors, source selection, consolidation, calculations, validation, completeness, corrections, persistence, workers, API routes, narratives, and rendering.

Frontend tests exercise API interactions and the project, file, review, and report workflows. Browser-level tests cover the complete user path through upload, correction, report generation, and download.

Dataset and scenario tests evaluate extraction against changed names, changed layouts, different properties, missing information, conflicts, irrelevant files, and OCR conditions. PDF checks validate dimensions, fonts, page markers, expected text, and rendered content.

The test layers follow the implementation boundaries so a failure can be attributed to document reading, interpretation, consolidation, interaction, or rendering rather than reported only as an incorrect final PDF.
