$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating Python virtual environment in .venv..."
    python -m venv .venv
}

Write-Host "Installing/updating Python dependencies..."
& $venvPython -m pip install -r requirements.txt

$env:ESPFLASHER_DEV = "1"

Write-Host "Starting LauncherESPFlasher in dev mode..."
& $venvPython src\main.py
