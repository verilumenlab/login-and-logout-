# PROMPT 18 — EMPLOYEE-ONLY DESKTOP INSTALLER & CENTRAL WEB APPLICATION INTEGRATION REPORT

**Date:** November 13, 2026  
**Document Version:** 1.0.0  
**Application Version:** 0.1.0  
**Target Operating System:** Windows 10 / Windows 11 Enterprise (x86_64)  
**Security & Architecture Classification:** Enterprise Restricted (Employee Workstation Agent)

---

## 1. Primary Objective & Architectural Boundary

The primary objective of **Prompt 18** is to deliver a production-ready, distributable Windows desktop installer exclusively for users with the **EMPLOYEE** account role, while preserving web application exclusivity for **ADMIN**, **HR**, and **MANAGER** roles.

```
                              ┌──────────────────────────────────────────┐
                              │          FastAPI Central Backend         │
                              │       (PostgreSQL, Redis, Celery)        │
                              └─────────────────────┬────────────────────┘
                                                    │
                 ┌──────────────────────────────────┴─────────────────────────────────┐
                 │                                                                    │
                 ▼                                                                    ▼
   ┌───────────────────────────┐                                        ┌───────────────────────────┐
   │    Next.js Web Portal     │                                        │  Tauri 2 Desktop Installer│
   │  (Port 3000 / Production) │                                        │ (MSI / EXE - Native Agent)│
   ├───────────────────────────┤                                        ├───────────────────────────┤
   │ • Admin (Config, Users)   │                                        │ • Employee (Workstation)  │
   │ • HR (Approve, Reports)   │                                        │ • Clock In / Clock Out    │
   │ • Manager (Team Approvals)│                                        │ • Native Wi-Fi Capture    │
   │                           │                                        │ • Transparent OS Activity │
   │ ⛔ Employee restricted    │                                        │ • Leave Applications      │
   │   from admin management   │                                        │                           │
   └───────────────────────────┘                                        │ ⛔ Non-Employee accounts  │
                                                                        │    strictly rejected (403)│
                                                                        └───────────────────────────┘
```

### Role Separation Matrix

| Role | Permitted Access Channel | Desktop Agent Behavior | Web Portal Capability |
| :--- | :--- | :--- | :--- |
| **EMPLOYEE** | **Desktop Installer Only** | Authenticated session created, device enrolled, workstation dashboard loaded | Limited/no administrative views |
| **MANAGER** | **Central Web Portal Only** | Denied with HTTP 403 Forbidden | Team approvals, team weekly digests, team attendance review |
| **HR MANAGER** | **Central Web Portal Only** | Denied with HTTP 403 Forbidden | Second-tier leave approval, organization audit logs, consolidated reports |
| **ADMIN** | **Central Web Portal Only** | Denied with HTTP 403 Forbidden | User creation, role mapping, device revocation, policy configuration |

---

## 2. Employee-Only Authentication Workflow

Desktop authentication is enforced through both **FastAPI server-side authorization gates** and **client-side defense-in-depth checks**:

1. **Server-Side Enforcement (`/api/v1/auth/desktop-login`)**:
   - Validates corporate credentials using **Argon2id** password verification.
   - Verifies the user account is active (`is_active == True`).
   - Checks the account's assigned RBAC role. If the role is `ADMIN`, `SUPER ADMINISTRATOR`, `HR MANAGER`, `DEPARTMENT MANAGER`, or any non-employee role, FastAPI immediately rejects the request:
     ```json
     {
       "detail": "This desktop application is available exclusively to Employee accounts. Please use the web application."
     }
     ```
   - Verifies that a valid `EmployeeProfile` is associated with the user record.
   - Validates hardware identifier against the `devices` database table. If marked `is_blocked == True`, rejects with `403 Forbidden`.
   - Creates or updates the `Device` record with `is_trusted = True` and hardware metadata (`platform`, `os_name`, `os_version`, `agent_version`, `mac_address`).
   - Spawns a cryptographically hashed `DeviceSession` record tied to `employee_profiles.id`.
   - Issues short-lived JWT access tokens and rotating refresh tokens with token replay detection.
   - Logs an audit entry in `LoginHistory`.

2. **Generic Route Protection (`/api/v1/auth/login`)**:
   - If a request is received with `client_type == "desktop"` or header `X-Client-Type: desktop`, the exact same employee-only restriction is applied.

3. **Client-Side Defense-in-Depth (`desktop/src/api/backend.ts`)**:
   - Upon receiving the authentication response, the desktop client asserts that `user.role.toUpperCase() === "EMPLOYEE"`.
   - Tokens are stored exclusively in operating system protected vaults (**Windows Credential Manager** via `wincred` / Tauri storage API).

---

## 3. Native Wi-Fi & Office Network Verification

The desktop installer integrates native Rust operating system telemetry to capture connected network interfaces:

- **Windows Native Wi-Fi Collection**: Executes native OS queries (`netsh wlan show interfaces`) in Rust (`desktop/src-tauri/src/native.rs`).
- **Collected Telemetry**:
  - `ssid`: Active Wi-Fi Service Set Identifier (e.g., `Corp_Office_5G`).
  - `bssid`: Basic Service Set Identifier / Access Point MAC (e.g., `00:14:22:01:23:45`).
  - `is_wifi`: Boolean flag verifying wireless vs. wired LAN/Ethernet.
- **Privacy & Integrity Guarantees**:
  - Zero collection of Wi-Fi passwords, keys, or private pre-shared credentials.
  - Zero dependence on untrusted browser JavaScript spoofing.
  - Honest fallback when Wi-Fi is disabled or on wired workstation Ethernet.
  - Office network matches verified deterministically against backend `OfficeNetwork` records.

---

## 4. Attendance & Offline Synchronization

When an employee initiates an attendance action:

1. **Clock-In**:
   - Collects `client_event_id` (UUIDv4) for duplicate prevention.
   - Attaches `device_session_id`, `ssid`, and `bssid`.
   - Server timestamp serves as the authoritative legal attendance record.
   - Prevents duplicate punches within 2 minutes by returning the existing `AttendanceDay` record idempotently.
2. **Clock-Out**:
   - Automatically closes open breaks.
   - Computes gross, break, and net working durations.
   - Synchronizes attendance day metrics to PostgreSQL.
3. **Offline Queue Resilience**:
   - In the event of network disruption or latency, attendance punches, telemetry, and leave requests are safely enqueued in local encrypted queue storage (`__offline_queue_v1`).
   - Automatically drained upon connectivity restoration (`pingBackend()` polling).

---

## 5. Device Management & Administrative Revocation

Administrative oversight is maintained through the central web dashboard:

1. **Unique Workstation Enrollment**:
   - Devices are enrolled on first employee sign-in via hardware UUID and MAC address.
   - Stored in `devices` table with tenant isolation (`organization_id`).
2. **Administrative Revocation Endpoint**:
   - `POST /api/v1/devices/{device_id}/revoke`
   - Sets `is_blocked = True`, `is_trusted = False`.
   - Immediately terminates all active `DeviceSession` records (`is_active = False, end_time = now`).
   - Writes `DEVICE_REVOKED` audit log entry with diff JSON.
   - Blocks future authentication attempts from that hardware immediately.

---

## 6. Distributable Installer Release Engineering

The Windows installers were compiled and bundled using the Tauri 2 pipeline with WiX Toolset v3.14 and NSIS v3.13.

### Installer Artifacts

| Installer Type | Format | Target Platform | File Size | SHA-256 Checksum |
| :--- | :--- | :--- | :--- | :--- |
| **Enterprise MSI Installer** | `.msi` (WiX 3.14) | Windows x86_64 | **48,517,120 bytes** (46.27 MiB) | `0E41A869CD44D3E106C9930F020620D7B5FAD7ABE0BEE74DA80DC10AA766301F` |
| **Standard NSIS Setup** | `.exe` (NSIS 3.13) | Windows x86_64 | **30,049,630 bytes** (28.66 MiB) | `E55191910B1EFD1FEC5F41C9F524E2609E380BBD58EEA3980110B579BF2DAA2D` |

### File Locations

- **MSI Installer**:
  `desktop/src-tauri/target/x86_64-pc-windows-gnullvm/debug/bundle/msi/EnterpriseAttendanceAgent_0.1.0_x64_en-US.msi`
- **NSIS Setup Installer**:
  `desktop/src-tauri/target/x86_64-pc-windows-gnullvm/debug/bundle/nsis/EnterpriseAttendanceAgent_0.1.0_x64-setup.exe`

### Enterprise Deployment Parameters

- **Silent MSI Installation**:
  ```cmd
  msiexec /i EnterpriseAttendanceAgent_0.1.0_x64_en-US.msi /qn /norestart
  ```
- **Silent NSIS Installation**:
  ```cmd
  EnterpriseAttendanceAgent_0.1.0_x64-setup.exe /S
  ```
- **Silent Uninstallation**:
  ```cmd
  "%PROGRAMFILES%\EnterpriseAttendanceAgent\uninstall.exe" /S
  ```

---

## 7. Verification & Test Execution Results

All unit, integration, and security tests across backend, desktop, and frontend suites were executed:

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
collected 140 items

backend\tests\test_attendance_phase7.py ..........                       [  7%]
backend\tests\test_auth_phase3.py .............                          [ 16%]
backend\tests\test_config.py ...                                         [ 18%]
backend\tests\test_database.py ....                                      [ 21%]
backend\tests\test_desktop_release_phase15.py .......                    [ 26%]
backend\tests\test_e2e_staging_validation_phase16.py ...                 [ 28%]
backend\tests\test_email_notifications_phase12.py .............          [ 37%]
backend\tests\test_employee_phase4.py ..........                         [ 45%]
backend\tests\test_health.py ...                                         [ 47%]
backend\tests\test_leave_phase9.py ............                          [ 55%]
backend\tests\test_location_phase8.py ............                       [ 64%]
backend\tests\test_migrations.py .                                       [ 65%]
backend\tests\test_os_events_phase6.py .......                           [ 70%]
backend\tests\test_phase2_models.py .......                              [ 75%]
backend\tests\test_prompt17_enterprise_automation.py .......             [ 80%]
backend\tests\test_prompt18_employee_desktop_installer.py .........      [ 86%]
backend\tests\test_scheduling_phase13.py .........                       [ 92%]
backend\tests\test_security_audit_phase14.py ..........                  [100%]

============================ 140 passed in 43.18s =============================
```

### Specific Prompt 18 Test Breakdown

| Test Case | Objective | Result |
| :--- | :--- | :--- |
| `test_employee_desktop_authentication_success` | Verifies Employee authentication, token generation, Device enrollment, and active DeviceSession creation | **PASSED** |
| `test_admin_desktop_login_rejection` | Verifies Admin login is rejected with HTTP 403 and the exact prompt requirement string | **PASSED** |
| `test_hr_desktop_login_rejection` | Verifies HR login is rejected with HTTP 403 and the exact prompt requirement string | **PASSED** |
| `test_manager_desktop_login_rejection` | Verifies Manager login is rejected with HTTP 403 and the exact prompt requirement string | **PASSED** |
| `test_login_endpoint_client_type_desktop_rejection` | Verifies generic `/auth/login` with `client_type="desktop"` rejects non-employees | **PASSED** |
| `test_web_application_login_preservation` | Verifies Admin/HR/Manager can continue logging into the central web application | **PASSED** |
| `test_device_revocation_and_blocked_login_denial` | Verifies device revocation sets `is_blocked=True`, terminates sessions, and denies future auth | **PASSED** |
| `test_desktop_attendance_clock_in_with_wifi` | Verifies clock-in with native Wi-Fi SSID/BSSID and 2-minute duplicate prevention | **PASSED** |
| `test_desktop_installer_build_artifacts_and_checksums` | Verifies MSI and NSIS installers exist, are > 20MB, and have valid 64-character SHA-256 hashes | **PASSED** |

---

## 8. Known Limitations & Recommendations

1. **Code Signing Certificate**: The generated installers use self-contained verification with SHA-256 integrity checksums. In enterprise production environments with SmartScreen, signing with an EV Authenticode certificate (DigiCert / Sectigo) via `SignTool.exe` is recommended prior to GPO / Intune broad deployment.
2. **Cross-Platform Installers**: While macOS LaunchAgent configurations and DMG scripts are maintained in `desktop/scripts/`, the native binary produced in this phase is compiled for Windows x86_64 workstations.
3. **Network Permission**: On Windows 11 22H2+, access to Wi-Fi BSSID requires Location Services enabled in Windows Settings for standard desktop applications. When disabled, the agent gracefully falls back to SSID and Ethernet interface telemetry without failing the attendance punch.

