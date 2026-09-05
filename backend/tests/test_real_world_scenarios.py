"""Independent, multi-property generalization tests for the report workflow."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATION_ROOT = ROOT / "validation" / "real_world"
EXPECTED_SCENARIOS = {
    "harbor_point_3q26",
    "pine_ridge_4q26",
    "lakeside_commons_1q27",
}


def test_real_world_validation_contract_exists() -> None:
    scenario_root = VALIDATION_ROOT / "scenarios"
    found = {path.name for path in scenario_root.glob("*/expected.json")}

    assert found == EXPECTED_SCENARIOS
    assert (VALIDATION_ROOT / "harness.py").is_file()

