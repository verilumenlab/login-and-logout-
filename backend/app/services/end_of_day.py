"""
End-of-day (18:30 Asia/Kolkata) idle logout.

After 6:30 PM local, open attendance sessions that look unused (open idle/lock/sleep
break, or no recent presence signal) are clocked out automatically so Hours stop
instead of running overnight toward ~24h.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.attendance import (
    AttendanceDay,
    AttendanceEvent,
    AttendanceEventType,
    AttendanceSource,
    BreakSource,
)
from app.models.employee import EmployeeProfile, EmploymentStatus
from app.core.office_policy import OFFICE_END
from app.services.attendance_engine import (
    ensure_utc,
    is_clock_in,
    local_work_date,
    org_zone,
    recalculate_attendance_day,
)

logger = logging.getLogger(__name__)

EOD_HOUR = OFFICE_END.hour
EOD_MINUTE = OFFICE_END.minute
IDLE_BREAK_SOURCES = {
    BreakSource.AUTO_IDLE.value,
    BreakSource.AUTO_LOCK.value,
    BreakSource.AUTO_SLEEP.value,
    "AUTO_IDLE",
    "AUTO_LOCK",
    "AUTO_SLEEP",
}


def eod_cutoff_utc(work_date) -> datetime:
    """18:30 local on the given work date, as UTC."""
    tz = org_zone()
    local = datetime.combine(work_date, time(EOD_HOUR, EOD_MINUTE), tzinfo=tz)
    return local.astimezone(UTC)


def _is_open_session(day: AttendanceDay, now: datetime) -> bool:
    ordered = sorted(day.events or [], key=lambda e: ensure_utc(e.timestamp) or now)
    return bool(ordered) and is_clock_in(ordered[-1].event_type)


def _has_open_idle_break(day: AttendanceDay) -> bool:
    for br in day.breaks or []:
        if br.end_time is None and (br.source or "") in IDLE_BREAK_SOURCES:
            return True
    return False


async def _clock_out_eod(
    db: AsyncSession,
    day: AttendanceDay,
    close_at: datetime,
) -> None:
    db.add(
        AttendanceEvent(
            attendance_day_id=day.id,
            event_type=AttendanceEventType.CLOCK_OUT,
            timestamp=close_at,
            source=AttendanceSource.DESKTOP,
            client_event_id=f"presence:eod-idle:{day.id}"[:100],
            sync_delay_seconds=round(max(0.0, (datetime.now(UTC) - close_at).total_seconds()), 2),
            notes="Auto-logout at 6:30 PM — laptop idle / not in use",
        )
    )
    await db.flush()
    await recalculate_attendance_day(db, day.id)


async def run_end_of_day_idle_logout(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    organization_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """
    Close idle open sessions after 6:30 PM local.
    Active (recent signal, no idle break) sessions are left open and listed for notice.
    """
    now = ensure_utc(now) or datetime.now(UTC)
    work_date = local_work_date(now)
    cutoff = eod_cutoff_utc(work_date)
    if now < cutoff:
        return {
            "status": "skipped",
            "reason": "before_eod",
            "work_date": work_date.isoformat(),
            "closed": [],
            "still_active": [],
        }

    day_stmt = (
        select(AttendanceDay)
        .options(
            selectinload(AttendanceDay.events),
            selectinload(AttendanceDay.breaks),
            selectinload(AttendanceDay.employee),
        )
        .where(AttendanceDay.work_date == work_date)
    )
    if organization_id is not None:
        day_stmt = day_stmt.where(AttendanceDay.organization_id == organization_id)

    days = (await db.execute(day_stmt)).scalars().all()
    closed: list[dict[str, Any]] = []
    still_active: list[dict[str, Any]] = []

    for day in days:
        emp: EmployeeProfile | None = day.employee
        if emp is not None and emp.employment_status == EmploymentStatus.TERMINATED:
            continue
        if not _is_open_session(day, now):
            continue

        ordered = sorted(day.events or [], key=lambda e: ensure_utc(e.timestamp) or now)
        last_in = ensure_utc(ordered[-1].timestamp) or now
        idle_break = _has_open_idle_break(day)

        emp_name = f"{emp.first_name} {emp.last_name}".strip() if emp else str(day.employee_id)
        emp_code = emp.employee_code if emp else None

        # Idle/lock/sleep break = not using the laptop. Active sessions stay open
        # (desktop app also auto-logs out after 5 min idle past 6:30).
        if idle_break:
            close_at = cutoff if last_in <= cutoff else last_in
            await _clock_out_eod(db, day, close_at)
            meta = dict(day.metadata_json or {})
            meta["eod_auto_logout_at"] = close_at.isoformat()
            meta["eod_auto_logout_reason"] = "idle_break"
            day.metadata_json = meta
            closed.append(
                {
                    "employee_id": str(day.employee_id),
                    "employee_code": emp_code,
                    "full_name": emp_name,
                    "closed_at": close_at.isoformat(),
                    "reason": "idle_break",
                }
            )
            logger.info("EOD idle logout: %s (%s) at %s", emp_name, emp_code, close_at.isoformat())
        else:
            meta = dict(day.metadata_json or {})
            meta["eod_still_active_at"] = now.isoformat()
            day.metadata_json = meta
            still_active.append(
                {
                    "employee_id": str(day.employee_id),
                    "employee_code": emp_code,
                    "full_name": emp_name,
                }
            )

    await db.commit()
    return {
        "status": "ok",
        "work_date": work_date.isoformat(),
        "cutoff": cutoff.isoformat(),
        "closed_count": len(closed),
        "still_active_count": len(still_active),
        "closed": closed,
        "still_active": still_active,
    }
