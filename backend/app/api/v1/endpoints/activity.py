"""
Activity Tracking Endpoints
Used by desktop client to sync employee computer activity telemetry.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.models.auth import User
from app.models.device import DeviceSession, OSActivityEvent
from app.schemas.activity import ActivitySyncRequest, ActivitySyncResponse

router = APIRouter()


@router.post("/sync", response_model=ActivitySyncResponse, status_code=status.HTTP_201_CREATED)
async def sync_activity_logs(
    payload: ActivitySyncRequest,
    current_user: User = Depends(require_permission("activity:telemetry:ingest")),
    db: AsyncSession = Depends(get_db),
) -> ActivitySyncResponse:
    if not payload.logs:
        return ActivitySyncResponse(synced_count=0, message="No logs in sync batch")

    # Validate that the session exists
    session_res = await db.execute(select(DeviceSession).where(DeviceSession.id == payload.device_session_id))
    device_session = session_res.scalars().first()
    if not device_session:
        raise HTTPException(status_code=404, detail="Device session not found")

    records: list[OSActivityEvent] = []
    for item in payload.logs:
        rec = OSActivityEvent(
            device_session_id=payload.device_session_id,
            device_event_id=item.device_event_id,
            application_name=item.application_name,
            window_title=item.window_title,
            process_id=item.process_id,
            start_time=item.start_time,
            end_time=item.end_time,
            duration_seconds=item.duration_seconds,
            idle_seconds=item.idle_seconds,
            keystrokes_count=item.keystrokes_count,
            mouse_clicks_count=item.mouse_clicks_count,
        )
        records.append(rec)

    db.add_all(records)
    await db.commit()

    return ActivitySyncResponse(
        synced_count=len(records),
        message=f"Successfully ingested {len(records)} activity records",
    )
