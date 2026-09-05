# Production-Readiness Remediation Design

Date: 2026-09-05. Scope: the `Claude` implementation only. `GPT-Implemenation`, the supplied source files and the reference report are not touched.

## Purpose

The application already supports the documented assisted workflow (upload, extract with provenance, flag missing and conflicting values, correct, optionally draft narratives, generate an immutable ten-page report). The audit confirmed that a ten-page PDF can still be functionally incomplete, that partially usable comparable rows are dropped, that the real-world validation never exercised narratives, images, underwriting or complete manual review, and that no scenario other than The Boardwalk has ever produced a genuinely complete report. This design closes those gaps without changing documented behaviour merely to make tests pass.

## Concepts

### Structural versus complete

- **Structural**: files were ingested, supported values extracted, and a ten-page PDF rendered without overflow, regardless of missing optional information. This is graceful degradation and stays supported: any built project can be previewed and generated.
- **Complete**: every value and table that a finished investor report needs has been reviewed and populated. This is decided by one centralised specification, `backend/app/consolidate/completeness.py`, never by tests or templates.

The specification is a list of requirement groups. Each group names the page it lands on, a label, and a check over the effective `ReportData` that returns zero or more *gaps* `(path, label, page, group, reason)`. Groups, at minimum:

| Group | Page | What must be present |
|---|---|---|
| property | 1, 2 | name, units, year built, acquisition date, city/state, prepared by, building class, site acres, hold period, description |
| in_place_rent | 2 | at least one floor-plan row with current and prior rent; weighted totals for both |
| capital | 3 | purchase price, equity invested, quarter contributions, total called, distributions to date, quarter distributions (a genuine zero satisfies these) |
| business_plan | 3 | business plan summary |
| underwriting | 3 | at least one row with category, section, original budget and spent to date; the spent-period note |
| financing | 4 | loan amount, lender, rate, rate type, effective and maturity dates, term, IO months (zero allowed), amortisation years, one monthly payment (IO or P&I), recourse, prepayment terms, financing commentary |
| financials | 6 | total revenue, total opex, NOI and net cash flow with quarter actual, quarter budget and YTD actual; no reconciliation warning on the financial table |
| capex | 7 | at least one capital line with a quarter actual or budget; capital commentary |
| submarket | 8 | vacancy, YoY rent growth, average asking rent, under construction (zero allowed), submarket and market names |
| comps | 8 | a subject row and at least two comparable rows that each carry leased %, asking rent or effective rent; a comp-set asking-rent average |
| occupancy | 9 | current and prior date, occupancy, occupied units, total units |
| leasing | 9 | new-lease and renewal rows, or the reviewed no-activity statement (`occupancy.fields.no_activity_note`) when a table is empty |
| status | 10 | at least one status item with title and body |
| goals | 10 | at least one goal with title and body |
| narratives | 2, 5, 7, 8, 9 | commentary takeaway, revenue, opex and NOI bodies and the three outlooks; in-place rent commentary; submarket occupancy, rent and concession commentary; occupancy commentary; new-lease and renewal commentary when the corresponding table has rows; capital commentary; rent-trend caption when the chart has data |

Rules:

- A genuine zero (a Slate export stating no calls, a reviewer entering 0) satisfies a numeric requirement; `None` does not. Leasing distinguishes rows (activity), an empty table plus the reviewed note (no activity) and an empty table without the note (missing).
- Reviewer text, extracted values and AI drafts all count as populated. The result also reports how many drafts are still unreviewed, as advice, not as a gap.
- Optional fields (subtitles, the unused business-plan headline, prior-variance note, recent deliveries, servicer, yield-maintenance date, open-prepayment window, replacement reserve, repairs escrow, chart methodology note) are never gaps.
- The same specification decides issue severity on the review screen: a missing required field is a warning naming its page; a missing optional field is informational. Structural essentials (name, units, revenue, opex, NOI, occupancy) stay errors.

### Exposure

- `GET /projects/{id}/completeness` returns `{complete, gap_count, gaps[], groups[], ai_drafts_pending}`; the same object rides in `summary.completeness` of the report-data payload so the review screen needs no extra call.
- Every report version records `complete` and `gap_count` at snapshot time. `report_public` exposes them. An incomplete version downloads as `<name>-v<N>-draft.pdf`.
- The rendered report of an incomplete snapshot carries a discreet marker: the cover badge line and every footer read `DRAFT · N items outstanding`. Complete reports are unchanged. This is the least disruptive way to keep previews and structural generation working while making a draft unmistakable.
- The review screen shows a "Report completeness" panel (gaps grouped by page, each jumping to its section). The report screen shows a badge, labels the button "Generate draft PDF" while gaps remain, and marks draft versions.

## Comparable rows (page 8)

`_submarket` builds the comp table from the properties of the source that defines the comp set: the HelloData listings export when present (the source the client's own report is built from), otherwise the HelloData comp sheet, otherwise the one-page PDF summary. Every summary enriches rows by tolerant name match ('Westchase' and 'Westchase Apartments' are one row); a property with only metadata is kept when its source defines the set. A summary of a different, broader report that names extra properties raises an informational issue listing them, so nothing is lost silently and a reviewer can add them to the editable table. Per cell, the first available source wins and is recorded as provenance:

- units, vintage: comp summary (sheet), else missing.
- leased %: subject from the rent roll; otherwise listings leased/rows when listings exist for the property, else the summary's leased % (sheet) or leased/(leased+active) (PDF).
- asking rent, effective rent: listings means when listings exist, else the PDF summary's average rent and NER, else missing.
- concession: derived from asking and effective when both exist.

Nothing is invented; a cell with no source stays `missing` and editable. Totals use only present values: a column is unit-weighted only when every comparable that has a value for that column also has a unit count, else it is a simple average over the comparables that have the value. The subject row never enters an average. The footnote states, per column, whether it is unit-weighted or a simple average and how many comparables contributed.

## Narratives

- A third provider, `mock`, selected with `NARRATIVE_PROVIDER=mock`, drafts deterministically from the structured payload: one sentence restating the instruction's subject, then the field's leading figures verbatim. It calls nothing external, so automated tests can exercise the whole workflow.
- Drafts are stored as `{"text": ..., "basis": <sha256 of the payload>}`; older string drafts still load. On every read the current payload hash is compared: a draft whose basis changed is still shown but flagged with a note and a warning ("predates a change to the numbers it was written from"). The drafting job re-drafts empty fields and stale drafts, never reviewer text.
- Provider resolution reads settings at call time so tests can switch providers.

## Validation suite

`validation/real_world` keeps its public-API harness and gains:

- `classification` in every manifest: `structural` or `complete`.
- Completeness assertions before generation: complete scenarios must have no gaps and no conflicts; structural scenarios must match their `expected_gaps` exactly (a new gap fails the test) and their `expected_warning_paths` exactly.
- `narratives: "mock"` runs the drafting job with the mock provider and asserts every empty supported narrative received a draft with `ai_draft` status and provenance.
- `assets`: the harness renders a deterministic PNG with Pillow, uploads it through `PUT /projects/{id}/assets/{cover,logo}`, then checks the cover and property pages embed an image, that a later replacement does not change the frozen image of the earlier version, and that a scenario without assets renders the placeholder.
- `row_additions` through `add_rows` of the correction API, and a reset check (`overrides/reset`) proving the extracted value returns.
- Per-page checks: heading order, property and period on every page, per-page `text_contains`, forbidden text, image counts, plus the repository raster and Type 3 checks. Every page is rendered to `results/<scenario>/pages/page-NN.png`.
- A provenance matrix per scenario (`completeness.json` and the aggregate `assessment.md`): counts of extracted, derived, reviewer-corrected, mock-drafted, intentionally missing, unsupported and failed items, page by page.

New scenario `riverbend_station_4q25`: a 228-unit Denver property reporting the quarter ended December 31, 2025, built by `build_riverbend.py` with openpyxl and Chromium (no external runtime). Sources are split across three workbooks with unfamiliar names and shuffled sheet order, plus Slate capital-call and distribution PDFs. It contains no Boardwalk identity, code, address, filename, narrative or financing value. Its manifest supplies realistic reviewer corrections for every genuinely manual field, underwriting rows, mock narratives and assets, and asserts a complete report with page-level content.

## Data and API changes

- `reports.complete`, `reports.gap_count` (migration in `init_db`).
- `occupancy.fields.no_activity_note` (manual longtext) rendered on page 9 when a leasing table is empty.
- `summary.completeness` in the report-data payload; `GET .../completeness`.
- `ai_drafts` values may be objects; stale drafts add a warning issue.

## Regression protection

Boardwalk extraction and calculation tests are unchanged; the deliverable is regenerated and must be `complete` without a draft marker; the dataset test asserts that no alternate-property identity appears in the Boardwalk payload; every scenario asserts that no Boardwalk identity appears in its output.

## Limitations that stay documented

Loan-document extraction, underwriting extraction, OCR, live AI drafting, property photos and qualitative business updates remain manual or optional. Nothing in this design claims automatic support for them.
