"""
Missing login alert after 10:30 IST — queue for admin approval, then send on approve.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.office_policy import MISSING_LOGIN_ALERT, OFFICE_START
from app.core.security import get_password_hash
from app.core.seeds import seed_permissions, seed_system_roles
from app.models.attendance import AttendanceDay, AttendanceStatus
from app.models.auth import User
from app.models.department import Department
from app.models.employee import EmployeeProfile, EmploymentStatus, ManagerAssignment
from app.models.leave import LeaveCategory, LeaveRequest, LeaveStatus, LeaveType
from app.models.missing_login import MissingLoginAlert, MissingLoginAlertStatus
from app.models.notification import EmailOutbox
from app.models.organization import Organization
from app.models.schedule import WorkSchedule
from app.services.email_templates import render_email_template
from app.services.missing_login_alert import (
    approve_missing_login_alert,
    missing_login_cutoff_utc,
    reject_missing_login_alert,
    run_missing_login_alerts,
)

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture
async def missing_login_env(db_session: AsyncSession):
    suffix = uuid.uuid4().hex[:6].upper()
    org = Organization(
        name="Missing Login Corp",
        code=f"MLC-{suffix}",
        slug=f"mlc-{suffix.lower()}",
        is_active=True,
    )
    db_session.add(org)
    await db_session.flush()

    perm_map = await seed_permissions(db_session)
    role_map = await seed_system_roles(db_session, perm_map)

    dept = Department(organization_id=org.id, name="Ops", code="OPS")
    db_session.add(dept)
    await db_session.flush()

    schedule = WorkSchedule(
        organization_id=org.id,
        name="Standard Office 9:30–6:30",
        shift_start_time=OFFICE_START,
        shift_end_time=time(18, 30),
        flexible_minutes=60,
        working_days=[1, 2, 3, 4, 5],
        is_active=True,
    )
    db_session.add(schedule)
    await db_session.flush()

    async def make_user(email: str, role_name: str, first: str, last: str):
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
            work_schedule_id=schedule.id,
            employee_code=f"E-{uuid.uuid4().hex[:4].upper()}",
            first_name=first,
            last_name=last,
            hire_date=date(2026, 1, 1),
            employment_status=EmploymentStatus.ACTIVE,
        )
        db_session.add(emp)
        await db_session.flush()
        return user, emp

    admin_user, admin_emp = await make_user(
        f"admin_{suffix.lower()}@mlc.corp", "Administrator", "Ada", "Admin"
    )
    hr_user, hr_emp = await make_user(
        f"hr_{suffix.lower()}@mlc.corp", "HR Manager", "Hana", "HR"
    )
    mgr_user, mgr_emp = await make_user(
        f"mgr_{suffix.lower()}@mlc.corp", "Department Manager", "Mark", "Manager"
    )
    emp_user, emp = await make_user(
        f"emp_{suffix.lower()}@mlc.corp", "Employee", "Eve", "Employee"
    )

    db_session.add(
        ManagerAssignment(
            organization_id=org.id,
            manager_id=mgr_emp.id,
            employee_id=emp.id,
            is_primary=True,
        )
    )
    await db_session.commit()

    return {
        "org": org,
        "schedule": schedule,
        "admin": (admin_user, admin_emp),
        "hr": (hr_user, hr_emp),
        "mgr": (mgr_user, mgr_emp),
        "emp": (emp_user, emp),
    }


def _weekday_after_cutoff() -> datetime:
    local = datetime.now(IST)
    while local.isoweekday() > 5:
        local -= timedelta(days=1)
    return local.replace(hour=10, minute=35, second=0, microsecond=0)


@pytest.mark.asyncio
async def test_missing_login_template_includes_name_and_email():
    subject, html, text = render_email_template(
        "attendance_missing_alert",
        {
            "recipient_name": "Ada Admin",
            "employee_name": "Eve Employee",
            "employee_email": "eve@mlc.corp",
            "employee_code": "E-1001",
            "work_date": "2026-11-18",
            "scheduled_shift": "09:30 – 18:30",
            "department_name": "Ops",
            "grace_minutes": 60,
            "alert_time": "10:30",
        },
    )
    assert "Eve Employee" in subject
    assert "eve@mlc.corp" in html
    assert "Name: Eve Employee" in text
    assert MISSING_LOGIN_ALERT.strftime("%H:%M") in subject or "10:30" in subject


@pytest.mark.asyncio
async def test_skips_before_1030(db_session: AsyncSession, missing_login_env):
    org = missing_login_env["org"]
    work_date = date(2026, 11, 18)
    before = missing_login_cutoff_utc(work_date) - timedelta(minutes=5)

    result = await run_missing_login_alerts(
        db_session, now=before, organization_id=org.id
    )
    assert result["status"] == "skipped"
    assert result["queued_count"] == 0


@pytest.mark.asyncio
async def test_queues_pending_until_admin_approves(
    db_session: AsyncSession, missing_login_env
):
    org = missing_login_env["org"]
    emp_user, emp = missing_login_env["emp"]
    admin_user, _ = missing_login_env["admin"]
    mgr_user, _ = missing_login_env["mgr"]
    hr_user, _ = missing_login_env["hr"]

    now_utc = _weekday_after_cutoff().astimezone(UTC)

    result = await run_missing_login_alerts(
        db_session, now=now_utc, organization_id=org.id
    )
    assert result["status"] == "success"
    assert result["queued_count"] == 1

    # No emails until approval
    outboxes = (
        await db_session.execute(
            select(EmailOutbox).where(EmailOutbox.organization_id == org.id)
        )
    ).scalars().all()
    assert len(outboxes) == 0

    alert = (
        await db_session.execute(
            select(MissingLoginAlert).where(
                MissingLoginAlert.employee_id == emp.id,
            )
        )
    ).scalars().first()
    assert alert is not None
    assert alert.status == MissingLoginAlertStatus.PENDING
    assert alert.employee_email == emp_user.email.lower()

    # Approve → send
    sent = await approve_missing_login_alert(db_session, alert.id, reviewer=admin_user)
    assert sent.status == MissingLoginAlertStatus.SENT
    assert sent.emails_sent_count >= 3

    outboxes2 = (
        await db_session.execute(
            select(EmailOutbox).where(EmailOutbox.organization_id == org.id)
        )
    ).scalars().all()
    recipient_emails = {o.recipient_email for o in outboxes2}
    assert emp_user.email.lower() in recipient_emails
    assert mgr_user.email.lower() in recipient_emails
    assert hr_user.email.lower() in recipient_emails
    assert admin_user.email.lower() in recipient_emails


@pytest.mark.asyncio
async def test_reject_does_not_send_mail(db_session: AsyncSession, missing_login_env):
    org = missing_login_env["org"]
    admin_user, _ = missing_login_env["admin"]
    now_utc = _weekday_after_cutoff().astimezone(UTC)

    await run_missing_login_alerts(db_session, now=now_utc, organization_id=org.id)
    alert = (
        await db_session.execute(
            select(MissingLoginAlert).where(MissingLoginAlert.organization_id == org.id)
        )
    ).scalars().first()
    assert alert is not None

    rejected = await reject_missing_login_alert(
        db_session, alert.id, reviewer=admin_user, note="Excuse accepted"
    )
    assert rejected.status == MissingLoginAlertStatus.REJECTED

    outboxes = (
        await db_session.execute(
            select(EmailOutbox).where(EmailOutbox.organization_id == org.id)
        )
    ).scalars().all()
    assert len(outboxes) == 0


@pytest.mark.asyncio
async def test_skips_when_already_logged_in(db_session: AsyncSession, missing_login_env):
    org = missing_login_env["org"]
    _, emp = missing_login_env["emp"]
    now = _weekday_after_cutoff().astimezone(UTC)
    work_date = now.astimezone(IST).date()

    db_session.add(
        AttendanceDay(
            organization_id=org.id,
            employee_id=emp.id,
            work_date=work_date,
            status=AttendanceStatus.PRESENT,
            shift_start=datetime.combine(work_date, time(9, 40), tzinfo=IST).astimezone(UTC),
        )
    )
    await db_session.commit()

    result = await run_missing_login_alerts(
        db_session, now=now, organization_id=org.id
    )
    assert result["queued_count"] == 0


@pytest.mark.asyncio
async def test_skips_approved_leave(db_session: AsyncSession, missing_login_env):
    org = missing_login_env["org"]
    _, emp = missing_login_env["emp"]
    now = _weekday_after_cutoff().astimezone(UTC)
    work_date = now.astimezone(IST).date()

    leave_type = LeaveType(
        organization_id=org.id,
        name="Casual",
        code=f"CAS-{uuid.uuid4().hex[:4]}",
        category=LeaveCategory.CASUAL,
        annual_allowance=12,
        is_active=True,
    )
    db_session.add(leave_type)
    await db_session.flush()
    db_session.add(
        LeaveRequest(
            organization_id=org.id,
            employee_id=emp.id,
            leave_type_id=leave_type.id,
            start_date=work_date,
            end_date=work_date,
            total_days=1,
            reason="Personal",
            status=LeaveStatus.APPROVED,
        )
    )
    await db_session.commit()

    result = await run_missing_login_alerts(
        db_session, now=now, organization_id=org.id
    )
    assert result["queued_count"] == 0
