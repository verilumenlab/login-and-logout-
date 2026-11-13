#!/usr/bin/env bash
# ==============================================================================
# Enterprise Attendance Agent - macOS LaunchAgent Installer (Phase 15)
# Configures persistent background monitoring on user login with crash recovery.
# ==============================================================================

set -euo pipefail

LABEL="com.enterprise.attendance.agent"
PLIST_SRC="$(dirname "$0")/com.enterprise.attendance.agent.plist"
TARGET_DIR="${HOME}/Library/LaunchAgents"
TARGET_PLIST="${TARGET_DIR}/${LABEL}.plist"
LOG_DIR="/Users/Shared/EnterpriseAttendanceAgent"

echo "=========================================================="
echo " Enterprise Attendance Agent - macOS Installer"
echo "=========================================================="

# 1. Create Directories
mkdir -p "${TARGET_DIR}"
mkdir -p "${LOG_DIR}"
chmod 777 "${LOG_DIR}"

# 2. Copy LaunchAgent plist
echo "[1/3] Installing LaunchAgent plist..."
cp "${PLIST_SRC}" "${TARGET_PLIST}"
chmod 644 "${TARGET_PLIST}"

# 3. Load LaunchAgent
echo "[2/3] Registering service with launchd..."
# Unload previous instance if present
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
# Load new instance
launchctl bootstrap "gui/$(id -u)" "${TARGET_PLIST}"

# 4. Check status
echo "[3/3] Verifying agent launch status..."
sleep 1
if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    echo "  -> LaunchAgent successfully loaded and running."
else
    echo "  -> Note: Agent will launch automatically on next user login."
fi

echo ""
echo "Installation complete. Accessibility and Notification permissions will be requested on initial prompt."

