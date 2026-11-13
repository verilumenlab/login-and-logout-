"""
Email Templates, Outbox Dispatch, and Delivery Logging Models
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.organization import Organization


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class DeliveryEventType(str, enum.Enum):
    DELIVERED = "DELIVERED"
    BOUNCED = "BOUNCED"
    DROPPED = "DROPPED"
    OPENED = "OPENED"
    CLICKED = "CLICKED"


class EmailTemplate(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Reusable transactional email blueprint."""

    __tablename__ = "email_templates"
    __table_args__ = (UniqueConstraint("organization_id", "template_key", name="uq_email_template_org_key"),)

    template_key: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    subject_template: Mapped[str] = mapped_column(String(255), nullable=False)
    body_html_template: Mapped[str] = mapped_column(Text, nullable=False)
    body_text_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="email_templates")
    outbox_messages: Mapped[list[EmailOutbox]] = relationship("EmailOutbox", back_populates="template")


class EmailOutbox(Base, UUIDMixin, TenantMixin):
    """Asynchronous transactional email dispatch buffer."""

    __tablename__ = "email_outbox"

    template_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("email_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    recipient_email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    recipient_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    sender_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus), default=OutboxStatus.PENDING, index=True, nullable=False
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="email_outbox")
    template: Mapped[EmailTemplate | None] = relationship("EmailTemplate", back_populates="outbox_messages")
    delivery_logs: Mapped[list[EmailDeliveryLog]] = relationship(
        "EmailDeliveryLog", back_populates="outbox_message", cascade="all, delete-orphan"
    )


class EmailDeliveryLog(Base, UUIDMixin):
    """Webhook and telemetry receipts from external mail transfer agents."""

    __tablename__ = "email_delivery_logs"

    email_outbox_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("email_outbox.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    event_type: Mapped[DeliveryEventType] = mapped_column(Enum(DeliveryEventType), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    outbox_message: Mapped[EmailOutbox] = relationship("EmailOutbox", back_populates="delivery_logs")
