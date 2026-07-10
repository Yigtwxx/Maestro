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
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating virtualenv..."
  python3 -m venv "$VENV"
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
( cd "$BACKEND" && exec "$VENV_PY" -m uvicorn app.main:app --reload --port "$BACKEND_PORT" ) &
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
