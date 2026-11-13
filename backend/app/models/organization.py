"""
Organization Database Model (Multi-tenant Foundation)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONBType, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.attendance import AttendanceDay
    from app.models.auth import AuditLog, IdempotencyKey, Role, User
    from app.models.department import Department
    from app.models.device import Device
    from app.models.employee import EmployeeProfile
    from app.models.leave import LeaveBalance, LeaveRequest, LeaveType
    from app.models.notification import EmailOutbox, EmailTemplate
    from app.models.office import Office
    from app.models.reporting import ReportJob
    from app.models.schedule import Holiday, WorkSchedule


class Organization(Base, UUIDMixin, TimestampMixin):
    """Represents a top-level corporate tenant."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings_json: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, default=dict, nullable=True)

    # Relationships
    users: Mapped[list[User]] = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    roles: Mapped[list[Role]] = relationship("Role", back_populates="organization", cascade="all, delete-orphan")
    departments: Mapped[list[Department]] = relationship(
        "Department", back_populates="organization", cascade="all, delete-orphan"
    )
    employee_profiles: Mapped[list[EmployeeProfile]] = relationship(
        "EmployeeProfile", back_populates="organization", cascade="all, delete-orphan"
    )
    work_schedules: Mapped[list[WorkSchedule]] = relationship(
        "WorkSchedule", back_populates="organization", cascade="all, delete-orphan"
    )
    holidays: Mapped[list[Holiday]] = relationship(
        "Holiday", back_populates="organization", cascade="all, delete-orphan"
    )
    offices: Mapped[list[Office]] = relationship("Office", back_populates="organization", cascade="all, delete-orphan")
    devices: Mapped[list[Device]] = relationship("Device", back_populates="organization", cascade="all, delete-orphan")
    attendance_days: Mapped[list[AttendanceDay]] = relationship(
        "AttendanceDay", back_populates="organization", cascade="all, delete-orphan"
    )
    leave_types: Mapped[list[LeaveType]] = relationship(
        "LeaveType", back_populates="organization", cascade="all, delete-orphan"
    )
    leave_balances: Mapped[list[LeaveBalance]] = relationship(
        "LeaveBalance", back_populates="organization", cascade="all, delete-orphan"
    )
    leave_requests: Mapped[list[LeaveRequest]] = relationship(
        "LeaveRequest", back_populates="organization", cascade="all, delete-orphan"
    )
    report_jobs: Mapped[list[ReportJob]] = relationship(
        "ReportJob", back_populates="organization", cascade="all, delete-orphan"
    )
    email_templates: Mapped[list[EmailTemplate]] = relationship(
        "EmailTemplate", back_populates="organization", cascade="all, delete-orphan"
    )
    email_outbox: Mapped[list[EmailOutbox]] = relationship(
        "EmailOutbox", back_populates="organization", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog", back_populates="organization", cascade="all, delete-orphan"
    )
    idempotency_keys: Mapped[list[IdempotencyKey]] = relationship(
        "IdempotencyKey", back_populates="organization", cascade="all, delete-orphan"
    )
