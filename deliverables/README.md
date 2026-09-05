# Sample deliverable: The Boardwalk, 2Q26 Quarterly Investor Report

| File | What it is |
|---|---|
| `boardwalk-2q26-investor-report.pdf` | The generated report: 10 pages, 720 x 404.88 pt, Source Serif 4 and JetBrains Mono embedded |
| `boardwalk-2q26-reviewed-data.json` | The exact reviewed-data snapshot the PDF was rendered from (the report version's `snapshot`), including every extracted value with its source, every reviewer correction (`override`) and the AI drafts |

## How it was produced

1. All 17 supplied source files (`SOURCE FILES/`, including the `_Misc. FIles` folder) were uploaded to one project, plus an unsupported `.docx` and a corrupt `.xlsx` to show isolation.
2. Extracted values were reviewed on the Review page. Values that no source file contains were entered by hand from the client's example report, as a reviewer would: the property description, class, site size and hold period, the location fields (South Fort Myers, FL 33967, Cape Coral-Fort Myers MSA), the business plan summary and the seven original underwriting budget rows, the loan terms (Fannie Mae, serviced by Newmark, fixed 5.23%, 60-month term, 36-month IO to August 1, 2028, 30-year amortization, P&I $201,207 per month, yield maintenance through January 31, 2030 with a 6-month open window, $8,591 monthly replacement reserve, $43,594 repairs escrow, non-recourse with carve-outs), the three outlook paragraphs, the two status items and the three next-quarter goals.
3. The commentary and narrative paragraphs on pages 2, 5, 7, 8 and 9 were drafted by the optional AI provider from the section's structured numbers and reviewed; they carry the `ai_draft` status in the snapshot.
4. Generate PDF snapshotted the reviewed data, the layout check confirmed every page fits its box, and Chromium printed the PDF.
5. `python scripts/check_pdf.py deliverables/boardwalk-2q26-investor-report.pdf --expect "Fannie Mae"` verifies page count, page size, embedded fonts, the end-of-page footer markers and expected text.

Every page was compared visually with the client's example at 110 dpi: same section order, tables, calculations and labels; no clipped headers, footers, tables or narratives. Two deliberate differences: the cover and page 2 show a placeholder panel because no property photo is part of the source package (the app has a cover photo and logo upload slot for it), and page 7 orders capital lines by quarter spend rather than by the example's hand ordering.

Commit used: see `git log -1` at the time this folder was last updated (recorded in the top-level handoff notes).
