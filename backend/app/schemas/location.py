"""
Pydantic Schemas for Location Telemetry, Compliance Verifications, and Disclosures (Phase 08)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.office import LocationPermissionStatus, VerificationMethod, VerificationStatus


class LocationVerifyRequest(BaseModel):
    latitude: float | None = Field(None, ge=-90.0, le=90.0)
    longitude: float | None = Field(None, ge=-180.0, le=180.0)
    accuracy_meters: float | None = Field(None, ge=0.0)
    is_mocked: bool = False
    permission_status: LocationPermissionStatus = LocationPermissionStatus.GRANTED
    source: str = Field(default="DESKTOP", max_length=50)
    client_event_id: str | None = Field(None, max_length=100)
    client_ssid: str | None = Field(None, max_length=100)
    client_bssid: str | None = Field(None, max_length=50)
    client_ip: str | None = Field(None, max_length=45)
    target_office_id: uuid.UUID | None = None
    metadata_json: dict[str, Any] | None = None


class LocationVerificationResponse(BaseModel):
    id: uuid.UUID
    location_event_id: uuid.UUID
    office_id: uuid.UUID | None
    office_geofence_id: uuid.UUID | None
    office_network_id: uuid.UUID | None
    verification_status: VerificationStatus
    verification_method: VerificationMethod
    distance_meters: float | None
    is_conclusive: bool
    confidence_score: float
    notes: str | None
    verified_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LocationEventResponse(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    latitude: float
    longitude: float
    accuracy_meters: float | None
    is_mocked: bool
    source: str
    permission_status: LocationPermissionStatus
    client_event_id: str | None
    recorded_at: datetime
    verification: LocationVerificationResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class LocationComplianceDisclosureResponse(BaseModel):
    organization_id: uuid.UUID
    disclosure_policy_name: str
    purpose: str
    gps_tracking_policy: str
    non_conclusive_rule: str
    data_retention_days: int
    employee_rights: list[str]
    retention_purge_enabled: bool

