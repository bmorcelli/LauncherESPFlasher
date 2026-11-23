#!/bin/bash
# Runs inside the Docker build environment.
# Reads packaging/meta.env, builds the .deb, and writes it to dist/.
set -e

source packaging/meta.env

INSTALL_PREFIX="/usr/share/APPLaunch"
APP_INSTALL_DIR="$INSTALL_PREFIX/apps/$PKG_NAME"
STAGE=$(mktemp -d)

export STAGE INSTALL_PREFIX APP_INSTALL_DIR PKG_NAME PKG_VERSION

echo "==[ $PKG_NAME $PKG_VERSION-$PKG_REVISION (arm64) ]=="

echo "-- build.sh"
bash packaging/build.sh

echo "-- stage.sh"
bash packaging/stage.sh

# DEBIAN/control
mkdir -p "$STAGE/DEBIAN"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $PKG_VERSION-$PKG_REVISION
Architecture: arm64
Maintainer: bmorcelli <bmorcelli@users.noreply.github.com>
Description: $PKG_DESC
Depends: $PKG_DEPENDS
EOF

# .desktop entry
DESKTOP_DIR="$STAGE$INSTALL_PREFIX/applications"
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/$PKG_NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Exec=$APP_EXEC
Terminal=$APP_TERMINAL
Icon=$APP_ICON
EOF

# App icon
if [ -f "packaging/icon.png" ]; then
    ICON_TARGET="$STAGE$INSTALL_PREFIX/$APP_ICON"
    install -Dm644 "packaging/icon.png" "$ICON_TARGET"
fi

# Optional Debian hooks
for hook in postinst prerm; do
    if [ -f "packaging/$hook" ]; then
        cp "packaging/$hook" "$STAGE/DEBIAN/"
        chmod 755 "$STAGE/DEBIAN/$hook"
    fi
done

mkdir -p dist
DEB_FILE="dist/${PKG_NAME}_${PKG_VERSION}-${PKG_REVISION}_arm64.deb"
dpkg-deb --build --root-owner-group "$STAGE" "$DEB_FILE"
rm -rf "$STAGE"

echo "-- built: $DEB_FILE"
ls -lh "$DEB_FILE"
