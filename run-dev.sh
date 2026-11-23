#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "Python was not found. Install Python 3 and try again." >&2
    exit 1
fi

VENV_PYTHON=".venv/bin/python"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "Creating Python virtual environment in .venv..."
    "$PYTHON" -m venv .venv
fi

echo "Installing/updating Python dependencies..."
"$VENV_PYTHON" -m pip install -r requirements.txt

echo "Starting LauncherESPFlasher in dev mode..."
ESPFLASHER_DEV=1 "$VENV_PYTHON" src/main.py
