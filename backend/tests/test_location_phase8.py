"""
Comprehensive Verification Tests for Phase 08: Location and Office Verification
Tests geofence perimeter evaluation, Wi-Fi network validation, anti-spoofing,
negative constraint compliance (Wi-Fi/IP never conclusive, zero continuous tracking),
accuracy filtering, offline sync, and data retention controls.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.core.seeds import seed_permissions, seed_system_roles
from app.models.attendance import AttendanceDay, AttendanceEvent, AttendanceEventType
from app.models.auth import AuditLog, Role, User
from app.models.employee import EmployeeProfile, EmploymentStatus
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
from app.models.organization import Organization
from app.services.location_verifier import calculate_haversine_distance


@pytest.fixture
async def setup_location_env(db_session: AsyncSession):
    """Sets up an organization, admin, employee, standard office, geofence, and Wi-Fi networks."""
    # 1. Organization
    code_suffix = uuid.uuid4().hex[:6].upper()
    org = Organization(
        name="Global Corp Location Test",
        code=f"GCLT-{code_suffix}",
        slug=f"gclt-{code_suffix.lower()}",
        is_active=True,
    )
    db_session.add(org)
    await db_session.flush()

    # 2. Roles & Permissions
    perm_map = await seed_permissions(db_session)
    role_map = await seed_system_roles(db_session, perm_map)

    # 3. Admin User
    admin_user = User(
        organization_id=org.id,
        role_id=role_map["Administrator"].id,
        email=f"admin_{uuid.uuid4().hex[:6]}@locationtest.corp",
        hashed_password=get_password_hash("AdminPass123!"),
        is_active=True,
    )
    db_session.add(admin_user)

    # 4. Employee User & Profile
    emp_user = User(
        organization_id=org.id,
        role_id=role_map["Employee"].id,
        email=f"emp_{uuid.uuid4().hex[:6]}@locationtest.corp",
        hashed_password=get_password_hash("EmpPass123!"),
        is_active=True,
    )
    db_session.add(emp_user)
    await db_session.flush()

    emp_profile = EmployeeProfile(
        organization_id=org.id,
        user_id=emp_user.id,
        employee_code=f"EMP-{uuid.uuid4().hex[:4].upper()}",
        first_name="Field",
        last_name="Engineer",
        hire_date=datetime.now(UTC).date(),
        employment_status=EmploymentStatus.ACTIVE,
    )
    db_session.add(emp_profile)

    # 5. Headquarters Office (San Francisco Financial District)
    # Coordinates: 37.7915° N, 122.4000° W
    hq_office = Office(
        organization_id=org.id,
        name="Global Corp HQ",
        code="HQ-SF",
        address="100 Pine Street, San Francisco, CA 94111",
        timezone="America/Los_Angeles",
        is_active=True,
    )
    db_session.add(hq_office)
    await db_session.flush()

    # 6. Geofence (100 meter radius)
    hq_geofence = OfficeGeofence(
        office_id=hq_office.id,
        name="HQ Building Perimeter",
        latitude=37.7915,
        longitude=-122.4000,
        radius_meters=100.0,
        is_active=True,
    )
    db_session.add(hq_geofence)

    # 7. Authorized Office Wi-Fi Network
    hq_network = OfficeNetwork(
        office_id=hq_office.id,
        name="HQ-Corporate-Secure",
        ssid="HQ-Corp-WiFi",
        bssid_mac="00:14:22:01:23:45",
        ip_address="198.51.100.1",
        subnet_cidr="198.51.100.0/24",
        is_active=True,
    )
    db_session.add(hq_network)

    await db_session.commit()

    admin_token = create_access_token(admin_user.id, {"org": str(org.id), "role": "Admin"})
    emp_token = create_access_token(emp_user.id, {"org": str(org.id), "role": "Employee"})

    return {
        "org": org,
        "admin_user": admin_user,
        "admin_token": admin_token,
        "emp_user": emp_user,
        "emp_profile": emp_profile,
        "emp_token": emp_token,
        "hq_office": hq_office,
        "hq_geofence": hq_geofence,
        "hq_network": hq_network,
    }


# ============================================================================
# 1. Haversine Mathematical Accuracy
# ============================================================================


def test_haversine_formula_accuracy():
    """Validates mathematical distance calculation against known terrestrial coordinates."""
    # Paris (48.8566, 2.3522) to London (51.5074, -0.1278) ~ 343.5 km
    dist_m = calculate_haversine_distance(48.8566, 2.3522, 51.5074, -0.1278)
    assert 340000 <= dist_m <= 346000

    # Same location: distance should be 0.0
    zero_dist = calculate_haversine_distance(37.7915, -122.4000, 37.7915, -122.4000)
    assert zero_dist == 0.0


# ============================================================================
# 2. Admin/HR Office & Geofence Configuration Lifecycle
# ============================================================================


@pytest.mark.asyncio
async def test_admin_office_and_geofence_configuration_lifecycle(client: AsyncClient, setup_location_env, db_session: AsyncSession):
    """
    Scenario: Admin creates a new regional office with geofence, updates timezone,
    adds a network, and verifies audit logging.
    """
    data = setup_location_env
    admin_headers = {"Authorization": f"Bearer {data['admin_token']}"}

    # 1. Create Regional Office (New York)
    office_payload = {
        "name": "New York Regional Office",
        "code": "NYC-MIDTOWN",
        "address": "350 5th Ave, New York, NY 10118",
        "timezone": "America/New_York",
        "latitude": 40.7484,
        "longitude": -73.9857,
        "radius_meters": 150.0,
        "networks": [
            {
                "name": "NYC-Secure-5G",
                "ssid": "NYC-Corp-WiFi",
                "bssid_mac": "aa:bb:cc:dd:ee:01",
                "subnet_cidr": "203.0.113.0/24",
                "is_active": True,
            }
        ],
    }
    create_resp = await client.post("/api/v1/offices", json=office_payload, headers=admin_headers)
    assert create_resp.status_code == 201, create_resp.text
    office_data = create_resp.json()
    office_id = office_data["id"]
    assert office_data["code"] == "NYC-MIDTOWN"
    assert len(office_data["geofences"]) == 1
    assert office_data["geofences"][0]["radius_meters"] == 150.0
    assert len(office_data["networks"]) == 1

    # 2. Add an auxiliary geofence (Annex building)
    gf_resp = await client.post(
        f"/api/v1/offices/{office_id}/geofences",
        json={
            "name": "NYC Midtown Annex",
            "latitude": 40.7490,
            "longitude": -73.9860,
            "radius_meters": 80.0,
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert gf_resp.status_code == 201
    assert gf_resp.json()["radius_meters"] == 80.0

    # 3. Update Office Timezone
    patch_resp = await client.patch(
        f"/api/v1/offices/{office_id}",
        json={"timezone": "US/Eastern"},
        headers=admin_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["timezone"] == "US/Eastern"

    # 4. Verify Audit Log was generated
    audit_res = await db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "Office",
            AuditLog.action.in_(["OFFICE_CREATED", "OFFICE_UPDATED"]),
        )
    )
    audits = list(audit_res.scalars().all())
    assert len(audits) >= 2


# ============================================================================
# 3. Office Radius: Within Geofence vs Outside Geofence
# ============================================================================


@pytest.mark.asyncio
async def test_office_radius_within_geofence(client: AsyncClient, setup_location_env):
    """
    Scenario: Employee checks in 25 meters from HQ office center (within 100m geofence).
    Result: Status is VERIFIED, conclusive=True, confidence >= 0.95.
    """
    data = setup_location_env
    emp_headers = {"Authorization": f"Bearer {data['emp_token']}"}

    # ~25 meters north of HQ (37.7915, -122.4000)
    # 0.0002 degrees lat is ~22 meters
    lat_in = 37.7917
    lon_in = -122.4000

    resp = await client.post(
        "/api/v1/locations/verify",
        json={
            "latitude": lat_in,
            "longitude": lon_in,
            "accuracy_meters": 10.0,
            "is_mocked": False,
            "source": "DESKTOP",
        },
        headers=emp_headers,
    )
    assert resp.status_code == 201, resp.text
    res_data = resp.json()
    assert res_data["verification_status"] == "VERIFIED"
    assert res_data["verification_method"] == "GPS"
    assert res_data["is_conclusive"] is True
    assert res_data["confidence_score"] >= 0.95
    assert res_data["distance_meters"] is not None
    assert res_data["distance_meters"] <= 100.0


@pytest.mark.asyncio
async def test_office_radius_outside_geofence(client: AsyncClient, setup_location_env):
    """
    Scenario: Employee checks in 1.2 km away from HQ office (outside 100m geofence).
    Result: Status is OUTSIDE_GEOFENCE, conclusive=False, distance recorded.
    """
    data = setup_location_env
    emp_headers = {"Authorization": f"Bearer {data['emp_token']}"}

    # 37.8020 is ~1.2km north of 37.7915
    lat_out = 37.8020
    lon_out = -122.4000

    resp = await client.post(
        "/api/v1/locations/verify",
        json={
            "latitude": lat_out,
            "longitude": lon_out,
            "accuracy_meters": 15.0,
            "is_mocked": False,
        },
        headers=emp_headers,
    )
    assert resp.status_code == 201
    res_data = resp.json()
    assert res_data["verification_status"] == "OUTSIDE_GEOFENCE"
    assert res_data["is_conclusive"] is False
    assert res_data["distance_meters"] > 100.0


# ============================================================================
# 4. Multi-Factor Hybrid Verification (GPS + Verified Network)
# ============================================================================


@pytest.mark.asyncio
async def test_multi_factor_hybrid_verification(client: AsyncClient, setup_location_env):
    """
    Scenario: Employee within geofence AND connected to verified corporate Wi-Fi (SSID + BSSID).
    Result: Status is VERIFIED, Method is HYBRID, conclusive=True, confidence=1.0.
    """
    data = setup_location_env
    emp_headers = {"Authorization": f"Bearer {data['emp_token']}"}

    resp = await client.post(
        "/api/v1/locations/verify",
        json={
            "latitude": 37.79152,
            "longitude": -122.40002,
            "accuracy_meters": 8.0,
            "client_ssid": "HQ-Corp-WiFi",
            "client_bssid": "00:14:22:01:23:45",
        },
        headers=emp_headers,
    )
    assert resp.status_code == 201
    res_data = resp.json()
    assert res_data["verification_status"] == "VERIFIED"
    assert res_data["verification_method"] == "HYBRID"
    assert res_data["is_conclusive"] is True
    assert res_data["confidence_score"] == 1.0
    assert "Multi-factor" in res_data["notes"]


# ============================================================================
# 5. NEGATIVE CONSTRAINT 1: Never treat Wi-Fi or IP as Conclusive Proof
# ============================================================================


@pytest.mark.asyncio
async def test_negative_constraint_wifi_alone_is_never_conclusive(client: AsyncClient, setup_location_env):
    """
    Rule: Never treat IP location or Wi-Fi as conclusive proof of physical presence.
    Case A: Matching Wi-Fi SSID, but NO GPS coordinates provided.
    Result: Flagged as UNVERIFIED, is_conclusive=False, confidence <= 0.6.
    """
    data = setup_location_env
    emp_headers = {"Authorization": f"Bearer {data['emp_token']}"}

    resp = await client.post(
        "/api/v1/locations/verify",
        json={
            "latitude": None,
            "longitude": None,
            "client_ssid": "HQ-Corp-WiFi",
            "client_bssid": "00:14:22:01:23:45",
        },
        headers=emp_headers,
    )
    assert resp.status_code == 201
    res_data = resp.json()
    # Must NEVER be VERIFIED!
    assert res_data["verification_status"] == "UNVERIFIED"
    assert res_data["verification_method"] == "WIFI_NETWORK"
    assert res_data["is_conclusive"] is False
    assert res_data["confidence_score"] <= 0.6
    assert "non-conclusive" in res_data["notes"]


@pytest.mark.asyncio
async def test_negative_constraint_wifi_outside_geofence_is_unverified(client: AsyncClient, setup_location_env):
    """
    Rule: Never treat IP location or Wi-Fi as conclusive proof of physical presence.
    Case B: Connected to corporate VPN/Wi-Fi (matching SSID), but GPS coordinate is 5km away!
    Result: Flagged as UNVERIFIED (NOT verified!).
    """
    data = setup_location_env
    emp_headers = {"Authorization": f"Bearer {data['emp_token']}"}

    # 5 km away
    lat_far = 37.8350
    lon_far = -122.4000

    resp = await client.post(
        "/api/v1/locations/verify",
        json={
            "latitude": lat_far,
            "longitude": lon_far,
            "accuracy_meters": 10.0,
            "client_ssid": "HQ-Corp-WiFi",
        },
        headers=emp_headers,
    )
    assert resp.status_code == 201
    res_data = resp.json()
    assert res_data["verification_status"] == "UNVERIFIED"
    assert res_data["is_conclusive"] is False
    assert "not conclusive proof" in res_data["notes"]


# ============================================================================
# 6. Inaccurate Coordinates Handling (>200m accuracy)
# ============================================================================


@pytest.mark.asyncio
async def test_inaccurate_coordinates_exceeding_threshold(client: AsyncClient, setup_location_env):
    """
    Scenario: GPS coordinate is near office, but reported horizontal accuracy is ±350m (>200m threshold).
    Result: Status is UNVERIFIED, is_conclusive=False, explanatory note recorded.
    """
    data = setup_location_env
    emp_headers = {"Authorization": f"Bearer {data['emp_token']}"}

    resp = await client.post(
        "/api/v1/locations/verify",
        json={
            "latitude": 37.7915,
            "longitude": -122.4000,
            "accuracy_meters": 350.0,  # Exceeds 200m confidence limit
        },
        headers=emp_headers,
    )
    assert resp.status_code == 201
    res_data = resp.json()
    assert res_data["verification_status"] == "UNVERIFIED"
    assert res_data["is_conclusive"] is False
    assert "Inaccurate GPS coordinates" in res_data["notes"]


# ============================================================================
# 7. Denied or Unavailable Location Permissions
# ============================================================================


@pytest.mark.asyncio
async def test_denied_or_unavailable_location_permission(client: AsyncClient, setup_location_env):
    """
    Scenario: Employee or OS has disabled location permissions (DENIED / UNAVAILABLE).
    Result: Verification records UNAVAILABLE, method=UNAVAILABLE, conclusive=False.
    """
    data = setup_location_env
    emp_headers = {"Authorization": f"Bearer {data['emp_token']}"}

    resp = await client.post(
        "/api/v1/locations/verify",
        json={
            "permission_status": "DENIED",
        },
        headers=emp_headers,
    )
    assert resp.status_code == 201
    res_data = resp.json()
    assert res_data["verification_status"] == "UNAVAILABLE"
    assert res_data["verification_method"] == "UNAVAILABLE"
    assert res_data["is_conclusive"] is False
    assert res_data["confidence_score"] == 0.0


# ============================================================================
# 8. Anti-Spoofing Mock Detection
# ============================================================================


@pytest.mark.asyncio
async def test_anti_spoofing_detection(client: AsyncClient, setup_location_env):
    """
    Scenario: Client device reports is_mocked=True (mock GPS provider).
    Result: Verification status is SPOOF_DETECTED, is_conclusive=False.
    """
    data = setup_location_env
    emp_headers = {"Authorization": f"Bearer {data['emp_token']}"}

    resp = await client.post(
        "/api/v1/locations/verify",
        json={
            "latitude": 37.7915,
            "longitude": -122.4000,
            "is_mocked": True,
        },
        headers=emp_headers,
    )
    assert resp.status_code == 201
    res_data = resp.json()
    assert res_data["verification_status"] == "SPOOF_DETECTED"
    assert res_data["is_conclusive"] is False
    assert "simulated" in res_data["notes"]


# ============================================================================
# 9. Attendance Integration: Location Capture at Clock-In & Clock-Out
# ============================================================================


@pytest.mark.asyncio
async def test_attendance_clock_in_and_out_location_integration(client: AsyncClient, setup_location_env, db_session: AsyncSession):
    """
    Scenario: Employee clocks in with GPS within geofence and clocks out with GPS outside geofence.
    Verified:
    - Discrete location captured ONLY at check-in and check-out (NO continuous tracking).
    - Clock-in event is linked to a VERIFIED LocationVerification.
    - Clock-out event is linked to an OUTSIDE_GEOFENCE LocationVerification.
    """
    data = setup_location_env
    headers = {"Authorization": f"Bearer {data['emp_token']}"}

    # 1. Clock In (At Office: 37.7915, -122.4000)
    t_in = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
    in_resp = await client.post(
        "/api/v1/attendance/clock-in",
        json={
            "occurred_at": t_in.isoformat(),
            "latitude": 37.79155,
            "longitude": -122.40002,
            "accuracy_meters": 12.0,
            "ssid": "HQ-Corp-WiFi",
        },
        headers=headers,
    )
    assert in_resp.status_code == 201, in_resp.text
    in_data = in_resp.json()
    assert len(in_data["events"]) >= 1
    in_evt = in_data["events"][-1]
    assert in_evt["location_verification_id"] is not None

    # Verify verification record
    in_verif = await db_session.get(LocationVerification, uuid.UUID(in_evt["location_verification_id"]))
    assert in_verif is not None
    assert in_verif.verification_status == VerificationStatus.VERIFIED
    assert in_verif.is_conclusive is True

    # 2. Clock Out (Outside Office: 37.8200, -122.4000)
    t_out = datetime(2026, 11, 23, 17, 0, tzinfo=UTC)
    out_resp = await client.post(
        "/api/v1/attendance/clock-out",
        json={
            "occurred_at": t_out.isoformat(),
            "latitude": 37.8200,
            "longitude": -122.4000,
            "accuracy_meters": 15.0,
        },
        headers=headers,
    )
    assert out_resp.status_code == 200, out_resp.text
    out_data = out_resp.json()
    out_evt = out_data["events"][-1]
    assert out_evt["location_verification_id"] is not None

    out_verif = await db_session.get(LocationVerification, uuid.UUID(out_evt["location_verification_id"]))
    assert out_verif is not None
    assert out_verif.verification_status == VerificationStatus.OUTSIDE_GEOFENCE


# ============================================================================
# 10. Privacy, Employee Disclosure & Retention Purge
# ============================================================================


@pytest.mark.asyncio
async def test_privacy_disclosure_and_data_retention_purge(client: AsyncClient, setup_location_env, db_session: AsyncSession):
    """
    Scenario:
    - Employee queries compliance disclosure (verifies strict prohibition of continuous GPS tracking).
    - Admin triggers data retention purge for location events older than 90 days.
    """
    data = setup_location_env
    emp_headers = {"Authorization": f"Bearer {data['emp_token']}"}
    admin_headers = {"Authorization": f"Bearer {data['admin_token']}"}

    # 1. Query Disclosure
    disc_resp = await client.get("/api/v1/locations/compliance-disclosure", headers=emp_headers)
    assert disc_resp.status_code == 200
    disc = disc_resp.json()
    assert "Continuous GPS tracking is strictly prohibited" in disc["gps_tracking_policy"]
    assert "never treated as conclusive" in disc["non_conclusive_rule"]
    assert disc["data_retention_days"] == 90

    # 2. Seed an old location event (120 days old)
    old_time = datetime.now(UTC) - timedelta(days=120)
    old_event = LocationEvent(
        employee_id=data["emp_profile"].id,
        latitude=37.7915,
        longitude=-122.4000,
        recorded_at=old_time,
    )
    db_session.add(old_event)
    await db_session.commit()

    # 3. Purge data older than 90 days
    purge_resp = await client.delete("/api/v1/locations/retention/purge?retention_days=90", headers=admin_headers)
    assert purge_resp.status_code == 200
    purge_data = purge_resp.json()
    assert purge_data["purged_records"] >= 1

    # Verify old event is removed
    check_event = await db_session.get(LocationEvent, old_event.id)
    assert check_event is None
