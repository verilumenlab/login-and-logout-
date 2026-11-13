"""
Authentication, Authorization, RBAC, Tokens, Audit, and Idempotency Models
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONBType, TenantMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.employee import EmployeeProfile
    from app.models.organization import Organization


class Permission(Base, UUIDMixin):
    """Granular operational authority."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    module: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # Relationships
    role_permissions: Mapped[list[RolePermission]] = relationship(
        "RolePermission", back_populates="permission", cascade="all, delete-orphan"
    )


class Role(Base, UUIDMixin, TimestampMixin):
    """Named collection of permissions within an organization or system-wide."""

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_role_org_name"),)

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    organization: Mapped[Organization | None] = relationship("Organization", back_populates="roles")
    role_permissions: Mapped[list[RolePermission]] = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )
    users: Mapped[list[User]] = relationship("User", back_populates="role")


class RolePermission(Base):
    """Junction binding roles to granular permissions."""

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )

    role: Mapped[Role] = relationship("Role", back_populates="role_permissions")
    permission: Mapped[Permission] = relationship("Permission", back_populates="role_permissions")


class User(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Corporate account identity with credential state and RBAC role."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_user_org_email"),)

    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="users")
    role: Mapped[Role] = relationship("Role", back_populates="users")
    employee_profile: Mapped[EmployeeProfile | None] = relationship(
        "EmployeeProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    password_reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        "PasswordResetToken", back_populates="user", cascade="all, delete-orphan"
    )
    login_history: Mapped[list[LoginHistory]] = relationship(
        "LoginHistory", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        """Convenience property to access person's name or email identifier."""
        try:
            if self.employee_profile:
                return f"{self.employee_profile.first_name} {self.employee_profile.last_name}".strip()
        except Exception:
            pass
        return self.email.split("@")[0].replace(".", " ").title()
    audit_logs: Mapped[list[AuditLog]] = relationship("AuditLog", back_populates="user")
    idempotency_keys: Mapped[list[IdempotencyKey]] = relationship("IdempotencyKey", back_populates="user")


class RefreshToken(Base, UUIDMixin):
    """Cryptographically hashed rotating refresh token session."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    family_id: Mapped[uuid.UUID | None] = mapped_column(sa.UUID(as_uuid=True), index=True, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    device_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")


class PasswordResetToken(Base, UUIDMixin):
    """Secure password reset token and optional 6-digit email OTP."""

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    otp_code: Mapped[str | None] = mapped_column(String(6), index=True, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="password_reset_tokens")


class LoginHistory(Base, UUIDMixin):
    """Tracks authentication history, failure reasons, and device metadata."""

    __tablename__ = "login_history"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True, nullable=False
    )

    user: Mapped[User | None] = relationship("User", back_populates="login_history")


class IdempotencyKey(Base, UUIDMixin, TenantMixin):
    """Ensures exactly-once execution of mutating API endpoints."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key", name="uq_idempotency_key_org"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    target_path: Mapped[str] = mapped_column(String(255), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_headers: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    organization: Mapped[Organization] = relationship("Organization", back_populates="idempotency_keys")
    user: Mapped[User | None] = relationship("User", back_populates="idempotency_keys")


class AuditLog(Base, UUIDMixin, TenantMixin):
    """Immutable audit trail for compliance and security events."""

    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    diff_json: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True, nullable=False
    )

    organization: Mapped[Organization] = relationship("Organization", back_populates="audit_logs")
    user: Mapped[User | None] = relationship("User", back_populates="audit_logs")
