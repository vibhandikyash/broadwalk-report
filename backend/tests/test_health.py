from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_status():
    with TestClient(app) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert set(body) >= {"ok", "llm_enabled", "pdf_renderer", "workers"}
