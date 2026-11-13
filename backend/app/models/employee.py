"""
Employee Profile and Manager Assignment Models
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONBType, TenantMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.attendance import AttendanceAdjustment, AttendanceDay
    from app.models.auth import User
    from app.models.department import Department
    from app.models.device import DeviceSession
    from app.models.leave import LeaveApproval, LeaveBalance, LeaveRequest
    from app.models.office import LocationEvent
    from app.models.organization import Organization
    from app.models.schedule import WorkSchedule


class EmploymentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ON_LEAVE = "ON_LEAVE"
    PROBATION = "PROBATION"
    TERMINATED = "TERMINATED"


class EmployeeProfile(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Detailed corporate employee personnel record."""

    __tablename__ = "employee_profiles"
    __table_args__ = (UniqueConstraint("organization_id", "employee_code", name="uq_employee_code_per_org"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    employee_code: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    work_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("work_schedules.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    employment_status: Mapped[EmploymentStatus] = mapped_column(
        Enum(EmploymentStatus),
        default=EmploymentStatus.ACTIVE,
        nullable=False,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, default=dict, nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="employee_profiles")
    user: Mapped[User] = relationship("User", back_populates="employee_profile")
    department: Mapped[Department | None] = relationship("Department", back_populates="employees")
    work_schedule: Mapped[WorkSchedule | None] = relationship("WorkSchedule", back_populates="employees")

    direct_managers: Mapped[list[ManagerAssignment]] = relationship(
        "ManagerAssignment",
        foreign_keys="ManagerAssignment.employee_id",
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    direct_reports: Mapped[list[ManagerAssignment]] = relationship(
        "ManagerAssignment",
        foreign_keys="ManagerAssignment.manager_id",
        back_populates="manager",
        cascade="all, delete-orphan",
    )

    device_sessions: Mapped[list[DeviceSession]] = relationship(
        "DeviceSession", back_populates="employee", cascade="all, delete-orphan"
    )
    location_events: Mapped[list[LocationEvent]] = relationship(
        "LocationEvent", back_populates="employee", cascade="all, delete-orphan"
    )
    attendance_days: Mapped[list[AttendanceDay]] = relationship(
        "AttendanceDay", back_populates="employee", cascade="all, delete-orphan"
    )
    attendance_adjustments_requested: Mapped[list[AttendanceAdjustment]] = relationship(
        "AttendanceAdjustment",
        foreign_keys="AttendanceAdjustment.requester_id",
        back_populates="requester",
    )
    attendance_adjustments_approved: Mapped[list[AttendanceAdjustment]] = relationship(
        "AttendanceAdjustment",
        foreign_keys="AttendanceAdjustment.approver_id",
        back_populates="approver",
    )
    leave_balances: Mapped[list[LeaveBalance]] = relationship(
        "LeaveBalance", back_populates="employee", cascade="all, delete-orphan"
    )
    leave_requests: Mapped[list[LeaveRequest]] = relationship(
        "LeaveRequest", back_populates="employee", cascade="all, delete-orphan"
    )
    leave_approvals: Mapped[list[LeaveApproval]] = relationship("LeaveApproval", back_populates="approver")


class ManagerAssignment(Base, UUIDMixin, TenantMixin):
    """Hierarchical or matrix management reporting link."""

    __tablename__ = "manager_assignments"
    __table_args__ = (UniqueConstraint("employee_id", "manager_id", name="uq_emp_manager_assignment"),)

    employee_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    manager_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    employee: Mapped[EmployeeProfile] = relationship(
        "EmployeeProfile", foreign_keys=[employee_id], back_populates="direct_managers"
    )
    manager: Mapped[EmployeeProfile] = relationship(
        "EmployeeProfile", foreign_keys=[manager_id], back_populates="direct_reports"
    )
