# Enterprise Desktop Agent - Release & Deployment Guide (Phase 15)

## 1. Overview
The Enterprise Attendance & Activity Desktop Agent is packaged for automated enterprise distribution across **Windows 10/11** and **macOS 12+ (Intel & Apple Silicon)** via centralized Mobile Device Management (MDM) platforms.

---

## 2. Windows Enterprise Deployment (Intune / GPO / SCCM)

### 2.1 Silent Installer Execution
The signed Windows NSIS installer supports automated command-line switches:

```powershell
# Silent installation for all workstation users into Program Files
EnterpriseAttendanceAgent-Setup-0.1.0.exe /S /ALLUSERS /D="C:\Program Files\EnterpriseAttendanceAgent"
```

| Switch | Description |
| :--- | :--- |
| `/S` | Silent execution without GUI wizard or user interaction |
| `/ALLUSERS` | Configures per-machine installation (HKLM Run Key & Scheduled Task) |
| `/D=<path>` | Custom destination directory (must be the last parameter on the command line) |

### 2.2 Background Agent Service & Startup Registration
The installer automatically performs:
1. **Registry Run Key**: Writes to `HKLM\Software\Microsoft\Windows\CurrentVersion\Run` so the agent starts minimized (`--background`) upon any user logon.
2. **Resilient Scheduled Task**: Registers task `EnterpriseAttendanceAgent` set to trigger on workstation logon with highest privileges and automatic restart upon crash.
3. **Stand-alone PowerShell Service Helper**:
   ```powershell
   powershell -ExecutionPolicy Bypass -File "C:\Program Files\EnterpriseAttendanceAgent\install_service.ps1"
   ```

### 2.3 Silent Workstation Uninstallation
```powershell
# Silent uninstallation and registry/task cleanup
"C:\Program Files\EnterpriseAttendanceAgent\uninstall.exe" /S
```

---

## 3. macOS Enterprise Deployment (Jamf Pro / Kandji / MDM)

### 3.1 Distribution Format
- **Distribution Package**: Signed & Apple Notarized `.dmg` or `.pkg`.
- **Target Location**: `/Applications/EnterpriseAttendanceAgent.app`.

### 3.2 LaunchAgent Configuration
The background agent is managed by `launchd` via user-scoped LaunchAgent:
- **Identifier**: `com.enterprise.attendance.agent`
- **Location**: `~/Library/LaunchAgents/com.enterprise.attendance.agent.plist`
- **Arguments**: `/Applications/EnterpriseAttendanceAgent.app/Contents/MacOS/enterprise-attendance-desktop --background`
- **Configuration Flags**: `RunAtLoad = true`, `KeepAlive = { Crashed: true }`.

### 3.3 MDM PPPC Configuration Profile (Privacy & Permissions)
To prevent end-user permission prompts, push a mobileconfig profile containing:
- **Accessibility**: Allow `com.enterprise.attendance.agent` (for system idle & lock/unlock telemetry).
- **Notifications**: Allow critical attendance reminders.

### 3.4 Automated Uninstall
```bash
sudo bash /Applications/EnterpriseAttendanceAgent.app/Contents/Resources/uninstall.sh
```

---

## 4. Multi-Channel Update Infrastructure

### 4.1 Channels
| Channel | Purpose | Audience | Endpoint |
| :--- | :--- | :--- | :--- |
| **staging** | Pre-release validation | IT test pilot group (5% fleet) | `https://updates.enterprise.com/staging/{{target}}/{{current_version}}` |
| **production** | General availability | All corporate employees | `https://updates.enterprise.com/production/{{target}}/{{current_version}}` |

### 4.2 Cryptographic Update Verification
Every update payload is verified by Tauri's internal updater using:
- **Pinned Ed25519 Public Key**: Embedded in `tauri.conf.json`.
- **Signed Manifest**: `latest.json` provides base64 Ed25519 signature per target architecture.
- **Anti-Rollback Protection**: Updates with version numbers lower than or equal to the current version are rejected.

---

## 5. Rollback Procedures
If a release exhibits unexpected behavior in staging:
1. Re-issue the previous stable release with an incremented patch version (e.g., `0.1.0` -> `0.1.1` containing reverted stable binaries).
2. Publish signed `latest.json` to the target channel.
3. Workstation agents automatically update to the verified stable build during the next periodic check interval.

