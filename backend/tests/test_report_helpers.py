# backend/tests/test_report_helpers.py
from app.report import formatters as fm
from app.report.chart import line_chart_svg


def test_formatters():
    assert fm.money(1346580.4) == "$1,346,580" and fm.money(-22) == "−$22" and fm.money(None) == "—"
    assert fm.money_m(48000000) == "$48.0M" and fm.money_m(48000000, 0) == "$48M"
    assert fm.num(-53131) == "(53,131)" and fm.num(9961) == "9,961"
    assert fm.signed_money(4183) == "+$4,183" and fm.signed_money(-34283) == "−$34,283"
    assert fm.signed_num(4183) == "+4,183" and fm.signed_num(-34283) == "(34,283)" and fm.signed_num(0) == "0"
    assert fm.pct(0.1916) == "19.2%" and fm.pct(-0.9729, 1, True) == "−97.3%" and fm.pct(0.1916, 1, True) == "+19.2%"
    assert fm.var_pct(0.0) == "flat" and fm.var_pct(None) == "—"
    assert fm.bps(-118) == "−118 bps" and fm.date_long("2025-07-30") == "Jul 30, 2025" and fm.date_short("2025-07-30") == "Jul ’25"
    assert fm.integer(338.0) == "338" and fm.text(None) == "—" and fm.sf(841) == "841 sf" and fm.psf(1.5) == "$1.50"


def test_line_chart_svg():
    svg = line_chart_svg(["Jul '25", "Aug '25"], [{"name": "Subject gross", "values": [1.83, 1.75], "color": "#b3261e"},
                                                    {"name": "Comp effective", "values": [1.5, None], "color": "#1b3a6b", "dash": True}])
    assert svg.startswith("<svg") and "Subject gross" in svg and "stroke-dasharray" in svg and svg.count("<circle") == 3
    assert line_chart_svg([], []) == ""


def test_line_chart_legend_wraps_instead_of_running_off_the_chart():
    import re

    def legend_boxes(svg):
        return [(int(x), int(y)) for x, y in re.findall(r'<text x="(\d+)" y="(\d+)" class="legend">', svg)]

    short = [{"name": f"{p} {k}", "values": [1.0, 2.0], "color": "#000000"} for p in ("The Boardwalk", "Comp Set") for k in ("gross", "effective")]
    one_row = line_chart_svg(["Jan", "Feb"], short)
    assert len({y for _, y in legend_boxes(one_row)}) == 1 and 'viewBox="0 0 760 380"' in one_row

    long = [{"name": f"{p} {k}", "values": [1.0, 2.0], "color": "#000000"}
            for p in ("Pine Ridge", "West Raleigh Comp Set") for k in ("gross", "effective")]
    wrapped = line_chart_svg(["Jan", "Feb"], long)
    boxes = legend_boxes(wrapped)
    assert len({y for _, y in boxes}) == 2, "the fourth entry must move to a second row"
    assert all(x + 6.2 * len(s["name"]) <= 760 - 16 for (x, _), s in zip(boxes, long)), "every label ends inside the chart"
    assert 'viewBox="0 0 760 394"' in wrapped, "the extra row is paid for by a taller viewBox, not by covering the x axis"


def test_formatters_round_half_away_from_zero():
    from app.report.formatters import bps, integer, money, num, pct, signed_money, signed_num

    assert money(1424.5) == "$1,425" and money(1412.5) == "$1,413" and money(-1424.5) == "−$1,425"
    assert num(2.5) == "3" and num(0.125, 2) == "0.13" and signed_num(-0.5) == "(1)" and signed_money(0.5) == "+$1"
    assert integer(1834.5) == "1,835" and bps(-117.5) == "−118 bps"
    assert pct(0.905) == "90.5%" and pct(0.90525) == "90.5%" and pct(0.90535, 2) == "90.54%" and pct(0.0005, 1) == "0.1%"


def test_render_pdf_removes_a_stale_partial_after_a_rejected_render(tmp_path):
    import pytest

    from app.report.render import LayoutOverflow, chromium_available, render_html, render_pdf
    from tests.test_builder import sample_files
    from app.consolidate.builder import build

    if not chromium_available():
        pytest.skip("Playwright Chromium is not installed")
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    data.field("status.fields.status1_body").override = "word " * 900
    html, pdf = tmp_path / "r.html", tmp_path / "r.pdf"
    html.write_text(render_html(data, {"name": "P"}))
    stale = pdf.with_name(pdf.name + ".partial")
    stale.write_bytes(b"%PDF-1.4 fragment from a crashed run")
    with pytest.raises(LayoutOverflow):
        render_pdf(html, pdf)
    assert not stale.exists() and not pdf.exists()
