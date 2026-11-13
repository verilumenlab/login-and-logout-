"""
Employee Presence Engine

Turns desktop-agent signals into attendance:
- LOGIN  = earliest of (app login, laptop Wi-Fi connected)  -> opens a session (clock-in)
- LOGOUT = latest of (app logout, laptop Wi-Fi disconnected) -> closes the session (clock-out)

Every raw signal is stored as a PresenceEvent so the employee and HR can see exactly
when the app was used and when the laptop joined or left a Wi-Fi network.
"""

from __future__ import annotations

import calendar
import hashlib
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.attendance import (
    AttendanceDay,
    AttendanceEvent,
    AttendanceEventType,
    AttendanceSource,
    AttendanceStatus,
)
from app.models.auth import Role, User
from app.models.employee import EmployeeProfile, EmploymentStatus
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.presence import (
    LOGIN_EVENT_TYPES,
    PresenceAttendanceAction,
    PresenceEvent,
    PresenceEventType,
)
from app.models.schedule import Holiday
from app.schemas.presence import (
    PresenceDay,
    PresenceEventIn,
    PresenceEventOut,
    PresenceEventResult,
    PresenceMonthSummary,
    TeamPresenceCounts,
    TeamPresenceRow,
)
from app.services.attendance_engine import (
    determine_work_date_for_clock_in,
    ensure_utc,
    is_clock_in,
    recalculate_attendance_day,
)

MAX_EVENT_AGE = timedelta(days=7)
MAX_CLOCK_SKEW = timedelta(minutes=5)
DEFAULT_WORKING_WEEKDAYS = [1, 2, 3, 4, 5]


def _attendance_client_event_id(employee_id: uuid.UUID, client_event_id: str) -> str:
    digest = hashlib.sha256(f"{employee_id}:{client_event_id}".encode()).hexdigest()[:40]
    return f"presence:{digest}"


async def _open_session(db: AsyncSession, employee_id: uuid.UUID) -> tuple[AttendanceDay, datetime] | None:
    """Returns (day, last clock-in time) when the employee's latest attendance day is still open."""
    day = (
        await db.execute(
            select(AttendanceDay)
            .where(AttendanceDay.employee_id == employee_id, AttendanceDay.shift_start.is_not(None))
            .order_by(AttendanceDay.work_date.desc())
            .limit(1)
        )
    ).scalars().first()
    if day is None:
        return None

    events = (
        await db.execute(
            select(AttendanceEvent)
            .where(AttendanceEvent.attendance_day_id == day.id)
            .order_by(AttendanceEvent.timestamp)
        )
    ).scalars().all()
    if not events or not is_clock_in(events[-1].event_type):
        return None
    return day, ensure_utc(events[-1].timestamp) or datetime.now(UTC)


async def _add_attendance_event(
    db: AsyncSession,
    day: AttendanceDay,
    event_type: AttendanceEventType,
    occurred_at: datetime,
    client_event_id: str,
    notes: str,
) -> None:
    db.add(
        AttendanceEvent(
            attendance_day_id=day.id,
            event_type=event_type,
            timestamp=occurred_at,
            source=AttendanceSource.DESKTOP,
            client_event_id=client_event_id,
            sync_delay_seconds=round(max(0.0, (datetime.now(UTC) - occurred_at).total_seconds()), 2),
            notes=notes,
        )
    )
    await db.flush()
    await recalculate_attendance_day(db, day.id)


async def _clock_in(
    db: AsyncSession, employee: EmployeeProfile, occurred_at: datetime, client_event_id: str, notes: str
) -> None:
    work_date = determine_work_date_for_clock_in(occurred_at, employee.work_schedule)
    day = (
        await db.execute(
            select(AttendanceDay).where(
                AttendanceDay.employee_id == employee.id,
                AttendanceDay.work_date == work_date,
            )
        )
    ).scalars().first()
    if day is None:
        day = AttendanceDay(
            organization_id=employee.organization_id,
            employee_id=employee.id,
            work_date=work_date,
            status=AttendanceStatus.PRESENT,
            shift_start=occurred_at,
        )
        db.add(day)
        await db.flush()
    await _add_attendance_event(db, day, AttendanceEventType.CLOCK_IN, occurred_at, client_event_id, notes)


def _describe(event: PresenceEventIn) -> str:
    labels = {
        PresenceEventType.APP_LOGIN: "Desktop app login",
        PresenceEventType.APP_LOGOUT: "Desktop app logout",
        PresenceEventType.WIFI_CONNECTED: "Wi-Fi connected",
        PresenceEventType.WIFI_DISCONNECTED: "Wi-Fi disconnected",
    }
    label = labels[event.event_type]
    return f"{label} ({event.ssid})" if event.ssid else label


async def record_presence_event(
    db: AsyncSession,
    employee: EmployeeProfile,
    event: PresenceEventIn,
) -> PresenceEventResult:
    """Stores one presence signal and opens/closes the attendance session according to the login/logout rule."""
    now = datetime.now(UTC)
    occurred_at = ensure_utc(event.occurred_at) or now

    if occurred_at > now + MAX_CLOCK_SKEW:
        return PresenceEventResult(
            client_event_id=event.client_event_id, status="REJECTED", detail="Event time is in the future"
        )
    if occurred_at < now - MAX_EVENT_AGE:
        return PresenceEventResult(
            client_event_id=event.client_event_id, status="REJECTED", detail="Event is older than 7 days"
        )

    existing = (
        await db.execute(
            select(PresenceEvent).where(
                PresenceEvent.employee_id == employee.id,
                PresenceEvent.client_event_id == event.client_event_id,
            )
        )
    ).scalars().first()
    if existing is not None:
        return PresenceEventResult(
            client_event_id=event.client_event_id,
            status="DUPLICATE",
            attendance_action=PresenceAttendanceAction(existing.attendance_action),
        )

    attendance_id = _attendance_client_event_id(employee.id, event.client_event_id)
    action = PresenceAttendanceAction.NONE
    open_session = await _open_session(db, employee.id)
    event_work_date = determine_work_date_for_clock_in(occurred_at, employee.work_schedule)

    if event.event_type in LOGIN_EVENT_TYPES:
        if open_session is not None and open_session[0].work_date < event_work_date:
            # Previous day never logged out (e.g. laptop shut down offline): close it at the last signal we saw.
            stale_day, last_in = open_session
            last_seen = await db.scalar(
                select(PresenceEvent.occurred_at)
                .where(
                    PresenceEvent.employee_id == employee.id,
                    PresenceEvent.occurred_at >= last_in,
                    PresenceEvent.occurred_at < occurred_at,
                )
                .order_by(PresenceEvent.occurred_at.desc())
                .limit(1)
            )
            await _add_attendance_event(
                db,
                stale_day,
                AttendanceEventType.CLOCK_OUT,
                ensure_utc(last_seen) or last_in,
                f"{attendance_id}:autoclose"[:100],
                "Auto-closed: no logout was recorded",
            )
            open_session = None

        if open_session is None:
            await _clock_in(db, employee, occurred_at, attendance_id, _describe(event))
            action = PresenceAttendanceAction.CLOCK_IN
        else:
            # A signal synced late (e.g. Wi-Fi connected before the app started) moves the day's login earlier.
            day = open_session[0]
            first_in = ensure_utc(day.shift_start)
            if day.work_date == event_work_date and first_in is not None and occurred_at < first_in:
                await _add_attendance_event(
                    db, day, AttendanceEventType.CLOCK_IN, occurred_at, attendance_id, _describe(event)
                )
                action = PresenceAttendanceAction.CLOCK_IN
    elif open_session is not None:
        if occurred_at >= open_session[1]:
            await _add_attendance_event(
                db, open_session[0], AttendanceEventType.CLOCK_OUT, occurred_at, attendance_id, _describe(event)
            )
            action = PresenceAttendanceAction.CLOCK_OUT
    else:
        # Already logged out today: a later app logout / Wi-Fi disconnect becomes the day's logout time.
        day = (
            await db.execute(
                select(AttendanceDay).where(
                    AttendanceDay.employee_id == employee.id,
                    AttendanceDay.work_date == event_work_date,
                )
            )
        ).scalars().first()
        last_out = ensure_utc(day.shift_end) if day is not None else None
        if day is not None and last_out is not None and occurred_at > last_out:
            await _add_attendance_event(
                db, day, AttendanceEventType.CLOCK_OUT, occurred_at, attendance_id, _describe(event)
            )
            action = PresenceAttendanceAction.CLOCK_OUT

    db.add(
        PresenceEvent(
            organization_id=employee.organization_id,
            employee_id=employee.id,
            event_type=event.event_type.value,
            occurred_at=occurred_at,
            client_event_id=event.client_event_id,
            device_id=event.device_id,
            ssid=event.ssid,
            bssid=event.bssid,
            attendance_action=action.value,
        )
    )
    await db.commit()
    return PresenceEventResult(client_event_id=event.client_event_id, status="RECORDED", attendance_action=action)


async def is_logged_in(db: AsyncSession, employee_id: uuid.UUID) -> bool:
    return await _open_session(db, employee_id) is not None


def _day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time.min, tzinfo=UTC), datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)


async def get_presence_days(
    db: AsyncSession,
    employee: EmployeeProfile,
    start_date: date,
    end_date: date,
) -> list[PresenceDay]:
    """Per-day login/logout table rows (newest first) with the raw app and Wi-Fi events of each day."""
    now = datetime.now(UTC)
    days = (
        await db.execute(
            select(AttendanceDay)
            .options(selectinload(AttendanceDay.events))
            .where(
                AttendanceDay.employee_id == employee.id,
                AttendanceDay.work_date >= start_date,
                AttendanceDay.work_date <= end_date,
            )
        )
    ).scalars().all()
    day_map = {d.work_date: d for d in days}

    range_start, range_end = _day_bounds(start_date, end_date)
    events = (
        await db.execute(
            select(PresenceEvent)
            .where(
                PresenceEvent.employee_id == employee.id,
                PresenceEvent.occurred_at >= range_start,
                PresenceEvent.occurred_at < range_end,
            )
            .order_by(PresenceEvent.occurred_at)
        )
    ).scalars().all()
    events_by_date: dict[date, list[PresenceEvent]] = defaultdict(list)
    for ev in events:
        occurred = ensure_utc(ev.occurred_at) or now
        events_by_date[occurred.date()].append(ev)

    rows: list[PresenceDay] = []
    for work_date in sorted(set(day_map) | set(events_by_date), reverse=True):
        att = day_map.get(work_date)
        day_events = events_by_date.get(work_date, [])
        row = PresenceDay(
            work_date=work_date,
            events=[
                PresenceEventOut(
                    event_type=e.event_type,
                    occurred_at=ensure_utc(e.occurred_at) or now,
                    ssid=e.ssid,
                    attendance_action=e.attendance_action,
                )
                for e in day_events
            ],
        )

        wifi_connects = [e for e in day_events if e.event_type == PresenceEventType.WIFI_CONNECTED.value]
        if wifi_connects:
            row.first_wifi_connected_at = ensure_utc(wifi_connects[0].occurred_at)
            row.wifi_networks = list(dict.fromkeys(e.ssid for e in wifi_connects if e.ssid))

        if att is not None and att.shift_start is not None:
            ordered = sorted(att.events, key=lambda e: ensure_utc(e.timestamp) or now)
            row.is_logged_in = bool(ordered) and is_clock_in(ordered[-1].event_type)
            row.first_login = ensure_utc(att.shift_start)
            row.status = att.status.value if hasattr(att.status, "value") else str(att.status)
            if row.is_logged_in:
                row.worked_minutes = max(0, int((now - row.first_login).total_seconds() // 60)) if row.first_login else 0
            else:
                row.last_logout = ensure_utc(att.shift_end)
                row.worked_minutes = att.total_work_minutes
        elif att is not None:
            row.status = att.status.value if hasattr(att.status, "value") else str(att.status)
        rows.append(row)
    return rows


async def get_team_presence(
    db: AsyncSession,
    organization_id: uuid.UUID,
    employee_ids: list[uuid.UUID] | None,
    work_date: date,
) -> tuple[list[TeamPresenceRow], TeamPresenceCounts, int]:
    """
    One row per active employee-role account for the given day: login, logout, Wi-Fi and leave.
    `employee_ids=None` means the whole organization.
    Returns (rows, counts, pending leave requests in scope).
    """
    now = datetime.now(UTC)
    stmt = (
        select(EmployeeProfile)
        .join(User, User.id == EmployeeProfile.user_id)
        .join(Role, Role.id == User.role_id)
        .options(selectinload(EmployeeProfile.department))
        .where(
            EmployeeProfile.organization_id == organization_id,
            EmployeeProfile.employment_status != EmploymentStatus.TERMINATED,
            User.is_active.is_(True),
            func.lower(Role.name) == "employee",
        )
        .order_by(EmployeeProfile.first_name, EmployeeProfile.last_name)
    )
    if employee_ids is not None:
        if not employee_ids:
            return [], TeamPresenceCounts(), 0
        stmt = stmt.where(EmployeeProfile.id.in_(employee_ids))
    employees = (await db.execute(stmt)).scalars().all()
    ids = [e.id for e in employees]
    if not ids:
        return [], TeamPresenceCounts(), 0

    att_days = (
        await db.execute(
            select(AttendanceDay)
            .options(selectinload(AttendanceDay.events))
            .where(AttendanceDay.employee_id.in_(ids), AttendanceDay.work_date == work_date)
        )
    ).scalars().all()
    att_by_emp = {d.employee_id: d for d in att_days}

    day_start, day_end = _day_bounds(work_date, work_date)
    signals = (
        await db.execute(
            select(PresenceEvent)
            .where(
                PresenceEvent.employee_id.in_(ids),
                PresenceEvent.occurred_at >= day_start,
                PresenceEvent.occurred_at < day_end,
            )
            .order_by(PresenceEvent.occurred_at)
        )
    ).scalars().all()
    signals_by_emp: dict[uuid.UUID, list[PresenceEvent]] = defaultdict(list)
    for sig in signals:
        signals_by_emp[sig.employee_id].append(sig)

    leaves = (
        await db.execute(
            select(LeaveRequest)
            .options(selectinload(LeaveRequest.leave_type))
            .where(
                LeaveRequest.employee_id.in_(ids),
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.start_date <= work_date,
                LeaveRequest.end_date >= work_date,
            )
        )
    ).scalars().all()
    leave_by_emp = {lv.employee_id: lv for lv in leaves}

    pending_leaves = await db.scalar(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.employee_id.in_(ids),
            LeaveRequest.status == LeaveStatus.PENDING,
        )
    ) or 0

    rows: list[TeamPresenceRow] = []
    counts = TeamPresenceCounts(total=len(employees))
    for emp in employees:
        row = TeamPresenceRow(
            employee_id=emp.id,
            employee_code=emp.employee_code,
            full_name=f"{emp.first_name} {emp.last_name}".strip(),
            department_name=emp.department.name if emp.department else None,
            status="NOT_LOGGED_IN",
        )
        emp_signals = signals_by_emp.get(emp.id, [])
        if emp_signals:
            row.last_signal_at = ensure_utc(emp_signals[-1].occurred_at)
            connects = [s for s in emp_signals if s.event_type == PresenceEventType.WIFI_CONNECTED.value]
            if connects:
                row.first_wifi_connected_at = ensure_utc(connects[0].occurred_at)
                row.wifi_networks = list(dict.fromkeys(s.ssid for s in connects if s.ssid))

        att = att_by_emp.get(emp.id)
        if att is not None and att.shift_start is not None:
            ordered = sorted(att.events, key=lambda e: ensure_utc(e.timestamp) or now)
            row.first_login = ensure_utc(att.shift_start)
            if ordered and is_clock_in(ordered[-1].event_type):
                row.status = "LOGGED_IN"
                row.worked_minutes = max(0, int((now - row.first_login).total_seconds() // 60)) if row.first_login else 0
            else:
                row.status = "LOGGED_OUT"
                row.last_logout = ensure_utc(att.shift_end)
                row.worked_minutes = att.total_work_minutes

        leave = leave_by_emp.get(emp.id)
        if leave is not None:
            row.leave_type_name = leave.leave_type.name if leave.leave_type else None
            if row.status == "NOT_LOGGED_IN":
                row.status = "ON_LEAVE"

        if row.status == "LOGGED_IN":
            counts.logged_in += 1
        elif row.status == "LOGGED_OUT":
            counts.logged_out += 1
        elif row.status == "ON_LEAVE":
            counts.on_leave += 1
        else:
            counts.not_logged_in += 1
        rows.append(row)

    return rows, counts, int(pending_leaves)


async def get_month_summary(
    db: AsyncSession,
    employee: EmployeeProfile,
    year: int,
    month: int,
) -> PresenceMonthSummary:
    """Dashboard totals: working days vs present vs leave vs absent, plus total login time."""
    today = datetime.now(UTC).date()
    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    elapsed_end = min(today, month_end)

    schedule = employee.work_schedule
    working_weekdays = schedule.working_days if (schedule and schedule.working_days) else DEFAULT_WORKING_WEEKDAYS
    holidays = set(
        (
            await db.execute(
                select(Holiday.holiday_date).where(
                    Holiday.organization_id == employee.organization_id,
                    Holiday.holiday_date >= month_start,
                    Holiday.holiday_date <= month_end,
                )
            )
        ).scalars().all()
    )

    def is_working_day(d: date) -> bool:
        return d.isoweekday() in working_weekdays and d not in holidays

    rows = await get_presence_days(db, employee, month_start, month_end)
    present_dates = {r.work_date for r in rows if r.first_login is not None and r.work_date <= elapsed_end}

    leaves = (
        await db.execute(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == employee.id,
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.start_date <= month_end,
                LeaveRequest.end_date >= month_start,
            )
        )
    ).scalars().all()
    leave_days = 0.0
    upcoming_leave_days = 0.0
    leave_dates: set[date] = set()
    for lv in leaves:
        weight = 0.5 if lv.is_half_day else 1.0
        d = max(lv.start_date, month_start)
        while d <= min(lv.end_date, month_end):
            if is_working_day(d):
                if d <= elapsed_end:
                    leave_days += weight
                    leave_dates.add(d)
                else:
                    upcoming_leave_days += weight
            d += timedelta(days=1)

    working_days = 0
    absent_days = 0
    d = month_start
    while d <= elapsed_end:
        if is_working_day(d):
            working_days += 1
            # Today only becomes "absent" once it is over.
            if d < today and d not in present_dates and d not in leave_dates:
                absent_days += 1
        d += timedelta(days=1)

    total_minutes = sum(r.worked_minutes for r in rows if r.work_date <= elapsed_end)
    today_row = next((r for r in rows if r.work_date == today), None)
    if today_row is None:
        today_row = (await get_presence_days(db, employee, today, today) or [PresenceDay(work_date=today)])[0]

    return PresenceMonthSummary(
        month=f"{year:04d}-{month:02d}",
        working_days=working_days,
        present_days=len(present_dates),
        leave_days=leave_days,
        upcoming_leave_days=upcoming_leave_days,
        absent_days=absent_days,
        total_worked_minutes=total_minutes,
        average_daily_minutes=int(total_minutes / len(present_dates)) if present_dates else 0,
        today=today_row,
    )
