#!/usr/bin/env bash
# ==============================================================================
# Enterprise Attendance Agent - macOS Code Signing & Notarization (Phase 15)
# Signs bundle with Apple Developer ID, submits to Apple notary service, and staples.
# ==============================================================================

set -euo pipefail

APP_PATH="${1:-target/release/bundle/macos/EnterpriseAttendanceAgent.app}"
SIGNING_IDENTITY="${APPLE_SIGNING_IDENTITY:-Developer ID Application: Enterprise Solutions Inc (TEAMID)}"
ENTITLEMENTS="src-tauri/entitlements.plist"

echo "=========================================================="
echo " macOS Code Signing & Apple Notarization Pipeline"
echo " Target: ${APP_PATH}"
echo "=========================================================="

if [ ! -d "${APP_PATH}" ]; then
    echo "Error: Application bundle not found at '${APP_PATH}'"
    exit 1
fi

# 1. Sign internal frameworks, libraries, and binaries
echo "[1/4] Signing embedded dylibs and frameworks with Hardened Runtime..."
find "${APP_PATH}/Contents/Frameworks" -type f \( -name "*.dylib" -o -name "*.framework" \) -exec \
    codesign --force --timestamp --options runtime --sign "${SIGNING_IDENTITY}" {} + 2>/dev/null || true

# 2. Deep sign main application bundle with entitlements
echo "[2/4] Signing main application bundle..."
codesign --force --deep --timestamp --options runtime \
    --entitlements "${ENTITLEMENTS}" \
    --sign "${SIGNING_IDENTITY}" \
    "${APP_PATH}"

# Verify signature
echo "[3/4] Verifying code signature..."
codesign --verify --deep --strict --verbose=2 "${APP_PATH}"

# 3. Notarize with Apple notarytool if credentials are provided in CI
if [ -n "${APPLE_API_KEY:-}" ] && [ -n "${APPLE_API_ISSUER:-}" ]; then
    echo "[4/4] Submitting to Apple Notary Service..."
    ZIP_PATH="${APP_PATH}.zip"
    ditto -c -k --keepParent "${APP_PATH}" "${ZIP_PATH}"
    
    xcrun notarytool submit "${ZIP_PATH}" \
        --key "${APPLE_API_KEY}" \
        --key-id "${APPLE_KEY_ID}" \
        --issuer "${APPLE_API_ISSUER}" \
        --wait

    echo "Stapling notarization ticket to application bundle..."
    xcrun stapler staple "${APP_PATH}"
    spctl -a -vvv -t install "${APP_PATH}"
    echo "Application bundle notarized and stapled successfully."
else
    echo "Notice: APPLE_API_KEY not set. Skipping live Apple Notarization submission."
fi

