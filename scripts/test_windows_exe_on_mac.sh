#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/LuxNews.exe" >&2
  exit 1
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This helper is intended to be run from macOS." >&2
  exit 1
fi

runner="$(command -v wine64 || command -v wine || true)"
if [[ -z "$runner" ]]; then
  echo "Wine is not installed. Use Wine/CrossOver, or test the .exe in a Windows VM such as UTM or Parallels." >&2
  exit 1
fi

exe_path="$1"
if [[ ! -f "$exe_path" ]]; then
  echo "Windows executable not found: $exe_path" >&2
  exit 1
fi

LUXNEWS_BROWSER_AUTO_OPEN=0 "$runner" "$exe_path"
