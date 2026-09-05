"""The reset-data helper must never delete anything that is not this application's data."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "scripts" / "run.sh"


def _reset(data_dir: Path, home: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "APP_DATA_DIR": str(data_dir), "HOME": str(home)}
    return subprocess.run(["bash", str(RUN), "reset-data"], capture_output=True, text=True, env=env, cwd=ROOT)


@pytest.mark.skipif(not RUN.exists(), reason="scripts/run.sh missing")
def test_reset_refuses_folders_that_are_not_application_data(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "photo.jpg").write_bytes(b"x")
    for target in (home, tmp_path / "docs"):
        target.mkdir(exist_ok=True)
        (target / "keep.txt").write_text("precious")
        r = _reset(target, home)
        assert r.returncode == 2 and "Refusing" in r.stderr, (target, r.stdout, r.stderr)
        assert (target / "keep.txt").exists()
    r = _reset(ROOT, home)
    assert r.returncode == 2 and (ROOT / "README.md").exists()
    r = _reset(Path("/"), home)
    assert r.returncode == 2


@pytest.mark.skipif(not RUN.exists(), reason="scripts/run.sh missing")
def test_reset_removes_only_known_runtime_entries(tmp_path):
    data = tmp_path / "data"
    (data / "projects" / "p1" / "uploads").mkdir(parents=True)
    (data / "projects" / "p1" / "uploads" / "a.xlsx").write_bytes(b"x")
    (data / "app.db").write_bytes(b"sqlite")
    (data / "app.db-wal").write_bytes(b"wal")
    (data / "notes.txt").write_text("not ours")
    r = _reset(data, tmp_path / "home")
    assert r.returncode == 0, r.stderr
    assert not (data / "projects").exists() and not (data / "app.db").exists() and not (data / "app.db-wal").exists()
    assert (data / "notes.txt").read_text() == "not ours"
    r = _reset(tmp_path / "missing", tmp_path / "home")
    assert r.returncode == 0 and "Nothing to reset" in r.stdout
