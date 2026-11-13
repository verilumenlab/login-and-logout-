"""
Pydantic Schemas for Corporate Offices, Geofences, and Authorized Networks (Phase 08)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OfficeGeofenceBase(BaseModel):
    name: str = Field(..., max_length=100)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    radius_meters: float = Field(default=100.0, ge=10.0, le=50000.0)
    is_active: bool = True


class OfficeGeofenceCreate(OfficeGeofenceBase):
    pass


class OfficeGeofenceResponse(OfficeGeofenceBase):
    id: uuid.UUID
    office_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OfficeNetworkBase(BaseModel):
    name: str = Field(..., max_length=100)
    ssid: str | None = Field(None, max_length=100)
    ip_address: str | None = Field(None, max_length=45)
    subnet_cidr: str | None = Field(None, max_length=50)
    bssid_mac: str | None = Field(None, max_length=50)
    is_active: bool = True


class OfficeNetworkCreate(OfficeNetworkBase):
    pass


class OfficeNetworkResponse(OfficeNetworkBase):
    id: uuid.UUID
    office_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OfficeCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    code: str = Field(..., min_length=2, max_length=50)
    address: str = Field(..., min_length=5, max_length=255)
    timezone: str = Field(default="UTC", max_length=50)
    # Optional initial geofence specification
    latitude: float | None = Field(None, ge=-90.0, le=90.0)
    longitude: float | None = Field(None, ge=-180.0, le=180.0)
    radius_meters: float | None = Field(default=100.0, ge=10.0, le=50000.0)
    # Optional initial network configurations
    networks: list[OfficeNetworkCreate] | None = None


class OfficeUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=150)
    address: str | None = Field(None, min_length=5, max_length=255)
    timezone: str | None = Field(None, max_length=50)
    is_active: bool | None = None


class OfficeResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    code: str
    address: str
    timezone: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    geofences: list[OfficeGeofenceResponse] = []
    networks: list[OfficeNetworkResponse] = []

    model_config = ConfigDict(from_attributes=True)


class OfficeListResponse(BaseModel):
    items: list[OfficeResponse]
    total: int
    page: int
    page_size: int

