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
