"""Cover photo and logo: uploaded through the API, embedded in the preview, frozen per report version."""
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.report.render import chromium_available
from app.workers.pool import pool
from tests.test_api_report_data import upload_all


def _png(color: tuple[int, int, int], size=(64, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def test_assets_are_embedded_and_frozen_per_version(tmp_path):
    with TestClient(app) as client:
        pid = client.post("/api/projects", json={"name": "Img"}).json()["id"]
        upload_all(client, pid, tmp_path)
        assert client.get(f"/api/projects/{pid}").json()["assets"] == {"cover": False, "logo": False}
        assert "data:image" not in client.get(f"/api/projects/{pid}/report/preview").text
        first = _png((10, 20, 200))
        r = client.put(f"/api/projects/{pid}/assets/cover", files={"file": ("photo.png", first, "image/png")})
        assert r.status_code == 200 and r.json() == {"cover": True, "logo": False}
        assert client.put(f"/api/projects/{pid}/assets/logo", files={"file": ("logo.png", _png((0, 0, 0), (32, 16)), "image/png")}).json()["logo"] is True
        assert client.put(f"/api/projects/{pid}/assets/cover", files={"file": ("notes.txt", b"hi", "text/plain")}).status_code == 422
        assert client.put(f"/api/projects/{pid}/assets/banner", files={"file": ("x.png", first, "image/png")}).status_code == 404
        assert client.get(f"/api/projects/{pid}/assets/cover").content == first
        html = client.get(f"/api/projects/{pid}/report/preview").text
        assert html.count("data:image/png;base64") >= 3  # cover on pages 1 and 2, logo in every header
        v1 = client.post(f"/api/projects/{pid}/reports").json()
        second = _png((200, 30, 30))
        client.put(f"/api/projects/{pid}/assets/cover", files={"file": ("photo2.png", second, "image/png")})
        v2 = client.post(f"/api/projects/{pid}/reports").json()
        assert pool.wait_idle(180)
        from app.config import settings

        out = settings.data_dir / "projects" / pid / "reports"
        assert (out / "report-v1-cover.png").read_bytes() == first and (out / "report-v2-cover.png").read_bytes() == second
        if chromium_available():
            import pdfplumber

            for v, expected in ((v1, first), (v2, second)):
                pdf = client.get(f"/api/projects/{pid}/reports/{v['id']}/download")
                assert pdf.status_code == 200
                with pdfplumber.open(io.BytesIO(pdf.content)) as doc:
                    assert len(doc.pages[0].images) >= 1 and len(doc.pages[1].images) >= 1, "cover photo on pages 1 and 2"
            with pdfplumber.open(io.BytesIO(client.get(f"/api/projects/{pid}/reports/{v1['id']}/download").content)) as d1, \
                 pdfplumber.open(io.BytesIO(client.get(f"/api/projects/{pid}/reports/{v2['id']}/download").content)) as d2:
                s1 = d1.pages[0].images[0]["stream"].get_data()
                s2 = d2.pages[0].images[0]["stream"].get_data()
                assert s1 != s2, "version 1 keeps its original image after the replacement"
        assert client.delete(f"/api/projects/{pid}/assets/cover").json() == {"cover": False, "logo": True}
        assert client.get(f"/api/projects/{pid}/assets/cover").status_code == 404
        assert client.get(f"/api/projects/{pid}/report/preview").text.count("data:image/png;base64") >= 1  # logo only
