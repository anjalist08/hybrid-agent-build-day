#!/usr/bin/env bash
# Start the Lens backend on all interfaces so the phone can reach it.
set -euo pipefail
cd "$(dirname "$0")"
set -a; [ -f .env ] && . ./.env; set +a
case "${1:-}" in
  --fake) export LENS_FAKE_MODE=true ;;
  "") ;;
  *) echo "Usage: $0 [--fake]" >&2; exit 2 ;;
esac
exec uv run uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
