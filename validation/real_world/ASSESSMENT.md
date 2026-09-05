# Real-world validation assessment

Date: 2026-09-05 (production-readiness remediation). The generated companion, `results/assessment.md`, carries the
per-scenario table and the page-by-page provenance matrix for every report; this file is the human verdict.

## What the suite now proves

- A property other than The Boardwalk (Riverbend Station, quarter ended 2025-12-31) reaches a **complete** ten-page
  report through the public workflow only: five files with unfamiliar names uploaded in an order that scatters the
  supported exports across three workbooks with shuffled sheets; 90 values checked against a hand-written oracle
  before any correction; four invalid corrections refused with 422 and no side effect; reviewer corrections for
  every field the exports cannot supply; five manual rows (four underwriting rows and one metadata-only comparable)
  through the same batch API the review screen uses; a reset that restores the extracted value; twelve narrative
  drafts from the deterministic mock provider, none of which invents a figure or overwrites reviewer text; a cover
  photo and logo through the asset API; a completeness result of zero gaps and zero conflicts; a version marked
  complete; a PDF whose ten pages carry the expected headings and content, the embedded image on pages 1 and 2,
  no draft marker, no Type 3 font, no overflow and no word that fails to draw; a snapshot that a later edit and a
  later image replacement leave untouched; and a second version that picks up the new image while the first keeps
  its own.
- The three earlier packages stay valuable as **structural** scenarios. Each now declares the exact set of gaps
  (40, 42 and 43) and warning paths the application must report; any new gap or warning fails the test. Their
  PDFs carry the draft marker on every page and download as drafts.
- Page 8 keeps every comparable the defining source names, even with no rent: Pine Ridge and Lakeside now show
  three comp rows each with units, vintage and leased %, missing rents visibly empty and editable, and averages
  computed from available values only (the footnote states per column whether the average is unit-weighted or
  simple). A summary that names properties outside the defining set raises an informational issue instead of
  silently merging two comp sets.
- The page 3 rent-trend legend wraps onto a second row when the subject and comp-set names are long. The first
  evidence pages for Pine Ridge, Lakeside and Riverbend clipped the fourth legend label at the chart edge, which
  the overflow check cannot see because the text is cut inside the SVG; the visual inspection caught it, the
  chart now wraps, and the regenerated page images show every label.
- The Boardwalk regression stays intact: original extraction and calculation tests pass unchanged, the deliverable
  regenerates as a complete report with the same ten comparables and the same averages as before, and no
  alternate-property identity appears in its data.

## Score

| Area | Score | Evidence |
|---|---:|---|
| Property, filename, sheet and period independence | 24/25 | Four properties, opaque uploads, shuffled sheets, four quarters; still schema-aware (supported export families only) |
| Numerical extraction and derived calculations | 20/20 | 90 Riverbend values plus the earlier oracles match, including comps, LTO, capital, financing and market fields |
| Manual completion and narratives | 14/15 | Every manual field completed through the public API; mock drafts deterministic and figure-faithful; live providers not exercised here |
| Conflict handling, sparse input, order independence | 12/15 | Duplicate export, decoy property, OCR scan, reversed order all pass; two equally complete same-period sources remain a tie for the user |
| Report completeness and version integrity | 14/15 | Completeness specification, draft marker, immutable snapshots and frozen images all verified; continuation pages are refused rather than produced |
| Breadth beyond known export families | 6/10 | No arbitrary-schema importer, no OCR |
| **Total** | **90/100** | |

## What remains manual, by design

Loan terms (beyond principal, monthly interest and reserve balance), the original underwriting, property class,
site size, hold period, description, submarket and market names when no CoStar PDF is supplied, the business plan,
status updates, next-quarter goals, the outlook and financing commentary, and the rent-trend caption. The report
cannot be complete without a reviewer, and the suite proves a reviewer can complete it.

## Limitations

1. Two same-period sources of identical completeness have no deterministic tie-breaker; the user excludes one.
2. Image-only PDFs are isolated with the `needs_ocr` status; OCR is not implemented.
3. The scenarios vary layouts inside the supported Yardi, HelloData, CoStar and Slate families; an unrelated
   accounting schema still needs a new extractor or mapping.
4. Live AI providers are not exercised by the automated suite; the mock provider proves the workflow, not the
   quality of a live model's prose.
5. The three structural fixtures were generated with a Codex-bundled workbook tool; their sources are committed,
   so they run everywhere, but regenerating them needs that runtime. Riverbend regenerates with the backend
   virtualenv alone.

## Verification totals at this commit

- Backend: 139 passed, 4 skipped (opt-in live checks) in the standard suite; 7 passed in the real-world scenario
  suite (four scenarios, contract, tolerance helpers, reversed upload order).
- Supplied plus mutated Boardwalk dataset: 2 passed.
- Frontend: 35 passed; production build passed; npm audit clean.
- Browser workflow: 1 passed (upload, isolation of an unsupported and a corrupt file, corrections, refused invalid
  edit, manual rows, images, drafts, generation, download, version immutability, narrow layout).
- Validation runner: 4/4 scenarios passed; 40 page images preserved under `results/*/pages/`.
