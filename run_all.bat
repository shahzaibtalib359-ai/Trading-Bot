@echo off
cd /d "%~dp0"
title SS Traderz - Trading Signal Bot
echo ==========================================
echo  SS Traderz - Starting...
echo ==========================================

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Run setup_windows.bat first!
    pause
    exit /b 1
)

set TRADING_BACKEND_PORT=8012
set TRADING_API_BASE_URL=http://127.0.0.1:8012/api

echo [1/2] Starting Backend (Port 8012)...
start "SS Traderz Backend" cmd /k ".venv\Scripts\python.exe main.py backend"

echo [2/2] Waiting for backend to start...
timeout /t 5 /nobreak >nul

echo [3/3] Opening App...
".venv\Scripts\python.exe" main.py desktop

exit /b %errorlevel%
