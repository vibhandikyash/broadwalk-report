"""Project images (cover photo, logo): stored per project, copied per report version, embedded as data URIs."""
from __future__ import annotations

import base64
import shutil
from pathlib import Path

from .config import settings

KINDS = ("cover", "logo")
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
MAX_BYTES = 8 * 1024 * 1024


def asset_dir(project_id: str) -> Path:
    return settings.data_dir / "projects" / project_id / "assets"


def find(project_id: str, kind: str) -> Path | None:
    d = asset_dir(project_id)
    if not d.is_dir():
        return None
    return next((p for p in sorted(d.iterdir()) if p.stem == kind and p.suffix.lower() in IMAGE_TYPES), None)


def save(project_id: str, kind: str, suffix: str, content: bytes) -> Path:
    remove(project_id, kind)
    d = asset_dir(project_id)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{kind}{suffix.lower()}"
    path.write_bytes(content)
    return path


def remove(project_id: str, kind: str) -> None:
    p = find(project_id, kind)
    if p:
        p.unlink(missing_ok=True)


def present(project_id: str) -> dict[str, bool]:
    return {k: find(project_id, k) is not None for k in KINDS}


def data_uri(path: Path) -> str:
    mime = IMAGE_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def copy_for_version(project_id: str, out_dir: Path, version: int) -> None:
    """Freeze the current images next to the version so later replacements do not change an old PDF."""
    for k in KINDS:
        p = find(project_id, k)
        if p:
            shutil.copy(p, out_dir / f"report-v{version}-{k}{p.suffix.lower()}")


def version_assets(out_dir: Path, version: int) -> dict[str, str]:
    out = {}
    for k in KINDS:
        hit = next((p for p in sorted(out_dir.glob(f"report-v{version}-{k}.*")) if p.suffix.lower() in IMAGE_TYPES), None)
        if hit:
            out[k] = data_uri(hit)
    return out


def current_assets(project_id: str) -> dict[str, str]:
    return {k: data_uri(p) for k in KINDS if (p := find(project_id, k))}
