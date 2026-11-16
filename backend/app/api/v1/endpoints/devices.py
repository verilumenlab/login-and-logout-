"""
Device Management Endpoints (Phase 10)
List devices, view enrolled hardware, block/unblock workstations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.auth import AuditLog, RefreshToken, User
from app.models.device import Device, DeviceSession
from app.models.employee import EmployeeProfile

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
    last_ip_address: str | None = None
    employee_id: uuid.UUID | None = None
    employee_name: str | None = None
    employee_code: str | None = None
    employee_email: str | None = None


async def _enrich_device(db: AsyncSession, device: Device) -> DeviceResponse:
    """Attach last session IP and the most recent employee who used this device."""
    session_stmt = (
        select(DeviceSession)
        .options(selectinload(DeviceSession.employee).selectinload(EmployeeProfile.user))
        .where(DeviceSession.device_id == device.id)
        .order_by(desc(DeviceSession.start_time))
        .limit(1)
    )
    session = (await db.execute(session_stmt)).scalars().first()

    last_ip = session.ip_address if session else None
    employee_id = None
    employee_name = None
    employee_code = None
    employee_email = None
    if session and session.employee:
        emp = session.employee
        employee_id = emp.id
        employee_name = f"{emp.first_name} {emp.last_name}".strip()
        employee_code = emp.employee_code
        employee_email = emp.user.email if emp.user else None

    return DeviceResponse(
        id=device.id,
        device_identifier=device.device_identifier,
        device_name=device.device_name,
        os_name=device.os_name,
        os_version=device.os_version,
        platform=device.platform,
        mac_address=device.mac_address,
        agent_version=device.agent_version,
        is_trusted=device.is_trusted,
        is_blocked=device.is_blocked,
        registered_at=device.registered_at,
        last_seen_at=device.last_seen_at,
        last_ip_address=last_ip,
        employee_id=employee_id,
        employee_name=employee_name,
        employee_code=employee_code,
        employee_email=employee_email,
    )


async def _revoke_device_user_sessions(db: AsyncSession, device: Device, now: datetime) -> int:
    """
    End device sessions and revoke JWT refresh tokens for every employee who used this device,
    so the desktop app cannot keep working after an admin block.
    """
    await db.execute(
        update(DeviceSession)
        .where(DeviceSession.device_id == device.id, DeviceSession.is_active == True)  # noqa: E712
        .values(end_time=now, is_active=False)
    )

    user_ids = list(
        (
            await db.execute(
                select(EmployeeProfile.user_id)
                .join(DeviceSession, DeviceSession.employee_id == EmployeeProfile.id)
                .where(DeviceSession.device_id == device.id)
                .distinct()
            )
        ).scalars().all()
    )
    if not user_ids:
        return 0

    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id.in_(user_ids), RefreshToken.is_revoked == False)  # noqa: E712
        .values(
            is_revoked=True,
            revoked_at=now,
            revocation_reason="Device blocked by administrator",
        )
    )
    return int(result.rowcount or 0)


@router.get("/", response_model=list[DeviceResponse])
async def list_devices(
    current_user: User = Depends(require_role(["Admin", "Super Admin", "HR"])),
    db: AsyncSession = Depends(get_db),
) -> list[DeviceResponse]:
    """List all registered devices in the organization with IP and employee details."""
    stmt = (
        select(Device)
        .where(Device.organization_id == current_user.organization_id)
        .order_by(desc(Device.registered_at))
    )
    result = await db.execute(stmt)
    devices = list(result.scalars().all())
    return [await _enrich_device(db, d) for d in devices]


@router.post("/{device_id}/block", response_model=DeviceResponse)
async def block_device(
    device_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> DeviceResponse:
    """Block a device, revoke desktop sessions/tokens, and stop the employee app immediately."""
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
    revoked = await _revoke_device_user_sessions(db, device, now)

    audit_entry = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="DEVICE_BLOCKED",
        entity_type="Device",
        entity_id=str(device.id),
        diff_json={
            "device_name": device.device_name,
            "identifier": device.device_identifier,
            "is_blocked": True,
            "refresh_tokens_revoked": revoked,
        },
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(device)
    return await _enrich_device(db, device)


@router.post("/{device_id}/revoke", response_model=DeviceResponse)
async def revoke_device_access(
    device_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> DeviceResponse:
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
    revoked = await _revoke_device_user_sessions(db, device, now)

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
            "refresh_tokens_revoked": revoked,
        },
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(device)
    return await _enrich_device(db, device)


@router.post("/{device_id}/unblock", response_model=DeviceResponse)
async def unblock_device(
    device_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> DeviceResponse:
    """Resume / unblock a previously blocked device so the employee can sign in again."""
    stmt = select(Device).where(
        Device.id == device_id,
        Device.organization_id == current_user.organization_id,
    )
    res = await db.execute(stmt)
    device = res.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.is_blocked = False
    device.is_trusted = True

    audit_entry = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="DEVICE_UNBLOCKED",
        entity_type="Device",
        entity_id=str(device.id),
        diff_json={
            "device_name": device.device_name,
            "identifier": device.device_identifier,
            "is_blocked": False,
            "is_trusted": True,
        },
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(device)
    return await _enrich_device(db, device)
