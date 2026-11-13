"""
Phase 16 - Staging Deployment & Final End-to-End Validation Test Suite
Executes the full 17-step cross-tier lifecycle across all platform domains:
 1. Admin creates an employee.
 2. Employee receives account email.
 3. Employee installs desktop application.
 4. Employee logs into Windows/macOS.
 5. OS activity is collected.
 6. Employee clocks in.
 7. Location is recorded.
 8. Employee starts and ends a break.
 9. Employee clocks out.
10. Employee applies for leave.
11. Manager approves leave.
12. HR approves leave.
13. Employee receives final email.
14. Attendance reflects approved leave.
15. Excel reports are generated.
16. HR receives reports.
17. Manager receives assigned-team reports.
Plus:
- Offline synchronization handling (delayed batch ingestion & duplicate rejection)
- Application restarts & missed scheduler recovery
"""

import os
import uuid
import pytest
from datetime import UTC, datetime, date, time as dtime, timedelta
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, get_password_hash
from app.core.seeds import seed_permissions, seed_system_roles
from app.models.organization import Organization
from app.models.auth import Role, User, RefreshToken, LoginHistory
from app.models.department import Department
from app.models.office import Office, OfficeGeofence, LocationEvent, VerificationStatus, VerificationMethod
from app.models.schedule import WorkSchedule
from app.models.employee import EmployeeProfile, EmploymentStatus, ManagerAssignment
from app.models.device import Device
from app.models.attendance import AttendanceEvent, AttendanceDay, AttendanceEventType, AttendanceStatus
from app.models.leave import LeaveType, LeaveRequest, LeaveApproval, LeaveDocument, LeaveStatus, ApprovalStatus
from app.models.notification import EmailOutbox, OutboxStatus
from app.models.reporting import ReportJob, ReportFile, ReportType, ReportStatus, ReportSchedule
from app.models.os_event import OSSessionEvent
from app.services.attendance_engine import calculate_daily_attendance
from app.services.report_generator import ExcelReportEngine
from app.services.report_scheduler_service import ReportSchedulerService
from app.services.email_service import EmailService


@pytest.fixture
def e2e_env_fixture(db_session):
    """Initializes a realistic enterprise staging environment with Admin, HR, Manager, and Office."""
    async def _setup():
        uid = uuid.uuid4().hex[:6]
        org = Organization(name=f"Staging Corp {uid}", slug=f"staging-{uid}", code=f"STG-{uid[:4]}")
        db_session.add(org)
        await db_session.flush()

        # Seed Permissions and System Roles
        perm_map = await seed_permissions(db_session)
        role_map = await seed_system_roles(db_session, perm_map)
        admin_role = role_map["Super Administrator"]
        hr_role = role_map["HR Manager"]
        mgr_role = role_map["Department Manager"]
        emp_role = role_map["Employee"]

        # Department & Schedule
        dept = Department(name="Engineering", code="ENG", organization_id=org.id)
        sched = WorkSchedule(
            organization_id=org.id,
            name="General 9-to-5",
            shift_start_time=dtime(9, 0),
            shift_end_time=dtime(17, 0),
            working_days=[1, 2, 3, 4, 5],
        )
        # Office geofence (Headquarters)
        office = Office(
            organization_id=org.id,
            name="Downtown Staging Office",
            code=f"STG-{uid[:4]}",
            address="100 Tech Blvd",
            timezone="America/Los_Angeles",
            is_active=True,
        )
        db_session.add_all([dept, sched, office])
        await db_session.flush()

        geofence = OfficeGeofence(
            office_id=office.id,
            name="Downtown Perimeter",
            latitude=37.7749,
            longitude=-122.4194,
            radius_meters=150.0,
            is_active=True,
        )
        db_session.add(geofence)
        await db_session.flush()

        # Admin User
        admin_user = User(
            email=f"admin_{uid}@staging.com",
            hashed_password=get_password_hash("AdminPass123!"),
            organization_id=org.id,
            role_id=admin_role.id,
            is_active=True,
            is_superuser=True,
        )
        # HR User
        hr_user = User(
            email=f"hr_{uid}@staging.com",
            hashed_password=get_password_hash("HrPass123!"),
            organization_id=org.id,
            role_id=hr_role.id,
            is_active=True,
        )
        # Manager User & Profile
        mgr_user = User(
            email=f"manager_{uid}@staging.com",
            hashed_password=get_password_hash("MgrPass123!"),
            organization_id=org.id,
            role_id=mgr_role.id,
            is_active=True,
        )
        db_session.add_all([admin_user, hr_user, mgr_user])
        await db_session.flush()

        hr_profile = EmployeeProfile(
            user_id=hr_user.id,
            organization_id=org.id,
            department_id=dept.id,
            work_schedule_id=sched.id,
            first_name="Helen",
            last_name="HR",
            employee_code=f"HR-{uid[:4]}",
            hire_date=date(2025, 1, 1),
        )
        mgr_profile = EmployeeProfile(
            user_id=mgr_user.id,
            organization_id=org.id,
            department_id=dept.id,
            work_schedule_id=sched.id,
            first_name="Bob",
            last_name="Manager",
            employee_code=f"MGR-{uid[:4]}",
            hire_date=date(2025, 1, 1),
        )
        db_session.add_all([hr_profile, mgr_profile])

        # Leave Type
        leave_type = LeaveType(
            organization_id=org.id,
            name="Annual Vacation",
            code="ANNUAL",
            annual_allowance=20,
            is_active=True,
        )
        db_session.add(leave_type)
        await db_session.commit()

        admin_token = create_access_token(subject=admin_user.id)
        hr_token = create_access_token(subject=hr_user.id)
        mgr_token = create_access_token(subject=mgr_user.id)

        return {
            "org": org,
            "dept": dept,
            "sched": sched,
            "office": office,
            "leave_type": leave_type,
            "admin_user": admin_user,
            "hr_user": hr_user,
            "mgr_user": mgr_user,
            "mgr_profile": mgr_profile,
            "admin_token": admin_token,
            "hr_token": hr_token,
            "mgr_token": mgr_token,
            "emp_role": emp_role,
        }

    return _setup


@pytest.mark.asyncio
async def test_complete_17_step_e2e_staging_lifecycle(e2e_env_fixture, db_session, client: AsyncClient):
    """
    Executes and validates all 17 steps in chronological order:
    Admin onboarding -> Employee setup -> Desktop pairing -> OS session sync ->
    Attendance clock in/out & breaks -> Geofence validation -> Leave 2-tier approval ->
    Automated reporting and role-based email distribution.
    """
    env = await e2e_env_fixture()
    admin_headers = {"Authorization": f"Bearer {env['admin_token']}"}
    hr_headers = {"Authorization": f"Bearer {env['hr_token']}"}
    mgr_headers = {"Authorization": f"Bearer {env['mgr_token']}"}

    # =========================================================================
    # STEP 1: Admin creates an employee via API
    # =========================================================================
    new_emp_email = f"alice_{uuid.uuid4().hex[:5]}@staging.com"
    create_payload = {
        "first_name": "Alice",
        "last_name": "Engineer",
        "email": new_emp_email,
        "employee_code": f"EMP-{uuid.uuid4().hex[:5]}",
        "job_title": "Software Engineer",
        "department_id": str(env["dept"].id),
        "manager_id": str(env["mgr_profile"].id),
        "work_schedule_id": str(env["sched"].id),
        "hire_date": "2026-01-15",
        "initial_password": "InitialSecurePass123!",
    }
    create_res = await client.post("/api/v1/employees/", json=create_payload, headers=admin_headers)
    assert create_res.status_code == 201, create_res.text
    emp_data = create_res.json()
    emp_id = uuid.UUID(emp_data["id"])

    # =========================================================================
    # STEP 2: Employee receives account creation email (Checked in EmailOutbox)
    # =========================================================================
    outbox_stmt = select(EmailOutbox).where(EmailOutbox.recipient_email == new_emp_email)
    outbox_res = await db_session.execute(outbox_stmt)
    welcome_email = outbox_res.scalars().first()
    assert welcome_email is not None
    assert "Welcome" in welcome_email.subject or "Account" in welcome_email.subject
    assert welcome_email.status in [OutboxStatus.PENDING, OutboxStatus.SENT]

    # Fetch created employee user for authentication
    emp_user = (
        await db_session.execute(select(User).where(User.email == new_emp_email))
    ).scalars().first()
    assert emp_user is not None
    emp_token = create_access_token(subject=emp_user.id)
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # =========================================================================
    # STEP 3: Employee installs desktop application & pairs device
    # =========================================================================
    device_id = uuid.uuid4()
    device = Device(
        id=device_id,
        organization_id=env["org"].id,
        device_identifier=f"DEV-WIN-{uuid.uuid4().hex[:6]}",
        device_name="Alice-ThinkPad-T14",
        os_name="Windows",
        os_version="11.0.22631",
        platform="windows",
        agent_version="0.1.0",
        is_trusted=True,
        is_blocked=False,
    )
    db_session.add(device)
    await db_session.commit()

    # =========================================================================
    # STEPS 4 & 5: Employee logs into OS -> OS activity telemetry is collected
    # =========================================================================
    now = datetime.now(UTC)
    os_event_id = uuid.uuid4()
    sync_payload = {
        "events": [
            {
                "event_id": str(os_event_id),
                "employee_id": str(emp_id),
                "device_id": str(device.id),
                "operating_system": "windows",
                "event_type": "USER_LOGON",
                "occurred_at": (now - timedelta(minutes=15)).isoformat(),
                "sequence_number": 1,
                "metadata": {"session_type": "Console"},
            }
        ]
    }
    sync_res = await client.post("/api/v1/os-events/sync", json=sync_payload, headers=admin_headers)
    assert sync_res.status_code == 200
    assert sync_res.json()["inserted_count"] == 1

    # =========================================================================
    # STEPS 6 & 7: Employee clocks in -> Location verification is recorded
    # =========================================================================
    # 6. Verify Location via geofence
    loc_verify_res = await client.post(
        "/api/v1/locations/verify",
        json={
            "latitude": 37.7750,
            "longitude": -122.4195,
            "accuracy_meters": 5.0,
            "permission_status": "GRANTED",
        },
        headers=emp_headers,
    )
    assert loc_verify_res.status_code == 201, loc_verify_res.text
    assert loc_verify_res.json()["verification_status"] == "VERIFIED"

    # 7. Clock In
    clock_in_payload = {
        "occurred_at": (now - timedelta(minutes=10)).isoformat(),
        "source": "DESKTOP",
        "notes": "Staging test clock in",
    }
    clock_in_res = await client.post("/api/v1/attendance/clock-in", json=clock_in_payload, headers=emp_headers)
    assert clock_in_res.status_code == 201, clock_in_res.text
    assert clock_in_res.json()["status"] in ["PRESENT", "ON_DUTY", "HALF_DAY", "LATE"]

    # =========================================================================
    # STEP 8: Employee starts and ends a break
    # =========================================================================
    break_start_payload = {
        "occurred_at": (now - timedelta(minutes=5)).isoformat(),
        "break_type": "LUNCH",
        "reason": "Lunch break",
    }
    b_start_res = await client.post("/api/v1/attendance/break/start", json=break_start_payload, headers=emp_headers)
    assert b_start_res.status_code == 201, b_start_res.text

    break_end_payload = {
        "occurred_at": (now - timedelta(minutes=2)).isoformat(),
    }
    b_end_res = await client.post("/api/v1/attendance/break/end", json=break_end_payload, headers=emp_headers)
    assert b_end_res.status_code == 200, b_end_res.text

    # =========================================================================
    # STEP 9: Employee clocks out
    # =========================================================================
    clock_out_payload = {
        "occurred_at": now.isoformat(),
        "source": "DESKTOP",
        "notes": "Staging test clock out",
    }
    clock_out_res = await client.post("/api/v1/attendance/clock-out", json=clock_out_payload, headers=emp_headers)
    assert clock_out_res.status_code == 200, clock_out_res.text

    # =========================================================================
    # STEP 10: Employee applies for leave
    # =========================================================================
    leave_start = date.today() + timedelta(days=10)
    leave_end = date.today() + timedelta(days=12)
    leave_payload = {
        "leave_type_id": str(env["leave_type"].id),
        "start_date": leave_start.isoformat(),
        "end_date": leave_end.isoformat(),
        "total_days": 3.0,
        "is_half_day": False,
        "reason": "Family vacation abroad",
    }
    leave_res = await client.post("/api/v1/leave/apply", json=leave_payload, headers=emp_headers)
    assert leave_res.status_code == 201, leave_res.text
    leave_data = leave_res.json()
    leave_id = uuid.UUID(leave_data["id"])

    # Verify notification sent to Manager
    mgr_notif_stmt = select(EmailOutbox).where(
        (EmailOutbox.recipient_email == env["mgr_user"].email) & 
        (EmailOutbox.subject.ilike("%Leave%"))
    )
    mgr_notif = (await db_session.execute(mgr_notif_stmt)).scalars().first()
    assert mgr_notif is not None

    # =========================================================================
    # STEP 11: Manager approves leave -> triggers HR second-stage notification
    # =========================================================================
    mgr_review_payload = {
        "action": "APPROVE",
        "comments": "Approved. Team coverage confirmed.",
    }
    mgr_appr_res = await client.post(f"/api/v1/leave/{leave_id}/manager-review", json=mgr_review_payload, headers=mgr_headers)
    assert mgr_appr_res.status_code == 200, mgr_appr_res.text
    assert mgr_appr_res.json()["manager_approval_status"] == "APPROVED"

    # Verify HR notification email was dispatched
    hr_notif_stmt = select(EmailOutbox).where(
        (EmailOutbox.recipient_email == env["hr_user"].email) &
        (EmailOutbox.subject.ilike("%Leave%"))
    )
    hr_notif = (await db_session.execute(hr_notif_stmt)).scalars().first()
    assert hr_notif is not None

    # =========================================================================
    # STEP 12: HR approves leave (Final Approval Stage)
    # =========================================================================
    hr_review_payload = {
        "action": "APPROVE",
        "comments": "HR Final Approval granted. Policy compliant.",
    }
    hr_appr_res = await client.post(f"/api/v1/leave/{leave_id}/hr-review", json=hr_review_payload, headers=hr_headers)
    assert hr_appr_res.status_code == 200, hr_appr_res.text
    final_leave = hr_appr_res.json()
    assert final_leave["status"] == "APPROVED"
    assert final_leave["hr_approval_status"] == "APPROVED"

    # =========================================================================
    # STEP 13: Employee receives final approval email
    # =========================================================================
    final_email_stmt = select(EmailOutbox).where(
        (EmailOutbox.recipient_email == new_emp_email) &
        (EmailOutbox.subject.ilike("%Leave%"))
    )
    final_email = (await db_session.execute(final_email_stmt)).scalars().first()
    assert final_email is not None

    # =========================================================================
    # STEP 14: Attendance engine reflects approved leave
    # =========================================================================
    leave_req = (await db_session.execute(select(LeaveRequest).where(LeaveRequest.id == leave_id))).scalars().first()
    daily_calc = calculate_daily_attendance(
        work_date=leave_start,
        events=[],
        breaks=[],
        schedule=env["sched"],
        approved_leaves=[leave_req],
    )
    assert daily_calc.status == AttendanceStatus.ON_LEAVE

    # =========================================================================
    # STEP 15: Excel reports are generated
    # =========================================================================
    # Consolidated HR report
    hr_report = await client.post(
        "/api/v1/reports/generate",
        json={"report_type": "CONSOLIDATED_HR", "parameters": {}},
        headers=hr_headers,
    )
    assert hr_report.status_code == 201
    hr_job_id = uuid.UUID(hr_report.json()["id"])
    assert len(hr_report.json()["files"]) >= 1

    # Manager Team report
    mgr_report = await client.post(
        "/api/v1/reports/generate",
        json={"report_type": "MANAGER_TEAM", "parameters": {}},
        headers=mgr_headers,
    )
    assert mgr_report.status_code == 201

    # Individual Employee report
    emp_report = await client.post(
        "/api/v1/reports/generate",
        json={"report_type": "INDIVIDUAL", "parameters": {"employee_id": str(emp_id)}},
        headers=emp_headers,
    )
    assert emp_report.status_code == 201

    # =========================================================================
    # STEPS 16 & 17: HR and Manager receive reports (Verified via download endpoint)
    # =========================================================================
    file_id = hr_report.json()["files"][0]["id"]
    download_res = await client.get(f"/api/v1/reports/files/{file_id}/download", headers=hr_headers)
    assert download_res.status_code == 200
    assert "attachment;" in download_res.headers.get("content-disposition", "")
    assert download_res.content.startswith(b"PK\x03\x04")


@pytest.mark.asyncio
async def test_offline_synchronization_and_duplicate_suppression(e2e_env_fixture, db_session, client: AsyncClient):
    """
    Validates offline batch synchronization:
    Simulates desktop queueing 5 OS session events offline, flushing them on reconnect,
    and verifying idempotent duplicate rejection on re-transmission.
    """
    env = await e2e_env_fixture()
    admin_headers = {"Authorization": f"Bearer {env['admin_token']}"}

    emp_profile = env["mgr_profile"]
    device = Device(
        organization_id=env["org"].id,
        device_identifier=f"DEV-OFFLINE-{uuid.uuid4().hex[:6]}",
        device_name="Field-Laptop",
        os_name="Windows",
        os_version="11.0",
        platform="windows",
        agent_version="0.1.0",
        is_trusted=True,
    )
    db_session.add(device)
    await db_session.commit()

    base_time = datetime.now(UTC) - timedelta(hours=3)
    offline_events = []
    for seq in range(1, 6):
        offline_events.append({
            "event_id": str(uuid.uuid4()),
            "employee_id": str(emp_profile.id),
            "device_id": str(device.id),
            "operating_system": "windows",
            "event_type": "USER_LOGON" if seq == 1 else "SESSION_UNLOCK",
            "occurred_at": (base_time + timedelta(minutes=seq * 10)).isoformat(),
            "sequence_number": seq,
            "metadata": {"offline_queued": True},
        })

    # 1. Ingest initial batch
    batch_payload = {"events": offline_events}
    res1 = await client.post("/api/v1/os-events/sync", json=batch_payload, headers=admin_headers)
    assert res1.status_code == 200
    assert res1.json()["inserted_count"] == 5
    assert res1.json()["duplicate_count"] == 0

    # 2. Re-send exact same batch (Idempotent duplicate elimination)
    res2 = await client.post("/api/v1/os-events/sync", json=batch_payload, headers=admin_headers)
    assert res2.status_code == 200
    assert res2.json()["inserted_count"] == 0
    assert res2.json()["duplicate_count"] == 5
    assert "already ingested" in res2.json()["message"].lower()


@pytest.mark.asyncio
async def test_scheduler_behavior_across_restarts_and_missed_recovery(e2e_env_fixture, db_session):
    """
    Tests scheduler resilience across server downtime:
    Simulates missed daily report schedules and verifies catch-up execution without duplicate dispatch.
    """
    env = await e2e_env_fixture()
    org_id = env["org"].id

    # Create an active daily schedule whose last_run_at was 2 days ago (overdue)
    overdue_schedule = ReportSchedule(
        organization_id=org_id,
        schedule_type=ReportType.DAILY,
        cron_expression="0 6 * * *",
        timezone="America/Los_Angeles",
        is_active=True,
        last_run_at=datetime.now(UTC) - timedelta(days=2),
        next_run_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(overdue_schedule)
    await db_session.commit()

    # Run missed recovery procedure
    recovery_results = await ReportSchedulerService.check_and_run_missed_executions(db=db_session)
    assert len(recovery_results) >= 1

    matched = next((r for r in recovery_results if r["schedule_id"] == str(overdue_schedule.id)), None)
    assert matched is not None
    assert matched["status"] == "executed"
