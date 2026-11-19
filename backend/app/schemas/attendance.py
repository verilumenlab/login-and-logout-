"""
Attendance Schemas (Phase 07)
Includes full support for clock-in/out, breaks, offline sync, adjustments, and diagnostics.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.attendance import (
    AdjustmentStatus,
    AdjustmentType,
    AttendanceEventType,
    AttendanceSource,
    AttendanceStatus,
    BreakSource,
    BreakType,
)


class ClockInRequest(BaseModel):
    notes: str | None = None
    source: AttendanceSource = AttendanceSource.WEB
    is_wfh: bool = False
    client_event_id: str | None = None
    occurred_at: datetime | None = None
    location_verification_id: uuid.UUID | None = None
    device_session_id: uuid.UUID | None = None
    # Inline location telemetry at check-in
    latitude: float | None = None
    longitude: float | None = None
    accuracy_meters: float | None = None
    is_mocked: bool = False
    permission_status: str | None = "GRANTED"
    ssid: str | None = None
    bssid: str | None = None
    ip_address: str | None = None
    office_id: uuid.UUID | None = None


class ClockOutRequest(BaseModel):
    notes: str | None = None
    source: AttendanceSource = AttendanceSource.WEB
    client_event_id: str | None = None
    occurred_at: datetime | None = None
    # Inline location telemetry at check-out
    latitude: float | None = None
    longitude: float | None = None
    accuracy_meters: float | None = None
    is_mocked: bool = False
    permission_status: str | None = "GRANTED"
    ssid: str | None = None
    bssid: str | None = None
    ip_address: str | None = None
    office_id: uuid.UUID | None = None


class BreakStartRequest(BaseModel):
    break_type: BreakType = BreakType.LUNCH
    reason: str | None = None
    source: BreakSource = BreakSource.MANUAL
    client_event_id: str | None = None
    occurred_at: datetime | None = None


class BreakEndRequest(BaseModel):
    client_event_id: str | None = None
    occurred_at: datetime | None = None


class AttendanceEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    attendance_day_id: uuid.UUID
    event_type: AttendanceEventType
    timestamp: datetime
    source: AttendanceSource
    is_wfh: bool = False
    client_event_id: str | None = None
    sync_delay_seconds: float = 0.0
    location_verification_id: uuid.UUID | None = None
    notes: str | None = None


class AttendanceBreakResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    attendance_day_id: uuid.UUID
    break_type: BreakType
    start_time: datetime
    end_time: datetime | None = None
    duration_minutes: int | None = None
    is_paid: bool
    reason: str | None = None
    source: str = BreakSource.MANUAL.value
    client_event_id: str | None = None


class AdminBreakUpdateRequest(BaseModel):
    """Admin-only keep / edit of an attendance break."""

    action: str = Field(..., pattern="^(keep|update)$")
    break_type: BreakType | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    reason: str | None = Field(None, max_length=255)
    notes: str | None = Field(None, max_length=500)


class AdminBreakDeleteResponse(BaseModel):
    ok: bool = True
    message: str
    attendance_day_id: uuid.UUID
    total_break_minutes: int = 0
    break_count: int = 0


class AttendanceAdjustmentCreateRequest(BaseModel):
    attendance_day_id: uuid.UUID
    adjustment_type: AdjustmentType
    requested_shift_start: datetime | None = None
    requested_shift_end: datetime | None = None
    reason: str = Field(..., min_length=3, max_length=1000)


class AttendanceAdjustmentReviewRequest(BaseModel):
    is_approved: bool
    review_notes: str | None = None


class AttendanceAdjustmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    attendance_day_id: uuid.UUID
    requester_id: uuid.UUID
    approver_id: uuid.UUID | None = None
    adjustment_type: AdjustmentType
    requested_shift_start: datetime | None = None
    requested_shift_end: datetime | None = None
    reason: str
    status: AdjustmentStatus
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime


class AttendanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    employee_id: uuid.UUID
    work_date: date
    status: AttendanceStatus
    shift_start: datetime | None = None
    shift_end: datetime | None = None
    total_work_minutes: int
    total_break_minutes: int
    total_idle_minutes: int
    late_minutes: int = 0
    early_departure_minutes: int = 0
    is_half_day: bool = False
    is_overtime: bool = False
    is_wfh: bool = False
    is_missing_checkout: bool = False
    events: list[AttendanceEventResponse] = Field(default_factory=list)
    breaks: list[AttendanceBreakResponse] = Field(default_factory=list)
    metadata_json: dict[str, Any] | None = None


class OfflineAttendanceItem(BaseModel):
    client_event_id: str
    action: str  # "CLOCK_IN" | "CLOCK_OUT" | "BREAK_START" | "BREAK_END"
    occurred_at: datetime
    break_type: BreakType | None = None
    source: BreakSource | None = None
    is_wfh: bool = False
    notes: str | None = None


class AttendanceOfflineBatchSyncRequest(BaseModel):
    events: list[OfflineAttendanceItem]


class AttendanceOfflineBatchSyncResponse(BaseModel):
    received_count: int
    inserted_count: int
    duplicate_count: int
    affected_work_dates: list[date]
    message: str


class CurrentAttendanceStatusResponse(BaseModel):
    mode: str  # "CLOCKED_OUT" | "CLOCKED_IN" | "ON_BREAK"
    work_date: date | None = None
    shift_start: datetime | None = None
    shift_end: datetime | None = None
    current_break: AttendanceBreakResponse | None = None
    total_work_minutes: int = 0
    total_break_minutes: int = 0
    late_minutes: int = 0
    status: AttendanceStatus | None = None
    is_wfh: bool = False
