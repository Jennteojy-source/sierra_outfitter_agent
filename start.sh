#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing $1. Install it, then rerun ./start.sh" >&2
    exit 1
  }
}

need python3
need npm

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

if [[ ! -d frontend/node_modules ]]; then
  echo "Installing frontend dependencies…"
  (cd frontend && npm ci)
fi

echo "API  → http://127.0.0.1:8000"
echo "UI   → http://127.0.0.1:5173"
echo ""

.venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT

cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
