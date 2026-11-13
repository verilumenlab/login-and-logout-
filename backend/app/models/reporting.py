"""
Reporting Jobs and Generated Files Models
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONBType, TenantMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.auth import User
    from app.models.employee import EmployeeProfile
    from app.models.organization import Organization


class ReportType(str, enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    INDIVIDUAL = "INDIVIDUAL"
    CONSOLIDATED_HR = "CONSOLIDATED_HR"
    MANAGER_TEAM = "MANAGER_TEAM"
    ATTENDANCE_SUMMARY = "ATTENDANCE_SUMMARY"
    ACTIVITY_BREAKDOWN = "ACTIVITY_BREAKDOWN"
    LEAVE_BALANCES = "LEAVE_BALANCES"
    AUDIT_TRAIL = "AUDIT_TRAIL"


class ReportStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ReportSchedule(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Automated recurring report dispatch configuration."""

    __tablename__ = "report_schedules"
    __table_args__ = (UniqueConstraint("organization_id", "schedule_type", name="uq_report_schedule_org_type"),)

    schedule_type: Mapped[ReportType] = mapped_column(Enum(ReportType), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(100), default="0 6 * * *", nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    send_email: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recipient_emails: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON-encoded list of emails
    include_individual_reports: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_manager_reports: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_consolidated_report: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization")
    jobs: Mapped[list[ReportJob]] = relationship("ReportJob", back_populates="schedule")


class ReportJob(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Asynchronous batch analytical computation request."""

    __tablename__ = "report_jobs"

    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("report_schedules.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    requester_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    report_type: Mapped[ReportType] = mapped_column(Enum(ReportType), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus), default=ReportStatus.QUEUED, index=True, nullable=False
    )
    parameters_json: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, default=dict, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="report_jobs")
    schedule: Mapped[ReportSchedule | None] = relationship("ReportSchedule", back_populates="jobs")
    requester: Mapped[User] = relationship("User")
    files: Mapped[list[ReportFile]] = relationship(
        "ReportFile", back_populates="report_job", cascade="all, delete-orphan"
    )


class ReportFile(Base, UUIDMixin):
    """Rendered spreadsheet or document produced by a report job."""

    __tablename__ = "report_files"

    report_job_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("report_jobs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    report_job: Mapped[ReportJob] = relationship("ReportJob", back_populates="files")
    employee: Mapped[EmployeeProfile | None] = relationship("EmployeeProfile")
