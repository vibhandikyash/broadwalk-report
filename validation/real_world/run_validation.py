#!/usr/bin/env python3
"""Run and preserve real-world generalization evidence outside pytest."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BACKEND = REPO / "backend"
for candidate in (str(REPO), str(BACKEND)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", action="append", default=[], help="scenario id to run; repeat to select several")
    parser.add_argument("--output", type=Path, default=HERE / "results", help="directory for preserved evidence")
    parser.add_argument("--timeout", type=float, default=240, help="seconds to wait for each background stage")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ["APP_DATA_DIR"] = tempfile.mkdtemp(prefix="irg-real-world-")
    os.environ["APP_WORKERS"] = "3"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ["NARRATIVE_PROVIDER"] = "off"

    from fastapi.testclient import TestClient

    from app.main import app
    from validation.real_world.harness import discover_scenarios, run_many

    scenarios = discover_scenarios()
    if args.scenario:
        requested = set(args.scenario)
        scenarios = [scenario for scenario in scenarios if scenario.scenario_id in requested]
        missing = requested - {scenario.scenario_id for scenario in scenarios}
        if missing:
            print(f"Unknown scenario(s): {', '.join(sorted(missing))}", file=sys.stderr)
            return 2
    args.output.mkdir(parents=True, exist_ok=True)
    with TestClient(app) as client:
        results = run_many(client, scenarios, args.output, timeout=args.timeout)

    summary = {
        "passed": all(result["passed"] for result in results),
        "scenario_count": len(results),
        "passed_count": sum(result["passed"] for result in results),
        "failed_count": sum(not result["passed"] for result in results),
        "scenarios": [
            {
                "id": result["scenario"],
                "passed": result["passed"],
                "failures": result["failures"],
                "stage_after_report": result.get("stage_after_report"),
                "report_page_count": result.get("report", {}).get("page_count"),
            }
            for result in results
        ],
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    for item in summary["scenarios"]:
        status = "PASS" if item["passed"] else "FAIL"
        print(f"{status} {item['id']}")
        for failure in item["failures"]:
            print(f"  - {failure}")
    print(f"{summary['passed_count']}/{summary['scenario_count']} scenarios passed; evidence: {args.output}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
