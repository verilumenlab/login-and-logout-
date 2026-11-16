"""Pydantic schemas for Employee Application Release Management."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReleaseFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str


class ReleaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel_name: str
    version: str
    build_number: str | None = None
    release_notes: str | None = None
    status: str
    os_name: str
    package_size: int
    sha256: str
    sha512: str | None = None
    uploaded_at: datetime
    published_at: datetime | None = None
    created_at: datetime
    files: list[ReleaseFileOut] = Field(default_factory=list)


class ReleaseSummary(BaseModel):
    current_published_version: str | None = None
    current_published_id: uuid.UUID | None = None
    latest_uploaded_version: str | None = None
    latest_uploaded_id: uuid.UUID | None = None
    new_release_available: bool = False
    channel: str
    registered_devices: int = 0
    devices_needing_update: int = 0
    successful_updates: int = 0
    failed_updates: int = 0


class ReleaseActionResponse(BaseModel):
    id: uuid.UUID
    status: str
    message: str


class UpdateCheckRequest(BaseModel):
    current_version: str
    channel: str = "production"
    device_id: uuid.UUID | None = None
    os_name: str = "windows"


class UpdateCheckResponse(BaseModel):
    update_available: bool
    version: str | None = None
    release_id: uuid.UUID | None = None
    notes: str | None = None
    mandatory: bool = False
    package_size: int | None = None
    sha256: str | None = None
    download_url: str | None = None


class UpdateReportRequest(BaseModel):
    device_id: uuid.UUID
    channel: str = "production"
    from_version: str | None = None
    to_version: str | None = None
    release_id: uuid.UUID | None = None
    status: str  # success | failed | downloading | installing | skipped
    error_message: str | None = None
    installed_version: str | None = None


class UpdateReportResponse(BaseModel):
    ok: bool
    message: str


class DeviceUpdateStatusOut(BaseModel):
    device_id: uuid.UUID
    device_name: str
    device_identifier: str
    employee_id: uuid.UUID | None = None
    agent_version: str
    installed_version: str | None = None
    needs_update: bool
    last_update_status: str | None = None
    last_check_at: datetime | None = None
    last_seen_at: datetime | None = None


class UpdateEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    message: str | None = None
    release_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None
    details_json: dict[str, Any] | None = None
    created_at: datetime


class UpdatePolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_name: str
    min_supported_version: str | None = None
    force_update: bool
    auto_download: bool
    check_interval_minutes: int
    allow_rollback_publish: bool
