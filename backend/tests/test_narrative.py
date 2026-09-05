# backend/tests/test_narrative.py
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.consolidate.builder import build
from app.main import app
from app.services import narrative
from app.services.narrative import NARRATIVES, draft_all, section_values
from tests.test_builder import sample_files


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        instruction = kwargs["messages"][0]["content"].split("\n")[0]
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=f"Draft: {instruction[:20]}")])


def fake_client():
    msgs = FakeMessages()
    return SimpleNamespace(beta=SimpleNamespace(messages=msgs)), msgs


def test_draft_all_fills_only_empty_narratives_from_section_values():
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    data.field("commentary.fields.takeaway").override = "Already written."
    client, msgs = fake_client()
    drafts = draft_all(data, model="claude-opus-5", client=client)
    assert "commentary.fields.takeaway" not in drafts and "commentary.fields.revenue_body" in drafts
    assert len(drafts) == len(NARRATIVES) - 1 and all(t.startswith("Draft: ") for t in drafts.values())
    call = msgs.calls[0]
    assert call["model"] == "claude-opus-5" and call["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in call["betas"]
    assert '"total_revenue"' in call["messages"][0]["content"] and "Never invent" in call["system"]
    sv = section_values(data, "financials")
    assert sv["tables"]["lines"]["rows"]["noi"]["ptd_actual"] == 550 and "longtext" not in str(sv)


def test_refusals_and_insufficient_data_are_skipped():
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    refusing = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(stop_reason="refusal", content=[]))))
    assert draft_all(data, client=refusing) == {}
    empty = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="INSUFFICIENT DATA")]))))
    assert draft_all(data, client=empty) == {}


def test_narratives_endpoint_requires_a_provider(monkeypatch):
    import dataclasses

    from app.config import settings

    monkeypatch.setattr("app.config.settings", dataclasses.replace(settings, narrative_provider="off"))
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "N"}).json()["id"]
        assert client.post(f"/api/projects/{pid}/narratives").status_code == 503


def test_provider_resolution():
    import dataclasses

    from app.config import settings

    off = dataclasses.replace(settings, narrative_provider="off", anthropic_api_key="k")
    assert off.llm_provider is None and not off.llm_enabled
    api = dataclasses.replace(settings, narrative_provider="auto", anthropic_api_key="k")
    assert api.llm_provider == "api"
    forced = dataclasses.replace(settings, narrative_provider="agent-sdk", anthropic_api_key="k")
    assert forced.llm_provider in ("agent-sdk", None)  # depends on whether claude-agent-sdk is installed


class _Msg(SimpleNamespace):
    pass


def _fake_stream(text: str, subtype: str = "success", stop_reason: str = "end_turn"):
    async def gen(prompt, options):
        assert options.allowed_tools == [] and options.max_turns == 1 and options.setting_sources == []
        yield _Msg(content=[SimpleNamespace(text=text)])
        yield _Msg(subtype=subtype, duration_ms=10, result=text if subtype == "success" else None, stop_reason=stop_reason)
    return gen


def test_agent_sdk_provider_parses_the_stream(monkeypatch):
    pytest_skip_if_no_sdk()
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    monkeypatch.setattr(narrative, "_agent_query", _fake_stream("Occupancy held in the low nineties."))
    drafts = draft_all(data, provider="agent-sdk")
    assert len(drafts) == len(NARRATIVES) and all(t == "Occupancy held in the low nineties." for t in drafts.values())


def test_agent_sdk_provider_refusal_and_error(monkeypatch):
    pytest_skip_if_no_sdk()
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    monkeypatch.setattr(narrative, "_agent_query", _fake_stream("no", stop_reason="refusal"))
    assert draft_all(data, provider="agent-sdk") == {}
    monkeypatch.setattr(narrative, "_agent_query", _fake_stream("x", subtype="error_max_turns"))
    import pytest as _pytest
    with _pytest.raises(RuntimeError):
        draft_all(data, provider="agent-sdk")


def pytest_skip_if_no_sdk():
    import importlib.util

    import pytest as _pytest

    if importlib.util.find_spec("claude_agent_sdk") is None:
        _pytest.skip("claude-agent-sdk not installed")


LIVE = __import__("os").getenv("LLM_LIVE")


@__import__("pytest").mark.skipif(not LIVE, reason="set LLM_LIVE=1 to call the configured narrative provider for real")
def test_live_provider_drafts_from_section_values():
    from app.config import settings

    assert settings.llm_provider, "no provider configured (API key or claude-agent-sdk + Claude Code login)"
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    for path, _instruction, _sections, _limit in NARRATIVES[1:]:  # keep the live run to one field
        data.field(path).override = "already written"
    drafts = draft_all(data)
    assert list(drafts) == ["commentary.fields.takeaway"], drafts
    text = drafts["commentary.fields.takeaway"]
    assert 20 < len(text) < 1200 and "\u2014" not in text


# ---------- mock provider and draft staleness ----------
def _numbers(text: str) -> set[str]:
    import re

    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def _is_rounded_payload_number(token: str, payload_numbers: set[str]) -> bool:
    """A draft figure is supported when some payload value rounds to it at the draft's precision."""
    decimals = len(token.split(".")[1]) if "." in token else 0
    try:
        value = float(token)
    except ValueError:
        return False
    return any(round(float(p), decimals) == value for p in payload_numbers)


def test_mock_provider_resolves_and_drafts_only_from_supplied_values():
    import dataclasses
    import json

    from app.config import settings

    assert dataclasses.replace(settings, narrative_provider="mock").llm_provider == "mock"
    data, _ = build({"id": "p", "name": "P"}, sample_files())
    data.field("commentary.fields.takeaway").override = "Reviewer wrote this."
    drafts = draft_all(data, provider="mock")
    assert "commentary.fields.takeaway" not in drafts and len(drafts) == len(NARRATIVES) - 1
    body = drafts["commentary.fields.revenue_body"]
    assert "1,000" in body or "1000" in body  # total revenue from the structured values
    payload_numbers = set()
    for _path, _instr, sections, _n in NARRATIVES:
        payload_numbers |= _numbers(json.dumps({s: section_values(data, s) for s in sections}, default=str))
    for path, text in drafts.items():
        assert text and "—" not in text and all(_is_rounded_payload_number(n, payload_numbers) or len(n) <= 2 for n in _numbers(text)), (path, text)
        assert "0000000" not in text  # figures are rounded to a readable precision
    assert draft_all(data, provider="mock") == drafts  # deterministic


def test_drafts_carry_a_basis_and_go_stale_when_their_numbers_change():
    from app.consolidate.builder import apply_overrides
    from app.consolidate.calc import recompute
    from app.services.narrative import basis, stale_drafts

    data, _ = build({"id": "p", "name": "P"}, sample_files())
    b = basis(data, "occupancy.fields.occupancy_narrative")
    assert isinstance(b, str) and len(b) == 64 and b == basis(data, "occupancy.fields.occupancy_narrative")
    overrides = {"ai_drafts": {"occupancy.fields.occupancy_narrative": {"text": "Occupancy held.", "basis": b},
                               "capex.fields.narrative": "legacy plain-string draft"}}
    fresh, _ = build({"id": "p", "name": "P"}, sample_files())
    apply_overrides(fresh, overrides)
    recompute(fresh)
    assert fresh.value("occupancy.fields.occupancy_narrative") == "Occupancy held." and fresh.field("occupancy.fields.occupancy_narrative").status == "ai_draft"
    assert fresh.value("capex.fields.narrative") == "legacy plain-string draft"
    assert stale_drafts(fresh, overrides) == []
    changed, _ = build({"id": "p", "name": "P"}, sample_files())
    overrides2 = {**overrides, "fields": {"occupancy.fields.current_pct": 0.5}}
    apply_overrides(changed, overrides2)
    recompute(changed)
    assert stale_drafts(changed, overrides2) == ["occupancy.fields.occupancy_narrative"]
    redrafted = draft_all(changed, provider="mock", stale={"occupancy.fields.occupancy_narrative"})
    assert "occupancy.fields.occupancy_narrative" in redrafted and "capex.fields.narrative" not in redrafted  # only the stale one is replaced


def test_drafting_job_stores_basis_flags_staleness_and_never_overwrites_reviewer_text(monkeypatch, tmp_path):
    import dataclasses

    import app.config as cfg
    from app import db
    from app.workers import jobs
    from tests.test_api_report_data import upload_all

    monkeypatch.setattr(cfg, "settings", dataclasses.replace(cfg.settings, narrative_provider="mock"))
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "Mock"}).json()["id"]
        upload_all(client, pid, tmp_path)
        client.patch(f"/api/projects/{pid}/report-data", json={"changes": [{"path": "commentary.fields.takeaway", "value": "Reviewer text stays."}]})
        assert client.post(f"/api/projects/{pid}/narratives").status_code == 202
        assert jobs.pool.wait_idle(60)
        ui = client.get(f"/api/projects/{pid}/report-data").json()
        fields = {f["path"]: f for s in ui["sections"] for f in s["fields"]}
        assert fields["commentary.fields.takeaway"]["effective"] == "Reviewer text stays." and fields["commentary.fields.takeaway"]["status"] == "manual"
        draft = fields["occupancy.fields.occupancy_narrative"]
        assert draft["status"] == "ai_draft" and "Drafted by AI" in draft["source"]["text"] and draft["effective"]
        stored = db.get_report_data(pid)["overrides"]["ai_drafts"]["occupancy.fields.occupancy_narrative"]
        assert set(stored) == {"text", "basis"}
        # a change to a value the draft was written from flags it
        client.patch(f"/api/projects/{pid}/report-data", json={"changes": [{"path": "occupancy.fields.current_pct", "value": 0.5}]})
        ui = client.get(f"/api/projects/{pid}/report-data").json()
        assert any("predates a change" in i["message"] and i["path"] == "occupancy.fields.occupancy_narrative" for i in ui["issues"])
        fields = {f["path"]: f for s in ui["sections"] for f in s["fields"]}
        assert "predates" in (fields["occupancy.fields.occupancy_narrative"]["note"] or "")
        # a second run replaces only the stale draft
        old_capex = fields["capex.fields.narrative"]["effective"]
        assert client.post(f"/api/projects/{pid}/narratives").status_code == 202 and jobs.pool.wait_idle(60)
        ui = client.get(f"/api/projects/{pid}/report-data").json()
        assert not any("predates a change" in i["message"] for i in ui["issues"])
        fields = {f["path"]: f for s in ui["sections"] for f in s["fields"]}
        assert fields["capex.fields.narrative"]["effective"] == old_capex and "0.5" in fields["occupancy.fields.occupancy_narrative"]["effective"]
        html = client.get(f"/api/projects/{pid}/report/preview").text
        assert fields["occupancy.fields.occupancy_narrative"]["effective"][:40] in html
