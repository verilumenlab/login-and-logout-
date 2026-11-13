"""
Office Management API Endpoints (Phase 08)
Administrative configuration for physical offices, geofences, and approved networks.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import (
    get_current_active_user,
    require_permission,
    require_role,
)
from app.models.auth import AuditLog, User
from app.models.office import Office, OfficeGeofence, OfficeNetwork
from app.schemas.office import (
    OfficeCreateRequest,
    OfficeGeofenceCreate,
    OfficeGeofenceResponse,
    OfficeListResponse,
    OfficeNetworkCreate,
    OfficeNetworkResponse,
    OfficeResponse,
    OfficeUpdateRequest,
)

router = APIRouter()


@router.post("", response_model=OfficeResponse, status_code=status.HTTP_201_CREATED)
async def create_office(
    payload: OfficeCreateRequest,
    current_user: Annotated[User, Depends(require_role(["Admin", "HR", "Super Admin"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Office:
    """Creates a corporate office, optional initial geofence, and authorized networks."""
    # Check duplicate code in organization
    existing = await db.execute(
        select(Office).where(
            Office.organization_id == current_user.organization_id,
            Office.code == payload.code.strip().upper(),
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail=f"Office with code '{payload.code}' already exists")

    new_office = Office(
        organization_id=current_user.organization_id,
        name=payload.name.strip(),
        code=payload.code.strip().upper(),
        address=payload.address.strip(),
        timezone=payload.timezone.strip(),
        is_active=True,
    )
    db.add(new_office)
    await db.flush()

    # Initial Geofence if coordinates supplied
    if payload.latitude is not None and payload.longitude is not None:
        geofence = OfficeGeofence(
            office_id=new_office.id,
            name=f"{new_office.name} Primary Perimeter",
            latitude=payload.latitude,
            longitude=payload.longitude,
            radius_meters=payload.radius_meters or 100.0,
            is_active=True,
        )
        db.add(geofence)

    # Initial Networks if supplied
    if payload.networks:
        for net_in in payload.networks:
            net = OfficeNetwork(
                office_id=new_office.id,
                name=net_in.name.strip(),
                ssid=net_in.ssid.strip() if net_in.ssid else None,
                ip_address=net_in.ip_address.strip() if net_in.ip_address else None,
                subnet_cidr=net_in.subnet_cidr.strip() if net_in.subnet_cidr else None,
                bssid_mac=net_in.bssid_mac.strip().lower() if net_in.bssid_mac else None,
                is_active=net_in.is_active,
            )
            db.add(net)

    # Audit Log
    audit = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="OFFICE_CREATED",
        entity_type="Office",
        entity_id=str(new_office.id),
        diff_json={
            "name": new_office.name,
            "code": new_office.code,
            "address": new_office.address,
            "timezone": new_office.timezone,
        },
    )
    db.add(audit)
    await db.commit()

    # Reload with relationships
    res = await db.execute(
        select(Office)
        .options(selectinload(Office.geofences), selectinload(Office.networks))
        .where(Office.id == new_office.id)
    )
    return res.scalars().first()


@router.get("", response_model=OfficeListResponse)
async def list_offices(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_active: bool | None = None,
) -> OfficeListResponse:
    """Lists corporate offices and their geofences for the authenticated user's organization."""
    query = (
        select(Office)
        .options(selectinload(Office.geofences), selectinload(Office.networks))
        .where(Office.organization_id == current_user.organization_id)
    )
    if is_active is not None:
        query = query.where(Office.is_active == is_active)

    total_stmt = select(func.count()).select_from(query.subquery())
    total_count = (await db.execute(total_stmt)).scalar() or 0

    query = query.order_by(desc(Office.created_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    offices = list(result.scalars().all())

    return OfficeListResponse(
        items=offices,
        total=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/{office_id}", response_model=OfficeResponse)
async def get_office(
    office_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Office:
    """Retrieves single office details with geofences and networks."""
    stmt = (
        select(Office)
        .options(selectinload(Office.geofences), selectinload(Office.networks))
        .where(
            Office.id == office_id,
            Office.organization_id == current_user.organization_id,
        )
    )
    res = await db.execute(stmt)
    office = res.scalars().first()
    if not office:
        raise HTTPException(status_code=404, detail="Office not found")
    return office


@router.patch("/{office_id}", response_model=OfficeResponse)
async def update_office(
    office_id: uuid.UUID,
    payload: OfficeUpdateRequest,
    current_user: Annotated[User, Depends(require_role(["Admin", "HR", "Super Admin"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Office:
    """Updates office metadata, timezone, or activation status with audit logging."""
    stmt = (
        select(Office)
        .options(selectinload(Office.geofences), selectinload(Office.networks))
        .where(
            Office.id == office_id,
            Office.organization_id == current_user.organization_id,
        )
    )
    res = await db.execute(stmt)
    office = res.scalars().first()
    if not office:
        raise HTTPException(status_code=404, detail="Office not found")

    diff = {}
    if payload.name is not None and payload.name != office.name:
        diff["name"] = {"old": office.name, "new": payload.name}
        office.name = payload.name
    if payload.address is not None and payload.address != office.address:
        diff["address"] = {"old": office.address, "new": payload.address}
        office.address = payload.address
    if payload.timezone is not None and payload.timezone != office.timezone:
        diff["timezone"] = {"old": office.timezone, "new": payload.timezone}
        office.timezone = payload.timezone
    if payload.is_active is not None and payload.is_active != office.is_active:
        diff["is_active"] = {"old": office.is_active, "new": payload.is_active}
        office.is_active = payload.is_active

    if diff:
        audit = AuditLog(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="OFFICE_UPDATED",
            entity_type="Office",
            entity_id=str(office.id),
            diff_json=diff,
        )
        db.add(audit)

    await db.commit()
    await db.refresh(office)
    return office


@router.delete("/{office_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_office(
    office_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(["Admin", "Super Admin"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Removes an office and cascades to associated geofences and networks."""
    stmt = select(Office).where(
        Office.id == office_id,
        Office.organization_id == current_user.organization_id,
    )
    res = await db.execute(stmt)
    office = res.scalars().first()
    if not office:
        raise HTTPException(status_code=404, detail="Office not found")

    audit = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="OFFICE_DELETED",
        entity_type="Office",
        entity_id=str(office.id),
        diff_json={"code": office.code, "name": office.name},
    )
    db.add(audit)
    await db.delete(office)
    await db.commit()


# ============================================================================
# Geofence Sub-Resources
# ============================================================================


@router.post("/{office_id}/geofences", response_model=OfficeGeofenceResponse, status_code=status.HTTP_201_CREATED)
async def add_geofence(
    office_id: uuid.UUID,
    payload: OfficeGeofenceCreate,
    current_user: Annotated[User, Depends(require_role(["Admin", "HR", "Super Admin"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OfficeGeofence:
    """Adds a new geofence perimeter to an office."""
    office_stmt = select(Office).where(
        Office.id == office_id,
        Office.organization_id == current_user.organization_id,
    )
    office_res = await db.execute(office_stmt)
    if not office_res.scalars().first():
        raise HTTPException(status_code=404, detail="Office not found")

    geofence = OfficeGeofence(
        office_id=office_id,
        name=payload.name.strip(),
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_meters=payload.radius_meters,
        is_active=payload.is_active,
    )
    db.add(geofence)

    audit = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="OFFICE_GEOFENCE_ADDED",
        entity_type="OfficeGeofence",
        entity_id=str(office_id),
        diff_json={
            "name": geofence.name,
            "latitude": geofence.latitude,
            "longitude": geofence.longitude,
            "radius_meters": geofence.radius_meters,
        },
    )
    db.add(audit)
    await db.commit()
    await db.refresh(geofence)
    return geofence


@router.delete("/{office_id}/geofences/{geofence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_geofence(
    office_id: uuid.UUID,
    geofence_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(["Admin", "HR", "Super Admin"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Deletes an office geofence perimeter."""
    stmt = (
        select(OfficeGeofence)
        .join(Office, OfficeGeofence.office_id == Office.id)
        .where(
            OfficeGeofence.id == geofence_id,
            OfficeGeofence.office_id == office_id,
            Office.organization_id == current_user.organization_id,
        )
    )
    res = await db.execute(stmt)
    gf = res.scalars().first()
    if not gf:
        raise HTTPException(status_code=404, detail="Geofence not found")

    await db.delete(gf)
    await db.commit()


# ============================================================================
# Network Sub-Resources
# ============================================================================


@router.post("/{office_id}/networks", response_model=OfficeNetworkResponse, status_code=status.HTTP_201_CREATED)
async def add_network(
    office_id: uuid.UUID,
    payload: OfficeNetworkCreate,
    current_user: Annotated[User, Depends(require_role(["Admin", "HR", "Super Admin"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OfficeNetwork:
    """Configures an approved office Wi-Fi network, BSSID MAC, or Subnet CIDR."""
    office_stmt = select(Office).where(
        Office.id == office_id,
        Office.organization_id == current_user.organization_id,
    )
    office_res = await db.execute(office_stmt)
    if not office_res.scalars().first():
        raise HTTPException(status_code=404, detail="Office not found")

    network = OfficeNetwork(
        office_id=office_id,
        name=payload.name.strip(),
        ssid=payload.ssid.strip() if payload.ssid else None,
        ip_address=payload.ip_address.strip() if payload.ip_address else None,
        subnet_cidr=payload.subnet_cidr.strip() if payload.subnet_cidr else None,
        bssid_mac=payload.bssid_mac.strip().lower() if payload.bssid_mac else None,
        is_active=payload.is_active,
    )
    db.add(network)
    await db.commit()
    await db.refresh(network)
    return network


@router.delete("/{office_id}/networks/{network_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_network(
    office_id: uuid.UUID,
    network_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(["Admin", "HR", "Super Admin"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Removes an office network identifier."""
    stmt = (
        select(OfficeNetwork)
        .join(Office, OfficeNetwork.office_id == Office.id)
        .where(
            OfficeNetwork.id == network_id,
            OfficeNetwork.office_id == office_id,
            Office.organization_id == current_user.organization_id,
        )
    )
    res = await db.execute(stmt)
    net = res.scalars().first()
    if not net:
        raise HTTPException(status_code=404, detail="Network not found")

    await db.delete(net)
    await db.commit()

