"""
Device Management Endpoints (Phase 10)
List devices, view enrolled hardware, block/unblock workstations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user, require_role
from app.models.auth import AuditLog, User
from app.models.device import Device, DeviceSession
from sqlalchemy import desc, select, update

router = APIRouter()


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_identifier: str
    device_name: str
    os_name: str
    os_version: str
    platform: str
    mac_address: str | None = None
    agent_version: str
    is_trusted: bool
    is_blocked: bool
    registered_at: datetime
    last_seen_at: datetime | None = None


@router.get("/", response_model=list[DeviceResponse])
async def list_devices(
    current_user: User = Depends(require_role(["Admin", "Super Admin", "HR"])),
    db: AsyncSession = Depends(get_db),
) -> list[Device]:
    """List all registered devices in the organization."""
    stmt = (
        select(Device)
        .where(Device.organization_id == current_user.organization_id)
        .order_by(desc(Device.registered_at))
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/{device_id}/block", response_model=DeviceResponse)
async def block_device(
    device_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> Device:
    """Block a device from syncing telemetry or logging in and revoke active sessions."""
    stmt = select(Device).where(
        Device.id == device_id,
        Device.organization_id == current_user.organization_id,
    )
    res = await db.execute(stmt)
    device = res.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.is_blocked = True
    now = datetime.now(UTC)

    # Immediately terminate all active device sessions
    await db.execute(
        update(DeviceSession)
        .where(DeviceSession.device_id == device.id, DeviceSession.is_active == True)  # noqa: E712
        .values(end_time=now, is_active=False)
    )

    # Record security audit log
    audit_entry = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="DEVICE_BLOCKED",
        entity_type="Device",
        entity_id=str(device.id),
        diff_json={"device_name": device.device_name, "identifier": device.device_identifier, "is_blocked": True},
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(device)
    return device


@router.post("/{device_id}/revoke", response_model=DeviceResponse)
async def revoke_device_access(
    device_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> Device:
    """Revoke device authorization immediately and terminate all sessions."""
    stmt = select(Device).where(
        Device.id == device_id,
        Device.organization_id == current_user.organization_id,
    )
    res = await db.execute(stmt)
    device = res.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.is_trusted = False
    device.is_blocked = True
    now = datetime.now(UTC)

    await db.execute(
        update(DeviceSession)
        .where(DeviceSession.device_id == device.id, DeviceSession.is_active == True)  # noqa: E712
        .values(end_time=now, is_active=False)
    )

    audit_entry = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="DEVICE_REVOKED",
        entity_type="Device",
        entity_id=str(device.id),
        diff_json={
            "device_name": device.device_name,
            "identifier": device.device_identifier,
            "is_blocked": True,
            "is_trusted": False,
        },
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(device)
    return device


@router.post("/{device_id}/unblock", response_model=DeviceResponse)
async def unblock_device(
    device_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> Device:
    """Unblock a previously blocked device."""
    stmt = select(Device).where(
        Device.id == device_id,
        Device.organization_id == current_user.organization_id,
    )
    res = await db.execute(stmt)
    device = res.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.is_blocked = False
    await db.commit()
    await db.refresh(device)
    return device

