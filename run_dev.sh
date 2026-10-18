#!/usr/bin/env bash
# One-command local startup for AccountFlow AI.
#   ./run_dev.sh            install deps (first run), start API :8000 + UI :5173
#   ./run_dev.sh --test     also run the backend end-to-end test flow first
#   ./run_dev.sh --reset    wipe and reseed the SQLite demo database
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
RUN_TESTS=false
RESET=false
for arg in "$@"; do
  case "$arg" in
    --test) RUN_TESTS=true ;;
    --reset) RESET=true ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

info() { printf '\033[1;34m▶ %s\033[0m\n' "$*"; }

# ── Python virtualenv ────────────────────────────────────────────────────────
if [ -x "$BACKEND/.venv/Scripts/python.exe" ]; then
  PY="$BACKEND/.venv/Scripts/python.exe"          # Windows (Git Bash)
elif [ -x "$BACKEND/.venv/bin/python" ]; then
  PY="$BACKEND/.venv/bin/python"                  # macOS / Linux
else
  info "Creating Python virtualenv"
  if command -v uv >/dev/null 2>&1; then
    uv venv "$BACKEND/.venv" --python 3.12 -q || uv venv "$BACKEND/.venv" -q
  else
    PYTHON_BIN="$(command -v python3 || command -v python)"
    "$PYTHON_BIN" -m venv "$BACKEND/.venv"
  fi
  if [ -x "$BACKEND/.venv/Scripts/python.exe" ]; then PY="$BACKEND/.venv/Scripts/python.exe"; else PY="$BACKEND/.venv/bin/python"; fi
fi

if ! "$PY" -c "import fastapi, pandas, PIL, apscheduler" >/dev/null 2>&1; then
  info "Installing backend dependencies"
  if command -v uv >/dev/null 2>&1; then
    uv pip install -q --python "$PY" -r "$BACKEND/requirements.txt"
  else
    "$PY" -m pip install -q -r "$BACKEND/requirements.txt"
  fi
fi

# ── Frontend deps ────────────────────────────────────────────────────────────
if [ ! -d "$FRONTEND/node_modules" ]; then
  info "Installing frontend dependencies"
  (cd "$FRONTEND" && npm install --no-audit --no-fund)
fi

if $RESET; then
  info "Resetting demo database"
  (cd "$BACKEND" && "$PY" seed.py --reset)
fi

if $RUN_TESTS; then
  info "Running backend end-to-end checks (test_flow.py)"
  (cd "$BACKEND" && PYTHONIOENCODING=utf-8 "$PY" test_flow.py | grep -v " INFO ")
fi

# ── Start servers ────────────────────────────────────────────────────────────
PIDS=()
cleanup() {
  echo
  info "Stopping servers"
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

info "Starting FastAPI on http://localhost:8000"
(cd "$BACKEND" && "$PY" -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload) &
PIDS+=($!)

info "Starting Vite on http://localhost:5173"
(cd "$FRONTEND" && npm run dev -- --host 127.0.0.1) &
PIDS+=($!)

sleep 4
cat <<EOF

  ┌──────────────────────────────────────────────────────────┐
  │  AccountFlow AI is running                               │
  │    Clerk dashboard  →  http://localhost:5173             │
  │    API + Swagger    →  http://localhost:8000/docs        │
  │  Press Ctrl+C to stop both servers.                      │
  └──────────────────────────────────────────────────────────┘

EOF
wait
