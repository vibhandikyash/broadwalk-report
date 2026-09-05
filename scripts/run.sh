#!/usr/bin/env bash
# Clean-start helper for local evaluation.
#   scripts/run.sh setup        create the Python venv, install backend deps and Chromium, npm ci the frontend
#   scripts/run.sh start        start the backend (port from BACKEND_PORT / .env, default 8000) and the Angular dev server
#   scripts/run.sh reset-data   delete ONLY this application's runtime data (projects/ uploads and reports, app.db); code and deps stay
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-python3}"
if [ -f .env ]; then  # .env fills in what the environment does not set, like the backend's own loader
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    key="${line%%=*}"; val="${line#*=}"
    key="$(printf '%s' "$key" | tr -d '[:space:]')"; val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
    case "$key" in *[!A-Za-z0-9_]*|'') continue ;; esac
    eval "current=\${$key:-}"
    [ -z "$current" ] && export "$key=$val"
  done < .env
fi
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
    TARGET="${TARGET%/}"
    [ -z "$TARGET" ] && TARGET="/"
    for bad in "/" "${HOME:-/nonexistent}" "$ROOT" "$ROOT/backend" "$ROOT/frontend" "$ROOT/backend/app"; do
      if [ "$TARGET" = "$bad" ]; then
        echo "Refusing to reset '$TARGET': that is not an application data folder" >&2
        exit 2
      fi
    done
    if [ ! -d "$TARGET" ]; then
      echo "Nothing to reset: $TARGET does not exist"
      exit 0
    fi
    if [ ! -e "$TARGET/app.db" ] && [ ! -d "$TARGET/projects" ]; then
      echo "Refusing to reset '$TARGET': it holds no app.db and no projects/ folder, so it does not look like this application's data" >&2
      exit 2
    fi
    echo "Removing runtime data in $TARGET: projects/ (uploads, images, generated reports) and app.db with its journal files"
    rm -rf "$TARGET/projects" "$TARGET/app.db" "$TARGET/app.db-wal" "$TARGET/app.db-shm"
    echo "Done. Other files in $TARGET were left alone; the next backend start recreates an empty database."
    ;;
  *)
    sed -n '2,5p' "$0"
    exit 1
    ;;
esac
