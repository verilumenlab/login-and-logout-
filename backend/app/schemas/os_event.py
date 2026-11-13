"""
Pydantic Schemas for Operating System Session Monitoring (Phase 06)
Implements Phase 06 Common Event Contract and Offline Synchronization Protocols.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OSSessionEventBase(BaseModel):
    """Core attributes matching the Phase 06 Common Event Contract."""

    event_id: uuid.UUID = Field(
        ...,
        description="Unique event UUID generated natively on the client device.",
    )
    employee_id: uuid.UUID = Field(
        ...,
        description="Target employee personnel record UUID.",
    )
    device_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Hardware or enrolled device identifier.",
    )
    operating_system: str = Field(
        ...,
        description="Client OS platform ('windows' | 'macos' | 'linux').",
    )
    event_type: str = Field(
        ...,
        description="OS event type (OS_LOGON, OS_LOGOFF, SESSION_LOCK, SESSION_UNLOCK, SYSTEM_STARTUP, SYSTEM_SHUTDOWN, SYSTEM_SLEEP, SYSTEM_WAKE, HEARTBEAT).",
    )
    occurred_at: datetime = Field(
        ...,
        description="UTC timestamp when the native OS event occurred on the host machine.",
    )
    sequence_number: int = Field(
        ...,
        ge=0,
        description="Monotonically increasing sequence number per device to prevent replay and track continuity.",
    )
    agent_version: str = Field(
        default="1.0.0",
        max_length=50,
        description="Tauri agent client version.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured non-sensitive telemetry context (power status, idle time, reason, clock checks). Strictly no keylogging or screenshots.",
    )


class OSSessionEventCreate(OSSessionEventBase):
    """Payload submitted by the agent client during single event ingestion."""

    pass


class OSSessionEventBatchSyncRequest(BaseModel):
    """Batch of queued offline events synchronized when network connectivity is available."""

    events: list[OSSessionEventCreate] = Field(
        ...,
        description="Ordered list of pending OS session events captured while offline.",
    )
    device_id: str | None = Field(
        default=None,
        description="Optional device identifier validating batch integrity.",
    )
    client_timestamp: datetime | None = Field(
        default=None,
        description="Timestamp on client when sync request was dispatched.",
    )


class OSSessionEventResponse(BaseModel):
    """Full database representation of an ingested OS session event."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    employee_id: uuid.UUID
    device_id: str
    operating_system: str
    event_type: str
    occurred_at: datetime
    received_at: datetime
    sequence_number: int
    sync_delay_seconds: float
    agent_version: str
    metadata_json: dict[str, Any]
    employee_name: str | None = None
    created_at: datetime


class OSSessionSyncResult(BaseModel):
    """Detailed synchronization receipt acknowledging ingested and deduplicated events."""

    received_count: int
    inserted_count: int
    duplicate_count: int
    rejected_count: int
    gaps_detected: list[int] = Field(default_factory=list)
    clock_skew_flagged: bool = False
    latest_sequence_number: int
    message: str


class OSEventHealthSummary(BaseModel):
    """Diagnostic health summary and telemetry continuity metrics for a monitored workstation."""

    device_id: str
    operating_system: str
    total_events: int
    last_event_type: str | None = None
    last_occurred_at: datetime | None = None
    last_received_at: datetime | None = None
    latest_sequence_number: int = 0
    missing_sequence_gaps: list[int] = Field(default_factory=list)
    average_sync_delay_seconds: float = 0.0
    clock_anomaly_count: int = 0
    is_healthy: bool = True

