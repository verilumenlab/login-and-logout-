"""
Attendance Management Engine API Endpoints (Phase 07)
Complete lifecycle support for Clock-In, Clock-Out, Breaks, Offline Batch Sync,
Overnight Shifts, Late/Early Computations, WFH Tracking, and Manual HR Corrections.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import (
    get_current_active_user,
    get_current_user,
    require_employee_access,
    require_permission,
    require_role,
)
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
from app.models.auth import AuditLog, User
from app.models.employee import EmployeeProfile, ManagerAssignment
from app.schemas.attendance import (
    AttendanceAdjustmentCreateRequest,
    AttendanceAdjustmentResponse,
    AttendanceAdjustmentReviewRequest,
    AttendanceBreakResponse,
    AttendanceEventResponse,
    AttendanceOfflineBatchSyncRequest,
    AttendanceOfflineBatchSyncResponse,
    AttendanceResponse,
    BreakEndRequest,
    BreakStartRequest,
    ClockInRequest,
    ClockOutRequest,
    CurrentAttendanceStatusResponse,
)
from app.models.office import LocationPermissionStatus
from app.services.attendance_engine import (
    determine_work_date_for_clock_in,
    ensure_utc,
    process_attendance_adjustment_review,
    recalculate_attendance_day,
)
from app.services.location_verifier import verify_and_persist_location

router = APIRouter()


async def get_current_employee_profile(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeProfile:
    result = await db.execute(
        select(EmployeeProfile)
        .options(selectinload(EmployeeProfile.work_schedule))
        .where(EmployeeProfile.user_id == current_user.id)
    )
    profile = result.scalars().first()
    if not profile:
        raise HTTPException(status_code=400, detail="User does not have an active employee personnel profile")
    return profile


@router.post("/clock-in", response_model=AttendanceResponse, status_code=status.HTTP_201_CREATED)
async def clock_in(
    payload: ClockInRequest,
    current_user: Annotated[User, Depends(require_permission("attendance:clock_in_out"))],
    current_emp: Annotated[EmployeeProfile, Depends(get_current_employee_profile)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AttendanceDay:
    """
    Records an employee clock-in timestamp.
    - Idempotent duplicate protection via client_event_id and time threshold.
    - Supports overnight shift canonical work date assignment.
    - Deterministically recalculates daily late arrival and shift rollups.
    - Strictly never triggered automatically by OS login.
    """
    now = datetime.now(UTC)
    event_timestamp = payload.occurred_at or now
    sync_delay = max(0.0, (now - event_timestamp).total_seconds())

    # 1. Deduplication by client_event_id (Rule 7 & 8)
    if payload.client_event_id:
        existing_ev = await db.execute(
            select(AttendanceEvent).where(AttendanceEvent.client_event_id == payload.client_event_id)
        )
        if existing_ev.scalars().first():
            # Idempotently return existing day
            att_day_res = await db.execute(
                select(AttendanceDay)
                .options(selectinload(AttendanceDay.events), selectinload(AttendanceDay.breaks))
                .where(AttendanceDay.employee_id == current_emp.id)
                .order_by(desc(AttendanceDay.work_date))
                .limit(1)
            )
            existing_day = att_day_res.scalars().first()
            if not existing_day:
                raise HTTPException(status_code=404, detail="Attendance day record not found")
            return existing_day

    # 2. Determine canonical work_date considering overnight shift schedules
    work_date = determine_work_date_for_clock_in(event_timestamp, current_emp.work_schedule)

    # 3. Find or create AttendanceDay record
    day_stmt = (
        select(AttendanceDay)
        .options(selectinload(AttendanceDay.events), selectinload(AttendanceDay.breaks))
        .where(
            AttendanceDay.employee_id == current_emp.id,
            AttendanceDay.work_date == work_date,
        )
    )
    res = await db.execute(day_stmt)
    att_day = res.scalars().first()

    if not att_day:
        att_day = AttendanceDay(
            organization_id=current_emp.organization_id,
            employee_id=current_emp.id,
            work_date=work_date,
            status=AttendanceStatus.PRESENT,
            shift_start=event_timestamp,
            is_wfh=payload.is_wfh,
        )
        db.add(att_day)
        await db.flush()
    else:
        # Check duplicate clock-in without clock-out
        open_clock_ins = [
            e for e in att_day.events if e.event_type == AttendanceEventType.CLOCK_IN
        ]
        open_clock_outs = [
            e for e in att_day.events if e.event_type == AttendanceEventType.CLOCK_OUT
        ]
        if len(open_clock_ins) > len(open_clock_outs):
            # Already clocked in! Check time delta
            last_in = open_clock_ins[-1]
            t_now = ensure_utc(event_timestamp)
            t_last = ensure_utc(last_in.timestamp)
            if t_now is not None and t_last is not None and (t_now - t_last).total_seconds() < 120:
                # Duplicate clock-in within 2 minutes: return existing
                return att_day

    # 4. Optional Location Verification at Clock-in
    loc_verif_id = payload.location_verification_id
    if (
        loc_verif_id is None
        and (payload.latitude is not None or payload.ssid is not None or payload.permission_status in ["DENIED", "UNAVAILABLE"])
    ):
        perm_status = (
            LocationPermissionStatus.DENIED
            if payload.permission_status == "DENIED"
            else LocationPermissionStatus.UNAVAILABLE
            if payload.permission_status == "UNAVAILABLE"
            else LocationPermissionStatus.GRANTED
        )
        _, verif = await verify_and_persist_location(
            db=db,
            employee_id=current_emp.id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            accuracy_meters=payload.accuracy_meters,
            is_mocked=payload.is_mocked,
            permission_status=perm_status,
            source=f"ATTENDANCE_CLOCK_IN_{payload.source.value}",
            client_ssid=payload.ssid,
            client_bssid=payload.bssid,
            client_ip=payload.ip_address,
            target_office_id=payload.office_id,
        )
        loc_verif_id = verif.id

    # 5. Record Discrete Attendance Event
    in_event = AttendanceEvent(
        attendance_day_id=att_day.id,
        event_type=AttendanceEventType.CLOCK_IN,
        timestamp=event_timestamp,
        source=payload.source,
        client_event_id=payload.client_event_id,
        is_wfh=payload.is_wfh,
        sync_delay_seconds=round(sync_delay, 2),
        location_verification_id=loc_verif_id,
        device_session_id=payload.device_session_id,
        notes=payload.notes,
    )
    db.add(in_event)
    await db.commit()

    # 6. Deterministic recalculation
    recalc_day = await recalculate_attendance_day(db, att_day.id)
    return recalc_day


@router.post("/clock-out", response_model=AttendanceResponse)
async def clock_out(
    payload: ClockOutRequest,
    current_user: Annotated[User, Depends(require_permission("attendance:clock_in_out"))],
    current_emp: Annotated[EmployeeProfile, Depends(get_current_employee_profile)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AttendanceDay:
    """
    Records an employee clock-out timestamp.
    - Closes active shift and any un-ended breaks.
    - Calculates net working minutes, early departure, and overtime.
    - Strictly never triggered automatically by OS logout.
    """
    now = datetime.now(UTC)
    event_timestamp = payload.occurred_at or now
    sync_delay = max(0.0, (now - event_timestamp).total_seconds())

    # 1. Deduplication check
    if payload.client_event_id:
        existing_ev = await db.execute(
            select(AttendanceEvent).where(AttendanceEvent.client_event_id == payload.client_event_id)
        )
        if existing_ev.scalars().first():
            att_day_res = await db.execute(
                select(AttendanceDay)
                .options(selectinload(AttendanceDay.events), selectinload(AttendanceDay.breaks))
                .where(AttendanceDay.employee_id == current_emp.id)
                .order_by(desc(AttendanceDay.work_date))
                .limit(1)
            )
            existing_day = att_day_res.scalars().first()
            if not existing_day:
                raise HTTPException(status_code=404, detail="Attendance day record not found")
            return existing_day

    # 2. Find most recent open attendance day
    stmt = (
        select(AttendanceDay)
        .options(selectinload(AttendanceDay.events), selectinload(AttendanceDay.breaks))
        .where(
            AttendanceDay.employee_id == current_emp.id,
            AttendanceDay.shift_start.is_not(None),
        )
        .order_by(desc(AttendanceDay.work_date))
        .limit(1)
    )
    result = await db.execute(stmt)
    att_day = result.scalars().first()

    if not att_day:
        raise HTTPException(status_code=400, detail="No active shift found to clock out")

    # 3. Close any ongoing active breaks automatically
    for b in att_day.breaks:
        if b.end_time is None:
            b.end_time = event_timestamp
            t_end = ensure_utc(event_timestamp)
            t_start = ensure_utc(b.start_time)
            if t_end is not None and t_start is not None:
                b.duration_minutes = max(0, int((t_end - t_start).total_seconds() / 60))
            else:
                b.duration_minutes = 0

    # 4. Optional Location Verification at Clock-out
    loc_verif_id = None
    if payload.latitude is not None or payload.ssid is not None or payload.permission_status in ["DENIED", "UNAVAILABLE"]:
        perm_status = (
            LocationPermissionStatus.DENIED
            if payload.permission_status == "DENIED"
            else LocationPermissionStatus.UNAVAILABLE
            if payload.permission_status == "UNAVAILABLE"
            else LocationPermissionStatus.GRANTED
        )
        _, verif = await verify_and_persist_location(
            db=db,
            employee_id=current_emp.id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            accuracy_meters=payload.accuracy_meters,
            is_mocked=payload.is_mocked,
            permission_status=perm_status,
            source=f"ATTENDANCE_CLOCK_OUT_{payload.source.value}",
            client_ssid=payload.ssid,
            client_bssid=payload.bssid,
            client_ip=payload.ip_address,
            target_office_id=payload.office_id,
        )
        loc_verif_id = verif.id

    # 5. Record Clock-out event
    out_event = AttendanceEvent(
        attendance_day_id=att_day.id,
        event_type=AttendanceEventType.CLOCK_OUT,
        timestamp=event_timestamp,
        source=payload.source,
        client_event_id=payload.client_event_id,
        sync_delay_seconds=round(sync_delay, 2),
        location_verification_id=loc_verif_id,
        notes=payload.notes,
    )
    db.add(out_event)
    await db.commit()

    # 6. Deterministic recalculation
    recalc_day = await recalculate_attendance_day(db, att_day.id)
    return recalc_day


@router.post("/break/start", response_model=AttendanceBreakResponse, status_code=status.HTTP_201_CREATED)
async def start_break(
    payload: BreakStartRequest,
    current_user: Annotated[User, Depends(require_permission("attendance:clock_in_out"))],
    current_emp: Annotated[EmployeeProfile, Depends(get_current_employee_profile)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AttendanceBreak:
    """Begins a categorized break (Lunch, Coffee, Personal, Meeting)."""
    now = datetime.now(UTC)
    event_timestamp = payload.occurred_at or now

    # Find active attendance day
    stmt = (
        select(AttendanceDay)
        .options(selectinload(AttendanceDay.breaks))
        .where(
            AttendanceDay.employee_id == current_emp.id,
            AttendanceDay.shift_start.is_not(None),
        )
        .order_by(desc(AttendanceDay.work_date))
        .limit(1)
    )
    res = await db.execute(stmt)
    att_day = res.scalars().first()

    if not att_day:
        raise HTTPException(status_code=400, detail="Cannot start a break without an active shift")

    # Verify not already on an active break
    for b in att_day.breaks:
        if b.end_time is None:
            raise HTTPException(status_code=400, detail=f"Already on an active {b.break_type.value} break")

    is_paid = payload.break_type in [BreakType.COFFEE, BreakType.MEETING]

    new_break = AttendanceBreak(
        attendance_day_id=att_day.id,
        break_type=payload.break_type,
        start_time=event_timestamp,
        is_paid=is_paid,
        reason=payload.reason,
    )
    db.add(new_break)
    await db.commit()
    await db.refresh(new_break)

    # Recalculate attendance day
    await recalculate_attendance_day(db, att_day.id)
    return new_break


@router.post("/break/end", response_model=AttendanceBreakResponse)
async def end_break(
    payload: BreakEndRequest,
    current_user: Annotated[User, Depends(require_permission("attendance:clock_in_out"))],
    current_emp: Annotated[EmployeeProfile, Depends(get_current_employee_profile)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AttendanceBreak:
    """Concludes the current ongoing break and recalculates break duration."""
    now = datetime.now(UTC)
    event_timestamp = payload.occurred_at or now

    stmt = (
        select(AttendanceBreak)
        .join(AttendanceDay, AttendanceBreak.attendance_day_id == AttendanceDay.id)
        .where(
            AttendanceDay.employee_id == current_emp.id,
            AttendanceBreak.end_time.is_(None),
        )
        .order_by(desc(AttendanceBreak.start_time))
        .limit(1)
    )
    res = await db.execute(stmt)
    active_break = res.scalars().first()

    if not active_break:
        raise HTTPException(status_code=400, detail="No active ongoing break found to end")

    active_break.end_time = event_timestamp
    t_end = ensure_utc(event_timestamp)
    t_start = ensure_utc(active_break.start_time)
    if t_end is not None and t_start is not None:
        active_break.duration_minutes = max(0, int((t_end - t_start).total_seconds() / 60))
    else:
        active_break.duration_minutes = 0
    await db.commit()
    await db.refresh(active_break)

    # Recalculate day
    await recalculate_attendance_day(db, active_break.attendance_day_id)
    return active_break


@router.get("/status", response_model=CurrentAttendanceStatusResponse)
async def get_current_attendance_status(
    current_emp: Annotated[EmployeeProfile, Depends(get_current_employee_profile)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CurrentAttendanceStatusResponse:
    """Returns current real-time attendance state for the authenticated employee."""
    today = datetime.now(UTC).date()

    stmt = (
        select(AttendanceDay)
        .options(selectinload(AttendanceDay.events), selectinload(AttendanceDay.breaks))
        .where(
            AttendanceDay.employee_id == current_emp.id,
            AttendanceDay.work_date >= today - timedelta(days=1),
        )
        .order_by(desc(AttendanceDay.work_date))
        .limit(1)
    )
    res = await db.execute(stmt)
    att_day = res.scalars().first()

    if not att_day or not att_day.shift_start:
        return CurrentAttendanceStatusResponse(mode="CLOCKED_OUT")

    # Check open breaks
    active_break = next((b for b in att_day.breaks if b.end_time is None), None)

    mode = "ON_BREAK" if active_break else ("CLOCKED_OUT" if att_day.shift_end else "CLOCKED_IN")

    break_resp = None
    if active_break:
        break_resp = AttendanceBreakResponse(
            id=active_break.id,
            attendance_day_id=active_break.attendance_day_id,
            break_type=active_break.break_type,
            start_time=active_break.start_time,
            end_time=active_break.end_time,
            duration_minutes=active_break.duration_minutes,
            is_paid=active_break.is_paid,
            reason=active_break.reason,
        )

    return CurrentAttendanceStatusResponse(
        mode=mode,
        work_date=att_day.work_date,
        shift_start=att_day.shift_start,
        shift_end=att_day.shift_end,
        current_break=break_resp,
        total_work_minutes=att_day.total_work_minutes,
        total_break_minutes=att_day.total_break_minutes,
        late_minutes=att_day.late_minutes,
        status=att_day.status,
        is_wfh=att_day.is_wfh,
    )


@router.post("/sync-offline", response_model=AttendanceOfflineBatchSyncResponse)
async def sync_offline_attendance(
    payload: AttendanceOfflineBatchSyncRequest,
    current_user: Annotated[User, Depends(require_permission("attendance:clock_in_out"))],
    current_emp: Annotated[EmployeeProfile, Depends(get_current_employee_profile)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AttendanceOfflineBatchSyncResponse:
    """
    Synchronizes queued offline attendance events from mobile or desktop agent.
    Deduplicates idempotently, applies events in sequence, and re-computes daily rollups.
    """
    if not payload.events:
        return AttendanceOfflineBatchSyncResponse(
            received_count=0,
            inserted_count=0,
            duplicate_count=0,
            affected_work_dates=[],
            message="No offline events in sync batch",
        )

    affected_days: set[uuid.UUID] = set()
    affected_dates: set[date] = set()
    inserted_count = 0
    duplicate_count = 0

    # Sort offline events chronologically
    sorted_items = sorted(payload.events, key=lambda x: x.occurred_at)

    for item in sorted_items:
        # Check duplicate
        dup_res = await db.execute(
            select(AttendanceEvent).where(AttendanceEvent.client_event_id == item.client_event_id)
        )
        if dup_res.scalars().first():
            duplicate_count += 1
            continue

        work_date = determine_work_date_for_clock_in(item.occurred_at, current_emp.work_schedule)
        affected_dates.add(work_date)

        # Get or create day
        day_res = await db.execute(
            select(AttendanceDay).where(
                AttendanceDay.employee_id == current_emp.id,
                AttendanceDay.work_date == work_date,
            )
        )
        att_day = day_res.scalars().first()
        if not att_day:
            att_day = AttendanceDay(
                organization_id=current_emp.organization_id,
                employee_id=current_emp.id,
                work_date=work_date,
                status=AttendanceStatus.PRESENT,
                is_wfh=item.is_wfh,
            )
            db.add(att_day)
            await db.flush()

        affected_days.add(att_day.id)

        sync_delay = max(0.0, (datetime.now(UTC) - item.occurred_at).total_seconds())

        if item.action == "CLOCK_IN":
            ev = AttendanceEvent(
                attendance_day_id=att_day.id,
                event_type=AttendanceEventType.CLOCK_IN,
                timestamp=item.occurred_at,
                source=AttendanceSource.DESKTOP,
                client_event_id=item.client_event_id,
                is_wfh=item.is_wfh,
                sync_delay_seconds=round(sync_delay, 2),
                notes=item.notes,
            )
            db.add(ev)
            inserted_count += 1
        elif item.action == "CLOCK_OUT":
            ev = AttendanceEvent(
                attendance_day_id=att_day.id,
                event_type=AttendanceEventType.CLOCK_OUT,
                timestamp=item.occurred_at,
                source=AttendanceSource.DESKTOP,
                client_event_id=item.client_event_id,
                sync_delay_seconds=round(sync_delay, 2),
                notes=item.notes,
            )
            db.add(ev)
            inserted_count += 1
        elif item.action == "BREAK_START":
            b_type = item.break_type or BreakType.LUNCH
            b_rec = AttendanceBreak(
                attendance_day_id=att_day.id,
                break_type=b_type,
                start_time=item.occurred_at,
                is_paid=b_type in [BreakType.COFFEE, BreakType.MEETING],
                reason=item.notes,
            )
            db.add(b_rec)
            inserted_count += 1
        elif item.action == "BREAK_END":
            # Find open break
            b_end_res = await db.execute(
                select(AttendanceBreak).where(
                    AttendanceBreak.attendance_day_id == att_day.id,
                    AttendanceBreak.end_time.is_(None),
                )
            )
            open_b = b_end_res.scalars().first()
            if open_b:
                open_b.end_time = item.occurred_at
                open_b.duration_minutes = max(0, int((item.occurred_at - open_b.start_time).total_seconds() / 60))
                inserted_count += 1

    await db.commit()

    # Recalculate all affected attendance days
    for day_id in affected_days:
        await recalculate_attendance_day(db, day_id)

    return AttendanceOfflineBatchSyncResponse(
        received_count=len(payload.events),
        inserted_count=inserted_count,
        duplicate_count=duplicate_count,
        affected_work_dates=sorted(list(affected_dates)),
        message=f"Processed offline sync: {inserted_count} inserted, {duplicate_count} deduplicated",
    )


@router.post("/recalculate", response_model=AttendanceResponse)
async def trigger_attendance_recalculation(
    attendance_day_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_permission("attendance:approve"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AttendanceDay:
    """Deterministically recalculates attendance day metrics and records audit log."""
    recalc_day = await recalculate_attendance_day(
        db,
        attendance_day_id,
        audit_actor_user_id=current_user.id,
        audit_reason="Administrative Recalculation Request",
    )
    return recalc_day


# ============================================================================
# Manual Correction & Adjustment Workflow
# ============================================================================


@router.post("/adjustments", response_model=AttendanceAdjustmentResponse, status_code=status.HTTP_201_CREATED)
async def submit_attendance_adjustment(
    payload: AttendanceAdjustmentCreateRequest,
    current_emp: Annotated[EmployeeProfile, Depends(get_current_employee_profile)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AttendanceAdjustment:
    """Submits an employee manual correction request for a missed clock-in/out or time adjustment."""
    # Verify attendance day belongs to employee
    res = await db.execute(
        select(AttendanceDay).where(
            AttendanceDay.id == payload.attendance_day_id,
            AttendanceDay.employee_id == current_emp.id,
        )
    )
    att_day = res.scalars().first()
    if not att_day:
        raise HTTPException(status_code=404, detail="Attendance day record not found for employee")

    adjustment = AttendanceAdjustment(
        attendance_day_id=payload.attendance_day_id,
        requester_id=current_emp.id,
        adjustment_type=payload.adjustment_type,
        requested_shift_start=payload.requested_shift_start,
        requested_shift_end=payload.requested_shift_end,
        reason=payload.reason,
        status=AdjustmentStatus.PENDING,
    )
    db.add(adjustment)
    await db.commit()
    await db.refresh(adjustment)
    return adjustment


@router.get("/adjustments", response_model=list[AttendanceAdjustmentResponse])
async def list_attendance_adjustments(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: AdjustmentStatus | None = Query(None, alias="status"),
    limit: int = 50,
    offset: int = 0,
) -> list[AttendanceAdjustment]:
    """
    Queries adjustment requests scoped by role:
    - Admin/HR: Full organization.
    - Manager: Direct reports.
    - Employee: Strictly own requests.
    """
    user_role_name = current_user.role.name.lower() if current_user.role else "employee"
    is_admin_or_hr = current_user.is_superuser or any(r in user_role_name for r in ["admin", "hr"])

    stmt = select(AttendanceAdjustment).options(selectinload(AttendanceAdjustment.requester))

    if not is_admin_or_hr:
        emp_res = await db.execute(select(EmployeeProfile).where(EmployeeProfile.user_id == current_user.id))
        emp = emp_res.scalars().first()
        if not emp:
            return []

        if "manager" in user_role_name:
            subs_res = await db.execute(
                select(ManagerAssignment.employee_id).where(
                    ManagerAssignment.manager_id == emp.id,
                    ManagerAssignment.is_primary.is_(True),
                )
            )
            sub_ids = list(subs_res.scalars().all()) + [emp.id]
            stmt = stmt.where(AttendanceAdjustment.requester_id.in_(sub_ids))
        else:
            stmt = stmt.where(AttendanceAdjustment.requester_id == emp.id)

    if status_filter:
        stmt = stmt.where(AttendanceAdjustment.status == status_filter)

    stmt = stmt.order_by(desc(AttendanceAdjustment.created_at)).offset(offset).limit(limit)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post("/adjustments/{adjustment_id}/review", response_model=AttendanceAdjustmentResponse)
async def review_attendance_adjustment(
    adjustment_id: uuid.UUID,
    payload: AttendanceAdjustmentReviewRequest,
    current_user: Annotated[User, Depends(require_role("Super Admin", "Administrator", "HR Manager", "Department Manager", "Manager"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AttendanceAdjustment:
    """
    Reviews and approves/rejects an adjustment request.
    On approval:
    - Updates shift timestamps and records synthetic manual event
    - Recalculates daily metrics deterministically
    - Records comprehensive HR correction entry in AuditLog
    """
    try:
        adj = await process_attendance_adjustment_review(
            db=db,
            adjustment_id=adjustment_id,
            approver_user_id=current_user.id,
            is_approved=payload.is_approved,
            review_notes=payload.review_notes,
        )
        return adj
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/adjustments/{adjustment_id}/admin-override", response_model=AttendanceAdjustmentResponse)
async def admin_override_attendance_adjustment(
    adjustment_id: uuid.UUID,
    payload: AttendanceAdjustmentReviewRequest,
    current_user: Annotated[User, Depends(require_role("Super Admin", "Administrator", "Admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AttendanceAdjustment:
    """
    Administrative override for attendance corrections with mandatory audit logging.
    """
    if not payload.review_notes or not payload.review_notes.strip():
        raise HTTPException(status_code=400, detail="Administrative override remarks are mandatory.")
    try:
        adj = await process_attendance_adjustment_review(
            db=db,
            adjustment_id=adjustment_id,
            approver_user_id=current_user.id,
            is_approved=payload.is_approved,
            review_notes=f"[ADMIN_OVERRIDE by {current_user.email}]: {payload.review_notes}",
        )
        from app.models.auth import AuditLog
        audit = AuditLog(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="ADMIN_OVERRIDE",
            entity_type="attendance_adjustment",
            entity_id=str(adjustment_id),
            diff_json={
                "is_approved": payload.is_approved,
                "notes": payload.review_notes,
                "admin": current_user.email,
            },
        )
        db.add(audit)
        await db.commit()
        return adj
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/history", response_model=list[AttendanceResponse])
async def get_own_attendance_history(
    current_emp: Annotated[EmployeeProfile, Depends(get_current_employee_profile)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 30,
) -> list[AttendanceDay]:
    """Retrieve personal attendance logs with events and breaks."""
    stmt = (
        select(AttendanceDay)
        .options(selectinload(AttendanceDay.events), selectinload(AttendanceDay.breaks))
        .where(AttendanceDay.employee_id == current_emp.id)
        .order_by(desc(AttendanceDay.work_date))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/employee/{employee_id}", response_model=list[AttendanceResponse])
async def get_employee_attendance(
    employee_id: uuid.UUID,
    target_emp_id: Annotated[uuid.UUID, Depends(require_employee_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 30,
) -> list[AttendanceDay]:
    """Retrieve attendance logs for specific employee with RBAC validation."""
    stmt = (
        select(AttendanceDay)
        .options(selectinload(AttendanceDay.events), selectinload(AttendanceDay.breaks))
        .where(AttendanceDay.employee_id == target_emp_id)
        .order_by(desc(AttendanceDay.work_date))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
