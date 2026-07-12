@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup_windows.bat first
    exit /b 1
)
set TRADING_BACKEND_PORT=8012
".venv\Scripts\python.exe" main.py backend
exit /b %errorlevel%
