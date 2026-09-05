#!/usr/bin/env bash
# Every automated check, in one place. Run from the repository root after scripts/run.sh setup.
#   scripts/check.sh                 backend tests (with the dataset checks when TEST_DATASET_DIR is set), frontend tests,
#                                    production build, dependency audits, and a PDF structure check on the latest sample
#   scripts/check.sh --e2e           additionally runs the browser end-to-end test against the running app (UI_E2E_URL)
# Environment: TEST_DATASET_DIR (folder with the supplied source files), UI_E2E_URL (default http://localhost:4200)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYBIN="backend/.venv/bin/python"
status=0
if [ -n "${TEST_DATASET_DIR:-}" ] && [ -d "$TEST_DATASET_DIR" ]; then
  TEST_DATASET_DIR="$(cd "$TEST_DATASET_DIR" && pwd)"   # absolute, so it survives the cd into backend/
elif [ -n "${TEST_DATASET_DIR:-}" ]; then
  echo "TEST_DATASET_DIR '$TEST_DATASET_DIR' does not exist" >&2; exit 2
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
fi

step "Python dependency vulnerabilities"
$PYBIN -m pip_audit -r backend/requirements.lock || status=1

step "Angular unit tests"
(cd frontend && npx ng test --watch=false) || status=1

step "Angular production build"
(cd frontend && npx ng build) || status=1

step "npm dependency vulnerabilities"
(cd frontend && npm audit --audit-level=high) || status=1

if [ "${1:-}" = "--e2e" ]; then
  step "Browser end-to-end test"
  (cd backend && UI_E2E_URL="${UI_E2E_URL:-http://localhost:4200}" TEST_DATASET_DIR="${TEST_DATASET_DIR:-}" ../$PYBIN -m pytest -p no:cacheprovider tests/test_ui_e2e.py -v) || status=1
fi

SAMPLE="deliverables/boardwalk-2q26-investor-report.pdf"
if [ -f "$SAMPLE" ]; then
  step "PDF structure of the sample deliverable"
  $PYBIN scripts/check_pdf.py "$SAMPLE" || status=1
fi

step "Result"
if [ $status -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "SOME CHECKS FAILED"; fi
exit $status
