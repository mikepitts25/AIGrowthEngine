#!/usr/bin/env bash
# Start AIGrowthEngine. Set ANTHROPIC_API_KEY first to enable AI generation.
cd "$(dirname "$0")"
exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"
