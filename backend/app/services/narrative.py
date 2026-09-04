"""Optional: draft narrative paragraphs with Claude from the structured numbers only.

The prompt carries the effective values of the relevant sections as JSON, never the source files, so the
model can only phrase numbers the reviewer already sees. Drafts are stored with status `ai_draft`.
"""
from __future__ import annotations

import json
from typing import Any

from ..config import settings
from ..models import ReportData

SYSTEM = (
    "You write concise commentary for a quarterly multifamily investor report. Use only the numbers in the JSON provided. "
    "Never invent figures, names, dates or events. Write two to four plain sentences: no bullet points, no headings, "
    "no em dashes. If the data needed for the request is missing, reply with exactly: INSUFFICIENT DATA"
)

# (field path, instruction, sections whose effective values are sent)
NARRATIVES: list[tuple[str, str, list[str]]] = [
    ("commentary.fields.takeaway", "Write the quarter's headline takeaway: revenue versus budget, NOI versus budget, and net cash flow after debt service.", ["commentary"]),
    ("commentary.fields.revenue_body", "Explain the revenue variance versus budget using gross potential rent, gain or loss to lease, concessions and vacancy.", ["commentary", "financials"]),
    ("commentary.fields.opex_body", "Explain the operating expense variance versus budget, naming the largest favourable and unfavourable lines.", ["commentary", "financials"]),
    ("commentary.fields.noi_body", "Explain NOI and net cash flow after debt service versus budget, then summarise capital spend versus budget.", ["commentary", "capex"]),
    ("in_place_rent.fields.narrative", "Describe how in-place rents moved quarter over quarter by floor plan and overall.", ["in_place_rent"]),
    ("submarket.fields.occupancy_narrative", "Compare the subject's occupancy with the comp set leased percentages.", ["submarket", "occupancy"]),
    ("submarket.fields.rent_narrative", "Compare the subject's asking and effective rent with the comp set average.", ["submarket"]),
    ("submarket.fields.concession_narrative", "Compare the subject's concession level with the comp set.", ["submarket"]),
    ("occupancy.fields.new_lease_narrative", "Summarise new-lease trade-outs by floor plan and overall.", ["occupancy"]),
    ("occupancy.fields.renewal_narrative", "Summarise renewal trade-outs by floor plan and overall.", ["occupancy"]),
    ("capex.fields.narrative", "Summarise capital spend for the quarter and year to date versus budget, naming the largest items.", ["capex", "commentary"]),
]


def section_values(data: ReportData, key: str) -> dict[str, Any]:
    """Effective values of one section, without narrative fields, as plain JSON-able dicts."""
    sec = data.sections.get(key)
    if sec is None:
        return {}
    out: dict[str, Any] = {"fields": {k: f.effective for k, f in sec.fields.items() if f.effective is not None and f.kind != "longtext"}, "tables": {}}
    for tk, t in sec.tables.items():
        out["tables"][tk] = {
            "rows": {rk: {ck: c.effective for ck, c in row.items() if c.effective is not None} for rk, row in t.rows.items()},
            "totals": {ck: c.effective for ck, c in t.totals.items() if c.effective is not None},
        }
    return out


def draft_all(data: ReportData, model: str | None = None, client: Any = None) -> dict[str, str]:
    """Return {field path: draft text} for every narrative field that is still empty."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    model = model or settings.anthropic_model
    drafts: dict[str, str] = {}
    for path, instruction, sections in NARRATIVES:
        fld = data.field(path)
        if fld is None or fld.effective not in (None, ""):
            continue
        payload = {"property": data.meta.get("property_name"), "period": data.meta.get("period"),
                   **{s: section_values(data, s) for s in sections}}
        response = client.beta.messages.create(
            model=model,
            max_tokens=1024,  # deliberately short: two to four sentences
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM,
            messages=[{"role": "user", "content": f"{instruction}\n\nDATA (JSON):\n{json.dumps(payload, default=str)}"}],
        )
        if response.stop_reason == "refusal":
            continue
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()
        if text and "INSUFFICIENT DATA" not in text.upper():
            drafts[path] = text
    return drafts
