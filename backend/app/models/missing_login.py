"""
Missing-login alert queue — requires Admin approval before emails are sent.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.auth import User
    from app.models.employee import EmployeeProfile
    from app.models.organization import Organization


class MissingLoginAlertStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SENT = "SENT"


class MissingLoginAlert(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """One row per employee per work day waiting for (or after) admin mail approval."""

    __tablename__ = "missing_login_alerts"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_missing_login_emp_date"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    employee_name: Mapped[str] = mapped_column(String(200), nullable=False)
    employee_email: Mapped[str] = mapped_column(String(255), nullable=False)
    employee_code: Mapped[str] = mapped_column(String(50), nullable=False)
    department_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    scheduled_shift: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[MissingLoginAlertStatus] = mapped_column(
        Enum(MissingLoginAlertStatus),
        default=MissingLoginAlertStatus.PENDING,
        index=True,
        nullable=False,
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    emails_sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    organization: Mapped[Organization] = relationship("Organization")
    employee: Mapped[EmployeeProfile] = relationship("EmployeeProfile")
    reviewed_by: Mapped[User | None] = relationship("User")
