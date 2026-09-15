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

from ..consolidate.provenance import CELL_INPUTS, OPERATORS, counts, describe, source_files
from ..models import Field, ReportData, Table
from .chart import line_chart_svg
from .formatters import FILTERS, MINUS, NONE

REPORT_DIR = Path(__file__).resolve().parent
BODY_PAGES = 10  # the fixed report; each page is followed by the provenance sheets for its own values
# A sheet's capacity, measured in single-line rows: 18 leaves headroom over the ~23 that fit. Rows now
# wrap, so they are budgeted rather than counted — an extra line costs the ratio of a line's height to
# a whole row's, and the character widths are the columns of the sheet table at its 7pt serif.
APPENDIX_ROWS_PER_PAGE = 18
EXTRA_LINE_COST = 0.68
HEADING_COST = 1.3
CHARS_PER_LINE = {"label": 40, "detail": 78}
MAX_DETAIL_CHARS = 600  # no single row may be taller than a sheet
INLINE_TEXT_LIMIT = 220
DETAIL_PAGE_CHARS = 450
# Which printed page a section's values land on. Section.page is the review screen's grouping; the
# cover repeats a few property and capital figures whose detail belongs with pages 2 and 3.
SHEET_PAGE = {"property": 2, "in_place_rent": 2, "capital": 3, "underwriting": 3, "rent_trend": 3,
              "financing": 4, "commentary": 5, "financials": 6, "capex": 7, "submarket": 8,
              "occupancy": 9, "status": 10}
# The report reserves the word DRAFT for the incomplete-version marker, so the appendix names an
# AI-written value differently from the review screen's 'AI draft' chip.
ORIGIN_LABELS = (("extracted", "Extracted"), ("inferred", "Inferred"), ("ocr", "Extracted by OCR"), ("computed", "Calculated"),
                 ("manual", "Entered by reviewer"), ("ai_draft", "AI-written"), ("missing", "Not found"))
ORIGIN_LABEL = dict(ORIGIN_LABELS)
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


_VALUE_FILTERS: dict[str, Callable] = {
    "money": FILTERS["money"], "percent": lambda v: FILTERS["pct"](v, 2), "integer": FILTERS["integer"],
    "number": lambda v: FILTERS["num"](v, 2), "date": FILTERS["date_long"],
}


# Years are integers that the report prints without grouping; the appendix must match it, not invent "1,973".
_PLAIN_NUMBER_KEYS = {"year_built", "vintage", "zip"}


def _value_text(path: str, f: Field, limit: int = 34) -> str:
    """The field's value as the report shows it, clipped so an appendix row stays one line high."""
    filt = FILTERS["text"] if path.rsplit(".", 1)[-1] in _PLAIN_NUMBER_KEYS else _VALUE_FILTERS.get(f.kind, FILTERS["text"])
    rendered = filt(f.effective)
    flat = " ".join(str(rendered).split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _and_list(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _appendix_field(path: str, f: Field, data: ReportData, label: str) -> dict:
    p = describe(path, f, data)
    return {"kind": "row", "label": label, "value": _value_text(path, f), "origin": p.origin,
            "method": ORIGIN_LABEL[p.origin], "detail": " ".join(p.detail.split())[:MAX_DETAIL_CHARS]}


def row_cost(item: dict) -> float:
    """How much of a sheet a row takes, in single-line rows. Wrapped text is the reason rows differ."""
    if item.get("kind") == "head":
        return HEADING_COST
    lines = max(1, *(-(-len(str(item.get(k, ""))) // CHARS_PER_LINE[k]) for k in CHARS_PER_LINE))
    return 1 + EXTRA_LINE_COST * (lines - 1)


def _appendix_table_row(tpath: str, rkey: str, label: str, cells: dict[str, Field], data: ReportData, columns: list,
                        expense_note: bool = False) -> dict:
    """One appendix line for a whole table row: rows are extracted from a single source line, so the
    interesting facts are that source and which columns of the row came back empty."""
    order = [c.key for c in columns if c.key in cells]
    inputs = [k for k in order if cells[k].status != "derived"]
    filled = [k for k in inputs if cells[k].effective not in (None, "")]
    empty = [cells[k].label for k in inputs if cells[k].effective in (None, "")]
    sourced = next((k for k in filled if cells[k].source and cells[k].source.filename), None)
    anchor = sourced or (filled[0] if filled else (inputs[0] if inputs else order[0]))
    p = describe(f"{tpath}.rows.{rkey}.{anchor}", cells[anchor], data)
    detail = p.detail
    if empty and filled:
        detail = f"{detail} No value in the source for: {', '.join(empty)}."
    # The row's derived cells are not explained here: their formula belongs to the column, and
    # _column_rules states it once for the whole table rather than repeating it on every row. The one
    # thing the column cannot say is which of its rows invert the subtraction, so those rows say it.
    if expense_note:
        detail = f"{detail} · An expense line: its variance is budget less actual, so favourable reads positive."
    return {"kind": "row", "label": label, "value": f"{len(filled)} of {len(inputs)} values", "origin": p.origin,
            "method": ORIGIN_LABEL[p.origin], "detail": " ".join(detail.split())[:MAX_DETAIL_CHARS]}


def _rule_text(op: str, columns: tuple[str, ...], t: Table) -> str:
    """A column's formula written in column names alone: 'Var $ ÷ 2Q26 budget'.

    The operator templates carry a value and a source beside each name so a single cell can be
    followed by eye; a column rule has neither, so those slots are left empty and the gaps closed up.
    """
    labels = {c.key: c.label for c in t.columns}
    slots: dict[str, str] = {}
    for i, ckey in enumerate(columns):
        slots[f"n{i}"], slots[f"v{i}"], slots[f"s{i}"] = labels.get(ckey, ckey), "", ""
    # The emptied value slot leaves a gap before any punctuation the template carries after it.
    return " ".join(OPERATORS[op].format(**slots).split()).replace(" ,", ",")


def _expense_rows(t: Table) -> list[str]:
    return [rkey for rkey in t.rows if t.row_meta.get(rkey, {}).get("expense")]


def _column_rules(t: Table, prefix: str) -> list[dict]:
    """One appendix line per derived column, giving the formula every row of that column applies.

    A derived cell's formula is a property of its column, not of its row: printing it against each
    row would repeat the same sentence up to 28 times and bury the rows that differ. An expense row
    inverts the subtraction so that a favourable result reads positive. Where every row is an expense
    the rule simply states the inverted form; where only some are, those rows say so themselves.
    """
    expense = _expense_rows(t)
    all_expense = bool(expense) and len(expense) == len(t.rows)
    out: list[dict] = []
    for col in t.columns:
        entry = CELL_INPUTS.get(col.key)
        if not entry or not any(col.key in cells and cells[col.key].status == "derived" for cells in t.rows.values()):
            continue
        op, columns = entry
        if op == "variance" and all_expense:
            op = "variance_expense"
        rule = f"Calculated for every row: {_rule_text(op, columns, t)}."
        if op == "variance" and expense:
            rule += " Expense lines invert this subtraction so that a favourable result reads positive; each says so."
        out.append({"kind": "row", "label": f"{prefix}{col.label}", "value": "every row", "origin": "computed",
                    "method": ORIGIN_LABEL["computed"], "detail": rule})
    return out


def _section_rows(skey: str, sec, data: ReportData) -> list[dict]:
    """One row per field, per table row and per table total. The table's name prefixes a row only when
    the section has more than one table, since otherwise the sheet's heading already says which it is."""
    rows = [_appendix_field(f"{skey}.fields.{fkey}", f, data, f.label) for fkey, f in sec.fields.items()]
    for tkey, t in sec.tables.items():
        tpath = f"{skey}.tables.{tkey}"
        prefix = f"{t.title}: " if len(sec.tables) > 1 else ""
        # Only worth marking a row as an expense when its neighbours are not: if every row inverts,
        # the column rule states the inverted form and a note on all 28 rows would say nothing.
        expense = _expense_rows(t)
        mark = expense if len(expense) < len(t.rows) else []
        for rkey, cells in t.rows.items():
            label = t.row_meta.get(rkey, {}).get("label", rkey)
            rows.append(_appendix_table_row(tpath, rkey, f"{prefix}{label}", cells, data, t.columns, rkey in mark))
        rows.extend(_column_rules(t, prefix))
        for ckey, f in t.totals.items():
            rows.append(_appendix_field(f"{tpath}.totals.{ckey}", f, data, f"{prefix}Total {f.label}"))
    return rows


def appendix_items(data: ReportData) -> dict[int, list[dict]]:
    """The provenance rows for each printed report page, so a page's sources follow the page itself.

    A page fed by more than one section gets a heading per section; a page fed by one does not, because
    the sheet's own header already names it.
    """
    grouped: dict[int, list[tuple[str, list[dict]]]] = {}
    for skey, sec in data.sections.items():
        rows = _section_rows(skey, sec, data)
        if rows:
            grouped.setdefault(SHEET_PAGE.get(skey, sec.page), []).append((sec.title, rows))
    out: dict[int, list[dict]] = {}
    for page, sections in sorted(grouped.items()):
        items: list[dict] = []
        for title, rows in sections:
            if len(sections) > 1:
                items.append({"kind": "head", "label": title, "page": page})
            items.extend(rows)
        out[page] = items
    return out


def paginate(items: list[dict], per_page: float = APPENDIX_ROWS_PER_PAGE) -> list[list[dict]]:
    """Chunk into sheets by height, never leaving a group heading stranded as the last line of a sheet."""
    pages: list[list[dict]] = []
    current: list[dict] = []
    used = 0.0
    for item in items:
        cost = row_cost(item)
        stranded = current and item["kind"] == "head" and used + cost + 1 > per_page
        if current and (used + cost > per_page or stranded):
            pages.append(current)
            current, used = [], 0.0
        current.append(item)
        used += cost
    if current:
        pages.append(current)
    return pages


def number_pages(by_page: dict[int, list[dict]], per_page: int = APPENDIX_ROWS_PER_PAGE,
                 detail_counts: dict[int, int] | None = None, closing_pages: int = 2) -> tuple[dict[int, int], dict[int, list[dict]], int]:
    """Interleave: each fixed page, its full-value details, its provenance sheets, then closing pages.

    Returns the printed number of each fixed page, the sheets that follow it (each carrying its own
    printed number and its position within that page's set), and the total page count.
    """
    printed: dict[int, int] = {}
    sheets: dict[int, list[dict]] = {}
    n = 0
    for body in range(1, BODY_PAGES + 1):
        n += 1
        printed[body] = n
        n += (detail_counts or {}).get(body, 0)
        chunks = paginate(by_page.get(body, []), per_page)
        entries = []
        for index, items in enumerate(chunks, start=1):
            n += 1
            entries.append({"items": items, "page": n, "index": index, "count": len(chunks)})
        sheets[body] = entries
    return printed, sheets, n + closing_pages


def context(data: ReportData, project: dict | None = None, assets: dict[str, str] | None = None, draft_gaps: int = 0,
            provenance_appendix: bool | None = None) -> dict:
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
    from ..config import settings

    annotated = settings.report_provenance if provenance_appendix is None else provenance_appendix
    long_text = {
        path: field for path, field in data.iter_fields()
        if ".fields." in path and field.kind in ("text", "longtext")
        and isinstance(field.effective, str) and len(field.effective) > INLINE_TEXT_LIMIT
        and path.split(".", 1)[0] in SHEET_PAGE
    }
    detail_pages_by_body: dict[int, list[dict]] = {}
    for path, field in long_text.items():
        value = field.effective
        chunks = [value[i:i + DETAIL_PAGE_CHARS] for i in range(0, len(value), DETAIL_PAGE_CHARS)]
        body = SHEET_PAGE[path.split(".", 1)[0]]
        for index, chunk in enumerate(chunks, start=1):
            detail_pages_by_body.setdefault(body, []).append({
                "path": path, "label": field.label, "text": chunk,
                "part": index, "parts": len(chunks), "source": field.source,
            })
    detail_counts = {body: len(pages) for body, pages in detail_pages_by_body.items()}
    printed, sheets, total = number_pages(appendix_items(data) if annotated else {},
                                          detail_counts=detail_counts,
                                          closing_pages=2 if annotated else 0)
    first_detail_page = {}
    for body, pages in detail_pages_by_body.items():
        for offset, detail in enumerate(pages, start=1):
            detail["page"] = printed[body] + offset
            first_detail_page.setdefault(detail["path"], detail["page"])

    def v(path: str):
        value = data.value(path)
        if path not in long_text:
            return value
        preview = value[:INLINE_TEXT_LIMIT].rsplit(" ", 1)[0] or value[:INLINE_TEXT_LIMIT]
        return f"{preview}… [complete value on page {first_detail_page[path]}]"

    return {
        "v": v, "f": data.field, "meta": data.meta, "project": project or {}, "MINUS": MINUS, "NONE": NONE, "assets": assets or {}, "draft_gaps": int(draft_gaps or 0),
        "pno": printed, "prov_sheets": sheets, "prov_origins": ORIGIN_LABELS, "provenance": annotated,
        "prov_counts": counts(data) if annotated else {},
        "prov_files": source_files(data) if annotated else [],
        "body_pages": BODY_PAGES, "total_pages": total,
        "detail_pages_by_body": detail_pages_by_body,
        "css": (REPORT_DIR / "static" / "report.css").read_text(), "fonts_css": _fonts_css(),
        "ipr_rows": _rows(data.table("in_place_rent.tables.by_floor_plan")), "ipr_totals": _totals(data.table("in_place_rent.tables.by_floor_plan")),
        "uw_groups": uw_groups, "uw_sub": uw_sub, "uw_totals": _totals(data.table("underwriting.tables.budget")), "chart_svg": chart_svg,
        "fin_rows": _rows(fin_t), "fin_meta": fin_t.row_meta if fin_t else {},
        "capex_rows": capex_rows, "capex_totals": _totals(data.table("capex.tables.lines")),
        "comp_rows": _rows(data.table("submarket.tables.comps")), "comp_totals": _totals(data.table("submarket.tables.comps")),
        "nl_rows": _rows(data.table("occupancy.tables.new_leases")), "nl_totals": _totals(data.table("occupancy.tables.new_leases")),
        "rn_rows": _rows(data.table("occupancy.tables.renewals")), "rn_totals": _totals(data.table("occupancy.tables.renewals")),
    }


def render_html(data: ReportData, project: dict | None = None, assets: dict[str, str] | None = None, draft_gaps: int = 0,
                provenance_appendix: bool | None = None) -> str:
    """draft_gaps > 0 marks every page as a draft: the reviewed data does not yet satisfy the completeness specification.

    provenance_appendix annexes the data-source sheets that say, for every value, which file and line
    it came from, whether OCR was needed, or why it is absent. None follows REPORT_PROVENANCE, which
    is off by default because a delivered report carries values only; True and False override it.
    """
    return env.get_template("report.html").render(**context(data, project, assets, draft_gaps, provenance_appendix))


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
