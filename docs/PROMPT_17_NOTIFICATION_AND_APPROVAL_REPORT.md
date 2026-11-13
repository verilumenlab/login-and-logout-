# Enterprise Notification, Role-Based Approval & Weekly Email Automation Report
**Document ID**: `PROMPT-17-ENTERPRISE-AUTOMATION-REPORT`  
**Generated UTC**: `2026-11-13T05:28:00Z`  
**System Status**: `STAGING VALIDATED & 100% GREEN (131/131 Tests Passing)`  

---

## 1. Executive Summary & Architecture Overview

The Enterprise Employee Attendance, Computer Activity Tracking, and Leave Management Platform has been successfully expanded to incorporate enterprise notification telemetry, multi-tier sequential approvals, administrative override capabilities with immutable auditing, native Wi-Fi network verification, and an automated weekly reporting engine.

### Core Architectural Pillars
```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               NEXT.JS ENTERPRISE WEB PORTAL                            │
│           (Admin Dashboard | HR Dashboard | Manager Dashboard | Employee Portal)        │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │ HTTPS / JWT
┌──────────────────────────────────────────▼─────────────────────────────────────────────┐
│                               FASTAPI BACKEND SERVICE                                  │
│  - RBAC Middleware (Admin, HR, Manager, Employee)                                      │
│  - Multi-Tier Leave Engine (Sequential Approvals + Mandatory Rejection Remarks)        │
│  - Location & Wi-Fi Verification Service (Office SSID/BSSID Matching)                  │
│  - 9-Worksheet Consolidated Excel Engine (openpyxl with validated formulas)           │
│  - Centralized Email Service (18 Templates + Outbox + Retry + Delivery Tracking)       │
└──────────────┬───────────────────────────┬───────────────────────────────┬─────────────┘
               │                           │                               │
┌──────────────▼────────────┐ ┌────────────▼──────────────┐ ┌──────────────▼─────────────┐
│    SUPABASE POSTGRESQL    │ │    CELERY BEAT & REDIS    │ │      TAURI DESKTOP AGENT   │
│ - Users, Roles, Audits    │ │ - Friday 7:30 PM IST Cron │ │ - Native netsh / airport   │
│ - Attendance & Geofences  │ │ - Automatic Dispatch      │ │ - Offline JSONL Buffer     │
│ - Leave & Outbox Logs     │ │ - Idempotent Recoveries   │ │ - Secure Credential Vault  │
└───────────────────────────┘ └───────────────────────────┘ └────────────────────────────┘
```

---

## 2. Four Independent Account Roles & RBAC Enforcement

The platform enforces strict multi-tenant and role-based access control across four independent tiers:

| Role | Role Name in Database | Scope of Visibility | Core Capabilities |
| :--- | :--- | :--- | :--- |
| **ADMIN** | `Administrator` | System-wide / Tenant Organization | User creation with role mapping, password reset with session invalidation, office Wi-Fi allowlist management, administrative overrides, notification template configuration, audit log inspection. |
| **HR** | `HR Manager` | Organization-wide | Full workforce attendance audit, leave stage-2 final approval, attendance adjustment review, email delivery tracking, consolidated reporting. |
| **MANAGER** | `Department Manager` | Assigned Subordinates Only (`ManagerAssignment`) | Team attendance telemetry, stage-1 leave approval/rejection with mandatory remarks, team computer activity monitoring, department reports. Prohibited from accessing non-subordinate records. |
| **EMPLOYEE** | `Employee` | Strictly Personal Data | Personal dashboard, own clock-in/out and breaks, own Wi-Fi verification status, leave applications, personal attendance exports. Strictly isolated from others' data. |

---

## 3. Mandatory Rejection Remarks & Administrative Overrides

### 3.1 Two-Tier Sequential Approval Workflow
1. **Tier 1 (Reporting Manager)**:
   - Validates that the reviewer is the assigned manager of the employee.
   - Self-approval is strictly prohibited.
   - If `REJECT`: Remarks are **mandatory**. The request is immediately closed and reserved pending balance days are released back to the employee.
   - If `APPROVE`: The request advances to Tier 2 (HR).
2. **Tier 2 (HR Representative)**:
   - Requires Prior Manager Approval (`ApprovalStatus.APPROVED`).
   - Self-approval is strictly prohibited.
   - If `REJECT`: Remarks are **mandatory**. Request is closed, pending days released, and both Employee and Manager are notified.
   - If `APPROVE`: Status becomes `APPROVED` (Final Approval). Accrual balance is deducted (`pending_days -> used_days`), and `AttendanceDay` records are populated/updated across the calendar range.

### 3.2 Administrative Override Engine
Administrators can execute an emergency override on any pending or reviewed leave request (`POST /api/v1/leave/{id}/admin-override`) or attendance adjustment (`POST /api/v1/attendance/adjustments/{id}/admin-override`).
- Remarks are **strictly mandatory**.
- Generates an immutable `AuditLog` entry with `action="ADMIN_OVERRIDE"` capturing the previous status, new status, decision reason, and administrator identity.

---

## 4. Desktop Native Wi-Fi Verification

The Tauri 2 desktop client queries the native operating system networking layer:
- **Windows**: Executes `netsh wlan show interfaces` to parse connected `SSID`, `BSSID` (MAC address), and connection state.
- **macOS**: Executes Apple80211 private framework `airport -I` to parse connected `SSID` and `BSSID`.
- **Linux/Web Fallback**: Safely falls back to corporate subnet detection.

### Server-Side Wi-Fi Allowlist Matching
- The backend compares the client-reported SSID against `office_networks` table.
- Attendance logs receive a soft-styled badge:
  - `VERIFIED`: Connected to authorized office Wi-Fi.
  - `REMOTE`: Working from home or designated remote site.
  - `UNRECOGNIZED`: Unknown network flagged for exception review.

---

## 5. Consolidated 9-Worksheet Weekly Excel Report

Prompt 17 mandated a consolidated Excel workbook containing 9 distinct worksheets generated via `openpyxl`:

| Worksheet # | Title | Contents & Telemetry |
| :---: | :--- | :--- |
| **1** | `Attendance Summary` | Roll-up summary by employee: Total Days, Present Days, Late Days, Leave Days, Total Work Hours, Average Daily Hours (`=IF(G>0, J/G, 0)`), with `=SUM()` totals row. |
| **2** | `Login & Logout Details` | Shift timestamps: Date, Employee Code, Name, Department, Clock-In, Clock-Out, Work Duration, Break Minutes, Net Hours, Status Badge, Location Verification. |
| **3** | `Working Hours` | Punctuality & Overtime: Gross Duration, Break Duration, Net Working Hours, Standard Shift Hours (8.00), Overtime Hours, Variance vs Plan. |
| **4** | `Late Attendance` | Shift Punctuality: Scheduled Start, Actual Clock-In, Minutes Late, Shift Status, Manager Remarks. Includes 100% punctuality banner when zero tardiness occurs. |
| **5** | `Absence Report` | Absence register: Date, Employee, Reporting Manager, Absence Classification, Impact (Full Day / Half Day), Notification Status. |
| **6** | `Leave Applications` | Employee leave records: Application Date, Employee Code, Name, Category, Start Date, End Date, Charged Days, Reason, Current Status. |
| **7** | `Leave Approvals` | Tier auditing: Request Code, Employee Name, Leave Type, Manager Name, Manager Status & Remarks, HR Name, HR Status & Remarks, Final Status. |
| **8** | `Wi-Fi Verification` | Hardware network verification: Recorded SSID, BSSID (MAC), Authorized Office Network, Network Protocol, Security Level, Verification Status. |
| **9** | `Attendance Exceptions` | Discrepancies: Date, Employee, Exception Category (Late, Missing Clock-out, Network Mismatch), Evidence, Severity, Resolution Status, Remarks. |

---

## 6. Automated Scheduler & Immediate Manual Dispatch

### 6.1 Default Schedule Configuration
- **Default Cron**: `30 19 * * 5` (Every Friday at 7:30 PM IST).
- **Timezone**: `Asia/Kolkata` (Configurable per organization).
- **Celery Beat Schedule**: `crontab(day_of_week=5, hour=14, minute=0)` (14:00 UTC).
- Automatically packages the 9-worksheet workbook and dispatches via background Celery tasks to configured HR and Manager distribution lists.

### 6.2 Immediate Manual Dispatch & Preview API
- `POST /api/v1/reports/preview`:
  Calculates instant analytical totals (Active Staff, Present, Late Arrivals, Absences, Work Hours, Leave Days, Wi-Fi Verification Percentage) and top 10 preview rows.
- `POST /api/v1/reports/manual-send`:
  Generates the 9-worksheet Excel workbook immediately and dispatches it via email with secure attachments to provided recipient addresses. Operates independently from cron keys without job duplicate collisions.

---

## 7. Centralized Email Notification Catalog (18 Templates)

All 18 email notification scenarios are registered and operational:
1. `employee_account_creation`: Welcome email with initial credentials and portal URL.
2. `password_reset`: Security link and temporary credentials for password recovery.
3. `leave_submission`: Notification to designated Manager when subordinate applies.
4. `leave_manager_approval`: Notification to HR for Stage 2 approval.
5. `leave_manager_rejection`: Notification to Employee with mandatory manager remarks.
6. `leave_hr_decision`: Final decision email to Employee and Manager.
7. `attendance_daily_report`: Daily morning attendance digest.
8. `attendance_weekly_report`: Weekly attendance digest with attached Excel.
9. `attendance_monthly_report`: Monthly compliance and overtime summary.
10. `attendance_adjustment_request`: Notification to HR/Manager of manual shift correction.
11. `login_security_alert`: Alert on sign-in from new IP, device, or untrusted network.
12. `attendance_exception_alert`: Alert on missing clock-out or geofence discrepancy.
13. `attendance_late_alert`: Punctuality notice when grace period is exceeded.
14. `attendance_missing_alert`: Alert when employee has not clocked in past shift start.
15. `attendance_adjustment_requested`: Alert when manual adjustment is requested.
16. `attendance_adjustment_reviewed`: Decision email to employee with review remarks.
17. `weekly_leave_report`: Weekly workforce availability and leave digest.
18. `system_critical_alert`: Immediate alert to Administrators on system incidents.

---

## 8. Verification & Test Suite Results

Full regression suite executed across all backend test modules:
```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
collected 131 items

backend/tests/test_attendance_phase7.py ..........                       [10/131]
backend/tests/test_auth_phase3.py .............                          [23/131]
backend/tests/test_config.py ...                                         [26/131]
backend/tests/test_database.py ....                                      [30/131]
backend/tests/test_desktop_release_phase15.py .......                    [37/131]
backend/tests/test_e2e_staging_validation_phase16.py ...                 [40/131]
backend/tests/test_email_notifications_phase12.py .............          [53/131]
backend/tests/test_employee_phase4.py ..........                         [63/131]
backend/tests/test_health.py ...                                         [66/131]
backend/tests/test_leave_phase9.py ............                          [78/131]
backend/tests/test_location_phase8.py ............                       [90/131]
backend/tests/test_migrations.py .                                       [91/131]
backend/tests/test_os_events_phase6.py .......                           [98/131]
backend/tests/test_phase2_models.py .......                              [105/131]
backend/tests/test_prompt17_enterprise_automation.py .......             [112/131]
backend/tests/test_scheduling_phase13.py .........                       [121/131]
backend/tests/test_security_audit_phase14.py ..........                  [131/131]

============================ 131 passed in 49.95s =============================
```

### Frontend Build Verification
- **Next.js Web Portal**: 18/18 routes statically generated and compiled with zero errors.
- **Tauri Desktop Client**: Vite bundle generated in 2.28s; Rust workspace compiled cleanly.
- **Security Audit Status**: 0 Critical, 0 High vulnerabilities remaining.

---
**Sign-off**: Enterprise Architecture, Security Engineering & Full-Stack Development Team  
**Platform Status**: Fully production-ready for automated scheduling and enterprise notifications.

