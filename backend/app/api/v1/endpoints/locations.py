"""
Location and Office Verification API Endpoints (Phase 08)
Enforces location verification, anti-spoofing checks, compliance disclosures, and data retention.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import (
    get_current_active_user,
    require_permission,
    require_role,
)
from app.models.auth import AuditLog, User
from app.models.employee import EmployeeProfile
from app.models.office import LocationEvent, LocationVerification
from app.schemas.location import (
    LocationComplianceDisclosureResponse,
    LocationEventResponse,
    LocationVerificationResponse,
    LocationVerifyRequest,
)
from app.services.location_verifier import (
    purge_expired_location_events,
    verify_and_persist_location,
)

router = APIRouter()


async def get_current_employee_profile(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeProfile:
    result = await db.execute(
        select(EmployeeProfile).where(EmployeeProfile.user_id == current_user.id)
    )
    profile = result.scalars().first()
    if not profile:
        raise HTTPException(status_code=400, detail="User does not have an active employee personnel record")
    return profile


@router.post("/verify", response_model=LocationVerificationResponse, status_code=status.HTTP_201_CREATED)
async def verify_location(
    payload: LocationVerifyRequest,
    current_emp: Annotated[EmployeeProfile, Depends(get_current_employee_profile)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LocationVerification:
    """
    Validates physical presence against corporate office geofences and authorized networks.
    - Computes exact Haversine distance to closest active office geofence.
    - Evaluates GPS accuracy against inaccuracy thresholds.
    - Never treats Wi-Fi or IP address alone as conclusive presence.
    - Supports permission denial, offline synchronization, and anti-spoofing.
    """
    _, verification = await verify_and_persist_location(
        db=db,
        employee_id=current_emp.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_meters=payload.accuracy_meters,
        is_mocked=payload.is_mocked,
        permission_status=payload.permission_status,
        source=payload.source,
        client_event_id=payload.client_event_id,
        client_ssid=payload.client_ssid,
        client_bssid=payload.client_bssid,
        client_ip=payload.client_ip,
        target_office_id=payload.target_office_id,
        metadata_json=payload.metadata_json,
    )
    return verification


@router.get("/history", response_model=list[LocationEventResponse])
async def get_location_history(
    current_emp: Annotated[EmployeeProfile, Depends(get_current_employee_profile)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
) -> list[LocationEvent]:
    """Returns discrete check-in/out location verification events for authenticated employee."""
    stmt = (
        select(LocationEvent)
        .options(selectinload(LocationEvent.verification))
        .where(LocationEvent.employee_id == current_emp.id)
        .order_by(desc(LocationEvent.recorded_at))
        .limit(limit)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.get("/compliance-disclosure", response_model=LocationComplianceDisclosureResponse)
async def get_location_compliance_disclosure(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> LocationComplianceDisclosureResponse:
    """
    Returns legal employee disclosures and privacy policies regarding workplace location verification.
    """
    return LocationComplianceDisclosureResponse(
        organization_id=current_user.organization_id,
        disclosure_policy_name="Enterprise Workplace Location Verification & Privacy Disclosure",
        purpose="Verification of physical office presence during explicit check-in and check-out events.",
        gps_tracking_policy="Continuous GPS tracking is strictly prohibited and technically disabled. Telemetry is collected solely on discrete employee check-in and check-out actions.",
        non_conclusive_rule="Wi-Fi SSID, BSSID, and IP geolocation are never treated as conclusive proof of physical presence.",
        data_retention_days=90,
        employee_rights=[
            "Right to view all recorded discrete check-in/check-out location events.",
            "Right to decline OS location permissions (system marks check-in as UNAVAILABLE without preventing employment record creation).",
            "Right to request manager manual verification review.",
            "Automatic rolling purge of location coordinates after 90 days.",
        ],
        retention_purge_enabled=True,
    )


@router.delete("/retention/purge", status_code=status.HTTP_200_OK)
async def purge_retention_data(
    current_user: Annotated[User, Depends(require_role(["Admin", "Super Admin"]))],
    db: Annotated[AsyncSession, Depends(get_db)],
    retention_days: int = Query(default=90, ge=30, le=365),
) -> dict[str, str | int]:
    """
    Administrative privacy enforcement: Purges discrete location telemetry older than specified retention days.
    """
    purged_count = await purge_expired_location_events(
        db=db,
        organization_id=current_user.organization_id,
        retention_days=retention_days,
    )

    audit = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="LOCATION_TELEMETRY_RETENTION_PURGE",
        entity_type="LocationEvent",
        entity_id=str(current_user.organization_id),
        diff_json={"retention_days": retention_days, "purged_count": purged_count},
    )
    db.add(audit)
    await db.commit()

    return {
        "status": "success",
        "purged_records": purged_count,
        "retention_days": retention_days,
        "message": f"Successfully purged {purged_count} location events older than {retention_days} days.",
    }

