"""PDF output: page count and size, embedded fonts, footers as end-of-content markers, and overflow rejection."""
import pytest

from app.consolidate.builder import build
from app.consolidate.calc import recompute
from app.report.chart import line_chart_svg
from app.report.render import LayoutOverflow, chromium_available, check_layout, render_html, render_pdf
from tests.test_builder import sample_files

needs_chromium = pytest.mark.skipif(not chromium_available(), reason="Playwright Chromium is not installed")


def _data():
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    data.field("financing.fields.lender").override = "Fannie Mae"
    return data


@needs_chromium
def test_normal_report_is_ten_pages_at_reference_size_with_embedded_fonts(tmp_path):
    import pdfplumber

    html, pdf = tmp_path / "r.html", tmp_path / "r.pdf"
    html.write_text(render_html(_data(), {"name": "P"}))
    assert check_layout(html) == []
    render_pdf(html, pdf)
    assert not pdf.with_name(pdf.name + ".partial").exists()
    with pdfplumber.open(pdf) as doc:
        assert len(doc.pages) == 10
        assert all(abs(p.width - 720) < 0.5 and abs(p.height - 404.88) < 0.5 for p in doc.pages)
        text = "\n".join(p.extract_text() or "" for p in doc.pages)
        fonts = {c["fontname"].split("+")[-1] for p in doc.pages for c in p.chars}
    for n in range(2, 11):
        assert text.count(f"{n:02d} / 10") == 1, n  # every page's end-of-content footer survived
    assert any("SourceSerif4" in f for f in fonts) and any("JetBrainsMono" in f for f in fonts), fonts


@needs_chromium
def test_overflowing_text_is_rejected_with_page_and_section(tmp_path):
    data = _data()
    data.field("status.fields.status1_title").override = "Long"
    data.field("status.fields.status1_body").override = "word " * 900
    html = tmp_path / "long.html"
    html.write_text(render_html(data, {"name": "P"}))
    with pytest.raises(LayoutOverflow) as e:
        render_pdf(html, tmp_path / "long.pdf")
    msg = str(e.value)
    assert "page 10" in msg and "Status Update" in msg and "too tall" in msg and "shorten" in msg
    assert not (tmp_path / "long.pdf").exists() and not (tmp_path / "long.pdf.partial").exists()


@needs_chromium
def test_horizontal_overflow_is_detected(tmp_path):
    html = tmp_path / "wide.html"
    html.write_text(render_html(_data(), {"name": "P"}).replace('<div class="callout">', '<div style="width:2000px;height:2px"></div><div class="callout">', 1))
    problems = check_layout(html)
    assert [p["page"] for p in problems] == [5] and problems[0]["dx"] > 1


@needs_chromium
def test_excess_rows_are_rejected_not_clipped(tmp_path):
    data = _data()
    t = data.table("submarket.tables.comps")
    for i in range(30):
        row = t.new_row(f"m{i}", label=f"Comp {i}", manual=True)
        row["name"].value, row["units"].value, row["asking_rent"].value, row["effective_rent"].value = f"Comp {i}", 100 + i, 1500.0, 1400.0
    recompute(data)
    html = tmp_path / "rows.html"
    html.write_text(render_html(data, {"name": "P"}))
    with pytest.raises(LayoutOverflow) as e:
        render_pdf(html, tmp_path / "rows.pdf")
    assert "page 8" in str(e.value) and "remove rows" in str(e.value)


def test_chart_escapes_data_driven_text():
    svg = line_chart_svg(["<b>Jan", "Feb"], [{"name": '</text><script>alert(1)</script><text onload="x"', "values": [1.0, 2.0], "color": "red;x"}])
    import re
    assert re.search(r"<(script|text onload)", svg) is None and "&lt;script&gt;" in svg and "&lt;text onload=&quot;x&quot;" in svg
    assert 'stroke="#000000"' in svg and "<b>" not in svg and "&lt;b&gt;Jan" in svg


def test_crafted_names_render_inert_in_the_html():
    data = _data()
    data.field("rent_trend.fields.subject_name").override = '<img src=x onerror=alert(1)>'
    data.field("submarket.tables.comps.rows.the-ashlar.name").override = '"><svg onload=alert(2)>'
    data.field("commentary.fields.takeaway").override = "<script>alert(3)</script>"
    html = render_html(data, {"name": "P"})
    assert "<img src=x" not in html and "<svg onload" not in html and "<script>" not in html
    assert "&lt;img src=x" in html and "&lt;script&gt;" in html
