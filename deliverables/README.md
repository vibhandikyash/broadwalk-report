# Sample deliverable: The Boardwalk, 2Q26 Quarterly Investor Report

| File | What it is |
|---|---|
| `boardwalk-2q26-investor-report.pdf` | The generated report: 10 pages, 720 x 404.88 pt, Source Serif 4 and JetBrains Mono embedded |
| `boardwalk-2q26-reviewed-data.json` | The exact reviewed-data snapshot the PDF was rendered from (the report version's `snapshot`), including every extracted value with its source, every reviewer correction (`override`) and the AI drafts |

## How it was produced

1. All 17 supplied source files (`SOURCE FILES/`, including the `_Misc. FIles` folder) were uploaded to one project, plus an unsupported `.docx` and a corrupt `.xlsx` to show isolation.
2. Extracted values were reviewed on the Review page. The purchase-price conflict (balance-sheet basis $48.0M versus the $38.1M CoStar sale record) was settled on the balance-sheet basis. Values that no source file contains were entered by hand from the client's example report, as a reviewer would: the property description, class, site size and hold period, the location fields (South Fort Myers, FL 33967, Cape Coral-Fort Myers MSA), the unit counts and vintages of the three comps the listings export lacks (so the comp averages are unit-weighted), the business plan summary and the seven original underwriting budget rows, the loan terms (Fannie Mae, serviced by Newmark, fixed 5.23%, 60-month term, 36-month IO to August 1, 2028, 30-year amortization, P&I $201,207 per month, yield maintenance through January 31, 2030 with a 6-month open window, $8,591 monthly replacement reserve, $43,594 repairs escrow, non-recourse with carve-outs), the three outlook paragraphs, the two status items and the three next-quarter goals.
3. The commentary and narrative paragraphs on pages 2, 5, 7, 8 and 9 were drafted by the optional AI provider from the section's structured numbers and reviewed; they carry the `ai_draft` status in the snapshot. The page 8 drafts were discarded and re-drafted after the comp unit counts changed the averages, and one sentence was corrected by hand where the draft had rounded before subtracting.
4. Generate PDF snapshotted the reviewed data, the layout check confirmed every page fits its box, and Chromium printed the PDF.
5. `python scripts/check_pdf.py deliverables/boardwalk-2q26-investor-report.pdf --expect "Fannie Mae"` verifies page count, page size, embedded fonts, the absence of Type 3 fonts, the end-of-page footer markers and expected text, and rasterises every page with PDFium to confirm that every extracted word actually draws.

Every page was compared visually with the client's example at 110 dpi, in Poppler and PDFium renders: same section order, tables, calculations and labels; no clipped headers, footers, tables or narratives. Two deliberate differences: the cover and page 2 show a placeholder panel because no property photo is part of the source package (the app has a cover photo and logo upload slot for it), and page 7 orders capital lines by quarter spend rather than by the example's hand ordering.

Commit used: ceb6840 (the sample was rendered by the code at this commit, from the snapshot in this folder).
