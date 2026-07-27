#!/usr/bin/env bash
#
# Start the full Maestro dev stack on macOS/Linux: infra (Docker), backend
# (FastAPI/uvicorn) and frontend (Next.js). Backend and frontend run together;
# Ctrl-C stops both.
#
# Usage:
#   ./scripts/dev.sh
#   ./scripts/dev.sh --skip-infra
#   ./scripts/dev.sh --skip-seed
#   BACKEND_PORT=8001 FRONTEND_PORT=3001 ./scripts/dev.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/frontend"

SKIP_INFRA=0
SKIP_SEED=0
for arg in "$@"; do
  case "$arg" in
    --skip-infra) SKIP_INFRA=1 ;;
    --skip-seed) SKIP_SEED=1 ;;
  esac
done
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

step() { printf '\n==> %s\n' "$1"; }

free_port() {
  local port="$1" pids
  pids="$(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null || true)"
  [ -z "$pids" ] && return 0
  echo "WARN: port $port is in use (PID(s): $pids); killing."
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true
  sleep 0.5
  pids="$(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null || true)"
  # shellcheck disable=SC2086
  [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
}

# --- 1. Infra (Docker) ----------------------------------------------------
if [ "$SKIP_INFRA" -eq 0 ]; then
  if command -v docker >/dev/null 2>&1; then
    step "Starting infra (Postgres, MongoDB, Qdrant) via docker-compose"
    (cd "$REPO_ROOT" && docker compose up -d) || echo "WARN: docker compose failed"
  else
    echo "WARN: Docker not found; skipping infra (pass --skip-infra to silence)."
  fi
fi

# --- 2. Backend -----------------------------------------------------------
step "Preparing backend"
VENV="$BACKEND/.venv"

# Backend requires Python >=3.11 (see CLAUDE.md). Pick the newest available
# interpreter; a venv built on an older python silently fails to resolve pins
# such as alembic>=1.17, which need >=3.10.
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  # Fall back to python3 only if it is >=3.11.
  if command -v python3 >/dev/null 2>&1 && \
     python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    PYTHON_BIN="python3"
  else
    echo "ERROR: Python >=3.11 is required but was not found." >&2
    echo "       Install it (e.g. 'brew install python@3.11') and re-run." >&2
    exit 1
  fi
fi

# Recreate the venv if it is missing or was built on an interpreter <3.11.
if [ -x "$VENV/bin/python" ] && \
   ! "$VENV/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Existing virtualenv uses an unsupported Python; recreating with $PYTHON_BIN..."
  rm -rf "$VENV"
fi
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating virtualenv with $PYTHON_BIN ($($PYTHON_BIN --version 2>&1))..."
  "$PYTHON_BIN" -m venv "$VENV"
fi
VENV_PY="$VENV/bin/python"

if [ ! -f "$BACKEND/.env" ]; then
  cp "$REPO_ROOT/.env.example" "$BACKEND/.env"
  echo "WARN: created backend/.env from .env.example — set real secrets before production."
fi

echo "Installing backend dependencies..."
"$VENV_PY" -m pip install --disable-pip-version-check -q -r "$BACKEND/requirements.txt"

echo "Running database migrations (alembic upgrade head)..."
( cd "$BACKEND" && "$VENV_PY" -m alembic upgrade head ) \
  || echo "WARN: alembic migration failed (is Postgres up?)"

if [ "$SKIP_SEED" -eq 0 ]; then
  echo "Seeding featured marketplace teams (idempotent)..."
  # Seeding is cosmetic: a missing Mongo must not stop the dev stack coming up.
  ( cd "$BACKEND" && "$VENV_PY" -m app.scripts.seed_marketplace ) \
    || echo "WARN: marketplace seed failed (is MongoDB up?)"
fi

# --- 3. Frontend ----------------------------------------------------------
step "Preparing frontend"
if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "Installing frontend dependencies..."
  (cd "$FRONTEND" && npm install)
fi
if [ ! -f "$FRONTEND/.env.local" ]; then
  cp "$FRONTEND/.env.local.example" "$FRONTEND/.env.local"
fi

# --- 4. Launch both, stop both on exit ------------------------------------
PIDS=()
cleanup() {
  step "Shutting down..."
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

free_port "$BACKEND_PORT"
step "Launching backend on http://localhost:$BACKEND_PORT"
# --reload-dir app restricts the watcher to the source package. Without it
# uvicorn watches the whole CWD including .venv, and touched site-package files
# (e.g. numpy) trigger an endless reload loop that drops in-flight requests.
( cd "$BACKEND" && exec "$VENV_PY" -m uvicorn app.main:app --reload --reload-dir app --port "$BACKEND_PORT" ) &
PIDS+=("$!")

free_port "$FRONTEND_PORT"
step "Launching frontend on http://localhost:$FRONTEND_PORT"
( cd "$FRONTEND" && exec npm run dev -- --port "$FRONTEND_PORT" ) &
PIDS+=("$!")

printf '\nMaestro is running:\n'
printf '  Backend : http://localhost:%s  (docs: /docs)\n' "$BACKEND_PORT"
printf '  Frontend: http://localhost:%s\n' "$FRONTEND_PORT"
printf 'Press Ctrl-C to stop both.\n'

wait
