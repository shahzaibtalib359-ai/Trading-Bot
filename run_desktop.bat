@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup_windows.bat first
    exit /b 1
)
set TRADING_BACKEND_PORT=8012
set TRADING_API_BASE_URL=http://127.0.0.1:8012/api
".venv\Scripts\python.exe" main.py desktop
exit /b %errorlevel%
