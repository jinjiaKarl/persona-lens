#!/bin/bash
set -e

cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
  exit 0
}
trap cleanup INT TERM

uv run uvicorn persona_lens.api.server:app --reload --port 8000 &
BACKEND_PID=$!

cd frontend && npm run dev &
FRONTEND_PID=$!

wait
