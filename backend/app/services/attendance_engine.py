"""
Attendance Calculation Engine (Phase 07)
Enterprise deterministic attendance evaluation engine.

Features:
- Pure calculation functions for daily rollups
- Schedule-driven late arrival and early departure computation
- Overnight shift detection and cross-midnight handling
- Half-day, absent, holiday, weekly-off, and approved leave handling
- Break duration and net working hours calculation
- Missing checkout detection
- Audit logging for manual corrections
- Strict negative constraint: Zero automatic clock-in from OS login
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.attendance import (
    AdjustmentStatus,
    AdjustmentType,
    AttendanceAdjustment,
    AttendanceBreak,
    AttendanceDay,
    AttendanceEvent,
    AttendanceEventType,
    AttendanceSource,
    AttendanceStatus,
    BreakType,
)
from app.models.auth import AuditLog
from app.models.employee import EmployeeProfile
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.schedule import Holiday, WorkSchedule


class AttendanceCalculationResult:
    """Deterministic calculation output for an attendance day."""

    def __init__(
        self,
        work_date: date,
        status: AttendanceStatus,
        shift_start: datetime | None,
        shift_end: datetime | None,
        total_work_minutes: int,
        total_break_minutes: int,
        late_minutes: int,
        early_departure_minutes: int,
        is_half_day: bool,
        is_missing_checkout: bool,
        is_overtime: bool,
        is_wfh: bool,
        notes: list[str] | None = None,
    ):
        self.work_date = work_date
        self.status = status
        self.shift_start = shift_start
        self.shift_end = shift_end
        self.total_work_minutes = total_work_minutes
        self.total_break_minutes = total_break_minutes
        self.late_minutes = late_minutes
        self.early_departure_minutes = early_departure_minutes
        self.is_half_day = is_half_day
        self.is_missing_checkout = is_missing_checkout
        self.is_overtime = is_overtime
        self.is_wfh = is_wfh
        self.notes = notes or []


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Normalizes any datetime (naive or localized) to UTC-aware datetime."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def is_overnight_schedule(schedule: WorkSchedule | None) -> bool:
    """Returns True if the schedule spans midnight (e.g. 22:00 to 06:00)."""
    if not schedule or not schedule.shift_start_time or not schedule.shift_end_time:
        return False
    return schedule.shift_start_time > schedule.shift_end_time


def calculate_schedule_expected_minutes(schedule: WorkSchedule | None) -> int:
    """Returns total expected working minutes for a scheduled shift."""
    if not schedule or not schedule.shift_start_time or not schedule.shift_end_time:
        return 8 * 60  # Default 8 hours (480 minutes)

    start_m = schedule.shift_start_time.hour * 60 + schedule.shift_start_time.minute
    end_m = schedule.shift_end_time.hour * 60 + schedule.shift_end_time.minute

    if schedule.shift_start_time > schedule.shift_end_time:
        # Overnight shift (e.g. 22:00 to 06:00 -> (1440 - 1320) + 360 = 480 mins)
        return (24 * 60 - start_m) + end_m
    else:
        return max(0, end_m - start_m)


def determine_work_date_for_clock_in(
    clock_in_time: datetime,
    schedule: WorkSchedule | None,
) -> date:
    """
    Determines the canonical work_date for a clock-in timestamp.
    Handles overnight shifts: if an overnight shift started yesterday (e.g. 22:00 yesterday to 06:00 today),
    and clock-in occurs past midnight in the early morning (e.g. 01:00 or 02:00), it belongs to yesterday's shift.
    """
    clock_in_utc = ensure_utc(clock_in_time) or datetime.now(UTC)
    target_date = clock_in_utc.date()
    if not schedule or not is_overnight_schedule(schedule):
        return target_date

    # Overnight shift: e.g. start at 22:00, end at 06:00
    # If clocking in between 00:00 and (end_time + 2 hours), it belongs to yesterday's shift!
    cutoff_dt = ensure_utc(datetime.combine(target_date, schedule.shift_end_time)) + timedelta(hours=2)

    if clock_in_utc <= cutoff_dt:
        return target_date - timedelta(days=1)

    return target_date


def is_clock_in(ev_type: Any) -> bool:
    val = ev_type.value if hasattr(ev_type, "value") else str(ev_type)
    return "CLOCK_IN" in str(val).upper()


def is_clock_out(ev_type: Any) -> bool:
    val = ev_type.value if hasattr(ev_type, "value") else str(ev_type)
    return "CLOCK_OUT" in str(val).upper()


# Auto-break classification (local wall-clock midday lunch window)
LUNCH_WINDOW_START_HOUR = 12
LUNCH_WINDOW_END_HOUR = 14
LUNCH_MIN_DURATION_MINUTES = 30


def _as_break_type(value: BreakType | str | None) -> BreakType | None:
    if value is None:
        return None
    if isinstance(value, BreakType):
        return value
    try:
        return BreakType(str(value))
    except ValueError:
        return None


def classify_break_type(
    start_time: datetime,
    end_time: datetime | None,
    *,
    current_type: BreakType | str | None = None,
) -> BreakType:
    """
    Classify break type from start/end times.
    Long midday away time (>=30m starting 12:00-14:00 local) becomes LUNCH.
    Preserves COFFEE/MEETING. Otherwise PERSONAL (tentative LUNCH at start if midday).
    """
    current = _as_break_type(current_type)
    if current in (BreakType.COFFEE, BreakType.MEETING):
        return current

    start = ensure_utc(start_time)
    if start is None:
        return current or BreakType.PERSONAL

    local_start = start.astimezone()
    in_lunch_window = LUNCH_WINDOW_START_HOUR <= local_start.hour < LUNCH_WINDOW_END_HOUR

    if end_time is None:
        return BreakType.LUNCH if in_lunch_window else BreakType.PERSONAL

    end = ensure_utc(end_time) or start
    duration_minutes = max(0, int((end - start).total_seconds() / 60))
    # Long enough: keep client midday LUNCH label, or upgrade when server-local window matches.
    if duration_minutes >= LUNCH_MIN_DURATION_MINUTES and (current == BreakType.LUNCH or in_lunch_window):
        return BreakType.LUNCH
    return BreakType.PERSONAL


def finalize_break(active_break: AttendanceBreak, end_time: datetime) -> AttendanceBreak:
    """Set end time, duration, and lunch reclassification on an open break."""
    t_end = ensure_utc(end_time) or datetime.now(UTC)
    t_start = ensure_utc(active_break.start_time) or t_end
    active_break.end_time = t_end
    active_break.duration_minutes = max(0, int((t_end - t_start).total_seconds() / 60))
    source = str(active_break.source or "MANUAL")
    if source.startswith("AUTO"):
        classified = classify_break_type(t_start, t_end, current_type=active_break.break_type)
        active_break.break_type = classified
        active_break.is_paid = classified in (BreakType.COFFEE, BreakType.MEETING)
    return active_break


def calculate_daily_attendance(
    work_date: date,
    events: list[AttendanceEvent],
    breaks: list[AttendanceBreak],
    schedule: WorkSchedule | None,
    holidays: list[Holiday] | None = None,
    approved_leaves: list[LeaveRequest] | None = None,
    evaluation_time: datetime | None = None,
) -> AttendanceCalculationResult:
    """
    Pure, deterministic attendance calculation function.
    Given raw events, breaks, schedule, holidays, and approved leaves,
    computes exact net duration, late arrival, early departure, and status.
    """
    now = ensure_utc(evaluation_time) or datetime.now(UTC)
    holidays = holidays or []
    approved_leaves = approved_leaves or []
    notes: list[str] = []

    # 1. Schedule defaults
    working_days = schedule.working_days if (schedule and schedule.working_days) else [1, 2, 3, 4, 5]
    is_scheduled_work_day = work_date.isoweekday() in working_days
    is_overnight = is_overnight_schedule(schedule)
    expected_shift_minutes = calculate_schedule_expected_minutes(schedule)
    flexible_minutes = schedule.flexible_minutes if schedule else 15

    # 2. Sort events and breaks chronologically (normalized to UTC)
    sorted_events = sorted(
        events,
        key=lambda e: ensure_utc(e.timestamp) or datetime.min.replace(tzinfo=UTC),
    )
    sorted_breaks = sorted(
        breaks,
        key=lambda b: ensure_utc(b.start_time) or datetime.min.replace(tzinfo=UTC),
    )

    # 3. Process Work from Home (WFH) flag
    is_wfh = any(e.is_wfh for e in sorted_events)

    # 4. Filter clock-ins and clock-outs
    clock_ins = [e for e in sorted_events if is_clock_in(e.event_type)]
    clock_outs = [e for e in sorted_events if is_clock_out(e.event_type)]

    first_clock_in = ensure_utc(clock_ins[0].timestamp) if clock_ins else None
    last_clock_out = ensure_utc(clock_outs[-1].timestamp) if clock_outs else None

    # 5. Calculate break durations
    total_break_minutes = 0
    total_unpaid_break_minutes = 0

    for b in sorted_breaks:
        b_start = ensure_utc(b.start_time)
        b_end = ensure_utc(b.end_time)
        if b_end and b_start:
            dur = max(0, int((b_end - b_start).total_seconds() / 60))
        elif first_clock_in and not last_clock_out and b_start:
            # Active ongoing break
            dur = max(0, int((now - b_start).total_seconds() / 60))
        else:
            dur = 0

        total_break_minutes += dur
        if not b.is_paid:
            total_unpaid_break_minutes += dur

    # 6. Calculate Gross & Net Working Minutes
    total_work_minutes = 0
    is_missing_checkout = False

    if first_clock_in:
        if last_clock_out and last_clock_out >= first_clock_in:
            # Shift completed
            gross_seconds = (last_clock_out - first_clock_in).total_seconds()
            gross_minutes = int(gross_seconds / 60)
            total_work_minutes = max(0, gross_minutes - total_unpaid_break_minutes)
        else:
            # Clocked in without clock-out
            # Check if shift has completed based on schedule
            scheduled_end_dt: datetime | None = None
            if schedule and schedule.shift_end_time:
                end_day = work_date + timedelta(days=1) if is_overnight else work_date
                scheduled_end_dt = ensure_utc(datetime.combine(end_day, schedule.shift_end_time))

            if scheduled_end_dt and now > scheduled_end_dt + timedelta(hours=2):
                is_missing_checkout = True
                notes.append("Missing clock-out detected past scheduled shift end")
                # Credit up to scheduled end
                gross_minutes = max(0, int((scheduled_end_dt - first_clock_in).total_seconds() / 60))
                total_work_minutes = max(0, gross_minutes - total_unpaid_break_minutes)
            else:
                # Live ongoing shift
                gross_minutes = max(0, int((now - first_clock_in).total_seconds() / 60))
                total_work_minutes = max(0, gross_minutes - total_unpaid_break_minutes)

    # 7. Late Arrival Calculation
    late_minutes = 0
    if first_clock_in and schedule and schedule.shift_start_time:
        scheduled_start_dt = ensure_utc(datetime.combine(work_date, schedule.shift_start_time))
        grace_dt = scheduled_start_dt + timedelta(minutes=flexible_minutes)

        if first_clock_in > grace_dt:
            late_minutes = max(0, int((first_clock_in - scheduled_start_dt).total_seconds() / 60))
            notes.append(f"Late arrival: {late_minutes} minutes after scheduled start")

    # 8. Early Departure Calculation
    early_departure_minutes = 0
    if last_clock_out and schedule and schedule.shift_end_time:
        end_day = work_date + timedelta(days=1) if is_overnight else work_date
        scheduled_end_dt = ensure_utc(datetime.combine(end_day, schedule.shift_end_time))
        if last_clock_out < scheduled_end_dt:
            early_departure_minutes = max(0, int((scheduled_end_dt - last_clock_out).total_seconds() / 60))
            notes.append(f"Early departure: {early_departure_minutes} minutes before scheduled end")

    # 9. Half-Day and Overtime Evaluation
    half_day_threshold = int(expected_shift_minutes * 0.5)
    is_half_day = False
    is_overtime = total_work_minutes > expected_shift_minutes

    if 0 < total_work_minutes < half_day_threshold:
        is_half_day = True
        notes.append(f"Half-day: worked {total_work_minutes}m (< {half_day_threshold}m threshold)")
        is_half_day = True
        notes.append(f"Half-day: worked {total_work_minutes}m (< {half_day_threshold}m threshold)")

    # 10. Check Approved Leaves and Holidays
    has_full_day_leave = False
    has_half_day_leave = False

    for l in approved_leaves:
        if l.status == LeaveStatus.APPROVED:
            if hasattr(l, "is_half_day") and getattr(l, "is_half_day", False):
                has_half_day_leave = True
            else:
                has_full_day_leave = True

    is_holiday = len(holidays) > 0

    # 11. Final Attendance Status Resolution
    if has_full_day_leave:
        status = AttendanceStatus.ON_LEAVE
    elif has_half_day_leave:
        status = AttendanceStatus.HALF_DAY
        is_half_day = True
    elif is_holiday:
        status = AttendanceStatus.PRESENT if first_clock_in else AttendanceStatus.HOLIDAY
    elif not is_scheduled_work_day:
        status = AttendanceStatus.PRESENT if first_clock_in else AttendanceStatus.WEEKEND
    elif not first_clock_in:
        # Scheduled working day with 0 clock-ins
        status = AttendanceStatus.ABSENT
    elif is_half_day:
        status = AttendanceStatus.HALF_DAY
    elif late_minutes > 0:
        status = AttendanceStatus.LATE
    else:
        status = AttendanceStatus.PRESENT

    return AttendanceCalculationResult(
        work_date=work_date,
        status=status,
        shift_start=first_clock_in,
        shift_end=last_clock_out,
        total_work_minutes=total_work_minutes,
        total_break_minutes=total_break_minutes,
        late_minutes=late_minutes,
        early_departure_minutes=early_departure_minutes,
        is_half_day=is_half_day,
        is_missing_checkout=is_missing_checkout,
        is_overtime=is_overtime,
        is_wfh=is_wfh,
        notes=notes,
    )


async def recalculate_attendance_day(
    db: AsyncSession,
    attendance_day_id: uuid.UUID,
    audit_actor_user_id: uuid.UUID | None = None,
    audit_reason: str | None = None,
) -> AttendanceDay:
    """
    Deterministic recalculation of an AttendanceDay record.
    Loads associated events, breaks, schedule, holidays, and leaves,
    runs calculate_daily_attendance, and commits updated rollup values.
    Preserves all original discrete events.
    """
    stmt = (
        select(AttendanceDay)
        .options(
            selectinload(AttendanceDay.events),
            selectinload(AttendanceDay.breaks),
            selectinload(AttendanceDay.employee).selectinload(EmployeeProfile.work_schedule),
        )
        .where(AttendanceDay.id == attendance_day_id)
    )
    result = await db.execute(stmt)
    att_day = result.scalars().first()

    if not att_day:
        raise ValueError(f"AttendanceDay {attendance_day_id} not found")

    # Snapshot before state for audit
    prev_state = {
        "status": att_day.status.value if hasattr(att_day.status, "value") else str(att_day.status),
        "shift_start": att_day.shift_start.isoformat() if att_day.shift_start else None,
        "shift_end": att_day.shift_end.isoformat() if att_day.shift_end else None,
        "total_work_minutes": att_day.total_work_minutes,
        "total_break_minutes": att_day.total_break_minutes,
        "late_minutes": att_day.late_minutes,
    }

    # Query holidays on work_date
    holidays_res = await db.execute(
        select(Holiday).where(
            Holiday.organization_id == att_day.organization_id,
            Holiday.holiday_date == att_day.work_date,
        )
    )
    holidays = list(holidays_res.scalars().all())

    # Query approved leaves on work_date
    leaves_res = await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.employee_id == att_day.employee_id,
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.start_date <= att_day.work_date,
            LeaveRequest.end_date >= att_day.work_date,
        )
    )
    leaves = list(leaves_res.scalars().all())

    schedule = att_day.employee.work_schedule if att_day.employee else None

    # Load events and breaks directly to prevent identity-map caching stale collections
    events_res = await db.execute(
        select(AttendanceEvent)
        .where(AttendanceEvent.attendance_day_id == attendance_day_id)
        .order_by(AttendanceEvent.timestamp)
    )
    events = list(events_res.scalars().all())

    breaks_res = await db.execute(
        select(AttendanceBreak)
        .where(AttendanceBreak.attendance_day_id == attendance_day_id)
        .order_by(AttendanceBreak.start_time)
    )
    breaks = list(breaks_res.scalars().all())

    # Perform pure deterministic calculation
    calc = calculate_daily_attendance(
        work_date=att_day.work_date,
        events=events,
        breaks=breaks,
        schedule=schedule,
        holidays=holidays,
        approved_leaves=leaves,
    )

    # Apply calculation
    att_day.status = calc.status
    att_day.shift_start = calc.shift_start
    att_day.shift_end = calc.shift_end
    att_day.total_work_minutes = calc.total_work_minutes
    att_day.total_break_minutes = calc.total_break_minutes
    att_day.late_minutes = calc.late_minutes
    att_day.early_departure_minutes = calc.early_departure_minutes
    att_day.is_overtime = calc.is_overtime
    att_day.is_wfh = calc.is_wfh
    att_day.is_missing_checkout = calc.is_missing_checkout

    meta = dict(att_day.metadata_json or {})
    meta["calculation_notes"] = calc.notes
    meta["recalculated_at"] = datetime.now(UTC).isoformat()
    att_day.metadata_json = meta

    # Record Audit Log if an actor requested recalculation or manual override
    if audit_actor_user_id:
        new_state = {
            "status": att_day.status.value if hasattr(att_day.status, "value") else str(att_day.status),
            "shift_start": att_day.shift_start.isoformat() if att_day.shift_start else None,
            "shift_end": att_day.shift_end.isoformat() if att_day.shift_end else None,
            "total_work_minutes": att_day.total_work_minutes,
            "total_break_minutes": att_day.total_break_minutes,
            "late_minutes": att_day.late_minutes,
        }
        audit = AuditLog(
            organization_id=att_day.organization_id,
            user_id=audit_actor_user_id,
            action="ATTENDANCE_DAY_RECALCULATED",
            entity_type="AttendanceDay",
            entity_id=str(att_day.id),
            diff_json={
                "previous": prev_state,
                "current": new_state,
                "reason": audit_reason or "Automated or Manual Recalculation",
            },
        )
        db.add(audit)

    await db.commit()
    reloaded_res = await db.execute(
        select(AttendanceDay)
        .options(
            selectinload(AttendanceDay.events),
            selectinload(AttendanceDay.breaks),
        )
        .where(AttendanceDay.id == att_day.id)
        .execution_options(populate_existing=True)
    )
    reloaded_day = reloaded_res.scalars().first()
    if reloaded_day:
        await db.refresh(reloaded_day, ["events", "breaks"])
    return reloaded_day


async def process_attendance_adjustment_review(
    db: AsyncSession,
    adjustment_id: uuid.UUID,
    approver_user_id: uuid.UUID,
    is_approved: bool,
    review_notes: str | None = None,
) -> AttendanceAdjustment:
    """
    Executes HR/Manager review of an attendance manual adjustment request.
    If approved:
    - Creates synthetic audit event with source=MANUAL_ENTRY preserving history
    - Adjusts shift_start / shift_end
    - Re-evaluates daily attendance
    - Records detailed change in AuditLog table
    """
    stmt = (
        select(AttendanceAdjustment)
        .options(
            selectinload(AttendanceAdjustment.attendance_day),
            selectinload(AttendanceAdjustment.requester),
        )
        .where(AttendanceAdjustment.id == adjustment_id)
    )
    res = await db.execute(stmt)
    adj = res.scalars().first()

    if not adj:
        raise ValueError(f"AttendanceAdjustment {adjustment_id} not found")

    if adj.status != AdjustmentStatus.PENDING:
        raise ValueError(f"Adjustment is already resolved ({adj.status})")

    # Find approver employee profile
    approver_prof_res = await db.execute(
        select(EmployeeProfile).where(EmployeeProfile.user_id == approver_user_id)
    )
    approver_prof = approver_prof_res.scalars().first()

    now = datetime.now(UTC)
    adj.approver_id = approver_prof.id if approver_prof else None
    adj.approved_at = now
    adj.status = AdjustmentStatus.APPROVED if is_approved else AdjustmentStatus.REJECTED
    adj.rejection_reason = review_notes if not is_approved else None

    if is_approved:
        att_day = adj.attendance_day
        prev_start = att_day.shift_start
        prev_end = att_day.shift_end

        # Apply corrections
        if adj.requested_shift_start:
            att_day.shift_start = adj.requested_shift_start
            # Preserve event audit trail
            in_ev = AttendanceEvent(
                attendance_day_id=att_day.id,
                event_type=AttendanceEventType.CLOCK_IN,
                timestamp=adj.requested_shift_start,
                source=AttendanceSource.MANUAL_ENTRY,
                notes=f"HR Correction approved by {approver_user_id}: {adj.reason}",
            )
            db.add(in_ev)

        if adj.requested_shift_end:
            att_day.shift_end = adj.requested_shift_end
            out_ev = AttendanceEvent(
                attendance_day_id=att_day.id,
                event_type=AttendanceEventType.CLOCK_OUT,
                timestamp=adj.requested_shift_end,
                source=AttendanceSource.MANUAL_ENTRY,
                notes=f"HR Correction approved by {approver_user_id}: {adj.reason}",
            )
            db.add(out_ev)

        await db.flush()

        # Deterministic recalculation
        await recalculate_attendance_day(
            db,
            att_day.id,
            audit_actor_user_id=approver_user_id,
            audit_reason=f"Approved adjustment {adj.id}: {adj.reason}",
        )

        # Explicit Audit Log entry for HR correction
        audit_rec = AuditLog(
            organization_id=att_day.organization_id,
            user_id=approver_user_id,
            action="ATTENDANCE_CORRECTION_APPROVED",
            entity_type="AttendanceDay",
            entity_id=str(att_day.id),
            diff_json={
                "adjustment_id": str(adj.id),
                "adjustment_type": adj.adjustment_type.value,
                "reason": adj.reason,
                "review_notes": review_notes,
                "previous_shift_start": prev_start.isoformat() if prev_start else None,
                "previous_shift_end": prev_end.isoformat() if prev_end else None,
                "new_shift_start": att_day.shift_start.isoformat() if att_day.shift_start else None,
                "new_shift_end": att_day.shift_end.isoformat() if att_day.shift_end else None,
            },
        )
        db.add(audit_rec)

    await db.commit()
    await db.refresh(adj)
    return adj
