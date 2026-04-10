#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" == "Linux" ]]; then
  python3 scripts/build_desktop.py --target linux "$@"
else
  python3 scripts/build_linux_docker.py "$@"
fi
