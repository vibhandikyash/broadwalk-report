"""Settings read from environment variables (and a .env file if present)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


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
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
        break


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("APP_DATA_DIR", str(BACKEND_DIR / "data"))).resolve()
    workers: int = int(os.getenv("APP_WORKERS", "3"))
    max_upload_mb: int = int(os.getenv("APP_MAX_UPLOAD_MB", "50"))
    cors_origins: tuple[str, ...] = tuple(
        o.strip() for o in os.getenv("APP_CORS_ORIGINS", "http://localhost:4200").split(",") if o.strip()
    )
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")
    config_dir: Path = BACKEND_DIR / "config"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


settings = Settings()
