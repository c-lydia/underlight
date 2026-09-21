#!/bin/bash
set -e

BUILD_DIR="build"
BUILD_TYPE="${1:-Release}"

echo "Building msi-ec-daemon ($BUILD_TYPE)..."

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

cmake .. -DCMAKE_BUILD_TYPE="$BUILD_TYPE" \
    -DBUILD_DBUS=ON \
    -DBUILD_CLI=ON \
    -DBUILD_SYSTEMD=ON

make -j$(nproc)

echo "Build complete. Binaries in $BUILD_DIR/"
echo "  msi-ec-cli   - Command line tool"
echo "  msi-ec-daemon - DBus daemon (if DBus enabled)"