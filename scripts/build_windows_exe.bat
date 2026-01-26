@echo off
setlocal
pyinstaller --onefile --clean --noconfirm --name luxnews_streamlit run_streamlit.py
endlocal
