#!/bin/bash
# Run from the project root (or anywhere — uses absolute paths).
# Requires Docker with linux/arm64 support.
# On Windows: run from Git Bash or WSL.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Building LauncherESPFlasher .deb package..."
echo "Project root: $PROJECT_ROOT"
echo ""

docker run --rm \
    --platform linux/arm64 \
    -v "$PROJECT_ROOT:/src" \
    -w /src \
    ghcr.io/cardputerzero/build-env:latest \
    bash scripts/pack-deb.sh

echo ""
echo "Done. Package ready in dist/:"
ls -lh "$PROJECT_ROOT/dist/"*.deb
