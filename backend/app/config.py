"""Settings read from environment variables (and a .env file if present)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


def _value(raw: str) -> str:
    """The value part of a .env line, without the trailing comment people copy from .env.example.

    'auto   # auto | api | off' -> 'auto'. A '#' that is not preceded by whitespace belongs to the
    value (an API key may contain one), and a quoted value keeps everything inside the quotes.
    """
    val = raw.strip()
    if val[:1] in ("'", '"'):
        end = val.find(val[0], 1)
        return val[1:end] if end > 0 else val[1:]
    return re.split(r"\s+#", val, maxsplit=1)[0].strip()


def _load_dotenv() -> None:
    """Minimal .env loader: KEY=VALUE lines, existing env vars win."""
    for candidate in (Path.cwd() / ".env", BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), _value(val))
        break


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    # A relative APP_DATA_DIR is taken from the repository root (the folder holding backend/ and frontend/),
    # so 'backend/data' means the same thing whether uvicorn starts from the root or from backend/.
    data_dir: Path = (REPO_DIR / os.getenv("APP_DATA_DIR", "backend/data")).resolve()
    workers: int = int(os.getenv("APP_WORKERS", "3"))
    max_upload_mb: int = int(os.getenv("APP_MAX_UPLOAD_MB", "50"))
    cors_origins: tuple[str, ...] = tuple(
        o.strip() for o in os.getenv("APP_CORS_ORIGINS", "http://localhost:4200").split(",") if o.strip()
    )
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    anthropic_model: str | None = os.getenv("ANTHROPIC_MODEL") or None
    narrative_provider: str = os.getenv("NARRATIVE_PROVIDER", "auto").strip().lower()
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    ocr_dpi: int = int(os.getenv("OCR_DPI", "200"))
    ocr_timeout_seconds: int = int(os.getenv("OCR_TIMEOUT_SECONDS", "60"))
    ocr_min_text_chars: int = int(os.getenv("OCR_MIN_TEXT_CHARS", "20"))
    config_dir: Path = BACKEND_DIR / "config"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def llm_provider(self) -> str | None:
        """'api' (Anthropic SDK with ANTHROPIC_API_KEY), 'agent-sdk' (Claude Agent SDK using the local
        Claude Code login), or None. NARRATIVE_PROVIDER=auto prefers the API key when one is set."""
        want = self.narrative_provider
        if want in ("off", "none", "false", "0"):
            return None
        if want == "mock":  # deterministic drafts from the structured values only; for tests and offline demos
            return "mock"
        if want in ("auto", "api") and self.anthropic_api_key:
            return "api"
        if want in ("auto", "agent-sdk", "agent_sdk", "agent"):
            import importlib.util

            if importlib.util.find_spec("claude_agent_sdk") is not None:
                return "agent-sdk"
        return None

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider is not None

    @property
    def ocr_enabled(self) -> bool:
        return bool(self.gemini_api_key)


settings = Settings()
