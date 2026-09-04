# backend/tests/test_render_html.py
from app.consolidate.builder import build
from app.report.render import render_html
from tests.test_builder import sample_files


def test_render_html_contains_every_page_and_key_values():
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    data.field("financing.fields.lender").override = "Fannie Mae"
    html = render_html(data, {"name": "P"})
    assert html.count('class="page') == 10
    for s in ("The Boardwalk", "2Q26", "Fort Myers, FL", "$48.0M", "Fannie Mae", "Western Lee County", "Financial Performance",
              "Capital Projects", "Comp set average", "New Lease", "Plumbing &amp; Water Heaters", "<svg", "16.3%", "90.53%", "−118 bps"):
        assert s in html, s
    assert "Jinja" not in html and "{{" not in html
    assert "—" in html  # missing values render as an em dash, never as 'None'
    assert ">None<" not in html
