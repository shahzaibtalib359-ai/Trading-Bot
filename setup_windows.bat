@echo off
setlocal
cd /d "%~dp0"

echo.
echo === AI Trading Signal Windows Setup ===
echo.

python --version >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH.
    echo Install Python 3.12+ from https://www.python.org/downloads/windows/
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating project virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create .venv.
        exit /b 1
    )
) else (
    echo Project virtual environment already exists.
)

echo.
echo Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip.
    exit /b 1
)

echo.
echo Installing application dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed.
    echo If installation fails on Python 3.14, install Python 3.12 or 3.13 and recreate .venv.
    exit /b 1
)

echo.
echo Verifying required imports...
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, pydantic, PyQt6, requests; print('All required imports passed.')"
if errorlevel 1 (
    echo Import verification failed.
    exit /b 1
)

echo.
echo Setup complete.
echo.
echo Next commands:
echo   run_backend.bat
echo.
echo Then open a second CMD and run:
echo   run_desktop.bat
echo.
echo Or run both:
echo   run_all.bat
echo.

endlocal
