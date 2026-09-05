"""Independent, multi-property generalization tests for the report workflow.

Structural scenarios must reproduce their expected gaps and warnings exactly; the complete scenario must reach
`complete` through the public correction, narrative and asset APIs and pass every page check. See
validation/real_world/README.md.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VALIDATION_ROOT = ROOT / "validation" / "real_world"
sys.path.insert(0, str(ROOT))

from validation.real_world.harness import Scenario, discover_scenarios, run_scenario, value_mismatch  # noqa: E402

EXPECTED_SCENARIOS = {"harbor_point_3q26": "structural", "pine_ridge_4q26": "structural", "lakeside_commons_1q27": "structural", "riverbend_station_4q25": "complete"}


@pytest.fixture
def mock_narratives(monkeypatch):
    """Scenarios draft through the deterministic mock provider; no key, network or login is involved."""
    import app.config as cfg

    monkeypatch.setattr(cfg, "settings", dataclasses.replace(cfg.settings, narrative_provider="mock"))


def test_real_world_validation_contract_exists() -> None:
    found = {s.scenario_id: s.classification for s in discover_scenarios()}
    assert found == EXPECTED_SCENARIOS
    assert (VALIDATION_ROOT / "harness.py").is_file() and (VALIDATION_ROOT / "pdf_checks.py").is_file()
    assert sum(1 for c in found.values() if c == "complete") >= 1, "at least one non-Boardwalk scenario must be complete"


def test_scenario_discovery_and_tolerance_comparison(tmp_path: Path) -> None:
    assert value_mismatch(0.9004, {"value": 0.9, "tolerance": 0.001}) is None
    assert value_mismatch(0.902, {"value": 0.9, "tolerance": 0.001}) is not None
    assert value_mismatch(None, {"value": None}) is None and value_mismatch(1, {"value": None}) is not None
    bad = tmp_path / "directory_name"
    bad.mkdir()
    (bad / "expected.json").write_text(json.dumps({"id": "different_name", "classification": "structural", "sources": [{"name": "x"}]}))
    with pytest.raises(ValueError, match="id must match"):
        discover_scenarios(tmp_path)
    (bad / "expected.json").write_text(json.dumps({"id": "directory_name", "classification": "partial", "sources": [{"name": "x"}]}))
    with pytest.raises(ValueError, match="classification"):
        discover_scenarios(tmp_path)


@pytest.mark.parametrize("scenario", discover_scenarios(), ids=lambda item: item.scenario_id)
def test_real_world_scenario_end_to_end(scenario, tmp_path: Path, mock_narratives) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        result = run_scenario(client, scenario, tmp_path, timeout=240)
    assert result["passed"], "\n".join(result["failures"])
    comp = result["completeness"]
    if scenario.classification == "complete":
        assert comp["complete"] is True and comp["gap_count"] == 0 and result["report"]["complete"] is True
        assert result["provenance"] and all(v["missing_unexpected"] == 0 for v in result["provenance"].values())
        assert result["drafted"] and result["report"]["images_per_page"][0] >= 1
    else:
        assert comp["complete"] is False and result["report"]["complete"] is False
        assert {g["path"] for g in comp["gaps"]} == set(scenario.manifest["expected_gaps"])


def test_conflict_scenario_is_stable_when_upload_order_is_reversed(tmp_path: Path, mock_narratives) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    original = next(s for s in discover_scenarios() if s.scenario_id == "lakeside_commons_1q27")
    reversed_manifest = {**original.manifest, "sources": list(reversed(original.manifest["sources"]))}
    with TestClient(app) as client:
        result = run_scenario(client, Scenario(original.scenario_id, original.directory, reversed_manifest), tmp_path, timeout=240)
    assert result["passed"], "\n".join(result["failures"])
