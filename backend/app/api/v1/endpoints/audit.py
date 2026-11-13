"""
Audit Logs Endpoints (Phase 10)
Inspect immutable compliance audit trail.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.auth import AuditLog, User

router = APIRouter()


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None = None
    user_email: str | None = None
    action: str
    entity_type: str
    entity_id: str | None = None
    ip_address: str | None = None
    diff_json: dict[str, Any] | None = None
    created_at: datetime


@router.get("/", response_model=list[AuditLogResponse])
async def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    action: str | None = None,
    entity_type: str | None = None,
    current_user: User = Depends(require_role(["Admin", "Super Admin", "HR"])),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    """Retrieve audit logs with optional filtering."""
    stmt = (
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .where(AuditLog.organization_id == current_user.organization_id)
    )

    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type.ilike(f"%{entity_type}%"))

    stmt = stmt.order_by(desc(AuditLog.created_at)).limit(limit)
    res = await db.execute(stmt)
    records = res.scalars().all()

    return [
        AuditLogResponse(
            id=r.id,
            user_id=r.user_id,
            user_email=r.user.email if r.user else "System",
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            ip_address=r.ip_address,
            diff_json=r.diff_json,
            created_at=r.created_at,
        )
        for r in records
    ]

