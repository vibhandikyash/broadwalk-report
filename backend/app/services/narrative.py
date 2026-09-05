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
    "Never invent figures, names, dates or events. Round dollar amounts to whole dollars and percentages to one decimal. "
    "Write two to four plain sentences: no bullet points, no headings, no em dashes. "
    "If the data needed for the request is missing, reply with exactly: INSUFFICIENT DATA"
)

CONVENTIONS = {
    "variances": "A variance (any *_var or *_var_pct value) is favourable when positive and unfavourable when negative: "
                 "revenue above budget is positive, an expense below budget is positive, an expense over budget is negative.",
    "percentages": "Percent fields are fractions: 0.05 means 5%.",
    "money": "Amounts are US dollars for the period shown (ptd = the quarter, ytd = year to date).",
    "lto": "lto and lto_pct are the change from the prior lease to the new lease (negative = the new lease is lower).",
}

# (field path, instruction, sections whose effective values are sent, word budget)
NARRATIVES: list[tuple[str, str, list[str], int]] = [
    ("commentary.fields.takeaway", "Write the quarter's headline takeaway: revenue versus budget, NOI versus budget, and net cash flow after debt service.", ["commentary"], 70),
    ("commentary.fields.revenue_body", "Explain the revenue variance versus budget using gross potential rent, gain or loss to lease, concessions and vacancy.", ["commentary", "financials"], 90),
    ("commentary.fields.opex_body", "Explain the operating expense variance versus budget, naming the largest favourable and unfavourable lines.", ["commentary", "financials"], 90),
    ("commentary.fields.noi_body", "Explain NOI and net cash flow after debt service versus budget, then summarise capital spend versus budget.", ["commentary", "capex"], 90),
    ("in_place_rent.fields.narrative", "Describe how in-place rents moved quarter over quarter by floor plan and overall.", ["in_place_rent"], 50),
    ("submarket.fields.occupancy_narrative", "Compare the subject's occupancy with the comp set leased percentages.", ["submarket", "occupancy"], 35),
    ("submarket.fields.rent_narrative", "Compare the subject's asking and effective rent with the comp set average.", ["submarket"], 35),
    ("submarket.fields.concession_narrative", "Compare the subject's concession level with the comp set.", ["submarket"], 35),
    ("occupancy.fields.occupancy_narrative", "State how physical occupancy moved over the quarter and what the future/applicant count implies.", ["occupancy"], 30),
    ("occupancy.fields.new_lease_narrative", "Summarise new-lease trade-outs by floor plan and overall.", ["occupancy"], 40),
    ("occupancy.fields.renewal_narrative", "Summarise renewal trade-outs by floor plan and overall.", ["occupancy"], 40),
    ("capex.fields.narrative", "Summarise capital spend for the quarter and year to date versus budget, naming the largest items.", ["capex", "commentary"], 60),
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


API_DEFAULT_MODEL = "claude-opus-5"


def _complete_api(client: Any, model: str, user: str) -> str | None:
    """One completion through the Anthropic SDK (API key). Refusals return None."""
    response = client.beta.messages.create(
        model=model,
        max_tokens=1024,  # deliberately short: two to four sentences
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    if response.stop_reason == "refusal":
        return None
    return "".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()


def _agent_query(prompt: str, options: Any):
    """Indirection over claude_agent_sdk.query so tests can substitute a fake stream."""
    from claude_agent_sdk import query

    return query(prompt=prompt, options=options)


def _complete_agent_sdk(model: str | None, user: str) -> str | None:
    """One completion through the Claude Agent SDK, which runs the bundled Claude Code CLI and therefore
    uses whatever that CLI is logged in with (API key, or the local Claude Code subscription login).
    No tools, one turn, no settings or CLAUDE.md loaded, nothing written to the session history."""
    import asyncio

    from claude_agent_sdk import ClaudeAgentOptions

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM, tools=[], allowed_tools=[], permission_mode="dontAsk", max_turns=1, setting_sources=[],
        model=model, env={"CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1"},  # tools=[] drops the tool schemas from the context
    )

    async def run() -> str | None:
        texts: list[str] = []
        result: Any = None
        async for message in _agent_query(user, options):
            content = getattr(message, "content", None)
            if isinstance(content, list):
                texts += [b.text for b in content if getattr(b, "text", None)]
            if getattr(message, "subtype", None) is not None and hasattr(message, "duration_ms"):
                result = message
        if result is not None:
            if getattr(result, "subtype", "success") != "success":
                raise RuntimeError(f"Claude Agent SDK returned {result.subtype}")
            if getattr(result, "stop_reason", None) == "refusal":
                return None
            final = getattr(result, "result", None)
            if final:
                return str(final).strip()
        return "".join(texts).strip()

    return asyncio.run(run())


def draft_all(data: ReportData, model: str | None = None, client: Any = None, provider: str | None = None) -> dict[str, str]:
    """Return {field path: draft text} for every narrative field that is still empty.

    provider: 'api' (Anthropic SDK; `client` may be injected) or 'agent-sdk'; defaults to settings.llm_provider.
    """
    provider = provider or ("api" if client is not None else settings.llm_provider)
    if provider is None:
        raise RuntimeError("No narrative provider configured: set ANTHROPIC_API_KEY or install claude-agent-sdk with a Claude Code login")
    if provider == "api":
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        model = model or settings.anthropic_model or API_DEFAULT_MODEL
    else:
        model = model or settings.anthropic_model  # None lets the Claude Code CLI use its configured default
    drafts: dict[str, str] = {}
    for path, instruction, sections, max_words in NARRATIVES:
        fld = data.field(path)
        if fld is None or fld.effective not in (None, ""):
            continue
        payload = {"property": data.meta.get("property_name"), "period": data.meta.get("period"), "conventions": CONVENTIONS,
                   **{s: section_values(data, s) for s in sections}}
        user = f"{instruction} Use at most {max_words} words; the space on the page is fixed.\n\nDATA (JSON):\n{json.dumps(payload, default=str)}"
        text = _complete_api(client, model, user) if provider == "api" else _complete_agent_sdk(model, user)
        if text and "INSUFFICIENT DATA" not in text.upper():
            drafts[path] = text
    return drafts
