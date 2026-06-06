#!/bin/bash
# =============================================================================
# deploy_app.sh — canonical local app launcher (FOREGROUND).
#
# Starts the Flask app in the foreground using the project virtualenv so that
# process managers (Claude preview, supervisors, IDE run configs, etc.) can
# track the real server PID and stop it cleanly. This is the complement to
# restart_server.sh, which daemonizes the server with `&`.
#
# Why this exists: a bare `python -m src.app` resolves to the *system* python,
# which doesn't have the project's dependencies installed (ModuleNotFoundError:
# flask). This script always uses ./venv/bin/python.
#
# Usage:
#   bash scripts/deploy_app.sh [local|e2e|smoke]    # default: local
#
# Ports:  local=3001   e2e=3002   smoke=3003
# =============================================================================
set -euo pipefail

# Always run from the project root so relative paths + the venv resolve.
cd "$(dirname "${BASH_SOURCE[0]}")/.."

APP_ENV="${1:-local}"
export APP_ENV

# --- Pick the project virtualenv python (system python lacks dependencies) ---
PYTHON="python3"
if [[ -x "venv/bin/python" ]]; then
  PYTHON="venv/bin/python"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  PYTHON="${VIRTUAL_ENV}/bin/python"
fi

# --- Load local environment (DATABASE_URL_*, secrets) if available ---
if [[ -f ".envrc" ]]; then
  set +eu
  # shellcheck disable=SC1091
  source .envrc 2>/dev/null || true
  set -eu
fi

# --- Resolve DB + port per environment (mirrors restart_server.sh) ---
case "$APP_ENV" in
  e2e | uat)
    PORT="${PORT:-3002}"
    DATABASE_URL="${DATABASE_URL:-${DATABASE_URL_E2E:-sqlite:///loopcloser_e2e.db}}"
    export ENV="test"
    ;;
  smoke)
    PORT="${PORT:-3003}"
    DATABASE_URL="${DATABASE_URL:-${DATABASE_URL_SMOKE:-sqlite:///loopcloser_smoke.db}}"
    export ENV="test"
    ;;
  *) # local (default)
    PORT="${PORT:-3001}"
    DATABASE_URL="${DATABASE_URL:-${DATABASE_URL_LOCAL:-sqlite:///loopcloser_dev.db}}"
    ;;
esac
export PORT DATABASE_URL

# --- Reclaim the port if a previous server is still bound (clean restarts) ---
if command -v lsof >/dev/null 2>&1 && lsof -ti ":$PORT" >/dev/null 2>&1; then
  echo "Port $PORT in use — terminating existing process(es)..."
  lsof -ti ":$PORT" | xargs kill -9 2>/dev/null || true
  sleep 1
fi

echo "Starting LoopCloser ($APP_ENV) on port $PORT using $PYTHON"
echo "Database: ${DATABASE_URL%%://*}://…"

# exec replaces this shell with the python process, so SIGTERM from the process
# manager reaches the server directly and the tracked PID is the real server.
exec "$PYTHON" -m src.app
