"""
Operating System Session Monitoring API Endpoints (Phase 06)
Provides native OS event synchronization, sequence gap auditing, and telemetry health diagnostics.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_permission
from app.models.auth import User
from app.models.device import Device
from app.models.employee import EmployeeProfile, ManagerAssignment
from app.models.os_event import OSSessionEvent
from app.schemas.os_event import (
    OSEventHealthSummary,
    OSSessionEventBatchSyncRequest,
    OSSessionEventCreate,
    OSSessionEventResponse,
    OSSessionSyncResult,
)

router = APIRouter()


@router.post("/sync", response_model=OSSessionSyncResult, status_code=status.HTTP_200_OK)
async def sync_os_session_events(
    payload: OSSessionEventBatchSyncRequest,
    current_user: Annotated[User, Depends(require_permission("activity:telemetry:ingest"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OSSessionSyncResult:
    """
    Synchronizes a batch of native OS session and power state transition events.
    Supports offline batching, duplicate elimination, sequence gap detection, and clock skew auditing.
    """
    if not payload.events:
        return OSSessionSyncResult(
            received_count=0,
            inserted_count=0,
            duplicate_count=0,
            rejected_count=0,
            gaps_detected=[],
            clock_skew_flagged=False,
            latest_sequence_number=0,
            message="No events received in sync packet",
        )

    now_utc = datetime.now(UTC)
    received_count = len(payload.events)

    # Security Check: Verify device authorization status
    raw_dev_id = payload.events[0].device_id
    try:
        parsed_dev_id = uuid.UUID(str(raw_dev_id))
    except (ValueError, TypeError):
        parsed_dev_id = None

    if parsed_dev_id:
        dev_stmt = select(Device).where(Device.id == parsed_dev_id)
        dev_res = await db.execute(dev_stmt)
        dev_record = dev_res.scalars().first()
        if dev_record and dev_record.is_blocked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security rejection: Device has been blocked or revoked by organization administrator.",
            )

    # 1. Deduplication check via existing event_ids
    incoming_uuids = [e.event_id for e in payload.events]
    existing_query = await db.execute(
        select(OSSessionEvent.event_id).where(OSSessionEvent.event_id.in_(incoming_uuids))
    )
    existing_ids = set(existing_query.scalars().all())

    # Filter out duplicates
    unique_events = [e for e in payload.events if e.event_id not in existing_ids]
    duplicate_count = len(payload.events) - len(unique_events)

    if not unique_events:
        # All events already received (idempotent success)
        latest_seq_res = await db.execute(
            select(func.max(OSSessionEvent.sequence_number)).where(
                OSSessionEvent.device_id == payload.events[0].device_id
            )
        )
        latest_seq = latest_seq_res.scalar() or 0
        return OSSessionSyncResult(
            received_count=received_count,
            inserted_count=0,
            duplicate_count=duplicate_count,
            rejected_count=0,
            gaps_detected=[],
            clock_skew_flagged=False,
            latest_sequence_number=latest_seq,
            message="All events in batch were already ingested (idempotent acknowledged)",
        )

    # 2. Sequence continuity and gap detection
    device_id = unique_events[0].device_id
    max_db_seq_res = await db.execute(
        select(func.max(OSSessionEvent.sequence_number)).where(
            OSSessionEvent.device_id == device_id
        )
    )
    prev_max_seq = max_db_seq_res.scalar()

    # Sort incoming new events by sequence number
    unique_events.sort(key=lambda x: x.sequence_number)

    gaps_detected: list[int] = []
    if prev_max_seq is not None:
        first_incoming_seq = unique_events[0].sequence_number
        if first_incoming_seq > prev_max_seq + 1:
            # Gaps between DB latest and batch start
            gap_range = list(range(prev_max_seq + 1, min(first_incoming_seq, prev_max_seq + 100)))
            gaps_detected.extend(gap_range)

    # Check for gaps within the batch itself
    for i in range(len(unique_events) - 1):
        curr_seq = unique_events[i].sequence_number
        next_seq = unique_events[i + 1].sequence_number
        if next_seq > curr_seq + 1:
            for missing in range(curr_seq + 1, min(next_seq, curr_seq + 50)):
                gaps_detected.append(missing)

    # 3. Clock Skew and Delay Calculation
    clock_skew_flagged = False
    records_to_insert: list[OSSessionEvent] = []

    for item in unique_events:
        # Calculate sync delay
        delay_sec = max(0.0, (now_utc - item.occurred_at).total_seconds())

        # Check future clock skew (> 300 seconds into future)
        meta = dict(item.metadata)
        if item.occurred_at > now_utc and (item.occurred_at - now_utc).total_seconds() > 300:
            clock_skew_flagged = True
            meta["clock_skew_warning"] = "Event timestamp is in the future relative to server UTC"

        rec = OSSessionEvent(
            event_id=item.event_id,
            employee_id=item.employee_id,
            device_id=item.device_id,
            operating_system=item.operating_system.lower(),
            event_type=item.event_type.upper(),
            occurred_at=item.occurred_at,
            received_at=now_utc,
            sequence_number=item.sequence_number,
            sync_delay_seconds=round(delay_sec, 2),
            agent_version=item.agent_version,
            metadata_json=meta,
            created_at=now_utc,
        )
        records_to_insert.append(rec)

    db.add_all(records_to_insert)
    await db.commit()

    latest_seq_num = max(e.sequence_number for e in unique_events)
    if prev_max_seq is not None and prev_max_seq > latest_seq_num:
        latest_seq_num = prev_max_seq

    return OSSessionSyncResult(
        received_count=received_count,
        inserted_count=len(records_to_insert),
        duplicate_count=duplicate_count,
        rejected_count=0,
        gaps_detected=gaps_detected[:50],
        clock_skew_flagged=clock_skew_flagged,
        latest_sequence_number=latest_seq_num,
        message=f"Successfully ingested {len(records_to_insert)} OS events ({duplicate_count} deduplicated)",
    )


@router.post("/", response_model=OSSessionEventResponse, status_code=status.HTTP_201_CREATED)
async def create_single_os_session_event(
    payload: OSSessionEventCreate,
    current_user: Annotated[User, Depends(require_permission("activity:telemetry:ingest"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OSSessionEventResponse:
    """Ingests a single OS session event."""
    sync_req = OSSessionEventBatchSyncRequest(events=[payload])
    sync_res = await sync_os_session_events(sync_req, current_user, db)

    # Fetch inserted or existing
    event_query = await db.execute(
        select(OSSessionEvent)
        .options(selectinload(OSSessionEvent.employee))
        .where(OSSessionEvent.event_id == payload.event_id)
    )
    event_obj = event_query.scalars().first()
    if not event_obj:
        raise HTTPException(status_code=500, detail="Failed to persist OS session event")

    emp_name = None
    if event_obj.employee:
        emp_name = f"{event_obj.employee.first_name} {event_obj.employee.last_name}"

    return OSSessionEventResponse(
        id=event_obj.id,
        event_id=event_obj.event_id,
        employee_id=event_obj.employee_id,
        device_id=event_obj.device_id,
        operating_system=event_obj.operating_system,
        event_type=event_obj.event_type,
        occurred_at=event_obj.occurred_at,
        received_at=event_obj.received_at,
        sequence_number=event_obj.sequence_number,
        sync_delay_seconds=event_obj.sync_delay_seconds,
        agent_version=event_obj.agent_version,
        metadata_json=event_obj.metadata_json,
        employee_name=emp_name,
        created_at=event_obj.created_at,
    )


@router.get("/", response_model=list[OSSessionEventResponse])
async def list_os_session_events(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    employee_id: uuid.UUID | None = Query(None, description="Filter by employee ID"),
    device_id: str | None = Query(None, description="Filter by hardware device ID"),
    event_type: str | None = Query(None, description="Filter by event type"),
    from_time: datetime | None = Query(None, description="Start range timestamp"),
    to_time: datetime | None = Query(None, description="End range timestamp"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[OSSessionEventResponse]:
    """
    Queries OS session events with RBAC boundary enforcement:
    - Super Admin & HR: All events.
    - Manager: Assigned direct reports & self.
    - Employee: Only own events.
    """
    user_role_name = current_user.role.name.lower() if current_user.role else "employee"
    is_admin_or_hr = current_user.is_superuser or any(
        r in user_role_name for r in ["admin", "hr"]
    )

    stmt = select(OSSessionEvent).options(selectinload(OSSessionEvent.employee))

    if not is_admin_or_hr:
        # Check employee profile
        emp_profile_res = await db.execute(
            select(EmployeeProfile).where(EmployeeProfile.user_id == current_user.id)
        )
        emp_profile = emp_profile_res.scalars().first()
        if not emp_profile:
            return []

        if "manager" in user_role_name:
            # Manager: direct reports + self
            subordinates_res = await db.execute(
                select(ManagerAssignment.employee_id).where(
                    ManagerAssignment.manager_id == emp_profile.id,
                    ManagerAssignment.is_primary.is_(True),
                )
            )
            subordinate_ids = list(subordinates_res.scalars().all())
            allowed_ids = set(subordinate_ids + [emp_profile.id])
            if employee_id:
                if employee_id not in allowed_ids:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You are not authorized to view this employee's OS activity",
                    )
                stmt = stmt.where(OSSessionEvent.employee_id == employee_id)
            else:
                stmt = stmt.where(OSSessionEvent.employee_id.in_(allowed_ids))
        else:
            # Standard Employee: strictly own records
            stmt = stmt.where(OSSessionEvent.employee_id == emp_profile.id)
    else:
        if employee_id:
            stmt = stmt.where(OSSessionEvent.employee_id == employee_id)

    if device_id:
        stmt = stmt.where(OSSessionEvent.device_id == device_id)
    if event_type:
        stmt = stmt.where(OSSessionEvent.event_type == event_type.upper())
    if from_time:
        stmt = stmt.where(OSSessionEvent.occurred_at >= from_time)
    if to_time:
        stmt = stmt.where(OSSessionEvent.occurred_at <= to_time)

    stmt = stmt.order_by(desc(OSSessionEvent.occurred_at)).offset(offset).limit(limit)
    res = await db.execute(stmt)
    records = res.scalars().all()

    response: list[OSSessionEventResponse] = []
    for r in records:
        emp_name = None
        if r.employee:
            emp_name = f"{r.employee.first_name} {r.employee.last_name}"
        response.append(
            OSSessionEventResponse(
                id=r.id,
                event_id=r.event_id,
                employee_id=r.employee_id,
                device_id=r.device_id,
                operating_system=r.operating_system,
                event_type=r.event_type,
                occurred_at=r.occurred_at,
                received_at=r.received_at,
                sequence_number=r.sequence_number,
                sync_delay_seconds=r.sync_delay_seconds,
                agent_version=r.agent_version,
                metadata_json=r.metadata_json,
                employee_name=emp_name,
                created_at=r.created_at,
            )
        )

    return response


@router.get("/health/{device_id}", response_model=OSEventHealthSummary)
async def get_device_event_health(
    device_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OSEventHealthSummary:
    """
    Audits the telemetry health, sequence continuity, and synchronization reliability for a device.
    """
    # 1. Total events count
    count_res = await db.execute(
        select(func.count(OSSessionEvent.id)).where(OSSessionEvent.device_id == device_id)
    )
    total_count = count_res.scalar() or 0

    if total_count == 0:
        return OSEventHealthSummary(
            device_id=device_id,
            operating_system="unknown",
            total_events=0,
            latest_sequence_number=0,
            missing_sequence_gaps=[],
            average_sync_delay_seconds=0.0,
            clock_anomaly_count=0,
            is_healthy=True,
        )

    # 2. Latest event details
    latest_event_res = await db.execute(
        select(OSSessionEvent)
        .where(OSSessionEvent.device_id == device_id)
        .order_by(desc(OSSessionEvent.sequence_number))
        .limit(1)
    )
    latest_event = latest_event_res.scalars().first()

    # 3. Average sync delay
    avg_delay_res = await db.execute(
        select(func.avg(OSSessionEvent.sync_delay_seconds)).where(
            OSSessionEvent.device_id == device_id
        )
    )
    avg_delay = float(avg_delay_res.scalar() or 0.0)

    # 4. Detect sequence gaps in recorded events
    all_seqs_res = await db.execute(
        select(OSSessionEvent.sequence_number)
        .where(OSSessionEvent.device_id == device_id)
        .order_by(OSSessionEvent.sequence_number)
    )
    seqs = all_seqs_res.scalars().all()
    seq_set = set(seqs)

    gaps: list[int] = []
    if seqs:
        min_seq = seqs[0]
        max_seq = seqs[-1]
        for expected in range(min_seq, min(max_seq + 1, min_seq + 500)):
            if expected not in seq_set:
                gaps.append(expected)

    import sqlalchemy as sa

    # 5. Clock anomaly count
    clock_skew_res = await db.execute(
        select(func.count(OSSessionEvent.id)).where(
            OSSessionEvent.device_id == device_id,
            sa.cast(OSSessionEvent.metadata_json, sa.String).like("%clock_skew_warning%"),
        )
    )
    anomaly_count = clock_skew_res.scalar() or 0

    return OSEventHealthSummary(
        device_id=device_id,
        operating_system=latest_event.operating_system if latest_event else "unknown",
        total_events=total_count,
        last_event_type=latest_event.event_type if latest_event else None,
        last_occurred_at=latest_event.occurred_at if latest_event else None,
        last_received_at=latest_event.received_at if latest_event else None,
        latest_sequence_number=latest_event.sequence_number if latest_event else 0,
        missing_sequence_gaps=gaps[:30],
        average_sync_delay_seconds=round(avg_delay, 2),
        clock_anomaly_count=anomaly_count,
        is_healthy=len(gaps) == 0 and anomaly_count == 0,
    )
