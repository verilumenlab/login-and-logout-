#!/usr/bin/env bash
# ==============================================================================
# Enterprise Attendance Agent - macOS Uninstaller (Phase 15)
# Unloads LaunchAgent, cleans logs, and removes application components.
# ==============================================================================

set -euo pipefail

LABEL="com.enterprise.attendance.agent"
TARGET_PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
APP_DIR="/Applications/EnterpriseAttendanceAgent.app"
DATA_DIR="${HOME}/Library/Application Support/com.enterprise.attendance.agent"
LOG_DIR="/Users/Shared/EnterpriseAttendanceAgent"

echo "=========================================================="
echo " Enterprise Attendance Agent - macOS Removal Helper"
echo "=========================================================="

# 1. Unload and unregister LaunchAgent
echo "[1/4] Stopping background agent service..."
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true

# 2. Terminate any remaining instances
killall enterprise-attendance-desktop 2>/dev/null || true

# 3. Remove LaunchAgent plist
echo "[2/4] Removing LaunchAgent configuration..."
rm -f "${TARGET_PLIST}"

# 4. Remove Application bundle
if [ -d "${APP_DIR}" ]; then
    echo "[3/4] Removing application bundle from /Applications..."
    rm -rf "${APP_DIR}"
fi

# 5. Clean Application Support data & logs
echo "[4/4] Cleaning local application support and caches..."
rm -rf "${DATA_DIR}"
rm -rf "${LOG_DIR}"

echo ""
echo "Enterprise Attendance Agent uninstallation completed."

