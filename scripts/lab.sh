#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.venv/bin:$PATH"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.lab/browsers"
exec python scripts/lab.py "$@"
