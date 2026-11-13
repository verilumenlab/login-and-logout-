"""
Location and Office Verification Service (Phase 08)
Enterprise Geofence Evaluation, Wi-Fi Network Matching, and Anti-Spoofing Engine.

Standing Compliance Rules:
1. Never treat IP location or Wi-Fi as conclusive proof of physical presence.
2. Do not continuously track GPS (discrete check-in/out verification only).
3. Distinguish VERIFIED, UNVERIFIED, UNAVAILABLE, and SPOOF_DETECTED.
4. Support inaccurate coordinate thresholds and permission rejection handling.
"""

from __future__ import annotations

import ipaddress
import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auth import AuditLog
from app.models.employee import EmployeeProfile
from app.models.office import (
    LocationEvent,
    LocationPermissionStatus,
    LocationVerification,
    Office,
    OfficeGeofence,
    OfficeNetwork,
    VerificationMethod,
    VerificationStatus,
)

# Mean Earth radius in meters
EARTH_RADIUS_METERS = 6371000.0

# GPS Accuracy threshold in meters (coordinates with accuracy > 200m are deemed inaccurate)
ACCURACY_THRESHOLD_METERS = 200.0


def calculate_haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Computes great-circle distance between two points on Earth using the Haversine formula.
    Returns distance in meters.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(EARTH_RADIUS_METERS * c, 2)


def is_coordinate_valid(lat: float | None, lon: float | None) -> bool:
    """Verifies that latitude and longitude fall within physical terrestrial bounds."""
    if lat is None or lon is None:
        return False
    if not (-90.0 <= lat <= 90.0):
        return False
    if not (-180.0 <= lon <= 180.0):
        return False
    return True


def match_network(
    client_ssid: str | None,
    client_bssid: str | None,
    client_ip: str | None,
    office_networks: list[OfficeNetwork],
) -> OfficeNetwork | None:
    """
    Evaluates client network identifiers against authorized office networks.
    Matches BSSID MAC address, SSID name, or IP subnet CIDR.
    """
    if not office_networks:
        return None

    norm_bssid = client_bssid.strip().lower() if client_bssid else None
    norm_ssid = client_ssid.strip().lower() if client_ssid else None

    # 1. BSSID match (highest fidelity for local AP)
    if norm_bssid:
        for net in office_networks:
            if not net.is_active:
                continue
            if net.bssid_mac and net.bssid_mac.strip().lower() == norm_bssid:
                return net

    # 2. SSID match
    if norm_ssid:
        for net in office_networks:
            if not net.is_active:
                continue
            if net.ssid and net.ssid.strip().lower() == norm_ssid:
                return net
            if net.name and net.name.strip().lower() == norm_ssid:
                return net

    # 3. IP / Subnet CIDR match
    if client_ip:
        try:
            ip_obj = ipaddress.ip_address(client_ip.strip())
            for net in office_networks:
                if not net.is_active:
                    continue
                if net.ip_address and net.ip_address.strip() == client_ip.strip():
                    return net
                if net.subnet_cidr:
                    network_obj = ipaddress.ip_network(net.subnet_cidr.strip(), strict=False)
                    if ip_obj in network_obj:
                        return net
        except ValueError:
            pass

    return None


class LocationVerificationResult:
    """Intermediate computation output for location compliance evaluation."""

    def __init__(
        self,
        verification_status: VerificationStatus,
        verification_method: VerificationMethod,
        is_conclusive: bool,
        confidence_score: float,
        distance_meters: float | None = None,
        office_id: uuid.UUID | None = None,
        geofence_id: uuid.UUID | None = None,
        network_id: uuid.UUID | None = None,
        notes: str | None = None,
    ):
        self.verification_status = verification_status
        self.verification_method = verification_method
        self.is_conclusive = is_conclusive
        self.confidence_score = confidence_score
        self.distance_meters = distance_meters
        self.office_id = office_id
        self.geofence_id = geofence_id
        self.network_id = network_id
        self.notes = notes


def evaluate_location_compliance(
    latitude: float | None,
    longitude: float | None,
    accuracy_meters: float | None,
    is_mocked: bool,
    permission_status: LocationPermissionStatus,
    client_ssid: str | None,
    client_bssid: str | None,
    client_ip: str | None,
    offices: list[Office],
    target_office_id: uuid.UUID | None = None,
) -> LocationVerificationResult:
    """
    Evaluates physical location telemetry against corporate office geofences and networks.
    Enforces all privacy and conclusive presence rules.
    """
    # Rule 1: Denied or unavailable location permissions
    if permission_status in [LocationPermissionStatus.DENIED, LocationPermissionStatus.UNAVAILABLE]:
        # Check if network is available as non-conclusive fallback
        candidate_networks = [net for o in offices for net in o.networks if net.is_active]
        matched_net = match_network(client_ssid, client_bssid, client_ip, candidate_networks)
        if matched_net:
            return LocationVerificationResult(
                verification_status=VerificationStatus.UNVERIFIED,
                verification_method=VerificationMethod.WIFI_NETWORK,
                is_conclusive=False,
                confidence_score=0.4,
                office_id=matched_net.office_id,
                network_id=matched_net.id,
                notes="Location permission unavailable; office network detected but cannot be treated as conclusive presence",
            )
        return LocationVerificationResult(
            verification_status=VerificationStatus.UNAVAILABLE,
            verification_method=VerificationMethod.UNAVAILABLE,
            is_conclusive=False,
            confidence_score=0.0,
            notes=f"Location verification unavailable: OS permission status is {permission_status.value}",
        )

    # Rule 2: Anti-spoofing check
    if is_mocked:
        return LocationVerificationResult(
            verification_status=VerificationStatus.SPOOF_DETECTED,
            verification_method=VerificationMethod.GPS,
            is_conclusive=False,
            confidence_score=0.0,
            notes="Mock or simulated coordinate injection detected by client OS",
        )

    # Rule 3: Valid coordinates check
    has_coords = is_coordinate_valid(latitude, longitude)

    # Rule 4: No GPS coordinates provided (Wi-Fi or IP only)
    if not has_coords:
        candidate_networks = [net for o in offices for net in o.networks if net.is_active]
        matched_net = match_network(client_ssid, client_bssid, client_ip, candidate_networks)
        if matched_net:
            method = VerificationMethod.WIFI_NETWORK if (client_ssid or client_bssid) else VerificationMethod.IP_APPROXIMATE
            return LocationVerificationResult(
                verification_status=VerificationStatus.UNVERIFIED,
                verification_method=method,
                is_conclusive=False,
                confidence_score=0.5 if client_bssid else 0.35,
                office_id=matched_net.office_id,
                network_id=matched_net.id,
                notes=f"Network match ({matched_net.name}); flagged UNVERIFIED because Wi-Fi/IP alone is non-conclusive proof",
            )
        return LocationVerificationResult(
            verification_status=VerificationStatus.UNVERIFIED,
            verification_method=VerificationMethod.IP_APPROXIMATE,
            is_conclusive=False,
            confidence_score=0.05,
            notes="No valid GPS coordinates provided and network unrecognized",
        )

    assert latitude is not None and longitude is not None

    # Filter target office or evaluate against all organization offices
    eval_offices = [o for o in offices if o.is_active]
    if target_office_id:
        eval_offices = [o for o in eval_offices if o.id == target_office_id]

    if not eval_offices:
        return LocationVerificationResult(
            verification_status=VerificationStatus.OUTSIDE_GEOFENCE,
            verification_method=VerificationMethod.GPS,
            is_conclusive=False,
            confidence_score=0.1,
            notes="No active corporate offices configured for verification",
        )

    # Check network match across active offices
    all_networks = [net for o in eval_offices for net in o.networks if net.is_active]
    matched_net = match_network(client_ssid, client_bssid, client_ip, all_networks)

    # Rule 5: Accuracy evaluation (inaccurate GPS coordinates)
    if accuracy_meters is not None and accuracy_meters > ACCURACY_THRESHOLD_METERS:
        return LocationVerificationResult(
            verification_status=VerificationStatus.UNVERIFIED,
            verification_method=VerificationMethod.GPS,
            is_conclusive=False,
            confidence_score=0.25,
            office_id=eval_offices[0].id,
            network_id=matched_net.id if matched_net else None,
            notes=f"Inaccurate GPS coordinates: accuracy (±{round(accuracy_meters, 1)}m) exceeds threshold ({ACCURACY_THRESHOLD_METERS}m)",
        )

    # Rule 6: Iterate through geofences to find closest match
    closest_distance = float("inf")
    best_office: Office | None = None
    best_geofence: OfficeGeofence | None = None
    is_inside_geofence = False

    for office in eval_offices:
        for geofence in office.geofences:
            if not geofence.is_active:
                continue
            dist = calculate_haversine_distance(latitude, longitude, geofence.latitude, geofence.longitude)
            if dist < closest_distance:
                closest_distance = dist
                best_office = office
                best_geofence = geofence
            if dist <= geofence.radius_meters:
                is_inside_geofence = True
                best_office = office
                best_geofence = geofence
                closest_distance = dist
                break
        if is_inside_geofence:
            break

    if is_inside_geofence and best_office and best_geofence:
        if matched_net and matched_net.office_id == best_office.id:
            # Multi-factor hybrid verification
            return LocationVerificationResult(
                verification_status=VerificationStatus.VERIFIED,
                verification_method=VerificationMethod.HYBRID,
                is_conclusive=True,
                confidence_score=1.0,
                distance_meters=closest_distance,
                office_id=best_office.id,
                geofence_id=best_geofence.id,
                network_id=matched_net.id,
                notes=f"Multi-factor verification: GPS distance {closest_distance}m <= {best_geofence.radius_meters}m and verified network {matched_net.name}",
            )
        else:
            # GPS within perimeter
            return LocationVerificationResult(
                verification_status=VerificationStatus.VERIFIED,
                verification_method=VerificationMethod.GPS,
                is_conclusive=True,
                confidence_score=0.95,
                distance_meters=closest_distance,
                office_id=best_office.id,
                geofence_id=best_geofence.id,
                network_id=matched_net.id if matched_net else None,
                notes=f"Verified: GPS coordinate within office perimeter ({closest_distance}m <= {best_geofence.radius_meters}m)",
            )

    # Outside geofence
    if matched_net:
        # Crucial Negative Constraint:
        # Connected to office Wi-Fi, but GPS coordinates show employee is outside geofence!
        # Never treat Wi-Fi as conclusive proof!
        return LocationVerificationResult(
            verification_status=VerificationStatus.UNVERIFIED,
            verification_method=VerificationMethod.WIFI_NETWORK,
            is_conclusive=False,
            confidence_score=0.5,
            distance_meters=closest_distance if closest_distance != float("inf") else None,
            office_id=matched_net.office_id,
            geofence_id=best_geofence.id if best_geofence else None,
            network_id=matched_net.id,
            notes=f"Office Wi-Fi ({matched_net.name}) detected, but GPS distance ({closest_distance}m) is outside geofence. Network is not conclusive proof.",
        )

    return LocationVerificationResult(
        verification_status=VerificationStatus.OUTSIDE_GEOFENCE,
        verification_method=VerificationMethod.GPS,
        is_conclusive=False,
        confidence_score=0.1,
        distance_meters=closest_distance if closest_distance != float("inf") else None,
        office_id=best_office.id if best_office else None,
        geofence_id=best_geofence.id if best_geofence else None,
        notes=f"Outside geofence perimeter: {closest_distance}m from closest office geofence",
    )


async def verify_and_persist_location(
    db: AsyncSession,
    employee_id: uuid.UUID,
    latitude: float | None,
    longitude: float | None,
    accuracy_meters: float | None = None,
    is_mocked: bool = False,
    permission_status: LocationPermissionStatus = LocationPermissionStatus.GRANTED,
    source: str = "DESKTOP",
    client_event_id: str | None = None,
    client_ssid: str | None = None,
    client_bssid: str | None = None,
    client_ip: str | None = None,
    target_office_id: uuid.UUID | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> tuple[LocationEvent, LocationVerification]:
    """
    Executes location evaluation and commits LocationEvent & LocationVerification.
    Deduplicates against client_event_id for offline synchronization reliability.
    """
    # 1. Deduplication check
    if client_event_id:
        existing_ev = await db.execute(
            select(LocationEvent)
            .options(selectinload(LocationEvent.verification))
            .where(LocationEvent.client_event_id == client_event_id)
        )
        existing = existing_ev.scalars().first()
        if existing and existing.verification:
            return existing, existing.verification

    # 2. Query employee and organization offices
    emp_stmt = select(EmployeeProfile).where(EmployeeProfile.id == employee_id)
    emp_res = await db.execute(emp_stmt)
    emp = emp_res.scalars().first()
    if not emp:
        raise ValueError(f"Employee {employee_id} not found")

    offices_stmt = (
        select(Office)
        .options(
            selectinload(Office.geofences),
            selectinload(Office.networks),
        )
        .where(
            Office.organization_id == emp.organization_id,
            Office.is_active == True,  # noqa: E712
        )
    )
    offices_res = await db.execute(offices_stmt)
    offices = list(offices_res.scalars().all())

    # 3. Deterministic compliance evaluation
    eval_result = evaluate_location_compliance(
        latitude=latitude,
        longitude=longitude,
        accuracy_meters=accuracy_meters,
        is_mocked=is_mocked,
        permission_status=permission_status,
        client_ssid=client_ssid,
        client_bssid=client_bssid,
        client_ip=client_ip,
        offices=offices,
        target_office_id=target_office_id,
    )

    # 4. Create LocationEvent
    event = LocationEvent(
        employee_id=employee_id,
        latitude=latitude if latitude is not None else 0.0,
        longitude=longitude if longitude is not None else 0.0,
        accuracy_meters=accuracy_meters,
        is_mocked=is_mocked,
        source=source,
        permission_status=permission_status,
        client_event_id=client_event_id,
        metadata_json=metadata_json or {},
    )
    db.add(event)
    await db.flush()

    # 5. Create LocationVerification
    verification = LocationVerification(
        location_event_id=event.id,
        office_id=eval_result.office_id,
        office_geofence_id=eval_result.geofence_id,
        office_network_id=eval_result.network_id,
        verification_status=eval_result.verification_status,
        verification_method=eval_result.verification_method,
        distance_meters=eval_result.distance_meters,
        is_conclusive=eval_result.is_conclusive,
        confidence_score=eval_result.confidence_score,
        notes=eval_result.notes,
    )
    db.add(verification)
    await db.commit()
    await db.refresh(event)
    await db.refresh(verification)

    return event, verification


async def purge_expired_location_events(
    db: AsyncSession,
    organization_id: uuid.UUID,
    retention_days: int = 90,
) -> int:
    """
    Data retention enforcement: Permanently removes discrete location telemetry
    older than the specified retention window (default: 90 days).
    """
    cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)

    stmt = (
        select(LocationEvent)
        .join(EmployeeProfile, LocationEvent.employee_id == EmployeeProfile.id)
        .where(
            EmployeeProfile.organization_id == organization_id,
            LocationEvent.recorded_at < cutoff_date,
        )
    )
    result = await db.execute(stmt)
    expired_events = list(result.scalars().all())

    count = len(expired_events)
    for ev in expired_events:
        await db.delete(ev)

    await db.commit()
    return count

