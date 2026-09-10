# backend/tests/test_render_html.py
from app.consolidate.builder import build
from app.report.render import render_html
from tests.test_builder import sample_files


def test_render_html_contains_every_page_and_key_values():
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    data.field("financing.fields.lender").override = "Fannie Mae"
    html = render_html(data, {"name": "P"}, provenance_appendix=False)
    assert html.count('class="page') == 10
    for s in ("The Boardwalk", "2Q26", "Fort Myers, FL", "$48.0M", "Fannie Mae", "Western Lee County", "Financial Performance",
              "Capital Projects", "Comp set average", "New Lease", "Plumbing &amp; Water Heaters", "<svg", "16.3%", "90.53%", "−118 bps"):
        assert s in html, s
    assert "Jinja" not in html and "{{" not in html
    assert "—" in html  # missing values render as an em dash, never as 'None'
    assert ">None<" not in html



def test_incomplete_reports_carry_a_draft_marker_and_complete_ones_do_not():
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    html = render_html(data, {"name": "P"}, draft_gaps=17)
    assert html.count("DRAFT") >= 10 and "17 items outstanding" in html
    clean = render_html(data, {"name": "P"}, draft_gaps=0)
    assert "DRAFT" not in clean


def test_the_data_source_annex_follows_the_setting_and_can_be_overridden():
    """A delivered report carries figures only; REPORT_PROVENANCE annexes the working papers."""
    import dataclasses

    import app.config as cfg
    from app.report import render

    data, _ = build({"id": "p", "name": "P"}, sample_files())
    plain = render.render_html(data, {"name": "P"}, provenance_appendix=False)
    assert plain.count('class="page') == 10
    assert "Not part of the report" not in plain and "Annotated copy" not in plain

    annotated = render.render_html(data, {"name": "P"}, provenance_appendix=True)
    assert annotated.count('class="page') > 10
    assert "Annotated copy" in annotated and annotated.count("Not part of the report") > 1

    original = cfg.settings
    try:  # with no argument the setting decides
        cfg.settings = dataclasses.replace(original, report_provenance=False)
        assert render.render_html(data, {"name": "P"}).count('class="page') == 10
        cfg.settings = dataclasses.replace(original, report_provenance=True)
        assert render.render_html(data, {"name": "P"}).count('class="page') > 10
    finally:
        cfg.settings = original


def test_a_calculated_value_names_the_figures_it_came_from():
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    html = render_html(data, {"name": "P"}, provenance_appendix=True)
    # the formula, its inputs, their values, and where each input was itself read from
    assert ("Calculated: Purchase price $48,000,000 [bs.xlsx · sheet &#39;Report1&#39; rows 11, 13] "
            "÷ Units 338 [rr-jun.xlsx · sheet &#39;Report1&#39; summary block]") in html
    assert "the same figure as Financial Performance" in html                            # page 5 mirrors page 6
    assert "Calculated by the system from other values" not in html                      # nothing falls back


def test_a_derived_column_states_its_formula_once_for_the_whole_table():
    """A cell's formula belongs to its column, so the sheet states it per column, not per row."""
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    html = render_html(data, {"name": "P"}, provenance_appendix=True)
    assert "Calculated for every row: 2Q26 actual − 2Q26 budget." in html
    assert "Calculated for every row: Var $ ÷ 2Q26 budget." in html
    # naming the derived columns against every row said which were arithmetic, never how
    assert "are calculated from them." not in html


def test_an_expense_row_says_its_variance_is_inverted():
    """Favourable-positive is a property of the row, so the row carries it; a wholly expense table
    states the inverted form in the column rule instead of repeating it down every line."""
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    html = render_html(data, {"name": "P"}, provenance_appendix=True)
    assert "An expense line: its variance is budget less actual, so favourable reads positive." in html
    # capital projects are expenses to the last row, so the rule itself is the inverted one
    assert "Calculated for every row: 2Q26 budget − 2Q26 actual, the favourable-positive convention" in html


def test_an_extracted_value_names_the_part_of_the_file_it_was_read_from():
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    html = render_html(data, {"name": "P"}, provenance_appendix=True)
    # file, then the sheet and row inside it, then the line that was read
    assert "bs.xlsx · sheet &#39;Report1&#39; rows 11, 13 — &#34;Total Building + Total Furniture &amp; Fixtures&#34;" in html
    assert "rr-jun.xlsx · sheet &#39;Report1&#39; summary block — &#34;Totals&#34;" in html


def test_a_long_explanation_wraps_instead_of_being_cut_off():
    """The sheets budget their height, so a long source line costs extra rows rather than a lost tail."""
    from app.report import render

    data, _ = build({"id": "p", "name": "P"}, sample_files())
    long_detail = {"kind": "row", "label": "A field with a long name that itself has to wrap", "value": "—",
                   "origin": "missing", "method": "Not found", "detail": "x" * 400}
    assert render.row_cost(long_detail) > 4                       # roughly 400/78 lines
    assert render.row_cost({"kind": "row", "label": "Units", "detail": "short"}) == 1
    sheets = render.paginate([long_detail] * 12)
    assert len(sheets) > 1 and all(sum(render.row_cost(i) for i in s) <= render.APPENDIX_ROWS_PER_PAGE for s in sheets)
    html = render_html(data, {"name": "P"}, provenance_appendix=True)
    assert 'class="wrap"' in html and "text-overflow" not in html.split("</style>")[1]
