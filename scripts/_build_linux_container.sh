#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="${LUXNEWS_CONTAINER_VENV_DIR:-/tmp/luxnews-linux-builder-venv}"

python -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -e ".[packaging]"
"$VENV_DIR/bin/python" -m luxnews.cli install-playwright
"$VENV_DIR/bin/python" scripts/build_desktop.py --target linux "$@"
