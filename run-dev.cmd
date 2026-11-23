@echo off
setlocal

cd /d "%~dp0"

set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo Creating Python virtual environment in .venv...
    python -m venv .venv
    if errorlevel 1 exit /b %errorlevel%
)

echo Installing/updating Python dependencies...
"%VENV_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 exit /b %errorlevel%

set "ESPFLASHER_DEV=1"

echo Starting LauncherESPFlasher in dev mode...
"%VENV_PYTHON%" src\main.py
exit /b %errorlevel%
