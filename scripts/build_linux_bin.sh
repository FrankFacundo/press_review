#!/usr/bin/env bash
set -euo pipefail
pyinstaller --onefile --clean --noconfirm --name luxnews_streamlit run_streamlit.py
