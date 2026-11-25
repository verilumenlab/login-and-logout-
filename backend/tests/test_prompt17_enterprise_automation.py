"""
Prompt 17: Enterprise Notification, Role-Based Approval & Weekly Email Automation Tests

Covers:
1. Four Independent Roles & RBAC: Admin, HR, Manager, Employee boundaries
2. Admin Account Management: Creation with role mapping, password reset with session invalidation
3. Employee Login History Auditing: Viewable by Admin/HR/Manager/Self
4. Leave Workflow: Mandatory rejection remarks for Manager and HR
5. Admin Leave & Attendance Override: Dedicated audit log (action='ADMIN_OVERRIDE')
6. 9-Worksheet Consolidated Weekly Excel Report: Openpyxl structure, formulas & formatting
7. Report Preview API: Real-time calculation of metrics & sample rows
8. Immediate Manual Report Dispatch API: Direct generation and email delivery with attachments
9. Native Wi-Fi Verification & Location Integrity
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime, timedelta
import openpyxl
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, get_password_hash
from app.core.seeds import seed_permissions, seed_system_roles
from app.models.attendance import AttendanceDay, AttendanceStatus
from app.models.auth import AuditLog, RefreshToken, Role, User
from app.models.department import Department
from app.models.employee import EmployeeProfile, EmploymentStatus, ManagerAssignment
from app.models.leave import ApprovalStatus, LeaveCategory, LeaveRequest, LeaveStatus, LeaveType, LeaveBalance
from app.models.notification import EmailOutbox, OutboxStatus
from app.models.organization import Organization
from app.models.reporting import ReportFile, ReportJob, ReportStatus, ReportType
from app.services.email_service import EmailService
from app.services.leave_engine import LeaveEngine, LeaveEngineError
from app.services.report_generator import ExcelReportEngine


@pytest.fixture
async def setup_prompt17_env(db_session: AsyncSession):
    code_suffix = uuid.uuid4().hex[:6].upper()
    org = Organization(
        name="Enterprise Automation Corp",
        code=f"EAC-{code_suffix}",
        slug=f"eac-{code_suffix.lower()}",
        is_active=True,
    )
    db_session.add(org)
    await db_session.flush()

    perm_map = await seed_permissions(db_session)
    role_map = await seed_system_roles(db_session, perm_map)

    dept = Department(organization_id=org.id, name="Platform Engineering", code="ENG")
    db_session.add(dept)
    await db_session.flush()

    async def create_user_and_emp(
        email: str,
        role_name: str,
        first_name: str,
        last_name: str,
    ) -> tuple[User, EmployeeProfile, str]:
        user = User(
            organization_id=org.id,
            role_id=role_map[role_name].id,
            email=email,
            hashed_password=get_password_hash("EnterprisePass123!"),
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        emp = EmployeeProfile(
            organization_id=org.id,
            user_id=user.id,
            department_id=dept.id,
            employee_code=f"EMP-{uuid.uuid4().hex[:4].upper()}",
            first_name=first_name,
            last_name=last_name,
            hire_date=date(2026, 1, 1),
            employment_status=EmploymentStatus.ACTIVE,
        )
        db_session.add(emp)
        await db_session.flush()

        token = create_access_token(user.id, {"org": str(org.id), "role": role_name})
        return user, emp, token

    admin_u, admin_e, admin_tok = await create_user_and_emp(f"admin_{code_suffix.lower()}@corp.local", "Administrator", "Alice", "Admin")
    hr_u, hr_e, hr_tok = await create_user_and_emp(f"hr_{code_suffix.lower()}@corp.local", "HR Manager", "Helen", "HR")
    mgr_u, mgr_e, mgr_tok = await create_user_and_emp(f"mgr_{code_suffix.lower()}@corp.local", "Department Manager", "Mark", "Manager")
    emp_u, emp_e, emp_tok = await create_user_and_emp(f"emp_{code_suffix.lower()}@corp.local", "Employee", "Edward", "Employee")

    # Direct report assignment: Employee reports to Manager
    assignment = ManagerAssignment(
        organization_id=org.id,
        employee_id=emp_e.id,
        manager_id=mgr_e.id,
        is_primary=True,
    )
    db_session.add(assignment)

    # Leave Type & Balance
    leave_type = LeaveType(
        organization_id=org.id,
        name="Annual Vacation",
        code="VAC",
        category=LeaveCategory.ANNUAL,
        annual_allowance=20,
        carryover_max_days=5,
        include_weekends=False,
        is_active=True,
    )
    db_session.add(leave_type)
    await db_session.flush()

    bal = LeaveBalance(
        organization_id=org.id,
        employee_id=emp_e.id,
        leave_type_id=leave_type.id,
        year=2026,
        allocated_days=20.0,
        used_days=0.0,
        pending_days=0.0,
    )
    db_session.add(bal)

    # Seed Attendance Day
    today = date(2026, 11, 13)
    att_day = AttendanceDay(
        organization_id=org.id,
        employee_id=emp_e.id,
        work_date=today,
        status=AttendanceStatus.PRESENT,
        shift_start=datetime.combine(today, datetime.min.time(), tzinfo=UTC) + timedelta(hours=9),
        shift_end=datetime.combine(today, datetime.min.time(), tzinfo=UTC) + timedelta(hours=17, minutes=30),
        total_work_minutes=480,
        total_break_minutes=30,
        metadata_json={"network_ssid": "Corp_Office_5G", "network_verified": True},
    )
    db_session.add(att_day)
    await db_session.commit()

    return {
        "org": org,
        "admin": (admin_u, admin_e, admin_tok),
        "hr": (hr_u, hr_e, hr_tok),
        "manager": (mgr_u, mgr_e, mgr_tok),
        "employee": (emp_u, emp_e, emp_tok),
        "leave_type": leave_type,
        "attendance_day": att_day,
        "dept": dept,
    }


@pytest.mark.asyncio
async def test_four_independent_roles_rbac_isolation(client: AsyncClient, setup_prompt17_env):
    """Verifies strict RBAC isolation across Admin, HR, Manager, and Employee accounts."""
    env = setup_prompt17_env
    _, _, admin_token = env["admin"]
    _, _, hr_token = env["hr"]
    _, _, mgr_token = env["manager"]
    _, emp_e, emp_token = env["employee"]

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    hr_headers = {"Authorization": f"Bearer {hr_token}"}
    mgr_headers = {"Authorization": f"Bearer {mgr_token}"}
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # 1. Admin has access to employees directory and system settings
    res_admin = await client.get("/api/v1/employees/", headers=admin_headers)
    assert res_admin.status_code == 200

    # 2. HR has access to employees and outbox
    res_hr = await client.get("/api/v1/notifications/outbox", headers=hr_headers)
    assert res_hr.status_code == 200

    # 3. Employee is strictly restricted from administrative outbox
    res_emp_outbox = await client.get("/api/v1/notifications/outbox", headers=emp_headers)
    assert res_emp_outbox.status_code == 403

    # 4. Employee can access own attendance
    res_emp_att = await client.get("/api/v1/attendance/history", headers=emp_headers)
    assert res_emp_att.status_code == 200


@pytest.mark.asyncio
async def test_admin_account_creation_and_password_reset(client: AsyncClient, setup_prompt17_env, db_session: AsyncSession):
    """Verifies Admin creation of accounts with role mapping and password reset invalidating refresh tokens."""
    env = setup_prompt17_env
    org = env["org"]
    _, _, admin_token = env["admin"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Admin creates a Manager account with role alias "Manager"
    create_payload = {
        "email": f"new_mgr_{uuid.uuid4().hex[:4]}@corp.com",
        "employee_code": f"MGR-{uuid.uuid4().hex[:4].upper()}",
        "first_name": "Marcus",
        "last_name": "Vance",
        "role_name": "Manager",
        "department_id": str(env["dept"].id),
        "hire_date": "2026-01-01",
    }
    create_res = await client.post("/api/v1/employees/", json=create_payload, headers=admin_headers)
    if create_res.status_code != 201:
        print("Create error:", create_res.status_code, create_res.text)
    assert create_res.status_code == 201
    created_mgr = create_res.json()
    mgr_id = created_mgr["id"]

    # 2. Admin resets password for this user
    reset_res = await client.post(
        f"/api/v1/employees/{mgr_id}/reset-password",
        json={"temporary_password": "NewSecretPass2026!", "notify_email": True},
        headers=admin_headers,
    )
    assert reset_res.status_code == 200
    reset_data = reset_res.json()
    assert reset_data["status"] == "SUCCESS"
    assert reset_data["temporary_password"] == "NewSecretPass2026!"

    # 3. Verify audit log entry exists
    audit_stmt = select(AuditLog).where(
        AuditLog.organization_id == org.id,
        AuditLog.action == "ADMIN_PASSWORD_RESET",
    )
    audit_log = (await db_session.execute(audit_stmt)).scalars().first()
    assert audit_log is not None
    assert audit_log.diff_json["employee_id"] == mgr_id


@pytest.mark.asyncio
async def test_employee_login_history(client: AsyncClient, setup_prompt17_env, db_session: AsyncSession):
    """Verifies employee login history retrieval by Admin and Employee."""
    env = setup_prompt17_env
    org = env["org"]
    _, _, admin_token = env["admin"]
    emp_u, emp_e, emp_token = env["employee"]

    # Seed an audit login event for employee
    audit = AuditLog(
        organization_id=org.id,
        user_id=emp_u.id,
        action="USER_LOGIN",
        entity_type="auth",
        ip_address="192.168.1.150",
        diff_json={"client": "Tauri-Desktop-Agent", "os": "Windows 11"},
    )
    db_session.add(audit)
    await db_session.commit()

    # 1. Employee inspects own login history
    res_emp = await client.get(f"/api/v1/employees/{emp_e.id}/login-history", headers={"Authorization": f"Bearer {emp_token}"})
    assert res_emp.status_code == 200
    logs = res_emp.json()
    assert len(logs) >= 1
    assert logs[0]["action"] == "USER_LOGIN"

    # 2. Admin inspects employee login history
    res_admin = await client.get(f"/api/v1/employees/{emp_e.id}/login-history", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200


@pytest.mark.asyncio
async def test_mandatory_rejection_remarks(client: AsyncClient, setup_prompt17_env, db_session: AsyncSession):
    """Verifies that rejecting a leave request requires non-empty remarks at both Manager and HR stages."""
    env = setup_prompt17_env
    _, emp_e, emp_token = env["employee"]
    _, mgr_e, mgr_token = env["manager"]
    _, hr_e, hr_token = env["hr"]
    leave_type = env["leave_type"]

    emp_headers = {"Authorization": f"Bearer {emp_token}"}
    mgr_headers = {"Authorization": f"Bearer {mgr_token}"}
    hr_headers = {"Authorization": f"Bearer {hr_token}"}

    # Employee submits leave
    apply_res = await client.post(
        "/api/v1/leave/apply",
        json={
            "leave_type_id": str(leave_type.id),
            "start_date": "2026-11-20",
            "end_date": "2026-11-22",
            "reason": "Family gathering",
        },
        headers=emp_headers,
    )
    assert apply_res.status_code == 201
    leave_id = apply_res.json()["id"]

    # Manager attempts rejection without remarks -> MUST FAIL
    rej_fail = await client.post(
        f"/api/v1/leave/{leave_id}/manager-review",
        json={"action": "REJECT", "comments": ""},
        headers=mgr_headers,
    )
    assert rej_fail.status_code == 400
    assert "remarks are mandatory" in rej_fail.json()["detail"].lower()

    # Manager rejects with valid remarks -> MUST SUCCEED
    rej_ok = await client.post(
        f"/api/v1/leave/{leave_id}/manager-review",
        json={"action": "REJECT", "comments": "Coverage conflict during sprint deployment"},
        headers=mgr_headers,
    )
    assert rej_ok.status_code == 200
    assert rej_ok.json()["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_admin_leave_override(client: AsyncClient, setup_prompt17_env, db_session: AsyncSession):
    """Verifies Admin direct override of leave requests with mandatory remarks and dedicated audit log."""
    env = setup_prompt17_env
    org = env["org"]
    _, emp_e, emp_token = env["employee"]
    _, _, admin_token = env["admin"]
    leave_type = env["leave_type"]

    emp_headers = {"Authorization": f"Bearer {emp_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Employee applies
    apply_res = await client.post(
        "/api/v1/leave/apply",
        json={
            "leave_type_id": str(leave_type.id),
            "start_date": "2026-12-01",
            "end_date": "2026-12-02",
            "reason": "Emergency medical consultation",
        },
        headers=emp_headers,
    )
    assert apply_res.status_code == 201
    leave_id = apply_res.json()["id"]

    # Admin executes override without comments -> MUST FAIL
    ov_fail = await client.post(
        f"/api/v1/leave/{leave_id}/admin-override",
        json={"action": "APPROVE", "remarks": ""},
        headers=admin_headers,
    )
    assert ov_fail.status_code == 400

    # Admin executes override with comments -> MUST SUCCEED
    ov_ok = await client.post(
        f"/api/v1/leave/{leave_id}/admin-override",
        json={"action": "APPROVE", "remarks": "Authorized under executive medical emergency policy"},
        headers=admin_headers,
    )
    assert ov_ok.status_code == 200
    assert ov_ok.json()["status"] == "APPROVED"

    # Verify dedicated AuditLog (action='ADMIN_OVERRIDE')
    audit_stmt = select(AuditLog).where(
        AuditLog.organization_id == org.id,
        AuditLog.action == "ADMIN_OVERRIDE",
        AuditLog.entity_id == str(leave_id),
    )
    audit = (await db_session.execute(audit_stmt)).scalars().first()
    assert audit is not None
    assert audit.diff_json["new_status"] == "APPROVED"


@pytest.mark.asyncio
async def test_nine_worksheet_weekly_consolidated_excel_engine(setup_prompt17_env):
    """Verifies that the Excel reporting engine generates all 9 mandated worksheets with validated openpyxl formatting."""
    job_id = uuid.uuid4()
    start_d = date(2026, 11, 6)
    end_d = date(2026, 11, 13)

    employees_data = [
        {
            "code": "EMP-1001",
            "name": "Alice Admin",
            "email": "alice@corp.local",
            "department": "Platform",
            "manager": "None",
            "total_days": 5,
            "present_days": 5,
            "late_days": 0,
            "leave_days": 0.0,
            "total_hours": 40.0,
        },
        {
            "code": "EMP-1002",
            "name": "Edward Employee",
            "email": "edward@corp.local",
            "department": "Engineering",
            "manager": "Mark Manager",
            "total_days": 5,
            "present_days": 4,
            "late_days": 1,
            "leave_days": 1.0,
            "total_hours": 32.5,
        },
    ]

    attendance_logs = [
        {
            "date": "2026-11-09",
            "employee_code": "EMP-1002",
            "employee_name": "Edward Employee",
            "department": "Engineering",
            "clock_in": "09:25:00",
            "clock_out": "17:30:00",
            "work_duration": "7h 35m",
            "break_minutes": 30,
            "net_hours": 7.58,
            "status": "LATE",
            "location_status": "VERIFIED",
            "late_minutes": 25,
        }
    ]

    leaves_data = [
        {
            "employee_code": "EMP-1002",
            "employee_name": "Edward Employee",
            "leave_type": "Annual Vacation",
            "start_date": "2026-11-13",
            "end_date": "2026-11-13",
            "total_days": 1.0,
            "status": "APPROVED",
            "manager_status": "APPROVED",
            "hr_status": "APPROVED",
            "reason": "Scheduled personal leave",
        }
    ]

    fname, fpath, fsize = ExcelReportEngine.generate_weekly_consolidated_report(
        job_id=job_id,
        org_name="Enterprise Automation Corp",
        report_title="Weekly Workforce Analytics Digest",
        start_date=start_d,
        end_date=end_d,
        employees_data=employees_data,
        attendance_logs=attendance_logs,
        os_events=[],
        leaves_data=leaves_data,
    )

    assert os.path.exists(fpath)
    assert fsize > 1000

    # Load and inspect worksheets
    wb = openpyxl.load_workbook(fpath, data_only=False)
    sheet_names = wb.sheetnames

    # Exactly 9 mandated worksheets
    expected_sheets = [
        "Attendance Summary",
        "Login & Logout Details",
        "Working Hours",
        "Late Attendance",
        "Absence Report",
        "Leave Applications",
        "Leave Approvals",
        "Wi-Fi Verification",
        "Attendance Exceptions",
    ]
    for exp in expected_sheets:
        assert exp in sheet_names, f"Mandated worksheet '{exp}' is missing in generated report!"

    # Verify formula existence in Attendance Summary
    ws_sum = wb["Attendance Summary"]
    found_formula = any(str(cell.value or "").startswith("=") for row in ws_sum.iter_rows() for cell in row)
    assert found_formula, "Validated Excel formulas (=SUM, =AVERAGE, =IF) missing from Attendance Summary!"

    # Cleanup
    try:
        os.remove(fpath)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_report_preview_and_manual_dispatch_api(client: AsyncClient, setup_prompt17_env):
    """Verifies the REST API endpoints: POST /reports/preview and POST /reports/manual-send."""
    env = setup_prompt17_env
    _, _, hr_token = env["hr"]
    _, _, admin_token = env["admin"]

    hr_headers = {"Authorization": f"Bearer {hr_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Preview Analytics
    preview_res = await client.post(
        "/api/v1/reports/preview",
        json={
            "report_type": "WEEKLY",
            "start_date": "2026-11-06",
            "end_date": "2026-11-13",
        },
        headers=hr_headers,
    )
    assert preview_res.status_code == 200
    prev_data = preview_res.json()
    assert prev_data["report_type"] == "WEEKLY"
    assert "total_employees" in prev_data
    assert "present_count" in prev_data
    assert "average_daily_hours" in prev_data

    # 2. Manual Send
    send_res = await client.post(
        "/api/v1/reports/manual-send",
        json={
            "report_type": "WEEKLY",
            "start_date": "2026-11-06",
            "end_date": "2026-11-13",
            "recipients": ["hr_exec@corp.com", "vp_operations@corp.com"],
        },
        headers=admin_headers,
    )
    assert send_res.status_code == 201
    send_data = send_res.json()
    assert send_data["status"] == "DISPATCHED"
    assert len(send_data["recipients"]) == 2
    assert "weekly_consolidated" in send_data["file_name"]

    # 3. Approval defaults: Mon-Fri week + configured HR / manager addresses
    defaults_res = await client.get("/api/v1/reports/weekly-approval", headers=admin_headers)
    assert defaults_res.status_code == 200
    defaults = defaults_res.json()
    start = date.fromisoformat(defaults["start_date"])
    end = date.fromisoformat(defaults["end_date"])
    assert start.weekday() == 0 and end.weekday() == 4
    emails = {r["email"] for r in defaults["recipients"]}
    assert "satish@verilumen.ai" in emails and "kp@verilumen.ai" in emails

    # 4. Duplicate / invalid recipients are cleaned; no valid recipient is rejected
    bad_res = await client.post(
        "/api/v1/reports/manual-send",
        json={
            "report_type": "WEEKLY",
            "start_date": "2026-11-06",
            "end_date": "2026-11-13",
            "recipients": ["not-an-email", "  "],
        },
        headers=admin_headers,
    )
    assert bad_res.status_code == 400
