"""
Offices, Geofences, Networks, and Location Verification Models
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONBType, TenantMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.attendance import AttendanceEvent
    from app.models.employee import EmployeeProfile
    from app.models.organization import Organization


class VerificationStatus(str, enum.Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    UNAVAILABLE = "UNAVAILABLE"
    OUTSIDE_GEOFENCE = "OUTSIDE_GEOFENCE"
    UNRECOGNIZED_NETWORK = "UNRECOGNIZED_NETWORK"
    SPOOF_DETECTED = "SPOOF_DETECTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"


class VerificationMethod(str, enum.Enum):
    GPS = "GPS"
    WIFI_NETWORK = "WIFI_NETWORK"
    IP_APPROXIMATE = "IP_APPROXIMATE"
    HYBRID = "HYBRID"
    UNAVAILABLE = "UNAVAILABLE"


class LocationPermissionStatus(str, enum.Enum):
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    RESTRICTED = "RESTRICTED"
    UNAVAILABLE = "UNAVAILABLE"


class Office(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Corporate physical work location."""

    __tablename__ = "offices"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_office_org_code"),)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="offices")
    geofences: Mapped[list[OfficeGeofence]] = relationship(
        "OfficeGeofence", back_populates="office", cascade="all, delete-orphan"
    )
    networks: Mapped[list[OfficeNetwork]] = relationship(
        "OfficeNetwork", back_populates="office", cascade="all, delete-orphan"
    )
    location_verifications: Mapped[list[LocationVerification]] = relationship(
        "LocationVerification", back_populates="office"
    )


class OfficeGeofence(Base, UUIDMixin):
    """Geographical perimeter boundary surrounding an office."""

    __tablename__ = "office_geofences"

    office_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("offices.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    radius_meters: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    office: Mapped[Office] = relationship("Office", back_populates="geofences")
    location_verifications: Mapped[list[LocationVerification]] = relationship(
        "LocationVerification", back_populates="office_geofence"
    )


class OfficeNetwork(Base, UUIDMixin):
    """Authorized office Wi-Fi network and CIDR gateway."""

    __tablename__ = "office_networks"

    office_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("offices.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    ssid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    subnet_cidr: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bssid_mac: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    office: Mapped[Office] = relationship("Office", back_populates="networks")
    location_verifications: Mapped[list[LocationVerification]] = relationship(
        "LocationVerification", back_populates="office_network"
    )


class LocationEvent(Base, UUIDMixin):
    """Raw GPS / Network telemetry event transmitted by client devices."""

    __tablename__ = "location_events"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    accuracy_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_mocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="DESKTOP", nullable=False)
    permission_status: Mapped[LocationPermissionStatus] = mapped_column(
        Enum(LocationPermissionStatus), default=LocationPermissionStatus.GRANTED, nullable=False
    )
    client_event_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True, nullable=False
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, default=dict, nullable=True)

    employee: Mapped[EmployeeProfile] = relationship("EmployeeProfile", back_populates="location_events")
    verification: Mapped[LocationVerification | None] = relationship(
        "LocationVerification", back_populates="location_event", uselist=False, cascade="all, delete-orphan"
    )


class LocationVerification(Base, UUIDMixin):
    """Compliance verification check matching a location event against office perimeter or network."""

    __tablename__ = "location_verifications"

    location_event_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("location_events.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    office_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("offices.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    office_geofence_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("office_geofences.id", ondelete="SET NULL"),
        nullable=True,
    )
    office_network_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("office_networks.id", ondelete="SET NULL"),
        nullable=True,
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus),
        default=VerificationStatus.VERIFIED,
        nullable=False,
    )
    verification_method: Mapped[VerificationMethod] = mapped_column(
        Enum(VerificationMethod),
        default=VerificationMethod.GPS,
        nullable=False,
    )
    distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_conclusive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    location_event: Mapped[LocationEvent] = relationship("LocationEvent", back_populates="verification")
    office: Mapped[Office | None] = relationship("Office", back_populates="location_verifications")
    office_geofence: Mapped[OfficeGeofence | None] = relationship(
        "OfficeGeofence", back_populates="location_verifications"
    )
    office_network: Mapped[OfficeNetwork | None] = relationship(
        "OfficeNetwork", back_populates="location_verifications"
    )
    attendance_events: Mapped[list[AttendanceEvent]] = relationship(
        "AttendanceEvent", back_populates="location_verification"
    )
