#!/usr/bin/env bash
# Clean-start helper for local evaluation.
#   scripts/run.sh setup        create the Python venv, install backend deps and Chromium, npm ci the frontend
#   scripts/run.sh start        start the backend (port from BACKEND_PORT / .env, default 8000) and the Angular dev server
#   scripts/run.sh reset-data   delete ONLY runtime data (uploads, SQLite database, generated reports); code and deps stay
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-python3}"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
PORT="${BACKEND_PORT:-8000}"
DATA_DIR="${APP_DATA_DIR:-backend/data}"

case "${1:-}" in
  setup)
    "$PY" -m venv backend/.venv
    backend/.venv/bin/python -m pip install -q --upgrade pip
    backend/.venv/bin/python -m pip install -q -r backend/requirements.lock
    backend/.venv/bin/python -m playwright install chromium
    backend/.venv/bin/python -m pip check
    (cd frontend && npm ci)
    [ -f .env ] || cp .env.example .env
    echo "Setup complete. Next: scripts/run.sh start"
    ;;
  start)
    echo "Backend on http://localhost:$PORT, frontend on http://localhost:4200 (Ctrl-C stops both)"
    (cd backend && exec .venv/bin/uvicorn app.main:app --port "$PORT") &
    BACK=$!
    trap 'kill $BACK 2>/dev/null || true' EXIT
    (cd frontend && BACKEND_PORT="$PORT" npm start)
    ;;
  reset-data)
    case "$DATA_DIR" in /*) TARGET="$DATA_DIR" ;; *) TARGET="$ROOT/$DATA_DIR" ;; esac
    echo "Removing runtime data in $TARGET (uploads, app.db, generated reports)"
    rm -rf "$TARGET"
    echo "Done. The next backend start recreates an empty database."
    ;;
  *)
    sed -n '2,5p' "$0"
    exit 1
    ;;
esac
