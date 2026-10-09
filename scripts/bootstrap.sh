#!/usr/bin/env bash
# APEX ONE bootstrap (macOS + Linux). Safe to re-run. Downloads only Python packages and (if missing) Chromium.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3.13 python3.12 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)'; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] || { echo "Python 3.12+ is required (macOS: brew install python@3.12)"; exit 1; }
echo "Using $($PY --version)"

if command -v uv >/dev/null 2>&1; then
  uv venv .venv --python "$PY" -q
  # shellcheck disable=SC1091
  source .venv/bin/activate
  uv pip install -q -e ".[dev]"
else
  "$PY" -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q --upgrade pip
  pip install -q -e ".[dev]"
fi

if ! python -c 'from apex_one.compute.hardware import find_chromium; import sys; sys.exit(0 if find_chromium() else 1)'; then
  echo "Installing Chromium for Playwright (~150 MB, one time)…"
  python -m playwright install chromium
fi

[ -f .env ] || cp .env.example .env
mkdir -p var artifacts
apex-one db-upgrade
apex-one doctor
echo
echo "Next: apex-one benchmark --suite golden --quality ultra"
