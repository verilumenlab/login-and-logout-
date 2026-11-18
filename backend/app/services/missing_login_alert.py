"""
Missing login alert after grace window (10:30 Asia/Kolkata).

After 10:30, find employees who have not logged in and email:
  - the employee (name + email — please log in)
  - their manager(s)
  - HR
  - Admin

Emails send automatically (Celery or Scan now). History is kept on Missing Login.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.office_policy import (
    DEFAULT_SCHEDULE_NAME,
    LATE_LOGIN_GRACE_MINUTES,
    MISSING_LOGIN_ALERT,
    OFFICE_START,
)
from app.models.attendance import AttendanceDay
from app.models.auth import Role, User
from app.models.employee import EmployeeProfile, EmploymentStatus, ManagerAssignment
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.missing_login import MissingLoginAlert, MissingLoginAlertStatus
from app.models.organization import Organization
from app.models.schedule import Holiday, WorkSchedule
from app.services.attendance_engine import ensure_utc, local_work_date, org_zone
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

HR_ADMIN_ROLE_NAMES = (
    "HR Manager",
    "Administrator",
    "Super Administrator",
    "Super Admin",
    "Admin",
    "HR",
    "Human Resources",
)


def missing_login_cutoff_utc(work_date) -> datetime:
    """10:30 local on the given work date, as UTC."""
    tz = org_zone()
    local = datetime.combine(work_date, MISSING_LOGIN_ALERT, tzinfo=tz)
    return local.astimezone(UTC)


def _scheduled_shift_label(schedule: WorkSchedule | None) -> str:
    if schedule and schedule.shift_start_time and schedule.shift_end_time:
        return (
            f"{schedule.shift_start_time.strftime('%H:%M')} – "
            f"{schedule.shift_end_time.strftime('%H:%M')}"
        )
    return (
        f"{OFFICE_START.strftime('%H:%M')} – "
        f"(login expected by {MISSING_LOGIN_ALERT.strftime('%H:%M')})"
    )


def _is_working_day(work_date, schedule: WorkSchedule | None, holidays: set) -> bool:
    if work_date in holidays:
        return False
    working_days = [1, 2, 3, 4, 5]
    if schedule and schedule.working_days:
        working_days = list(schedule.working_days)
    return work_date.isoweekday() in working_days


async def _hr_admin_recipients(
    db: AsyncSession,
    organization_id: uuid.UUID,
) -> list[tuple[str, str]]:
    stmt = (
        select(User)
        .join(Role, Role.id == User.role_id)
        .options(selectinload(User.employee_profile))
        .where(
            User.organization_id == organization_id,
            User.is_active.is_(True),
            Role.name.in_(HR_ADMIN_ROLE_NAMES),
        )
    )
    users = (await db.execute(stmt)).scalars().all()
    recipients: list[tuple[str, str]] = []
    seen: set[str] = set()
    for user in users:
        if not user.email:
            continue
        email = user.email.strip().lower()
        if email in seen:
            continue
        seen.add(email)
        emp = user.employee_profile
        if emp:
            name = f"{emp.first_name} {emp.last_name}".strip()
        else:
            name = user.full_name or user.email
        recipients.append((email, name or "HR / Admin"))
    return recipients


async def _send_alert_emails(
    db: AsyncSession,
    alert: MissingLoginAlert,
) -> list[str]:
    """Send missing-login emails for an approved alert. Returns recipient emails."""
    emp_stmt = (
        select(EmployeeProfile)
        .options(
            selectinload(EmployeeProfile.user),
            selectinload(EmployeeProfile.department),
            selectinload(EmployeeProfile.direct_managers)
            .selectinload(ManagerAssignment.manager)
            .selectinload(EmployeeProfile.user),
        )
        .where(EmployeeProfile.id == alert.employee_id)
    )
    emp = (await db.execute(emp_stmt)).scalars().first()
    if not emp or not emp.user or not emp.user.email:
        return []

    employee_name = alert.employee_name
    employee_email = alert.employee_email.strip().lower()
    department_name = alert.department_name or "Operations"
    scheduled_shift = alert.scheduled_shift or _scheduled_shift_label(None)
    work_date_str = alert.work_date.isoformat()

    recipients: list[tuple[str, str, str]] = [
        (employee_email, employee_name, "employee"),
    ]

    for assignment in emp.direct_managers or []:
        mgr = assignment.manager
        if not mgr or not mgr.user or not mgr.user.email:
            continue
        mgr_email = mgr.user.email.strip().lower()
        mgr_name = f"{mgr.first_name} {mgr.last_name}".strip() or "Manager"
        recipients.append((mgr_email, mgr_name, "manager"))

    for email, name in await _hr_admin_recipients(db, alert.organization_id):
        recipients.append((email, name, "hr_admin"))

    seen: set[str] = set()
    unique: list[tuple[str, str, str]] = []
    for email, name, kind in recipients:
        if email in seen:
            continue
        seen.add(email)
        unique.append((email, name, kind))

    notified: list[str] = []
    for recipient_email, recipient_name, kind in unique:
        outbox = await EmailService.notify_missing_login(
            db=db,
            organization_id=alert.organization_id,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            employee_name=employee_name,
            employee_email=employee_email,
            employee_code=alert.employee_code,
            work_date=work_date_str,
            scheduled_shift=scheduled_shift,
            department_name=department_name,
            grace_minutes=LATE_LOGIN_GRACE_MINUTES,
            alert_time=MISSING_LOGIN_ALERT.strftime("%H:%M"),
            audience=kind,
        )
        if outbox:
            notified.append(recipient_email)
    return notified


async def run_missing_login_alerts(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    organization_id: uuid.UUID | None = None,
    auto_send: bool = True,
) -> dict[str, Any]:
    """
    After 10:30 local, create alerts for employees with no login and (by default)
    email the employee + manager + HR + admin with the person's name and email.
    """
    now = ensure_utc(now) or datetime.now(UTC)
    work_date = local_work_date(now)
    cutoff = missing_login_cutoff_utc(work_date)

    if now < cutoff:
        return {
            "status": "skipped",
            "reason": "before_missing_login_cutoff",
            "work_date": work_date.isoformat(),
            "cutoff": cutoff.isoformat(),
            "queued_employees": [],
            "queued_count": 0,
            "sent_count": 0,
        }

    org_stmt = select(Organization).where(Organization.is_active.is_(True))
    if organization_id is not None:
        org_stmt = org_stmt.where(Organization.id == organization_id)
    orgs = (await db.execute(org_stmt)).scalars().all()

    queued: list[dict[str, Any]] = []
    sent_rows: list[dict[str, Any]] = []

    for org in orgs:
        default_schedule = (
            await db.execute(
                select(WorkSchedule).where(
                    WorkSchedule.organization_id == org.id,
                    WorkSchedule.is_active.is_(True),
                    WorkSchedule.name == DEFAULT_SCHEDULE_NAME,
                )
            )
        ).scalars().first()
        if default_schedule is None:
            default_schedule = (
                await db.execute(
                    select(WorkSchedule)
                    .where(
                        WorkSchedule.organization_id == org.id,
                        WorkSchedule.is_active.is_(True),
                    )
                    .order_by(WorkSchedule.created_at.asc())
                    .limit(1)
                )
            ).scalars().first()

        holidays = set(
            (
                await db.execute(
                    select(Holiday.holiday_date).where(
                        Holiday.organization_id == org.id,
                        Holiday.holiday_date == work_date,
                        Holiday.is_optional.is_(False),
                    )
                )
            ).scalars().all()
        )

        if not _is_working_day(work_date, default_schedule, holidays):
            continue

        emp_stmt = (
            select(EmployeeProfile)
            .join(User, User.id == EmployeeProfile.user_id)
            .join(Role, Role.id == User.role_id)
            .options(
                selectinload(EmployeeProfile.user),
                selectinload(EmployeeProfile.department),
                selectinload(EmployeeProfile.work_schedule),
            )
            .where(
                EmployeeProfile.organization_id == org.id,
                EmployeeProfile.employment_status.in_(
                    [EmploymentStatus.ACTIVE, EmploymentStatus.PROBATION]
                ),
                User.is_active.is_(True),
                func.lower(Role.name) == "employee",
            )
        )
        employees = (await db.execute(emp_stmt)).scalars().all()
        if not employees:
            continue

        emp_ids = [e.id for e in employees]

        logged_in_ids = set(
            (
                await db.execute(
                    select(AttendanceDay.employee_id).where(
                        AttendanceDay.employee_id.in_(emp_ids),
                        AttendanceDay.work_date == work_date,
                        AttendanceDay.shift_start.is_not(None),
                    )
                )
            ).scalars().all()
        )

        on_leave_ids = set(
            (
                await db.execute(
                    select(LeaveRequest.employee_id).where(
                        LeaveRequest.employee_id.in_(emp_ids),
                        LeaveRequest.status == LeaveStatus.APPROVED,
                        LeaveRequest.start_date <= work_date,
                        LeaveRequest.end_date >= work_date,
                    )
                )
            ).scalars().all()
        )

        existing = (
            await db.execute(
                select(MissingLoginAlert).where(
                    MissingLoginAlert.organization_id == org.id,
                    MissingLoginAlert.work_date == work_date,
                    MissingLoginAlert.employee_id.in_(emp_ids),
                )
            )
        ).scalars().all()
        existing_by_emp = {row.employee_id: row for row in existing}

        for emp in employees:
            if emp.id in logged_in_ids or emp.id in on_leave_ids:
                continue
            if not emp.user or not emp.user.email:
                continue

            schedule = emp.work_schedule or default_schedule
            if not _is_working_day(work_date, schedule, holidays):
                continue

            prior = existing_by_emp.get(emp.id)
            if prior is not None:
                # Already handled today — do not recreate or re-send.
                continue

            employee_name = f"{emp.first_name} {emp.last_name}".strip()
            employee_email = emp.user.email.strip().lower()
            alert = MissingLoginAlert(
                organization_id=org.id,
                employee_id=emp.id,
                work_date=work_date,
                employee_name=employee_name,
                employee_email=employee_email,
                employee_code=emp.employee_code,
                department_name=emp.department.name if emp.department else None,
                scheduled_shift=_scheduled_shift_label(schedule),
                status=MissingLoginAlertStatus.PENDING,
            )
            db.add(alert)
            await db.flush()

            row = {
                "employee_id": str(emp.id),
                "employee_name": employee_name,
                "employee_email": employee_email,
                "status": MissingLoginAlertStatus.PENDING.value,
                "emails_sent_count": 0,
            }

            if auto_send:
                try:
                    notified = await _send_alert_emails(db, alert)
                    alert.status = MissingLoginAlertStatus.SENT
                    alert.reviewed_at = now
                    alert.review_note = "Auto-sent after 10:30 — employee not logged in"
                    alert.emails_sent_count = len(notified)
                    row["status"] = MissingLoginAlertStatus.SENT.value
                    row["emails_sent_count"] = len(notified)
                    row["notified"] = notified
                    sent_rows.append(row)
                except Exception:
                    logger.exception(
                        "Failed auto-sending missing-login mail for %s (%s)",
                        employee_name,
                        employee_email,
                    )
                    row["status"] = MissingLoginAlertStatus.PENDING.value
                    queued.append(row)
            else:
                queued.append(row)

        await db.commit()

    return {
        "status": "success",
        "work_date": work_date.isoformat(),
        "cutoff": cutoff.isoformat(),
        "queued_count": len(queued),
        "queued_employees": queued,
        "sent_count": len(sent_rows),
        "sent_employees": sent_rows,
        "note": (
            "Emails sent automatically to employee, manager, HR, and admin (name + email included)."
            if auto_send
            else "Emails held until Admin/HR approves each alert."
        ),
    }


async def list_missing_login_alerts(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    status: MissingLoginAlertStatus | None = None,
    work_date=None,
    limit: int = 100,
) -> list[MissingLoginAlert]:
    stmt = (
        select(MissingLoginAlert)
        .where(MissingLoginAlert.organization_id == organization_id)
        .order_by(MissingLoginAlert.work_date.desc(), MissingLoginAlert.created_at.desc())
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(MissingLoginAlert.status == status)
    if work_date is not None:
        stmt = stmt.where(MissingLoginAlert.work_date == work_date)
    return list((await db.execute(stmt)).scalars().all())


async def approve_missing_login_alert(
    db: AsyncSession,
    alert_id: uuid.UUID,
    *,
    reviewer: User,
    note: str | None = None,
) -> MissingLoginAlert:
    alert = await db.get(MissingLoginAlert, alert_id)
    if not alert or alert.organization_id != reviewer.organization_id:
        raise ValueError("Alert not found")
    if alert.status == MissingLoginAlertStatus.SENT:
        return alert
    if alert.status != MissingLoginAlertStatus.PENDING:
        raise ValueError(f"Cannot approve alert in status {alert.status.value}")

    notified = await _send_alert_emails(db, alert)
    alert.status = MissingLoginAlertStatus.SENT
    alert.reviewed_by_user_id = reviewer.id
    alert.reviewed_at = datetime.now(UTC)
    alert.review_note = note
    alert.emails_sent_count = len(notified)
    await db.commit()
    await db.refresh(alert)
    return alert


async def reject_missing_login_alert(
    db: AsyncSession,
    alert_id: uuid.UUID,
    *,
    reviewer: User,
    note: str | None = None,
) -> MissingLoginAlert:
    alert = await db.get(MissingLoginAlert, alert_id)
    if not alert or alert.organization_id != reviewer.organization_id:
        raise ValueError("Alert not found")
    if alert.status != MissingLoginAlertStatus.PENDING:
        raise ValueError(f"Cannot reject alert in status {alert.status.value}")

    alert.status = MissingLoginAlertStatus.REJECTED
    alert.reviewed_by_user_id = reviewer.id
    alert.reviewed_at = datetime.now(UTC)
    alert.review_note = note or "Rejected by admin — mail not sent"
    await db.commit()
    await db.refresh(alert)
    return alert


async def approve_all_pending_missing_login_alerts(
    db: AsyncSession,
    *,
    reviewer: User,
    work_date=None,
) -> dict[str, Any]:
    stmt = select(MissingLoginAlert).where(
        MissingLoginAlert.organization_id == reviewer.organization_id,
        MissingLoginAlert.status == MissingLoginAlertStatus.PENDING,
    )
    if work_date is not None:
        stmt = stmt.where(MissingLoginAlert.work_date == work_date)
    pending = list((await db.execute(stmt)).scalars().all())

    sent: list[str] = []
    errors: list[str] = []
    for alert in pending:
        try:
            updated = await approve_missing_login_alert(db, alert.id, reviewer=reviewer)
            sent.append(str(updated.id))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed approving missing login alert %s", alert.id)
            errors.append(f"{alert.employee_email}: {exc}")

    return {
        "status": "success",
        "approved_count": len(sent),
        "approved_ids": sent,
        "errors": errors,
    }
