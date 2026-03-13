@echo off
setlocal
py -3 scripts\build_desktop.py --target windows %*
endlocal
