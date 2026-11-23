#!/bin/bash
set -e
mkdir -p "$STAGE$APP_INSTALL_DIR"
cp -r src/* "$STAGE$APP_INSTALL_DIR/"
if [ -d assets ]; then
    cp -r assets/ "$STAGE$APP_INSTALL_DIR/"
fi
