"""
Activity Tracking Schemas
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ActivityLogItem(BaseModel):
    device_event_id: str
    application_name: str
    window_title: str | None = None
    process_id: int | None = None
    start_time: datetime
    end_time: datetime
    duration_seconds: int = 60
    idle_seconds: int = 0
    keystrokes_count: int = 0
    mouse_clicks_count: int = 0


class ActivitySyncRequest(BaseModel):
    device_session_id: uuid.UUID
    logs: list[ActivityLogItem]


class ActivitySyncResponse(BaseModel):
    synced_count: int
    message: str = "Activity batch ingested successfully"


class ActivityLogResponse(ActivityLogItem):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_session_id: uuid.UUID
    created_at: datetime
