"""
Comprehensive Verification Tests for Phase 13: Automated Report Scheduling Engine

Tests:
1. Organization Timezone Support (Daily, Weekly, Monthly date ranges)
2. Daily Report Generation (Consolidated HR, Manager Team, Individual Employee Workbooks)
3. Weekly Report Generation (Working Hours, Absences, Leaves, Late Arrivals)
4. Monthly Report Generation (Executive Audit, Department Summaries, Leave Utilization)
5. Idempotent Execution: Strict Prevention of Duplicate Reports & Duplicate Emails
6. Manual Rerun: Forced On-Demand Regeneration
7. Celery Background Tasks Execution & Failure Retry with Backoff
8. Missed Execution Recovery Across Server Restarts
9. Email Delivery Telemetry & Attachment Verification
10. REST API Schedule Management & RBAC Boundaries
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, get_password_hash
from app.core.seeds import seed_permissions, seed_system_roles
from app.models.attendance import AttendanceDay, AttendanceStatus
from app.models.auth import Role, User
from app.models.department import Department
from app.models.employee import EmployeeProfile, EmploymentStatus, ManagerAssignment
from app.models.leave import ApprovalStatus, LeaveCategory, LeaveRequest, LeaveStatus, LeaveType
from app.models.notification import DeliveryEventType, EmailDeliveryLog, EmailOutbox, OutboxStatus
from app.models.organization import Organization
from app.models.reporting import ReportFile, ReportJob, ReportSchedule, ReportStatus, ReportType
from app.services.report_scheduler_service import ReportSchedulerService
from app.tasks.reporting_tasks import check_missed_executions, run_daily_reports, run_single_schedule


@pytest.fixture
async def setup_scheduler_env(db_session: AsyncSession):
    code_suffix = uuid.uuid4().hex[:6].upper()
    org = Organization(
        name="Apex Scheduling Test Corp",
        code=f"ASTC-{code_suffix}",
        slug=f"astc-{code_suffix.lower()}",
        is_active=True,
    )
    db_session.add(org)
    await db_session.flush()

    perm_map = await seed_permissions(db_session)
    role_map = await seed_system_roles(db_session, perm_map)

    dept = Department(organization_id=org.id, name="Cloud Reliability", code="CRE")
    db_session.add(dept)
    await db_session.flush()

    async def create_user_emp(email: str, role_name: str, first_name: str, last_name: str) -> tuple[User, EmployeeProfile, str]:
        user = User(
            organization_id=org.id,
            role_id=role_map[role_name].id,
            email=email,
            hashed_password=get_password_hash("SecurePass123!"),
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

    admin_user, admin_emp, admin_token = await create_user_emp(
        f"admin_{uuid.uuid4().hex[:4]}@astc.corp", "Administrator", "Alice", "Admin"
    )
    hr_user, hr_emp, hr_token = await create_user_emp(
        f"hr_{uuid.uuid4().hex[:4]}@astc.corp", "HR Manager", "Hannah", "HR"
    )
    mgr_user, mgr_emp, mgr_token = await create_user_emp(
        f"mgr_{uuid.uuid4().hex[:4]}@astc.corp", "Department Manager", "Mark", "Manager"
    )
    sub_user, sub_emp, sub_token = await create_user_emp(
        f"sub_{uuid.uuid4().hex[:4]}@astc.corp", "Employee", "Edward", "Employee"
    )

    # Manager Mark manages Employee Edward
    assignment = ManagerAssignment(
        organization_id=org.id,
        manager_id=mgr_emp.id,
        employee_id=sub_emp.id,
        is_primary=True,
    )
    db_session.add(assignment)

    # Leave Type
    leave_type = LeaveType(
        organization_id=org.id,
        name="Annual Vacation",
        code="VAC",
        category=LeaveCategory.ANNUAL,
        annual_allowance=20,
        is_active=True,
    )
    db_session.add(leave_type)

    # Mock historical Attendance Days
    target_date = date(2026, 11, 11)
    att_sub = AttendanceDay(
        organization_id=org.id,
        employee_id=sub_emp.id,
        work_date=target_date,
        status=AttendanceStatus.PRESENT,
        shift_start=datetime(2026, 11, 11, 9, 0, tzinfo=UTC),
        shift_end=datetime(2026, 11, 11, 17, 30, tzinfo=UTC),
        total_work_minutes=510,
        total_break_minutes=60,
    )
    att_mgr = AttendanceDay(
        organization_id=org.id,
        employee_id=mgr_emp.id,
        work_date=target_date,
        status=AttendanceStatus.PRESENT,
        shift_start=datetime(2026, 11, 11, 8, 45, tzinfo=UTC),
        shift_end=datetime(2026, 11, 11, 18, 0, tzinfo=UTC),
        total_work_minutes=555,
        total_break_minutes=45,
    )
    db_session.add_all([att_sub, att_mgr])

    # Default Schedules
    schedules = await ReportSchedulerService.get_or_create_default_schedules(
        db=db_session,
        organization_id=org.id,
        tz_name="UTC",
    )

    await db_session.commit()

    return {
        "org": org,
        "admin": (admin_user, admin_emp, admin_token),
        "hr": (hr_user, hr_emp, hr_token),
        "mgr": (mgr_user, mgr_emp, mgr_token),
        "sub": (sub_user, sub_emp, sub_token),
        "leave_type": leave_type,
        "schedules": schedules,
    }


def test_timezone_aware_date_ranges():
    """Verify organization timezone-aware date range calculation across DAILY, WEEKLY, and MONTHLY."""
    # Reference date: Wednesday Nov 12, 2026
    ref = date(2026, 11, 12)

    # 1. DAILY: Should return yesterday
    s_d, e_d, key_d = ReportSchedulerService.get_period_date_range(
        ReportType.DAILY, "Asia/Kolkata", target_reference_date=ref
    )
    assert s_d == date(2026, 11, 11)
    assert e_d == date(2026, 11, 11)
    assert key_d == "2026-11-11"

    # 2. WEEKLY: Should return previous week Monday to Sunday
    # For Nov 12, 2026 (Thursday), current week is W46 (Nov 9-15).
    # Previous week was Nov 2 to Nov 8.
    s_w, e_w, key_w = ReportSchedulerService.get_period_date_range(
        ReportType.WEEKLY, "UTC", target_reference_date=ref
    )
    assert s_w == date(2026, 11, 2)
    assert e_w == date(2026, 11, 8)
    assert "W45" in key_w

    # 3. MONTHLY: Should return 1st to last day of previous month
    # For November 2026, previous month was October (31 days)
    s_m, e_m, key_m = ReportSchedulerService.get_period_date_range(
        ReportType.MONTHLY, "America/New_York", target_reference_date=ref
    )
    assert s_m == date(2026, 10, 1)
    assert e_m == date(2026, 10, 31)
    assert key_m == "2026-10"


@pytest.mark.asyncio
async def test_daily_report_generation_all_workbooks(setup_scheduler_env, db_session: AsyncSession):
    """Daily schedule execution produces consolidated HR, Manager team, and Individual workbooks."""
    env = setup_scheduler_env
    org = env["org"]
    mgr_user, mgr_emp, _ = env["mgr"]
    sub_user, sub_emp, _ = env["sub"]

    # Target reference date: Nov 12, so previous day is Nov 11
    ref_date = date(2026, 11, 12)

    success, msg, job = await ReportSchedulerService.execute_scheduled_reporting(
        db=db_session,
        organization_id=org.id,
        schedule_type=ReportType.DAILY,
        target_reference_date=ref_date,
        force=True,
    )

    assert success is True
    assert job is not None
    assert job.status == ReportStatus.COMPLETED

    # Query generated files
    stmt = select(ReportFile).where(ReportFile.report_job_id == job.id)
    res = await db_session.execute(stmt)
    files = res.scalars().all()
    assert len(files) >= 3  # 1 consolidated HR, 1 manager team, at least 1 individual

    # Check Consolidated HR workbook
    hr_files = [f for f in files if f.employee_id is None]
    assert len(hr_files) == 1
    assert os.path.exists(hr_files[0].storage_path)

    # Check Manager workbook
    mgr_files = [f for f in files if f.employee_id == mgr_emp.id]
    assert len(mgr_files) >= 1
    assert os.path.exists(mgr_files[0].storage_path)

    # Check Individual employee workbook
    sub_files = [f for f in files if f.employee_id == sub_emp.id]
    assert len(sub_files) >= 1
    assert os.path.exists(sub_files[0].storage_path)


@pytest.mark.asyncio
async def test_weekly_and_monthly_report_generation(setup_scheduler_env, db_session: AsyncSession):
    """Weekly and Monthly scheduled runs compute metrics and generate workbooks."""
    env = setup_scheduler_env
    org = env["org"]

    ref_date = date(2026, 11, 12)

    # 1. Weekly Run
    w_succ, w_msg, w_job = await ReportSchedulerService.execute_scheduled_reporting(
        db=db_session,
        organization_id=org.id,
        schedule_type=ReportType.WEEKLY,
        target_reference_date=ref_date,
        force=True,
    )
    assert w_succ is True
    assert w_job.status == ReportStatus.COMPLETED

    # 2. Monthly Run
    m_succ, m_msg, m_job = await ReportSchedulerService.execute_scheduled_reporting(
        db=db_session,
        organization_id=org.id,
        schedule_type=ReportType.MONTHLY,
        target_reference_date=ref_date,
        force=True,
    )
    assert m_succ is True
    assert m_job.status == ReportStatus.COMPLETED


@pytest.mark.asyncio
async def test_idempotent_execution_prevents_duplicate_reports(setup_scheduler_env, db_session: AsyncSession):
    """
    Requirement: 'Do not send duplicate reports.'
    Subsequent runs for the same period must skip redundant generation and duplicate email dispatches.
    """
    env = setup_scheduler_env
    org = env["org"]
    ref_date = date(2026, 11, 12)

    # Run 1: Initial run for Nov 11
    succ1, msg1, job1 = await ReportSchedulerService.execute_scheduled_reporting(
        db=db_session,
        organization_id=org.id,
        schedule_type=ReportType.DAILY,
        target_reference_date=ref_date,
        force=False,
    )
    assert succ1 is True
    assert job1.status == ReportStatus.COMPLETED

    # Count outbox emails generated
    outbox_count_stmt = select(EmailOutbox).where(EmailOutbox.organization_id == org.id)
    outbox_res1 = await db_session.execute(outbox_count_stmt)
    initial_email_count = len(outbox_res1.scalars().all())
    assert initial_email_count > 0

    # Run 2: Second run for exact same period without force
    succ2, msg2, job2 = await ReportSchedulerService.execute_scheduled_reporting(
        db=db_session,
        organization_id=org.id,
        schedule_type=ReportType.DAILY,
        target_reference_date=ref_date,
        force=False,
    )
    assert succ2 is True
    assert "already executed (idempotent duplicate skipped)" in msg2
    assert job2.id == job1.id  # Returns existing completed job

    # Verify NO duplicate emails were created
    outbox_res2 = await db_session.execute(outbox_count_stmt)
    final_email_count = len(outbox_res2.scalars().all())
    assert final_email_count == initial_email_count  # Strictly zero duplicate emails sent!


@pytest.mark.asyncio
async def test_manual_rerun_with_force(setup_scheduler_env, db_session: AsyncSession):
    """When force=True is provided, manual rerun creates a distinct execution run."""
    env = setup_scheduler_env
    org = env["org"]
    ref_date = date(2026, 11, 12)

    succ1, _, job1 = await ReportSchedulerService.execute_scheduled_reporting(
        db=db_session,
        organization_id=org.id,
        schedule_type=ReportType.DAILY,
        target_reference_date=ref_date,
        force=False,
    )

    # Force rerun
    succ2, _, job2 = await ReportSchedulerService.execute_scheduled_reporting(
        db=db_session,
        organization_id=org.id,
        schedule_type=ReportType.DAILY,
        target_reference_date=ref_date,
        force=True,
    )
    assert succ2 is True
    assert job2.id != job1.id  # New job created for forced rerun


@pytest.mark.asyncio
async def test_missed_execution_recovery_across_restarts(setup_scheduler_env, db_session: AsyncSession):
    """
    Requirement: 'Test scheduler behavior across restarts and missed executions.'
    System detects missed runs on startup and executes catch-up reporting.
    """
    env = setup_scheduler_env
    org = env["org"]

    # Delete any existing jobs for this org to simulate missed execution
    del_jobs = select(ReportJob).where(ReportJob.organization_id == org.id)
    res = await db_session.execute(del_jobs)
    for j in res.scalars().all():
        await db_session.delete(j)
    await db_session.commit()

    # Step 1: Run recovery check
    results = await ReportSchedulerService.check_and_run_missed_executions(db_session)
    assert len(results) >= 3

    # At least one missed execution should have been detected and executed
    executed_items = [r for r in results if r["status"] == "executed"]
    assert len(executed_items) >= 1

    # Step 2: Running check again immediately should report all are skipped / up to date
    results_after = await ReportSchedulerService.check_and_run_missed_executions(db_session)
    skipped_items = [r for r in results_after if r["status"] == "skipped"]
    assert len(skipped_items) >= len(executed_items)


@pytest.mark.asyncio
async def test_email_delivery_tracking_with_workbooks(setup_scheduler_env, db_session: AsyncSession):
    """Verifies that scheduled runs enqueue transactional emails with attachments and delivery logs."""
    env = setup_scheduler_env
    org = env["org"]
    ref_date = date(2026, 11, 12)

    await ReportSchedulerService.execute_scheduled_reporting(
        db=db_session,
        organization_id=org.id,
        schedule_type=ReportType.DAILY,
        target_reference_date=ref_date,
        force=True,
    )

    # Inspect Outbox
    stmt = (
        select(EmailOutbox)
        .options(selectinload(EmailOutbox.delivery_logs))
        .where(
            EmailOutbox.organization_id == org.id,
            EmailOutbox.subject.ilike("%Daily Attendance Summary%"),
        )
    )
    res = await db_session.execute(stmt)
    emails = res.scalars().all()
    assert len(emails) >= 1

    # Check attachment and delivery log
    email = emails[0]
    assert email.status == OutboxStatus.SENT
    assert email.attachments is not None
    assert ".xlsx" in email.attachments
    assert len(email.delivery_logs) >= 1
    assert email.delivery_logs[0].event_type == DeliveryEventType.DELIVERED


@pytest.mark.asyncio
async def test_schedule_management_api_endpoints(client: AsyncClient, setup_scheduler_env):
    """Tests /api/v1/schedules REST API endpoints, updates, manual rerun, and RBAC."""
    env = setup_scheduler_env
    _, _, hr_token = env["hr"]
    _, _, sub_token = env["sub"]

    hr_headers = {"Authorization": f"Bearer {hr_token}"}
    sub_headers = {"Authorization": f"Bearer {sub_token}"}

    # 1. List schedules by HR
    list_res = await client.get("/api/v1/schedules/", headers=hr_headers)
    assert list_res.status_code == 200
    schedules = list_res.json()
    assert len(schedules) >= 3
    sched_types = [s["schedule_type"] for s in schedules]
    assert "DAILY" in sched_types
    assert "WEEKLY" in sched_types
    assert "MONTHLY" in sched_types

    # 2. RBAC: Employee cannot list schedules
    emp_res = await client.get("/api/v1/schedules/", headers=sub_headers)
    assert emp_res.status_code == 403

    # 3. Update schedule configuration
    sched_id = schedules[0]["id"]
    put_res = await client.put(
        f"/api/v1/schedules/{sched_id}",
        headers=hr_headers,
        json={
            "cron_expression": "30 5 * * *",
            "timezone": "Asia/Kolkata",
            "is_active": True,
            "send_email": True,
        },
    )
    assert put_res.status_code == 200
    updated = put_res.json()
    assert updated["cron_expression"] == "30 5 * * *"
    assert updated["timezone"] == "Asia/Kolkata"

    # 4. Manual on-demand rerun endpoint
    run_res = await client.post(
        f"/api/v1/schedules/{sched_id}/run",
        headers=hr_headers,
        json={"force": True, "reference_date": "2026-11-12"},
    )
    assert run_res.status_code == 200
    run_job = run_res.json()
    assert run_job["status"] == "COMPLETED"
    assert len(run_job["files"]) >= 1

    # 5. Check missed recovery endpoint
    missed_res = await client.post("/api/v1/schedules/check-missed", headers=hr_headers)
    assert missed_res.status_code == 200
    assert missed_res.json()["status"] == "success"


def test_celery_tasks_and_retry_on_failure(monkeypatch):
    """Test Celery task wrapper and retry backoff mechanism."""
    # 1. Test check_missed_executions Celery task
    mock_called = False

    async def mock_check_missed(db):
        nonlocal mock_called
        mock_called = True
        return [{"schedule_id": "test-id", "status": "skipped", "message": "Up to date"}]

    monkeypatch.setattr(
        "app.services.report_scheduler_service.ReportSchedulerService.check_and_run_missed_executions",
        mock_check_missed,
    )

    result = check_missed_executions()
    assert result["status"] == "success"
    assert result["checked_schedules"] == 1
    assert mock_called is True

    # 2. Test Celery failure retry handling
    retried = False

    def fake_retry(exc=None, countdown=None):
        nonlocal retried
        retried = True
        assert countdown == 60  # Initial retry delay
        raise RuntimeError("CeleryRetrySimulated")

    monkeypatch.setattr(run_daily_reports, "retry", fake_retry)

    def failing_run_async(coro):
        coro.close()
        raise RuntimeError("Database connection timeout")

    monkeypatch.setattr("app.tasks.reporting_tasks.run_async", failing_run_async)

    with pytest.raises(RuntimeError) as exc_info:
        run_daily_reports.apply(throw=True)
    assert retried is True
    assert "CeleryRetrySimulated" in str(exc_info.value)

