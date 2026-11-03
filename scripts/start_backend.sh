#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
export AUTONOMUS_HOST=127.0.0.1
export AUTONOMUS_PORT="${AUTONOMUS_PORT:-8000}"
exec python3 -m app.cli serve
