from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_status():
    with TestClient(app) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert set(body) >= {"ok", "llm_enabled", "ocr_enabled", "ocr_provider", "pdf_renderer", "workers"}
    assert body["ocr_enabled"] is False and body["ocr_provider"] is None


def test_the_app_fonts_are_served_from_the_report_font_directory():
    """The screen and the PDF share one set of font files; the app fetches them over /api/fonts."""
    from app.report.render import REPORT_DIR

    source = REPORT_DIR / "static" / "fonts" / "SourceSerif4-Semibold.ttf"
    with TestClient(app) as client:
        r = client.get("/api/fonts/SourceSerif4-Semibold.ttf")
        assert r.status_code == 200 and len(r.content) == source.stat().st_size
        assert client.get("/api/fonts/JetBrainsMono-Regular.ttf").status_code == 200
        assert client.get("/api/fonts/nope.ttf").status_code == 404
