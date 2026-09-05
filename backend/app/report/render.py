"""HTML rendering of ReportData with Jinja, and PDF printing with headless Chromium.

Before printing, every .page is measured in the browser; content that would be clipped by the fixed
page box rejects the render (LayoutOverflow) instead of silently disappearing from the PDF.
"""
from __future__ import annotations

import base64
import calendar
from functools import lru_cache
from pathlib import Path
from typing import Callable

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models import ReportData, Table
from .chart import line_chart_svg
from .formatters import FILTERS, MINUS

REPORT_DIR = Path(__file__).resolve().parent
env = Environment(loader=FileSystemLoader(REPORT_DIR / "templates"), autoescape=select_autoescape(["html"]),
                  trim_blocks=True, lstrip_blocks=True)
env.filters.update(FILTERS)

FONT_FACES = (
    ("Source Serif 4", "SourceSerif4-Regular.ttf", 400, "normal"), ("Source Serif 4", "SourceSerif4-Semibold.ttf", 600, "normal"),
    ("Source Serif 4", "SourceSerif4-It.ttf", 400, "italic"), ("JetBrains Mono", "JetBrainsMono-Regular.ttf", 400, "normal"),
    ("JetBrains Mono", "JetBrainsMono-Medium.ttf", 500, "normal"),
)


@lru_cache(maxsize=1)
def _fonts_css() -> str:
    """@font-face rules with the TTFs inlined as data URIs (Chromium refuses file:// fonts from a file:// page)."""
    fonts = REPORT_DIR / "static" / "fonts"
    faces = []
    for fam, file, w, style in FONT_FACES:
        path = fonts / file
        if path.exists():
            b64 = base64.b64encode(path.read_bytes()).decode()
            faces.append(f"@font-face{{font-family:'{fam}';src:url(data:font/ttf;base64,{b64}) format('truetype');"
                         f"font-weight:{w};font-style:{style};}}")
    return "\n".join(faces)


def _rows(t: Table | None, sort_key: Callable | None = None) -> list[dict]:
    if t is None:
        return []
    out = []
    for key, row in t.rows.items():
        meta = t.row_meta.get(key, {})
        out.append({"key": key, "label": meta.get("label", key), "subject": bool(meta.get("subject")),
                    "c": {ck: f.effective for ck, f in row.items()}})
    if sort_key:
        out.sort(key=sort_key)
    return out


def _totals(t: Table | None) -> dict:
    return {ck: f.effective for ck, f in t.totals.items()} if t else {}


def _month_tick(ym) -> str:
    try:
        y, m = str(ym).split("-")[:2]
        return f"{calendar.month_abbr[int(m)]} '{y[2:]}"
    except (ValueError, IndexError):
        return str(ym)


def _sum(rows: list[dict], col: str) -> float | None:
    vals = [r["c"].get(col) for r in rows if r["c"].get(col) is not None]
    return sum(vals) if vals else None


def context(data: ReportData, project: dict | None = None, assets: dict[str, str] | None = None, draft_gaps: int = 0) -> dict:
    v = data.value
    uw_rows = _rows(data.table("underwriting.tables.budget"))
    uw_groups = {"value_add": [r for r in uw_rows if str(r["c"].get("section") or "").lower().startswith("value")],
                 "recurring": [r for r in uw_rows if not str(r["c"].get("section") or "").lower().startswith("value")]}
    uw_sub = {}
    for g, rs in uw_groups.items():
        ob, sp = _sum(rs, "original_budget"), _sum(rs, "spent_to_date")
        uw_sub[g] = {"original_budget": ob, "spent_to_date": sp, "pct_spent": (sp / ob) if ob and sp is not None else None}
    trend = _rows(data.table("rent_trend.tables.monthly"))
    subject = v("rent_trend.fields.subject_name") or v("property.fields.name") or "Subject"
    comp = v("rent_trend.fields.comp_name") or "Comp Set"
    series = [
        {"name": f"{subject} gross", "values": [r["c"].get("subject_gross_psf") for r in trend], "color": "#b3261e"},
        {"name": f"{subject} effective", "values": [r["c"].get("subject_eff_psf") for r in trend], "color": "#b3261e", "dash": True},
        {"name": f"{comp} gross", "values": [r["c"].get("comp_gross_psf") for r in trend], "color": "#1b3a6b"},
        {"name": f"{comp} effective", "values": [r["c"].get("comp_eff_psf") for r in trend], "color": "#1b3a6b", "dash": True},
    ]
    chart_svg = line_chart_svg([_month_tick(r["c"].get("month")) for r in trend], series) if trend else ""
    capex_rows = _rows(data.table("capex.tables.lines"), sort_key=lambda r: (-(r["c"].get("ptd_actual") or 0), -(r["c"].get("ptd_budget") or 0)))
    fin_t = data.table("financials.tables.lines")
    return {
        "v": v, "f": data.field, "meta": data.meta, "project": project or {}, "MINUS": MINUS, "assets": assets or {}, "draft_gaps": int(draft_gaps or 0),
        "css": (REPORT_DIR / "static" / "report.css").read_text(), "fonts_css": _fonts_css(),
        "ipr_rows": _rows(data.table("in_place_rent.tables.by_floor_plan")), "ipr_totals": _totals(data.table("in_place_rent.tables.by_floor_plan")),
        "uw_groups": uw_groups, "uw_sub": uw_sub, "uw_totals": _totals(data.table("underwriting.tables.budget")), "chart_svg": chart_svg,
        "fin_rows": _rows(fin_t), "fin_meta": fin_t.row_meta if fin_t else {},
        "capex_rows": capex_rows, "capex_totals": _totals(data.table("capex.tables.lines")),
        "comp_rows": _rows(data.table("submarket.tables.comps")), "comp_totals": _totals(data.table("submarket.tables.comps")),
        "nl_rows": _rows(data.table("occupancy.tables.new_leases")), "nl_totals": _totals(data.table("occupancy.tables.new_leases")),
        "rn_rows": _rows(data.table("occupancy.tables.renewals")), "rn_totals": _totals(data.table("occupancy.tables.renewals")),
    }


def render_html(data: ReportData, project: dict | None = None, assets: dict[str, str] | None = None, draft_gaps: int = 0) -> str:
    """draft_gaps > 0 marks every page as a draft: the reviewed data does not yet satisfy the completeness specification."""
    return env.get_template("report.html").render(**context(data, project, assets, draft_gaps))


def chromium_available() -> bool:
    """True when a Playwright Chromium build is installed, checked on disk so no driver process is started."""
    try:
        import playwright
    except ImportError:
        return False
    import os
    import sys

    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env == "0":
        base = Path(playwright.__file__).resolve().parent / "driver" / "package" / ".local-browsers"
    elif env:
        base = Path(env)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches" / "ms-playwright"
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ms-playwright"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "ms-playwright"
    return base.is_dir() and any(d.is_dir() and d.name.startswith("chromium") for d in base.iterdir())


class LayoutOverflow(Exception):
    """Some page's content does not fit its fixed box; rendering it would clip or hide content."""

    def __init__(self, problems: list[dict]) -> None:
        self.problems = problems
        super().__init__("Content does not fit the page: " + "; ".join(_describe(p) for p in problems))


PX_PER_PT = 96 / 72
OVERFLOW_JS = """() => [...document.querySelectorAll('.page')].map((el, i) => {
  const h = el.querySelector('.hdr h1, .cover-title');
  return {page: i + 1, section: h ? h.textContent.trim() : '', dy: el.scrollHeight - el.clientHeight, dx: el.scrollWidth - el.clientWidth};
}).filter(p => p.dy > 1 || p.dx > 1)"""
HINTS = {
    "table": "remove rows from the table or shorten the narrative under it",
    "text": "shorten the text on this page",
}


def _describe(p: dict) -> str:
    where = f"page {p['page']}" + (f" ({p['section']})" if p.get("section") else "")
    amounts = []
    if p.get("dy", 0) > 1:
        amounts.append(f"{p['dy'] / PX_PER_PT:.0f} pt too tall")
    if p.get("dx", 0) > 1:
        amounts.append(f"{p['dx'] / PX_PER_PT:.0f} pt too wide")
    hint = HINTS["table"] if p.get("has_table") else HINTS["text"]
    return f"{where} is {' and '.join(amounts)}; {hint}"


def check_layout(html_path: Path) -> list[dict]:
    """Open the HTML in Chromium and return one entry per .page whose content overflows its box."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri(), wait_until="load")
            page.emulate_media(media="print")
            page.evaluate("document.fonts.ready")
            problems = page.evaluate(OVERFLOW_JS)
            for pr in problems:
                pr["has_table"] = page.evaluate("i => !!document.querySelectorAll('.page')[i].querySelector('table')", pr["page"] - 1)
            return problems
        finally:
            browser.close()


def render_pdf(html_path: Path, pdf_path: Path) -> None:
    """Print the saved HTML file to PDF with headless Chromium after checking that every page fits.

    Raises LayoutOverflow instead of producing a PDF with clipped content. The PDF is written to a
    temporary name and moved into place, so a failure never leaves a partial file at pdf_path.
    """
    from playwright.sync_api import sync_playwright

    tmp = pdf_path.with_name(pdf_path.name + ".partial")
    tmp.unlink(missing_ok=True)  # residue of a run that crashed mid-write
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(html_path.resolve().as_uri(), wait_until="load")
                page.emulate_media(media="print")
                page.evaluate("document.fonts.ready")
                problems = page.evaluate(OVERFLOW_JS)
                if problems:
                    for pr in problems:
                        pr["has_table"] = page.evaluate("i => !!document.querySelectorAll('.page')[i].querySelector('table')", pr["page"] - 1)
                    raise LayoutOverflow(problems)
                page.pdf(path=str(tmp), prefer_css_page_size=True, print_background=True)
            finally:
                browser.close()
        tmp.replace(pdf_path)
    finally:
        tmp.unlink(missing_ok=True)  # no-op after a successful move; removes the fragment after any failure
