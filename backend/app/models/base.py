"""
Base declarative class, mixins, and custom type definitions for SQLAlchemy models.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# Cross-dialect JSONB helper (native JSONB on PostgreSQL, standard JSON on SQLite)
JSONBType = JSONB().with_variant(sa.JSON(), "sqlite")


class UUIDMixin:
    """Provides a UUID v4 primary key compatible with PostgreSQL and SQLite."""

    id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        sort_order=-100,
    )


class TimestampMixin:
    """Enforces UTC timezone-aware created_at and updated_at tracking."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class TenantMixin:
    """Enforces organization-level data isolation on tenant-scoped entities."""

    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
