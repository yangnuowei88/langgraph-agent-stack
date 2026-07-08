#!/usr/bin/env bash
# README quickstart smoke test — COUPLED TO README.md BY DESIGN.
# If the documented quickstart commands change, update this script (and README) together.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

uv sync --extra anthropic
cp .env.example .env
export LLM_PROVIDER=mock

uv run uvicorn api.main:app --host 127.0.0.1 --port 8765 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:8765/health" >/dev/null; then
    break
  fi
  sleep 1
done

curl -sf -X POST "http://127.0.0.1:8765/run" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the latest advances in quantum computing?"}' \
  | grep -q executive_summary

curl -sf "http://127.0.0.1:8765/packs" | grep -q research_analysis

curl -sf -X POST "http://127.0.0.1:8765/packs/meeting_prep/run" \
  -H "Content-Type: application/json" \
  -d '{"company": "Acme", "person": "Jane", "meeting_goal": "discovery"}' \
  | grep -q talking_points

SSE_OUTPUT="$(curl -sfN -X POST "http://127.0.0.1:8765/run/stream" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the latest advances in quantum computing?"}' \
  --max-time 60 | head -5)"
echo "$SSE_OUTPUT" | grep -q '^data: '

docker compose -f infra/docker-compose.yml config >/dev/null

echo "readme-smoke: all quickstart checks passed"
