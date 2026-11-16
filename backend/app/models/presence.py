"""
Employee Presence Events
Raw login/logout signals captured by the employee desktop agent: application
login/logout and laptop Wi-Fi connect/disconnect. Each event may open or close
the employee's attendance session (see app.services.presence_service).
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.employee import EmployeeProfile


class PresenceEventType(str, enum.Enum):
    APP_LOGIN = "APP_LOGIN"
    APP_LOGOUT = "APP_LOGOUT"
    WIFI_CONNECTED = "WIFI_CONNECTED"
    WIFI_DISCONNECTED = "WIFI_DISCONNECTED"
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"
    SYSTEM_SUSPEND = "SYSTEM_SUSPEND"
    SYSTEM_RESUME = "SYSTEM_RESUME"
    SYSTEM_STARTUP = "SYSTEM_STARTUP"


LOGIN_EVENT_TYPES = frozenset(
    {
        PresenceEventType.APP_LOGIN,
        PresenceEventType.WIFI_CONNECTED,
        PresenceEventType.SYSTEM_STARTUP,
    }
)

LOGOUT_EVENT_TYPES = frozenset(
    {
        PresenceEventType.APP_LOGOUT,
        PresenceEventType.WIFI_DISCONNECTED,
        PresenceEventType.SYSTEM_SHUTDOWN,
    }
)

# Sleep/wake are audited as PresenceEvents but map to AttendanceBreaks (auto sleep),
# not clock-in/out — otherwise unpaid break minutes would double-count the gap.
AUDIT_ONLY_PRESENCE_EVENT_TYPES = frozenset(
    {
        PresenceEventType.SYSTEM_SUSPEND,
        PresenceEventType.SYSTEM_RESUME,
    }
)


class PresenceAttendanceAction(str, enum.Enum):
    CLOCK_IN = "CLOCK_IN"
    CLOCK_OUT = "CLOCK_OUT"
    NONE = "NONE"


class PresenceEvent(Base, UUIDMixin, TenantMixin):
    __tablename__ = "presence_events"
    __table_args__ = (
        UniqueConstraint("employee_id", "client_event_id", name="uq_presence_employee_client_event"),
        Index("ix_presence_events_emp_occurred", "employee_id", "occurred_at"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    client_event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ssid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bssid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attendance_action: Mapped[str] = mapped_column(
        String(20), default=PresenceAttendanceAction.NONE.value, nullable=False
    )

    employee: Mapped[EmployeeProfile] = relationship("EmployeeProfile", foreign_keys=[employee_id])
