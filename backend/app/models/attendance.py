"""
Attendance Days, Events, Breaks, and Adjustments Models
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONBType, TenantMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.device import DeviceSession
    from app.models.employee import EmployeeProfile
    from app.models.office import LocationVerification
    from app.models.organization import Organization


class AttendanceStatus(str, enum.Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    HALF_DAY = "HALF_DAY"
    LATE = "LATE"
    ON_LEAVE = "ON_LEAVE"
    HOLIDAY = "HOLIDAY"
    WEEKEND = "WEEKEND"


class AttendanceEventType(str, enum.Enum):
    CLOCK_IN = "CLOCK_IN"
    CLOCK_OUT = "CLOCK_OUT"


class AttendanceSource(str, enum.Enum):
    WEB = "WEB"
    DESKTOP = "DESKTOP"
    MOBILE = "MOBILE"
    MANUAL_ENTRY = "MANUAL_ENTRY"
    SYSTEM = "SYSTEM"


class BreakType(str, enum.Enum):
    LUNCH = "LUNCH"
    COFFEE = "COFFEE"
    PERSONAL = "PERSONAL"
    MEETING = "MEETING"


class BreakSource(str, enum.Enum):
    MANUAL = "MANUAL"
    AUTO_IDLE = "AUTO_IDLE"
    AUTO_LOCK = "AUTO_LOCK"
    AUTO_SLEEP = "AUTO_SLEEP"
    AUTO_APP_CLOSE = "AUTO_APP_CLOSE"


class AdjustmentType(str, enum.Enum):
    MISSED_CLOCK_IN = "MISSED_CLOCK_IN"
    MISSED_CLOCK_OUT = "MISSED_CLOCK_OUT"
    TIME_CORRECTION = "TIME_CORRECTION"
    STATUS_OVERRIDE = "STATUS_OVERRIDE"


class AdjustmentStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AttendanceDay(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Summarized daily attendance roll-up for a specific employee."""

    __tablename__ = "attendance_days"
    __table_args__ = (UniqueConstraint("employee_id", "work_date", name="uq_attendance_day_per_emp_date"),)

    employee_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus),
        default=AttendanceStatus.PRESENT,
        nullable=False,
    )
    shift_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shift_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_work_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_break_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_idle_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_overtime: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    early_departure_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_wfh: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_missing_checkout: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, default=dict, nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="attendance_days")
    employee: Mapped[EmployeeProfile] = relationship("EmployeeProfile", back_populates="attendance_days")
    events: Mapped[list[AttendanceEvent]] = relationship(
        "AttendanceEvent", back_populates="attendance_day", cascade="all, delete-orphan"
    )
    breaks: Mapped[list[AttendanceBreak]] = relationship(
        "AttendanceBreak", back_populates="attendance_day", cascade="all, delete-orphan"
    )
    adjustments: Mapped[list[AttendanceAdjustment]] = relationship(
        "AttendanceAdjustment", back_populates="attendance_day", cascade="all, delete-orphan"
    )


class AttendanceEvent(Base, UUIDMixin):
    """Discrete clock-in or clock-out operational timestamp."""

    __tablename__ = "attendance_events"

    attendance_day_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("attendance_days.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    event_type: Mapped[AttendanceEventType] = mapped_column(Enum(AttendanceEventType), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True, nullable=False
    )
    location_verification_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("location_verifications.id", ondelete="SET NULL"),
        nullable=True,
    )
    device_session_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("device_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[AttendanceSource] = mapped_column(
        Enum(AttendanceSource),
        default=AttendanceSource.WEB,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    client_event_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    is_wfh: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sync_delay_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # Relationships
    attendance_day: Mapped[AttendanceDay] = relationship("AttendanceDay", back_populates="events")
    location_verification: Mapped[LocationVerification | None] = relationship(
        "LocationVerification", back_populates="attendance_events"
    )
    device_session: Mapped[DeviceSession | None] = relationship("DeviceSession", back_populates="attendance_events")


class AttendanceBreak(Base, UUIDMixin):
    """Break periods taken throughout a working shift."""

    __tablename__ = "attendance_breaks"

    attendance_day_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("attendance_days.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    break_type: Mapped[BreakType] = mapped_column(Enum(BreakType), default=BreakType.LUNCH, nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default=BreakSource.MANUAL.value, nullable=False)
    client_event_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    attendance_day: Mapped[AttendanceDay] = relationship("AttendanceDay", back_populates="breaks")


class AttendanceAdjustment(Base, UUIDMixin):
    """Employee correction requests for missed or erroneous shift events."""

    __tablename__ = "attendance_adjustments"

    attendance_day_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("attendance_days.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    adjustment_type: Mapped[AdjustmentType] = mapped_column(Enum(AdjustmentType), nullable=False)
    requested_shift_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_shift_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AdjustmentStatus] = mapped_column(
        Enum(AdjustmentStatus), default=AdjustmentStatus.PENDING, nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    attendance_day: Mapped[AttendanceDay] = relationship("AttendanceDay", back_populates="adjustments")
    requester: Mapped[EmployeeProfile] = relationship(
        "EmployeeProfile", foreign_keys=[requester_id], back_populates="attendance_adjustments_requested"
    )
    approver: Mapped[EmployeeProfile | None] = relationship(
        "EmployeeProfile", foreign_keys=[approver_id], back_populates="attendance_adjustments_approved"
    )
