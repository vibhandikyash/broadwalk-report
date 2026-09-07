# Changelog

All notable changes to the investor report generator, newest first. Every entry names the commits it covers so the
history can be checked with `git log`. The whole build happened between 2026-09-05 and 2026-09-07; phases are the
audit-and-fix cycles the project went through, not calendar releases.

## Phase 5: documentation and first push (2026-09-07)

- Added this changelog, `STATUS.md` (what is implemented, how it was verified, what is still wrong or missing) and
  a rewritten `README.md` with setup, architecture, API, workflow, testing and a documentation index.
- Repository pushed to GitHub for the first time. No code changes in this phase.

## Phase 4: production-readiness remediation (2026-09-05, commits d347dbf to c580797)

Driven by a twelve-finding audit that asked for a clear line between a report that renders and a report that is
finished, for a non-Boardwalk property that reaches a complete report, and for page-by-page PDF evidence.

### Added

- **Completeness specification** (`backend/app/consolidate/completeness.py`): one place decides whether a report
  is complete. Requirements are declared per page; a genuine zero counts, an empty value does not; conditional
  requirements (the no-activity statement when a leasing table is empty, P&I or interest-only payment, the chart
  caption only when the chart has data). Read by validation severities, `GET /projects/{id}/completeness`,
  `summary.completeness`, the version record (`complete`, `gap_count`), the review screen and the report page.
  (d347dbf, 38f565a)
- **Draft versions**: a version generated while items are outstanding carries a DRAFT marker on the cover and in
  every footer, downloads as `...-draft.pdf`, and reports `complete: false` with its gap count. Complete versions
  are unchanged. (d347dbf)
- **Mock narrative provider** (`NARRATIVE_PROVIDER=mock`): deterministic drafts built only from the structured
  figures, so the drafting workflow is tested without a key, network access or login. (d347dbf)
- **Draft provenance and staleness**: every AI draft stores a hash of the figures it was written from. When a
  reviewer later changes one of those figures the draft is flagged out of date; the next drafting run replaces
  flagged and empty drafts only and never touches reviewer text. (d347dbf)
- **No-activity statement** (`occupancy.fields.no_activity_note`): the reviewed way to say a quarter had no new
  leases or renewals, shown on page 9 instead of an empty table. (d347dbf)
- **Completeness panel** on the review screen (gaps grouped by page, each jumping to its section) and
  complete/draft state on the report page, including the "Generate draft PDF" label. (38f565a)
- **Riverbend Station 4Q25 golden scenario**: a 228-unit Denver property that reaches a complete report through
  the public API only. Three workbooks with unfamiliar names and shuffled sheets, two Slate PDFs, a photo and logo
  through the asset API, 90 pre-correction values checked against a hand-written oracle, four invalid corrections
  refused, a reset check, four underwriting rows and one manual comparable through the batch correction API,
  twelve mock drafts, image freezing across versions, snapshot immutability. Built by `build_riverbend.py` with
  openpyxl and Chromium. (291b980)
- **Per-page PDF checks** (`validation/real_world/pdf_checks.py`): page size, embedded fonts, no Type 3 fonts,
  footer markers, expected headings and content per page, property identity on every page of a complete report,
  forbidden identities, image presence or placeholder, PDFium raster proof that every word draws, one PNG per page
  as preserved evidence. (291b980)
- **Provenance matrix**: the runner writes, per page, how many values were extracted, derived, corrected, drafted,
  missing intentionally, missing unexpectedly or in conflict. (291b980)

### Changed

- **Comparable rows**: the listings export defines the comp set; the HelloData comp sheet defines it only when no
  listings export exists; the one-page comp PDF defines it only when it is the only source and otherwise enriches
  matching rows. Rows without rents are kept with the missing cells visibly empty and editable. Averages use
  available values only, unit-weighted per column only when every contributing comparable has a unit count, and
  the footnote states the method. Extra properties named by a broader summary become an informational issue
  instead of a silent merge. (d347dbf)
- Missing values that the specification requires are now warnings naming their page; other missing values are
  informational. (d347dbf)
- The three earlier validation packages (Harbor Point 3Q26, Pine Ridge 4Q26, Lakeside Commons 1Q27) became
  **structural** scenarios with exact expected gap sets (40, 42, 43) and warning paths; any new gap or warning
  fails the test. (291b980)
- The Boardwalk deliverable was regenerated as a complete version with the same ten comparables and the same
  averages as before. (beaaf32, 0c5f6d3)
- README gained the "Structural versus complete" section, the mock provider and the list of always-manual fields;
  the validation README and `ASSESSMENT.md` were rewritten around the evidence. (beaaf32)

### Fixed

- **Rent-trend legend clipping**: the page 3 chart laid all four legend entries on one row, so long comp-set names
  ("West Raleigh Comp Set effective") were cut mid-word inside the SVG, where the overflow guard cannot see it.
  Found by visual inspection of the evidence pages. The legend now wraps and each extra row grows the canvas.
  Names that fit keep the single-row layout, so the Boardwalk chart is unchanged. (c580797)

## Phase 3: second review and parallel validation design (2026-09-05, commits 77bfd7b to b7eaea7)

Driven by a second external review scoring the project 85/100.

### Fixed

- **PDF portability**: the report CSS disables font synthesis and uses the real Medium face for monospace
  emphasis, so Chromium no longer emits Type 3 glyph outlines that some viewers draw as blanks. `check_pdf.py`
  fails on Type 3 fonts and rasterises every page with PDFium to confirm each extracted word draws. (77bfd7b)
- A stale `.partial` file left by a crashed render is removed before and after rendering. (77bfd7b)
- Formatters round half away from zero, matching financial statements. (77bfd7b)
- `scripts/run.sh reset-data` deletes only `projects/` and `app.db` inside `APP_DATA_DIR` and refuses the
  filesystem root, the home folder, the repository and any folder without application data. `.env` no longer
  overrides values already in the environment. (77bfd7b)
- `scripts/check.sh` requires `TEST_DATASET_DIR` and `UI_E2E_URL` for `--e2e` and names skipped steps in its
  last line; the dataset and browser tests refuse a folder that contains a code checkout. (77bfd7b)
- jsdom pinned to 28 so Node 22.12+ runs the frontend tests without engine warnings. (77bfd7b)
- The sample deliverable was refreshed: purchase-price conflict settled, comp unit counts and vintages entered so
  averages are unit-weighted, page 8 narratives re-drafted from the new figures, the financing narrative made
  consistent with the computed step-up. (77bfd7b, a443ede)
- A half-written contract test that had been swept into a commit by `git add -A` was untracked again. (64956c1)

### Added

- Design and plan for real-world generalization validation, and the first three independent scenario packages
  with their manifests, written in a parallel session. (f56ff43, b8524c1, b7eaea7)

## Phase 2: hardening after the first audit (2026-09-05, commits f17c999 to df729f8)

Driven by the first audit (72/100 at f17c999), recorded in `CLAUDE_CODE_HANDOFF.md`.

### Added

- **Typed, atomic corrections**: every batch is resolved against the effective data (path exists, target is
  editable), coerced to the field's kind with semantic rules (occupancy in 0-1, non-negative counts and prices,
  four-digit years, text limits), applied to a copy, recomputed, validated, serialised and rendered in memory,
  and only then persisted in one statement. Any failure returns 422 and stores nothing. Stored corrections that
  no longer fit are ignored on read with an issue and can be reset without loading the report. (9279ca7)
- **Immutable report versions**: each version snapshots the reviewed data at request time; version numbers are
  allocated inside an immediate transaction. (9279ca7)
- **Overflow rejection**: every page is measured in Chromium before printing; an overflowing page fails the
  version with page, section, amount and a hint instead of producing a clipped PDF. Footers sit in normal flow as
  end-of-page markers. (9279ca7)
- **Upload and recovery coordination**: uploads save every record before any job starts; one per-project-locked
  completion check consolidates when nothing is queued or processing; crashes leave files in a terminal state;
  type changes during processing are refused or re-run; restart re-queues files, report versions and narrative
  runs. (7551755, 9279ca7)
- **Date-aware Slate selection and identity checks**: Slate exports rank by print date, so an older populated
  capital-call list never replaces a current "no capital calls" export; sources naming another property are set
  aside; unit count, year built, submarket vacancy, purchase price and same-date Slate totals become conflicts
  with alternatives. New file statuses `unrecognized` and `needs_ocr`. (9279ca7)
- **Cover photo and logo slots**, frozen per report version. (9279ca7, ed4d75f)
- **Claude Agent SDK provider** on the local Claude Code login, prompt conventions and word budgets, live and UI
  drafting tests. (7551755)
- **Angular unit tests** (vitest, 33 specs at the time) and an **accessibility pass**: real buttons and links with
  names, `aria-current` on the stepper, live status regions, focused alerts, keyboard-operable drop zone, table
  captions and row headers, contrast, single-column reflow below 820 px. (ed4d75f)
- **Browser end-to-end test** and the **mutated-dataset test** (random file names, renamed sheets, inserted rows
  and columns, alternate date and percent spellings, a duplicated export, an unrelated property's rent roll, an
  image-only PDF). (f17c999)
- Embedded report fonts (Source Serif 4, JetBrains Mono), stylesheet escaping, chart text XML-escaping, a strict
  Content-Security-Policy on the preview. (f17c999, 9279ca7)
- Clean-start and check scripts, locked dependencies regenerated with pip-audit, the sample deliverable with its
  reviewed-data snapshot and a note recording the commit it came from. (ceb6840, 0303439, df729f8)

## Phase 1: initial build (2026-09-05, commits 67f34ea to f9daab2)

- Backend: xlsx and PDF readers producing a common `Document`, a content-signature classifier for Yardi (budget
  comparison, balance sheet, rent roll, market rent schedule, lease trade-out), HelloData (listings, comps),
  CoStar (Excel, PDF), the rent chart workbook and Slate (capital calls, distributions); per-type extractors with
  row and page provenance; source selection; the `ReportData` builder with sections, fields, tables and
  alternatives; derived calculations; validation; SQLite storage; a FastAPI API; a Jinja template rendered to a
  ten-page 16:9 PDF through Playwright Chromium. (67f34ea)
- Frontend: Angular 21 review workflow with projects, files, review and report pages. (8e5378c)
- Fixes that followed the first end-to-end runs: configurable backend port for the dev proxy, on-disk Chromium
  check, lease trade-out section titles, nested Yardi headers, dense layout for long tables, chart series names,
  a 12-month trend window. (3a61187, f9daab2)
- The implementation plan was committed with the code. (3a09ab1)
