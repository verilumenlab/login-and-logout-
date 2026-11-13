"""
Devices, Device Sessions, OS Activity Telemetry, and Agent Heartbeat Models
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONBType, TenantMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.attendance import AttendanceEvent
    from app.models.employee import EmployeeProfile
    from app.models.organization import Organization


class Device(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Enrolled and monitored hardware workstation or mobile device."""

    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("organization_id", "device_identifier", name="uq_device_org_identifier"),)

    device_identifier: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    device_name: Mapped[str] = mapped_column(String(150), nullable=False)
    os_name: Mapped[str] = mapped_column(String(50), nullable=False)
    os_version: Mapped[str] = mapped_column(String(50), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    mac_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    agent_version: Mapped[str] = mapped_column(String(50), nullable=False)
    is_trusted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="devices")
    sessions: Mapped[list[DeviceSession]] = relationship(
        "DeviceSession", back_populates="device", cascade="all, delete-orphan"
    )


class DeviceSession(Base, UUIDMixin):
    """Active desktop or background agent connection."""

    __tablename__ = "device_sessions"

    device_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    session_token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True, nullable=False
    )
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    device: Mapped[Device] = relationship("Device", back_populates="sessions")
    employee: Mapped[EmployeeProfile] = relationship("EmployeeProfile", back_populates="device_sessions")
    activity_events: Mapped[list[OSActivityEvent]] = relationship(
        "OSActivityEvent", back_populates="device_session", cascade="all, delete-orphan"
    )
    heartbeats: Mapped[list[AgentHeartbeat]] = relationship(
        "AgentHeartbeat", back_populates="device_session", cascade="all, delete-orphan"
    )
    attendance_events: Mapped[list[AttendanceEvent]] = relationship("AttendanceEvent", back_populates="device_session")


class OSActivityEvent(Base, UUIDMixin):
    """Granular foreground process, window title, and active telemetry capture."""

    __tablename__ = "os_activity_events"
    __table_args__ = (UniqueConstraint("device_session_id", "device_event_id", name="uq_device_session_event_id"),)

    device_session_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("device_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    device_event_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    application_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    window_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    process_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    idle_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    keystrokes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mouse_clicks_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, default=dict, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    device_session: Mapped[DeviceSession] = relationship("DeviceSession", back_populates="activity_events")


class AgentHeartbeat(Base, UUIDMixin):
    """Periodic health and performance heartbeat from desktop agent."""

    __tablename__ = "agent_heartbeats"

    device_session_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("device_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True, nullable=False
    )
    cpu_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    memory_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_idle: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_window: Mapped[str | None] = mapped_column(String(500), nullable=True)

    device_session: Mapped[DeviceSession] = relationship("DeviceSession", back_populates="heartbeats")
