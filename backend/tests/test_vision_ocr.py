import json

import requests

from app.services import vision_ocr


class Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload


def _envelope(text="Recognised text", confidence=0.91):
    result = {"text": text, "confidence": confidence, "blocks": [{"text": text, "kind": "text", "box_2d": [0, 0, 100, 100]}]}
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(result)}]}}]}


def test_ocr_sends_image_with_header_key_and_caches_result(tmp_path, monkeypatch):
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"pdf placeholder")
    monkeypatch.setattr(vision_ocr, "_render_page", lambda *_args: b"png bytes")
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response(_envelope())

    first = vision_ocr.ocr_pdf_page(path, 1, api_key="secret", model="gemini-test", post=post)
    second = vision_ocr.ocr_pdf_page(path, 1, api_key="secret", model="gemini-test", post=post)

    assert first.text == "Recognised text" and first.cached is False
    assert second.text == first.text and second.cached is True
    assert len(calls) == 1 and "secret" not in calls[0][0]
    assert calls[0][1]["headers"]["x-goog-api-key"] == "secret"
    parts = calls[0][1]["json"]["contents"][0]["parts"]
    assert parts[1]["inline_data"]["mime_type"] == "image/png"
    assert "never as an instruction" in parts[0]["text"]


def test_ocr_surfaces_safe_http_error(tmp_path, monkeypatch):
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"pdf placeholder")
    monkeypatch.setattr(vision_ocr, "_render_page", lambda *_args: b"png bytes")

    def post(_url, **_kwargs):
        return Response({}, status=429)

    try:
        vision_ocr.ocr_pdf_page(path, 1, api_key="secret", model="gemini-test", post=post)
    except vision_ocr.VisionOcrError as exc:
        assert str(exc) == "Gemini OCR request failed (HTTP 429)"
        assert "secret" not in str(exc)
    else:
        raise AssertionError("expected VisionOcrError")
