"""
Activity Tracking Endpoints
Desktop client syncs foreground-app telemetry; admins view the live board.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.models.auth import User
from app.models.device import DeviceSession, OSActivityEvent
from app.models.employee import EmployeeProfile, EmploymentStatus
from app.schemas.activity import (
    ActivitySyncRequest,
    ActivitySyncResponse,
    EmployeeActivityBoardResponse,
    EmployeeActivityNow,
)

router = APIRouter()

# Treat as still online if we saw activity within this window.
ONLINE_WITHIN = timedelta(minutes=5)
IDLE_THRESHOLD_SECONDS = 60


@router.post("/sync", response_model=ActivitySyncResponse, status_code=status.HTTP_201_CREATED)
async def sync_activity_logs(
    payload: ActivitySyncRequest,
    current_user: User = Depends(require_permission("activity:telemetry:ingest")),
    db: AsyncSession = Depends(get_db),
) -> ActivitySyncResponse:
    if not payload.logs:
        return ActivitySyncResponse(synced_count=0, message="No logs in sync batch")

    session_res = await db.execute(select(DeviceSession).where(DeviceSession.id == payload.device_session_id))
    device_session = session_res.scalars().first()
    if not device_session:
        raise HTTPException(status_code=404, detail="Device session not found")

    # Prefer matching the device session to this user's employee profile when loaded.
    emp = getattr(current_user, "employee_profile", None)
    if emp is not None and getattr(emp, "id", None) and device_session.employee_id != emp.id:
        raise HTTPException(status_code=403, detail="Device session does not belong to this employee")

    existing_ids = {
        row
        for row in (
            await db.execute(
                select(OSActivityEvent.device_event_id).where(
                    OSActivityEvent.device_session_id == payload.device_session_id,
                    OSActivityEvent.device_event_id.in_([i.device_event_id for i in payload.logs]),
                )
            )
        ).scalars().all()
    }

    inserted = 0
    for item in payload.logs:
        if item.device_event_id in existing_ids:
            continue
        # Never store keystroke/click counters from the agent (privacy).
        title = (item.window_title or "").strip() or None
        if title and len(title) > 500:
            title = title[:500]
        rec = OSActivityEvent(
            device_session_id=payload.device_session_id,
            device_event_id=item.device_event_id,
            application_name=(item.application_name or "Unknown")[:255],
            window_title=title,
            process_id=item.process_id,
            start_time=item.start_time,
            end_time=item.end_time,
            duration_seconds=max(0, int(item.duration_seconds or 0)),
            idle_seconds=max(0, int(item.idle_seconds or 0)),
            keystrokes_count=0,
            mouse_clicks_count=0,
        )
        db.add(rec)
        existing_ids.add(item.device_event_id)
        inserted += 1

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate activity event") from None

    return ActivitySyncResponse(
        synced_count=inserted,
        message=f"Successfully ingested {inserted} activity records",
    )


@router.get("/board", response_model=EmployeeActivityBoardResponse)
async def activity_board(
    current_user: User = Depends(require_permission("activity:telemetry:view_all")),
    db: AsyncSession = Depends(get_db),
    idle_seconds_threshold: int = Query(default=60, ge=30, le=3600),
) -> EmployeeActivityBoardResponse:
    """
    Admin-only: what each person is using on their laptop right now (latest foreground app).
    """
    now = datetime.now(UTC)
    org_id = current_user.organization_id

    emp_res = await db.execute(
        select(EmployeeProfile)
        .where(
            EmployeeProfile.organization_id == org_id,
            EmployeeProfile.employment_status != EmploymentStatus.TERMINATED,
        )
        .options(selectinload(EmployeeProfile.user), selectinload(EmployeeProfile.department))
        .order_by(EmployeeProfile.employee_code)
    )
    employees = list(emp_res.scalars().all())
    emp_ids = [e.id for e in employees]

    latest_by_emp: dict[uuid.UUID, tuple[OSActivityEvent, DeviceSession]] = {}
    if emp_ids:
        act_res = await db.execute(
            select(OSActivityEvent, DeviceSession)
            .join(DeviceSession, DeviceSession.id == OSActivityEvent.device_session_id)
            .where(DeviceSession.employee_id.in_(emp_ids))
            .options(selectinload(DeviceSession.device))
            .order_by(OSActivityEvent.end_time.desc())
        )
        for ev, sess in act_res.all():
            if sess.employee_id not in latest_by_emp:
                latest_by_emp[sess.employee_id] = (ev, sess)

    rows: list[EmployeeActivityNow] = []
    for emp in employees:
        user = emp.user
        name = f"{emp.first_name or ''} {emp.last_name or ''}".strip() or (
            user.email if user else emp.employee_code or "Employee"
        )
        email = user.email if user else None
        dept = emp.department.name if emp.department else None

        pair = latest_by_emp.get(emp.id)
        if not pair:
            rows.append(
                EmployeeActivityNow(
                    employee_id=emp.id,
                    employee_code=emp.employee_code,
                    employee_name=name,
                    email=email,
                    department_name=dept,
                    is_online=False,
                    is_idle=False,
                )
            )
            continue

        ev, sess = pair
        last_seen = ev.end_time
        online = bool(last_seen and (now - last_seen) <= ONLINE_WITHIN)
        idle_secs = int(ev.idle_seconds or 0)
        rows.append(
            EmployeeActivityNow(
                employee_id=emp.id,
                employee_code=emp.employee_code,
                employee_name=name,
                email=email,
                department_name=dept,
                device_name=sess.device.device_name if sess.device else None,
                application_name=ev.application_name,
                window_title=ev.window_title,
                started_at=ev.start_time,
                last_seen_at=last_seen,
                idle_seconds=idle_secs,
                is_idle=idle_secs >= idle_seconds_threshold,
                is_online=online,
            )
        )

    return EmployeeActivityBoardResponse(generated_at=now, employees=rows)
