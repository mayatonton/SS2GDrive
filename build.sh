#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
flatpak-builder --user --install --force-clean build-dir flatpak/com.ss2gd.SS2GDrive.json
echo "Run: flatpak run com.ss2gd.SS2GDrive tray --window"
