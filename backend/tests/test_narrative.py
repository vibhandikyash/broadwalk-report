# backend/tests/test_narrative.py
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.consolidate.builder import build
from app.main import app
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


def test_narratives_endpoint_requires_key():
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "N"}).json()["id"]
        assert client.post(f"/api/projects/{pid}/narratives").status_code == 503
