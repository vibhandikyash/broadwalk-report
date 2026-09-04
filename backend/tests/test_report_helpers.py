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
