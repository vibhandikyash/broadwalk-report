"""Independent, multi-property generalization tests for the report workflow."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
VALIDATION_ROOT = ROOT / "validation" / "real_world"
sys.path.insert(0, str(ROOT))

from validation.real_world.harness import Scenario, discover_scenarios, run_scenario, value_mismatch  # noqa: E402


EXPECTED_SCENARIOS = {
    "harbor_point_3q26",
    "pine_ridge_4q26",
    "lakeside_commons_1q27",
}


def test_real_world_validation_contract_exists() -> None:
    scenario_root = VALIDATION_ROOT / "scenarios"
    found = {path.parent.name for path in scenario_root.glob("*/expected.json")}

    assert found == EXPECTED_SCENARIOS
    assert (VALIDATION_ROOT / "harness.py").is_file()


def test_scenario_discovery_and_tolerance_comparison(tmp_path: Path) -> None:
    assert {scenario.scenario_id for scenario in discover_scenarios()} == EXPECTED_SCENARIOS
    assert value_mismatch(0.9004, {"value": 0.9, "tolerance": 0.001}) is None
    assert value_mismatch(0.902, {"value": 0.9, "tolerance": 0.001}) is not None

    bad = tmp_path / "directory_name"
    bad.mkdir()
    (bad / "expected.json").write_text(json.dumps({"id": "different_name", "sources": [{"name": "x"}]}))
    with pytest.raises(ValueError, match="id must match"):
        discover_scenarios(tmp_path)


@pytest.mark.parametrize("scenario", discover_scenarios(), ids=lambda item: item.scenario_id)
def test_real_world_scenario_end_to_end(scenario, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        result = run_scenario(client, scenario, tmp_path, timeout=240)

    assert result["passed"], "\n".join(result["failures"])


def test_conflict_scenario_is_stable_when_upload_order_is_reversed(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    original = next(scenario for scenario in discover_scenarios() if scenario.scenario_id == "lakeside_commons_1q27")
    reversed_manifest = {**original.manifest, "sources": list(reversed(original.manifest["sources"]))}
    reversed_scenario = Scenario(original.scenario_id, original.directory, reversed_manifest)
    with TestClient(app) as client:
        result = run_scenario(client, reversed_scenario, tmp_path, timeout=240)

    assert result["passed"], "\n".join(result["failures"])
