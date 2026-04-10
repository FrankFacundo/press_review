@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

if not defined LUXNEWS_BROWSER_AUTO_OPEN set "LUXNEWS_BROWSER_AUTO_OPEN=1"

if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
  "%REPO_ROOT%\.venv\Scripts\python.exe" "%REPO_ROOT%\run_streamlit.py"
) else (
  py -3 "%REPO_ROOT%\run_streamlit.py"
)

endlocal
