"""
Notification & Centralized Email Management Endpoints (Phase 12)

Provides:
- Outbox inspection with filtering & pagination
- Delivery log tracking and audit receipts
- Outbox retry triggers
- Email template catalog & schema previews
- Test email dispatch
- Background queue manual flush
- External delivery receipt webhook
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import get_current_active_user, require_role
from app.models.auth import User
from app.models.notification import DeliveryEventType, EmailDeliveryLog, EmailOutbox, OutboxStatus
from app.services.email_service import EmailService
from app.services.email_templates import TEMPLATES_CONFIG, render_email_template

router = APIRouter()


class DeliveryLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: DeliveryEventType
    provider_message_id: str | None = None
    response_code: int | None = None
    response_body: str | None = None
    timestamp: datetime


class EmailOutboxResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    recipient_email: str
    recipient_name: str | None = None
    sender_email: str | None = None
    sender_name: str | None = None
    subject: str
    body_html: str
    body_text: str | None = None
    attachments: str | None = None
    status: OutboxStatus
    retry_count: int
    idempotency_key: str | None = None
    error_message: str | None = None
    scheduled_at: datetime
    sent_at: datetime | None = None
    created_at: datetime
    delivery_logs: list[DeliveryLogResponse] = []


class EmailTemplateInfo(BaseModel):
    template_key: str
    subject_pattern: str
    badge_text: str
    badge_class: str
    required_variables: list[str]


class SendTestEmailRequest(BaseModel):
    recipient_email: EmailStr
    recipient_name: str | None = "Platform Administrator"
    template_key: str = "attendance_daily_report"
    context: dict[str, Any] = Field(default_factory=dict)


class DeliveryWebhookPayload(BaseModel):
    email_outbox_id: uuid.UUID
    event_type: DeliveryEventType
    provider_message_id: str | None = None
    response_code: int = 200
    response_body: str | None = None


@router.get("/outbox", response_model=list[EmailOutboxResponse])
async def list_email_outbox(
    status_filter: OutboxStatus | None = Query(default=None, alias="status"),
    recipient: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(
        require_role(["Admin", "Administrator", "Super Admin", "HR", "HR Manager"])
    ),
    db: AsyncSession = Depends(get_db),
) -> Sequence[EmailOutbox]:
    """
    Retrieve transactional email outbox history with delivery tracking logs.
    Restricted to HR and Admin roles.
    """
    stmt = (
        select(EmailOutbox)
        .options(selectinload(EmailOutbox.delivery_logs))
        .where(EmailOutbox.organization_id == current_user.organization_id)
    )

    if status_filter:
        stmt = stmt.where(EmailOutbox.status == status_filter)
    if recipient:
        stmt = stmt.where(EmailOutbox.recipient_email.ilike(f"%{recipient.strip()}%"))

    stmt = stmt.order_by(desc(EmailOutbox.created_at)).offset(offset).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/outbox/{outbox_id}", response_model=EmailOutboxResponse)
async def get_email_outbox_entry(
    outbox_id: uuid.UUID,
    current_user: User = Depends(
        require_role(["Admin", "Administrator", "Super Admin", "HR", "HR Manager"])
    ),
    db: AsyncSession = Depends(get_db),
) -> EmailOutbox:
    """Retrieve full audit record and delivery logs for a specific email."""
    stmt = (
        select(EmailOutbox)
        .options(selectinload(EmailOutbox.delivery_logs))
        .where(
            EmailOutbox.id == outbox_id,
            EmailOutbox.organization_id == current_user.organization_id,
        )
    )
    res = await db.execute(stmt)
    entry = res.scalars().first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email outbox record not found in this organization.",
        )
    return entry


@router.post("/outbox/{outbox_id}/retry", response_model=EmailOutboxResponse)
async def retry_failed_email(
    outbox_id: uuid.UUID,
    current_user: User = Depends(
        require_role(["Admin", "Administrator", "Super Admin", "HR", "HR Manager"])
    ),
    db: AsyncSession = Depends(get_db),
) -> EmailOutbox:
    """Manually re-triggers transmission for a failed or pending outbox email."""
    stmt = (
        select(EmailOutbox)
        .options(selectinload(EmailOutbox.delivery_logs))
        .where(
            EmailOutbox.id == outbox_id,
            EmailOutbox.organization_id == current_user.organization_id,
        )
    )
    res = await db.execute(stmt)
    entry = res.scalars().first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email outbox record not found.",
        )

    # Reset retry state
    entry.status = OutboxStatus.PENDING
    entry.scheduled_at = datetime.now(UTC)
    await db.commit()

    # Dispatch immediately
    await EmailService.dispatch_outbox_message(db, entry.id)
    
    # Re-fetch with delivery_logs eagerly loaded
    stmt = (
        select(EmailOutbox)
        .options(selectinload(EmailOutbox.delivery_logs))
        .where(EmailOutbox.id == entry.id)
    )
    res = await db.execute(stmt)
    return res.scalars().first()


@router.get("/templates", response_model=list[EmailTemplateInfo])
async def list_email_templates(
    current_user: User = Depends(get_current_active_user),
) -> list[EmailTemplateInfo]:
    """Catalog of all 10 standard enterprise notification templates."""
    results: list[EmailTemplateInfo] = []
    for key, info in TEMPLATES_CONFIG.items():
        results.append(
            EmailTemplateInfo(
                template_key=key,
                subject_pattern=info["subject"],
                badge_text=info["badge_text"],
                badge_class=info["badge_class"],
                required_variables=[
                    w.strip("{}")
                    for w in info["subject"].split()
                    if w.startswith("{") and w.endswith("}")
                ],
            )
        )
    return results


@router.post("/send-test", response_model=EmailOutboxResponse)
async def send_test_email(
    payload: SendTestEmailRequest,
    current_user: User = Depends(require_role(["Admin", "Super Admin", "HR"])),
    db: AsyncSession = Depends(get_db),
) -> EmailOutbox:
    """Dispatches a test notification to verify transport and template rendering."""
    test_context = {
        "employee_name": payload.recipient_name or "Test User",
        "employee_code": "EMP-TEST",
        "email": payload.recipient_email,
        "department_name": "Quality Assurance",
        "designation": "Systems Tester",
        "manager_name": current_user.full_name or "Department Manager",
        "recipient_name": payload.recipient_name or "Test User",
        "leave_type": "Annual Leave",
        "start_date": "2026-11-20",
        "end_date": "2026-11-22",
        "duration_days": 3,
        "reason": "Test notification dispatch",
        "report_date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "target_scope": "Testing Scope",
        "present_count": 42,
        "late_count": 2,
        "leave_count": 3,
        "total_net_hours": 336.0,
        "week_range": "2026-W46",
        "month_year": datetime.now(UTC).strftime("%B %Y"),
        **payload.context,
    }

    idempotency_key = f"test_{current_user.id}_{datetime.now(UTC).timestamp()}"
    outbox = await EmailService.enqueue_email(
        db=db,
        organization_id=current_user.organization_id,
        template_key=payload.template_key,
        recipient_email=payload.recipient_email,
        recipient_name=payload.recipient_name,
        context=test_context,
        idempotency_key=idempotency_key,
    )
    await EmailService.dispatch_outbox_message(db, outbox.id)
    
    # Re-fetch with delivery_logs eagerly loaded
    stmt = (
        select(EmailOutbox)
        .options(selectinload(EmailOutbox.delivery_logs))
        .where(EmailOutbox.id == outbox.id)
    )
    res = await db.execute(stmt)
    return res.scalars().first()


@router.post("/process-queue")
async def trigger_process_queue(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(
        require_role(["Admin", "Administrator", "Super Admin", "HR", "HR Manager"])
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Manually flushes the pending email outbox queue."""
    dispatched = await EmailService.process_pending_outbox(db, limit=limit)
    return {
        "status": "success",
        "dispatched_count": dispatched,
        "processed_at": datetime.now(UTC).isoformat(),
    }


@router.post("/webhook/delivery")
async def delivery_receipt_webhook(
    payload: DeliveryWebhookPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Webhook endpoint to record telemetry receipts (DELIVERED, BOUNCED, DROPPED, OPENED, CLICKED).
    """
    stmt = select(EmailOutbox).where(EmailOutbox.id == payload.email_outbox_id)
    res = await db.execute(stmt)
    outbox = res.scalars().first()
    if not outbox:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Referenced outbox entry not found.",
        )

    log = EmailDeliveryLog(
        email_outbox_id=outbox.id,
        event_type=payload.event_type,
        provider_message_id=payload.provider_message_id,
        response_code=payload.response_code,
        response_body=payload.response_body,
        timestamp=datetime.now(UTC),
    )
    db.add(log)

    if payload.event_type in (DeliveryEventType.BOUNCED, DeliveryEventType.DROPPED):
        outbox.status = OutboxStatus.FAILED
        outbox.error_message = payload.response_body or f"External {payload.event_type} event"

    await db.commit()
    return {"status": "recorded", "event_type": payload.event_type.value}
