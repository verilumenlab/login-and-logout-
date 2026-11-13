"""
Work Schedules & Holidays Models
"""

from __future__ import annotations

from datetime import date, time
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Date, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONBType, TenantMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.employee import EmployeeProfile
    from app.models.organization import Organization


class WorkSchedule(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Defines shift working hours, grace periods, and expected working days."""

    __tablename__ = "work_schedules"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shift_start_time: Mapped[time] = mapped_column(Time, nullable=False)
    shift_end_time: Mapped[time] = mapped_column(Time, nullable=False)
    flexible_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    working_days: Mapped[Any | None] = mapped_column(JSONBType, default=[1, 2, 3, 4, 5], nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="work_schedules")
    employees: Mapped[list[EmployeeProfile]] = relationship("EmployeeProfile", back_populates="work_schedule")


class Holiday(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Recognized corporate or public non-working day."""

    __tablename__ = "holidays"
    __table_args__ = (UniqueConstraint("organization_id", "holiday_date", name="uq_holiday_org_date"),)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    holiday_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="holidays")
