#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

echo "API  → http://127.0.0.1:8000"
echo "UI   → http://127.0.0.1:5173"
echo ""

.venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT

cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
