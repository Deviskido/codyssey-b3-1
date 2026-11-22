#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements-automation.txt
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.lab/browsers"
.venv/bin/python -m playwright install chromium
if ! command -v dot >/dev/null; then
  brew install graphviz
fi
