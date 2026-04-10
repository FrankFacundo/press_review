#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -n "${LUXNEWS_PYTHON:-}" ]]; then
  PYTHON_BIN="$LUXNEWS_PYTHON"
elif [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "Could not find python3. Set LUXNEWS_PYTHON to the interpreter you want to use." >&2
  exit 1
fi

export LUXNEWS_BROWSER_AUTO_OPEN="${LUXNEWS_BROWSER_AUTO_OPEN:-1}"

exec "$PYTHON_BIN" "$REPO_ROOT/run_streamlit.py"
