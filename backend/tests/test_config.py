"""The .env loader, and the promise that every variable .env.example advertises is actually read."""
from __future__ import annotations

import re
from pathlib import Path

from app.config import BACKEND_DIR, REPO_DIR, _value

EXAMPLE = REPO_DIR / ".env.example"
# BACKEND_PORT is for the launcher and the Angular dev proxy, not for the Python settings.
NOT_IN_SETTINGS = {"BACKEND_PORT"}


def example_keys() -> list[str]:
    text = EXAMPLE.read_text(encoding="utf-8")
    return re.findall(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=", text, re.M)


def test_every_documented_variable_is_read_somewhere():
    config = (BACKEND_DIR / "app" / "config.py").read_text(encoding="utf-8")
    proxy = (REPO_DIR / "frontend" / "proxy.conf.js").read_text(encoding="utf-8")
    run = (REPO_DIR / "scripts" / "run.sh").read_text(encoding="utf-8")
    keys = example_keys()
    assert keys, "the example should document the settings"
    for key in keys:
        if key in NOT_IN_SETTINGS:
            assert key in proxy and key in run, key
        else:
            assert f'"{key}"' in config, f"{key} is documented in .env.example but never read"


def test_a_trailing_comment_is_not_part_of_the_value():
    """.env.example writes 'auto   # auto | api | off'; uncommenting that verbatim must still mean 'auto'."""
    assert _value("auto   # auto | api | agent-sdk | off") == "auto"
    assert _value("3   # parallel workers") == "3"
    assert _value("  spaced  ") == "spaced"


def test_a_hash_inside_a_value_is_kept():
    """Only whitespace then '#' starts a comment, so a secret containing '#' survives."""
    assert _value("sk-ant-a#b") == "sk-ant-a#b"
    assert _value('"quoted # value"') == "quoted # value"
    assert _value("'single # value'") == "single # value"


def test_the_example_parses_into_the_values_it_documents(tmp_path: Path):
    """Copying .env.example to .env and uncommenting it yields the defaults the file claims."""
    lines = [ln.lstrip("# ").rstrip() for ln in EXAMPLE.read_text(encoding="utf-8").splitlines()
             if re.match(r"^\s*#?\s*[A-Z][A-Z0-9_]*\s*=", ln)]
    parsed = {ln.split("=", 1)[0].strip(): _value(ln.split("=", 1)[1]) for ln in lines}
    assert parsed["NARRATIVE_PROVIDER"] == "auto"
    assert parsed["APP_WORKERS"] == "3" and int(parsed["APP_MAX_UPLOAD_MB"]) == 50
    assert parsed["GEMINI_MODEL"] == "gemini-2.5-flash"
    assert parsed["GEMINI_API_KEY"] == ""  # unset means OCR stays off
    for key in ("APP_WORKERS", "APP_MAX_UPLOAD_MB", "OCR_DPI", "OCR_TIMEOUT_SECONDS", "OCR_MIN_TEXT_CHARS"):
        int(parsed[key])  # every numeric setting survives the loader as an int
