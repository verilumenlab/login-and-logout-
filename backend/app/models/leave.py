"""
Leave Types, Balances, Requests, Approvals, and Documents Models
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.employee import EmployeeProfile
    from app.models.organization import Organization


class LeaveCategory(str, enum.Enum):
    ANNUAL = "ANNUAL"
    SICK = "SICK"
    CASUAL = "CASUAL"
    MATERNITY = "MATERNITY"
    PATERNITY = "PATERNITY"
    BEREAVEMENT = "BEREAVEMENT"
    UNPAID = "UNPAID"
    COMP_OFF = "COMP_OFF"


class LeaveStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class LeaveType(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Catalog of policy-backed absence classifications."""

    __tablename__ = "leave_types"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_leave_type_org_code"),)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[LeaveCategory] = mapped_column(Enum(LeaveCategory), default=LeaveCategory.ANNUAL, nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    annual_allowance: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    carryover_max_days: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    requires_attachment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    include_weekends: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="leave_types")
    balances: Mapped[list[LeaveBalance]] = relationship(
        "LeaveBalance", back_populates="leave_type", cascade="all, delete-orphan"
    )
    requests: Mapped[list[LeaveRequest]] = relationship(
        "LeaveRequest", back_populates="leave_type", cascade="all, delete-orphan"
    )


class LeaveBalance(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Annual entitlement, usage, and carryover credits per employee."""

    __tablename__ = "leave_balances"
    __table_args__ = (UniqueConstraint("employee_id", "leave_type_id", "year", name="uq_leave_balance_emp_year"),)

    employee_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("leave_types.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    allocated_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    used_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pending_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    carryover_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="leave_balances")
    employee: Mapped[EmployeeProfile] = relationship("EmployeeProfile", back_populates="leave_balances")
    leave_type: Mapped[LeaveType] = relationship("LeaveType", back_populates="balances")


class LeaveRequest(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Formal employee time-off application."""

    __tablename__ = "leave_requests"
    __table_args__ = (CheckConstraint("end_date >= start_date", name="chk_leave_dates"),)

    employee_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("leave_types.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_days: Mapped[float] = mapped_column(Float, nullable=False)
    is_half_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    half_day_period: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[LeaveStatus] = mapped_column(
        Enum(LeaveStatus), default=LeaveStatus.PENDING, index=True, nullable=False
    )
    manager_approval_status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False
    )
    hr_approval_status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="leave_requests")
    employee: Mapped[EmployeeProfile] = relationship("EmployeeProfile", back_populates="leave_requests")
    leave_type: Mapped[LeaveType] = relationship("LeaveType", back_populates="requests")
    approvals: Mapped[list[LeaveApproval]] = relationship(
        "LeaveApproval", back_populates="leave_request", cascade="all, delete-orphan"
    )
    documents: Mapped[list[LeaveDocument]] = relationship(
        "LeaveDocument", back_populates="leave_request", cascade="all, delete-orphan"
    )


class LeaveApproval(Base, UUIDMixin):
    """Sequential or multi-stage manager approval decision step."""

    __tablename__ = "leave_approvals"

    leave_request_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("leave_requests.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    stage: Mapped[str] = mapped_column(String(20), default="MANAGER", nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False)
    comments: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    leave_request: Mapped[LeaveRequest] = relationship("LeaveRequest", back_populates="approvals")
    approver: Mapped[EmployeeProfile] = relationship("EmployeeProfile", back_populates="leave_approvals")


class LeaveDocument(Base, UUIDMixin):
    """Uploaded medical certificate, travel itinerary, or supporting evidence."""

    __tablename__ = "leave_documents"

    leave_request_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("leave_requests.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    leave_request: Mapped[LeaveRequest] = relationship("LeaveRequest", back_populates="documents")
