#!/usr/bin/env bash
# ==============================================================================
# Enterprise Attendance Agent - DMG Packaging Script (Phase 15)
# Packages signed & notarized .app bundle into an enterprise distributable DMG.
# ==============================================================================

set -euo pipefail

APP_PATH="${1:-target/release/bundle/macos/EnterpriseAttendanceAgent.app}"
OUTPUT_DMG="${2:-target/release/bundle/dmg/EnterpriseAttendanceAgent-0.1.0.dmg}"
VOLUME_NAME="Enterprise Attendance Agent"

mkdir -p "$(dirname "${OUTPUT_DMG}")"
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "${TEMP_DIR}"' EXIT

echo "Packaging DMG for ${APP_PATH} -> ${OUTPUT_DMG}..."

# Copy app bundle to staging directory
cp -R "${APP_PATH}" "${TEMP_DIR}/"

# Create symlink to Applications directory
ln -s /Applications "${TEMP_DIR}/Applications"

# Build DMG using hdiutil
hdiutil create -volname "${VOLUME_NAME}" \
    -srcfolder "${TEMP_DIR}" \
    -ov -format UDZO \
    "${OUTPUT_DMG}"

echo "DMG successfully created: ${OUTPUT_DMG}"

