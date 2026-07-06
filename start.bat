@echo off
REM The Arcanum launcher (Windows) — double-click to play.
cd /d "%~dp0"

REM Find a Python 3.11+ launcher: try the py launcher, then python, then python3.
set "PY="
for %%P in ("py -3" "python" "python3") do (
  %%~P -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "PY=%%~P"
    goto :run
  )
)

echo.
echo   Python 3.11 or newer was not found.
echo   Install it from https://www.python.org/downloads/
echo   ^(tick "Add Python to PATH" in the installer^), then run this again.
echo.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:run
echo   Lighting the candle... (close this window or press Ctrl+C to stop)
%PY% server.py
pause
