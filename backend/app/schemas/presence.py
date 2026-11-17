"""
Employee Presence Schemas: desktop login/logout + Wi-Fi events, history table, dashboard summary.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.presence import PresenceAttendanceAction, PresenceEventType


class PresenceEventIn(BaseModel):
    client_event_id: str = Field(min_length=1, max_length=100)
    event_type: PresenceEventType
    occurred_at: AwareDatetime
    ssid: str | None = Field(default=None, max_length=255)
    bssid: str | None = Field(default=None, max_length=64)
    device_id: str | None = Field(default=None, max_length=255)
    # Optional human note (e.g. auto-logout reason) stored on the attendance event.
    detail: str | None = Field(default=None, max_length=500)


class PresenceSyncRequest(BaseModel):
    events: list[PresenceEventIn] = Field(min_length=1, max_length=200)


class PresenceEventResult(BaseModel):
    client_event_id: str
    status: Literal["RECORDED", "DUPLICATE", "REJECTED"]
    attendance_action: PresenceAttendanceAction = PresenceAttendanceAction.NONE
    detail: str | None = None


class PresenceSyncResponse(BaseModel):
    results: list[PresenceEventResult]
    is_logged_in: bool


class PresenceEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    occurred_at: datetime
    ssid: str | None = None
    attendance_action: str
    # Optional label for break rows (e.g. "LUNCH · AUTO_IDLE · 45m").
    detail: str | None = None


class PresenceDay(BaseModel):
    work_date: date
    first_login: datetime | None = None
    last_logout: datetime | None = None
    is_logged_in: bool = False
    worked_minutes: int = 0
    break_count: int = 0
    total_break_minutes: int = 0
    status: str | None = None
    first_wifi_connected_at: datetime | None = None
    wifi_networks: list[str] = Field(default_factory=list)
    events: list[PresenceEventOut] = Field(default_factory=list)


class PresenceHistoryResponse(BaseModel):
    start_date: date
    end_date: date
    days: list[PresenceDay]


class PresenceProfile(BaseModel):
    employee_id: uuid.UUID
    employee_code: str
    first_name: str
    last_name: str
    job_title: str | None = None
    department_name: str | None = None


TeamPresenceStatus = Literal["LOGGED_IN", "LOGGED_OUT", "ON_LEAVE", "NOT_LOGGED_IN"]


class TeamPresenceRow(BaseModel):
    employee_id: uuid.UUID
    employee_code: str
    full_name: str
    department_name: str | None = None
    status: TeamPresenceStatus
    first_login: datetime | None = None
    last_logout: datetime | None = None
    worked_minutes: int = 0
    first_wifi_connected_at: datetime | None = None
    wifi_networks: list[str] = Field(default_factory=list)
    last_signal_at: datetime | None = None
    leave_type_name: str | None = None
    # Last clock-out note (e.g. no response after 7h/9h office check).
    logout_note: str | None = None


class TeamPresenceCounts(BaseModel):
    total: int = 0
    logged_in: int = 0
    logged_out: int = 0
    on_leave: int = 0
    not_logged_in: int = 0


class TeamPresenceResponse(BaseModel):
    work_date: date
    scope: Literal["ORGANIZATION", "TEAM"]
    counts: TeamPresenceCounts
    pending_leave_requests: int = 0
    rows: list[TeamPresenceRow]


class PresenceMonthSummary(BaseModel):
    month: str
    working_days: int
    present_days: int
    leave_days: float
    upcoming_leave_days: float
    absent_days: int
    total_worked_minutes: int
    average_daily_minutes: int
    today: PresenceDay
