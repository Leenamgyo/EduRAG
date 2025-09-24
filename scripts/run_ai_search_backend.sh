#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/ai-search"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

uv run uvicorn ai_search.service.api:app --host "$HOST" --port "$PORT" "$@"
