"""
Operating System Session Monitoring and Lifecycle Event Models
Represents native OS-level session state transitions (Logon, Lock, Sleep, Wake, etc.)
Strictly separated from attendance records and foreground process activity.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONBType, UUIDMixin

if TYPE_CHECKING:
    from app.models.employee import EmployeeProfile


class OSSessionEventType(str, enum.Enum):
    """Canonical operating system lifecycle and session event types."""

    OS_LOGON = "OS_LOGON"
    OS_LOGOFF = "OS_LOGOFF"
    SESSION_LOCK = "SESSION_LOCK"
    SESSION_UNLOCK = "SESSION_UNLOCK"
    SYSTEM_STARTUP = "SYSTEM_STARTUP"
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"
    SYSTEM_SLEEP = "SYSTEM_SLEEP"
    SYSTEM_WAKE = "SYSTEM_WAKE"
    HEARTBEAT = "HEARTBEAT"
    USER_ACTIVITY = "USER_ACTIVITY"


class OSSessionEvent(Base, UUIDMixin):
    """
    Native operating system session and power state transition event.
    Conforms to the enterprise Phase 06 Common Event Contract.
    """

    __tablename__ = "os_session_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_os_session_event_id"),
        UniqueConstraint("device_id", "sequence_number", name="uq_device_sequence_number"),
        Index("ix_os_session_events_dev_occurred", "device_id", "occurred_at"),
        Index("ix_os_session_events_emp_occurred", "employee_id", "occurred_at"),
        Index("ix_os_session_events_type", "event_type"),
    )

    # 1. Event Identification & Audit
    event_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        unique=True,
        index=True,
        nullable=False,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    device_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    operating_system: Mapped[str] = mapped_column(String(50), nullable=False)  # "windows" | "macos" | "linux"
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # 2. Timing & Sync Metrics
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sync_delay_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    agent_version: Mapped[str] = mapped_column(String(50), default="1.0.0", nullable=False)

    # 3. Transparent Metadata (Context, Power, Network, Clock Anomaly notes)
    # Strictly zero keylogging, zero screen capture, zero hidden surveillance.
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONBType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # Relationships
    employee: Mapped[EmployeeProfile] = relationship(
        "EmployeeProfile",
        foreign_keys=[employee_id],
        lazy="joined",
    )

