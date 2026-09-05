"""Browser end-to-end test of the Angular app against a running backend (opt-in).

Run with both servers up:  UI_E2E_URL=http://localhost:4200 TEST_DATASET_DIR="/path/to/SOURCE FILES" pytest tests/test_ui_e2e.py -v
"""
import base64
import os
import re
from pathlib import Path

import pytest

URL = (os.getenv("UI_E2E_URL") or "").rstrip("/")
DATASET = os.getenv("TEST_DATASET_DIR")
pytestmark = pytest.mark.skipif(not (URL and DATASET), reason="set UI_E2E_URL (running frontend) and TEST_DATASET_DIR")


def test_full_workflow_in_the_browser(tmp_path):
    import pdfplumber
    from playwright.sync_api import expect, sync_playwright

    from tests.helpers import dataset_files

    files = dataset_files(Path(DATASET))
    junk = tmp_path / "notes.docx"
    junk.write_bytes(b"not a report")
    corrupt = tmp_path / "broken.xlsx"
    corrupt.write_bytes(b"not a workbook at all")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.on("dialog", lambda d: d.accept())
        for stale in page.request.get(f"{URL}/api/projects").json():  # leftovers from an interrupted run
            if stale["name"] == "UI E2E":
                page.request.delete(f"{URL}/api/projects/{stale['id']}")
        page.goto(URL)

        # 1. create a report
        page.get_by_placeholder("New report name").fill("UI E2E")
        page.get_by_role("button", name="Create").click()
        page.wait_for_url(re.compile(r"/projects/[^/]+/files"))
        pid = page.url.rstrip("/").split("/")[-2]
        api = f"{URL}/api/projects/{pid}"

        # 2. upload through the file picker (hidden input inside the drop zone), plus an unsupported file
        page.get_by_label("Choose source files").set_input_files([str(f) for f in files] + [str(junk), str(corrupt)])
        expect(page.locator("tr .chip-processed")).to_have_count(len(files), timeout=120000)
        expect(page.locator("tr .chip-unsupported")).to_have_count(1)
        expect(page.locator("tr", has_text="notes.docx")).to_contain_text("Unsupported file type")
        expect(page.locator("tr", has_text="broken.xlsx").locator(".chip")).to_have_text("failed", timeout=30000)
        expect(page.locator("tr", has_text="broken.xlsx")).to_contain_text("Could not read file")
        expect(page.locator("p.status")).to_contain_text("need attention")

        # 3. drag-and-drop one small workbook onto the drop zone
        small = next(f for f in files if "Occupancy_03" in f.name)
        b64 = base64.b64encode(small.read_bytes()).decode()
        dt = page.evaluate_handle(
            """([name, b64]) => { const bin = atob(b64); const arr = new Uint8Array(bin.length);
               for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
               const dt = new DataTransfer(); dt.items.add(new File([arr], name)); return dt; }""",
            [small.name, b64],
        )
        page.dispatch_event("label.dropzone", "drop", {"dataTransfer": dt})
        expect(page.locator("tr", has_text=small.name)).to_have_count(2, timeout=30000)
        expect(page.locator("tr .chip-processed")).to_have_count(len(files) + 1, timeout=60000)

        # 4. Files page controls: exclude, type override and back, raw data, reprocess, remove
        chart_row = page.locator("tr", has_text="Rent_Chart")
        chart_row.get_by_role("checkbox").uncheck()
        expect(chart_row).to_have_class(re.compile("muted"))
        dist_row = page.locator("tr", has_text="Distributions.pdf")
        dist_row.get_by_role("combobox").select_option("slate_capital_calls")
        expect(dist_row.locator(".chip")).to_have_text("failed", timeout=30000)
        dist_row.get_by_role("combobox").select_option("")
        expect(dist_row.locator(".chip")).to_have_text("processed", timeout=30000)
        lto_row = page.locator("tr", has_text="Yardi LTO")
        lto_row.get_by_role("button", name=re.compile("^Show extracted data")).click()
        expect(page.locator("details.panel pre")).to_contain_text("yardi_lease_trade_out")
        lto_row.get_by_role("button", name=re.compile("^Reprocess")).click()
        expect(lto_row.locator(".chip")).to_have_text("processed", timeout=30000)
        page.locator("tr", has_text="notes.docx").get_by_role("button", name=re.compile("^Remove")).click()
        expect(page.locator("tr", has_text="notes.docx")).to_have_count(0)
        page.locator("tr", has_text="broken.xlsx").get_by_role("button", name=re.compile("^Remove")).click()
        expect(page.locator("tr", has_text="broken.xlsx")).to_have_count(0)

        # 4b. a cover photo through the reusable image slot
        from PIL import Image

        photo = tmp_path / "cover.png"
        Image.new("RGB", (640, 360), (27, 58, 107)).save(photo)
        page.get_by_label("Choose cover photo").set_input_files(str(photo))
        expect(page.locator("img.thumb")).to_have_count(1, timeout=15000)

        # 5. Review: conflict picker, manual rows, row deletion, rebuild, attention filter, narratives
        page.get_by_role("link", name=re.compile("Review data")).click()
        page.wait_for_url(re.compile("/review"))
        save_btn = page.get_by_role("button", name=re.compile(r"^Sav"))

        def save() -> None:
            save_btn.click()
            expect(save_btn).to_have_text(re.compile(r"^\s*Save\s*$"), timeout=30000)  # neither 'Saving…' nor 'Save (n)'
        page.get_by_role("button", name=re.compile("Capital Summary")).click()
        page.locator(".alts label", has_text="38,100,000").get_by_role("radio").check()
        save()
        expect(page.locator(".field", has_text="Purchase price").locator(".chip").first).to_have_text("edited")
        page.get_by_role("button", name=re.compile("Original Underwriting")).click()
        page.get_by_role("button", name=re.compile("^Add row")).click()
        row = page.locator("table.cells tbody tr:not(.totals)").first
        inputs = row.locator("input:not([disabled])")
        expect(inputs).to_have_count(4)
        for i, val in enumerate(("Amenity Upkeep", "value_add", "75000", "0")):
            inputs.nth(i).fill(val)
        save()
        rd = page.request.get(f"{api}/report-data").json()
        uw = next(t for s in rd["sections"] if s["key"] == "underwriting" for t in s["tables"])
        assert next(c["effective"] for c in uw["totals"] if c["key"] == "original_budget") == 75000
        page.get_by_role("button", name=re.compile("Submarket Comparison")).click()
        expect(page.locator("table.cells tbody tr", has_text="Westchase")).to_have_count(1)
        comps_rows = page.locator("table.cells tbody tr:not(.totals)")
        before = comps_rows.count()
        assert before > 2
        page.locator("table.cells tbody tr", has_text="Westchase").get_by_role("button", name=re.compile("^Delete row")).click()
        expect(comps_rows).to_have_count(before - 1)
        page.get_by_role("button", name="Rebuild from files").click()
        expect(comps_rows).to_have_count(before - 1)
        page.get_by_label("needs attention only").check()
        expect(page.locator(".fields .field:not(.attention)")).to_have_count(0)
        page.get_by_label("needs attention only").uncheck()
        page.get_by_role("button", name=re.compile("Financial & Capital Commentary")).click()
        page.locator(".field", has_text="Quarter takeaway").locator("textarea").fill("Revenue finished below budget while insurance savings offset utility overruns.")
        page.get_by_role("button", name=re.compile("Status Update")).click()
        page.locator(".field", has_text="Status item 1: title").locator("input").fill("Lender-required repairs")
        page.locator(".field", has_text="Status item 1: body").locator("textarea").fill("Seven of eight items are complete; the last has an approved extension.")
        save()
        # an invalid correction is refused with a readable message and the edit stays pending
        page.get_by_role("button", name=re.compile(r"^Property\b")).click()
        units = page.locator(".field", has_text="Units").first.locator("input")
        units.fill("12.5")
        save_btn.click()
        expect(page.get_by_role("alert")).to_contain_text("whole number", timeout=15000)
        units.fill("338")
        save()
        # stored corrections are listed and can be reset individually
        page.locator("details.corrections summary").click()
        expect(page.locator(".corrections li code", has_text="financing.fields.lender").or_(page.locator(".corrections li code").first)).to_be_visible()
        n_before = page.locator(".corrections li code").count()
        assert n_before >= 3
        page.locator("button[aria-label='Reset correction status.fields.status1_title']").click()
        expect(page.locator(".corrections li code")).to_have_count(n_before - 1)
        page.get_by_role("button", name=re.compile("Status Update")).click()
        page.locator(".field", has_text="Status item 1: title").locator("input").fill("Lender-required repairs")
        save()
        if os.getenv("LLM_LIVE"):  # one real drafting run through the UI button (uses the configured provider)
            page.get_by_role("button", name=re.compile("Draft narratives")).click()
            expect(page.get_by_role("button", name=re.compile("Drafting"))).to_be_visible(timeout=10000)
            expect(page.get_by_role("button", name=re.compile("Draft narratives with AI"))).to_be_visible(timeout=300000)
            page.get_by_role("button", name=re.compile("Submarket Comparison")).click()
            expect(page.locator(".field", has_text="Effective rent commentary").locator(".chip").first).to_have_text("AI draft")

        # 6. Report: preview, generate, download
        page.get_by_role("link", name=re.compile(r"^Report")).click()
        page.wait_for_url(re.compile("/report"))
        expect(page.frame_locator("iframe").locator("body")).to_contain_text("The Boardwalk", timeout=30000)
        page.get_by_role("button", name="Generate PDF").click()
        expect(page.locator(".version .chip-done")).to_have_count(1, timeout=120000)
        expect(page.locator("p.status")).to_contain_text("ready to download")
        href = page.locator("a", has_text="Download PDF").first.get_attribute("href")
        pdf = page.request.get(URL + href)
        assert pdf.ok and pdf.headers["content-type"] == "application/pdf" and pdf.body()[:4] == b"%PDF"
        out = tmp_path / "e2e.pdf"
        out.write_bytes(pdf.body())
        with pdfplumber.open(out) as doc:
            text = "\n".join(p.extract_text() or "" for p in doc.pages)
            assert len(doc.pages) == 10
        low = text.lower()
        assert "amenity upkeep" in low and "lender-required repairs" in low and "seven of eight items" in low and "insurance savings" in low
        assert "38,100,000" in text or "$38.1m" in low
        assert "westchase" not in low
        for n in range(2, 11):
            assert text.count(f"{n:02d} / 10") == 1, n
        snap = page.request.get(URL + href.replace("/download", "/snapshot")).json()
        assert snap["sections"]["status"]["fields"]["status1_title"]["override"] == "Lender-required repairs"

        # 7. edit again without re-uploading, generate v2; v1 is unchanged
        page.get_by_role("link", name=re.compile("Review")).click()
        page.wait_for_url(re.compile("/review"))
        page.get_by_role("button", name=re.compile(r"^Financing\b")).click()
        page.locator(".field", has_text="Lender").first.locator("input").fill("Fannie Mae")
        save()
        page.get_by_role("link", name=re.compile(r"^Report")).click()
        page.wait_for_url(re.compile("/report"))
        page.get_by_role("button", name="Generate PDF").click()
        expect(page.locator(".version .chip-done")).to_have_count(2, timeout=120000)
        reports = page.request.get(f"{api}/reports").json()
        v1, v2 = next(r for r in reports if r["version"] == 1), next(r for r in reports if r["version"] == 2)
        s1 = page.request.get(f"{api}/reports/{v1['id']}/snapshot").json()
        s2 = page.request.get(f"{api}/reports/{v2['id']}/snapshot").json()
        assert s1["sections"]["financing"]["fields"]["lender"]["override"] is None and s2["sections"]["financing"]["fields"]["lender"]["override"] == "Fannie Mae"
        pdf2 = page.request.get(f"{api}/reports/{v2['id']}/download").body()
        assert pdf2 != pdf.body() and b"%PDF" == pdf2[:4]

        # 8. narrow viewport: no horizontal scrolling, controls still reachable
        page.set_viewport_size({"width": 375, "height": 800})
        page.goto(f"{URL}/projects/{pid}/review")
        expect(page.get_by_role("button", name=re.compile(r"^Sav"))).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth") <= 375
        page.goto(f"{URL}/projects/{pid}/files")
        expect(page.get_by_role("link", name=re.compile("Review data"))).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth") <= 375

        # cleanup
        assert page.request.delete(api).status == 204
        browser.close()
