# Generalization Assessment

Date: 2026-09-05

## Verdict

The implementation is not hard-coded to The Boardwalk property, the original filenames, the original sheet names, or the original quarter. It successfully produced correct ten-page reports for three independent property packages and preserved immutable report snapshots.

**Generalization confidence: 92/100**

**Updated overall Claude implementation score: 94/100**

## Evidence

- Three scenario runs passed: Harbor Point 3Q26, Pine Ridge 4Q26, and Lakeside Commons 1Q27.
- Five generated XLSX sources and four generated PDF sources were uploaded through the public API, not injected into internal models.
- Harbor Point and Pine Ridge were uploaded with opaque filenames, proving that classification does not depend on the source filenames.
- Workbooks varied sheet names, sheet order, leading blank rows, values, unit mixes, comparable sets, and periods.
- Forty-seven independently declared pre-correction values were checked across property identity, occupancy, leasing counts, financial statements, capital activity, financing, and submarket metrics, with additional post-correction checks.
- The sparse Pine Ridge package reached report generation after unavailable facts were supplied through the normal batch correction endpoint.
- Lakeside Commons selected the fuller current-period financial source over a partial duplicate, set aside the `Regional Oaks` rent roll, and flagged the image-only vendor PDF as `needs_ocr` without blocking the report.
- The Lakeside package also passed with its upload order reversed.
- Forbidden identities were absent from effective report values and generated PDF text.
- A post-generation edit did not change any saved report snapshot.
- All three reports contain exactly ten pages and passed the repository PDF font/glyph/raster checker at 144 dpi.
- All 30 generated report pages were visually reviewed in contact sheets; key financial and occupancy pages were additionally inspected at full resolution. No clipping, overlap, blank output, missing glyphs, or implausible display values were found.
- Representative sheets from all five workbooks and every page of all four source PDFs were rendered and visually reviewed.

## Score rationale

| Area | Score | Evidence |
|---|---:|---|
| Property, filename, sheet, and period independence | 25/25 | Three new properties, opaque uploads, varied sheets, Q3/Q4/Q1 periods |
| Numerical extraction and derived calculations | 20/20 | Independent expected values all matched, including financial totals, occupancy, LTO counts, capital, rate, and market fields |
| Sparse-input resilience and corrections | 15/15 | Missing balance/loan inputs remained editable; corrections and recomputation succeeded |
| Conflict handling and order independence | 12/15 | Partial duplicate, decoy property, OCR scan, and reversed uploads passed; equally complete same-period sources remain a tie |
| Report generation and version integrity | 15/15 | Three ten-page PDFs, clean raster checks, immutable snapshots |
| Breadth beyond known export families | 5/10 | Strong across supported Yardi/HelloData/CoStar/Slate shapes; not an arbitrary-schema importer and no OCR implementation |
| **Total** | **92/100** | |

## What is intentionally format-specific

The system is schema-aware. It expects recognizable content labels such as `Budget Comparison`, `Summary Groups`, `Market Rent Schedule`, `Resident Name`, and `Vacancy Rate`, and it maps financial/capital rows through configurable regular expressions. This is appropriate domain parsing rather than Boardwalk-specific hard coding, but a materially different vendor export still needs a new extractor or mapping.

The report presentation is intentionally fixed to ten pages. Missing narratives and loan/property facts remain explicit review fields instead of being invented.

## Remaining limitations

1. Two same-period sources with identical completeness have no business timestamp or deterministic semantic tie-breaker. During fixture development, an intentionally equal-ranked duplicate could be chosen according to processing order. The final conflict scenario removes that ambiguity by making the archive objectively less complete, and it passes in both upload orders. Production users must exclude one of two truly equal candidates.
2. Image-only PDFs are detected and safely isolated, but OCR is not implemented.
3. The new scenarios vary layouts inside the supported export families; they do not prove compatibility with unrelated accounting or property-management schemas.
4. Optional live AI narrative drafting was not exercised because it requires external credentials. The application and reports work without it.

## Verification totals

- Backend: 126 passed, 4 skipped in the standard suite; the skips are opt-in/live checks.
- New generalization tests: 6 passed, including three scenario workflows and reversed conflict upload order.
- Original real dataset plus mutated dataset: 2 passed.
- Browser workflow: 1 passed, covering upload, review, correction validation, report generation, download, version immutability, and mobile layout.
- Frontend: 33 passed; production build passed.
- Python and npm vulnerability audits: passed with no known/high-severity findings.
- Original sample PDF plus all three new report PDFs: ten pages each, embedded expected fonts, full PDFium raster/glyph check passed.
