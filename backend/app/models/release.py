"""
Employee Application Release Management models (Electron / Windows auto-upgrade).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONBType, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.auth import User
    from app.models.device import Device
    from app.models.employee import EmployeeProfile
    from app.models.organization import Organization


class ApplicationReleaseChannel(Base, UUIDMixin, TimestampMixin):
    """Release distribution channel (staging / production)."""

    __tablename__ = "application_release_channels"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    releases: Mapped[list[ApplicationRelease]] = relationship(
        "ApplicationRelease", back_populates="channel", cascade="all, delete-orphan"
    )
    policies: Mapped[list[ApplicationUpdatePolicy]] = relationship(
        "ApplicationUpdatePolicy", back_populates="channel", cascade="all, delete-orphan"
    )


class ApplicationRelease(Base, UUIDMixin, TimestampMixin):
    """A versioned Windows Electron installer release package."""

    __tablename__ = "application_releases"
    __table_args__ = (
        UniqueConstraint("channel_id", "version", name="uq_release_channel_version"),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("application_release_channels.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    build_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # uploaded | approved | published | paused | cancelled | rolled_back
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="uploaded", index=True)
    os_name: Mapped[str] = mapped_column(String(30), nullable=False, default="windows")
    package_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    sha512: Mapped[str | None] = mapped_column(String(128), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, default=dict, nullable=True)

    channel: Mapped[ApplicationReleaseChannel] = relationship(
        "ApplicationReleaseChannel", back_populates="releases"
    )
    files: Mapped[list[ApplicationReleaseFile]] = relationship(
        "ApplicationReleaseFile", back_populates="release", cascade="all, delete-orphan"
    )
    created_by: Mapped[User | None] = relationship("User", foreign_keys=[created_by_user_id])


class ApplicationReleaseFile(Base, UUIDMixin, TimestampMixin):
    """Stored artifact for a release (setup exe, blockmap, latest.yml)."""

    __tablename__ = "application_release_files"

    release_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("application_releases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # setup | blockmap | latest_yml
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False, default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    release: Mapped[ApplicationRelease] = relationship("ApplicationRelease", back_populates="files")


class ApplicationUpdatePolicy(Base, UUIDMixin, TimestampMixin):
    """Per-channel update policy defaults for desktop clients."""

    __tablename__ = "application_update_policies"
    __table_args__ = (UniqueConstraint("channel_id", name="uq_update_policy_channel"),)

    channel_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("application_release_channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    min_supported_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    force_update: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_download: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    check_interval_minutes: Mapped[int] = mapped_column(Integer, default=240, nullable=False)
    allow_rollback_publish: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    channel: Mapped[ApplicationReleaseChannel] = relationship(
        "ApplicationReleaseChannel", back_populates="policies"
    )


class EmployeeAppInstallation(Base, UUIDMixin, TimestampMixin):
    """Update posture for an enrolled device (device remains hardware source of truth)."""

    __tablename__ = "employee_app_installations"
    __table_args__ = (UniqueConstraint("device_id", name="uq_app_installation_device"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel_name: Mapped[str] = mapped_column(String(50), nullable=False, default="production")
    installed_version: Mapped[str] = mapped_column(String(50), nullable=False)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_update_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization: Mapped[Organization] = relationship("Organization")
    device: Mapped[Device] = relationship("Device")
    employee: Mapped[EmployeeProfile | None] = relationship("EmployeeProfile")


class EmployeeUpdateHistory(Base, UUIDMixin):
    """Per-device update attempt history."""

    __tablename__ = "employee_update_history"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    release_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("application_releases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    from_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # pending | downloading | installing | success | failed | skipped
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    device: Mapped[Device] = relationship("Device")
    release: Mapped[ApplicationRelease | None] = relationship("ApplicationRelease")


class ApplicationUpdateEvent(Base, UUIDMixin):
    """Audit stream for release lifecycle and device update actions."""

    __tablename__ = "application_update_events"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    release_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("application_releases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # upload | approve | publish | pause | cancel | rollback | download | install_ok | install_fail | ci_register
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, default=dict, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )
