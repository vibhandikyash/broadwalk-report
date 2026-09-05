#!/usr/bin/env bash
# Every automated check, in one place. Run from the repository root after scripts/run.sh setup.
#   scripts/check.sh                 backend tests, dataset checks (needs TEST_DATASET_DIR), frontend tests, production build,
#                                    dependency audits, and a PDF structure and raster check on the sample deliverable
#   scripts/check.sh --e2e           additionally the browser end-to-end test against the running app (needs UI_E2E_URL and TEST_DATASET_DIR)
# Environment: TEST_DATASET_DIR (the folder holding ONLY the source files), UI_E2E_URL (for example http://localhost:4200)
# Exit code 0 only when every check that ran passed; steps that were skipped are named in the final line.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYBIN="backend/.venv/bin/python"
status=0
skipped=""
E2E=0
[ "${1:-}" = "--e2e" ] && E2E=1
if [ -n "${TEST_DATASET_DIR:-}" ] && [ -d "$TEST_DATASET_DIR" ]; then
  TEST_DATASET_DIR="$(cd "$TEST_DATASET_DIR" && pwd)"   # absolute, so it survives the cd into backend/
elif [ -n "${TEST_DATASET_DIR:-}" ]; then
  echo "TEST_DATASET_DIR '$TEST_DATASET_DIR' does not exist" >&2; exit 2
fi
if [ $E2E = 1 ] && { [ -z "${TEST_DATASET_DIR:-}" ] || [ -z "${UI_E2E_URL:-}" ]; }; then
  echo "--e2e needs both TEST_DATASET_DIR and UI_E2E_URL" >&2; exit 2
fi
step() { printf '\n==> %s\n' "$*"; }

step "Python static check (compileall)"
$PYBIN -m compileall -q backend/app backend/tests

step "Backend unit and API tests"
(cd backend && env -u TEST_DATASET_DIR -u UI_E2E_URL ../$PYBIN -m pytest -p no:cacheprovider) || status=1

if [ -n "${TEST_DATASET_DIR:-}" ]; then
  step "Supplied and mutated dataset tests"
  (cd backend && TEST_DATASET_DIR="$TEST_DATASET_DIR" ../$PYBIN -m pytest -p no:cacheprovider tests/test_dataset.py -v) || status=1
else
  echo "TEST_DATASET_DIR not set: dataset tests skipped"
  skipped="$skipped dataset-tests"
fi

step "Python dependency vulnerabilities"
$PYBIN -m pip_audit -r backend/requirements.lock || status=1

step "Angular unit tests"
(cd frontend && npx ng test --watch=false) || status=1

step "Angular production build"
(cd frontend && npx ng build) || status=1

step "npm dependency vulnerabilities"
(cd frontend && npm audit --audit-level=high) || status=1

if [ $E2E = 1 ]; then
  step "Browser end-to-end test"
  (cd backend && UI_E2E_URL="$UI_E2E_URL" TEST_DATASET_DIR="$TEST_DATASET_DIR" ../$PYBIN -m pytest -p no:cacheprovider tests/test_ui_e2e.py -v) || status=1
else
  skipped="$skipped browser-e2e"
fi

SAMPLE="deliverables/boardwalk-2q26-investor-report.pdf"
if [ -f "$SAMPLE" ]; then
  step "PDF structure and raster check of the sample deliverable"
  $PYBIN scripts/check_pdf.py "$SAMPLE" --expect "Fannie Mae" || status=1
else
  skipped="$skipped sample-pdf"
fi

step "Result"
if [ $status -eq 0 ]; then
  if [ -n "$skipped" ]; then echo "ALL CHECKS THAT RAN PASSED; skipped:$skipped"; else echo "ALL CHECKS PASSED"; fi
else
  echo "SOME CHECKS FAILED"
fi
exit $status
