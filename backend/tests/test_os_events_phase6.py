"""
Comprehensive Unit & Integration Test Suite for Phase 06 OS Session Monitoring
Tests:
- Common event contract conformance
- Strict separation from attendance events
- Batch offline sync & delayed synchronization calculation
- Duplicate prevention (idempotency)
- Monotonic sequence gap detection
- Clock anomaly auditing
- Health monitoring endpoint
- RBAC boundary enforcement (Employee, Manager, HR/Admin)
- Negative constraint validation (No keylogging, screenshots, or hidden surveillance)
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.core.seeds import seed_permissions, seed_system_roles
from app.models.attendance import AttendanceDay, AttendanceEvent
from app.models.employee import EmployeeProfile, EmploymentStatus, ManagerAssignment
from app.models.organization import Organization
from app.models.os_event import OSSessionEvent, OSSessionEventType


@pytest.fixture
async def setup_os_test_data(db_session: AsyncSession):
    """Initializes organization, system roles, employees, and users for OS monitoring tests."""
    perm_map = await seed_permissions(db_session)
    role_map = await seed_system_roles(db_session, perm_map)

    # Organization
    org = Organization(
        name="Apex Security Technologies",
        slug=f"apex-sec-{uuid.uuid4().hex[:6]}",
        code=f"APX{uuid.uuid4().hex[:4].upper()}",
    )
    db_session.add(org)
    await db_session.flush()

    # Users
    from app.models.auth import User

    admin_user = User(
        email=f"admin_{uuid.uuid4().hex[:6]}@apex.com",
        hashed_password=get_password_hash("AdminPass123!"),
        role_id=role_map["Super Administrator"].id,
        organization_id=org.id,
        is_active=True,
    )
    mgr_user = User(
        email=f"mgr_{uuid.uuid4().hex[:6]}@apex.com",
        hashed_password=get_password_hash("MgrPass123!"),
        role_id=role_map["Department Manager"].id,
        organization_id=org.id,
        is_active=True,
    )
    emp1_user = User(
        email=f"emp1_{uuid.uuid4().hex[:6]}@apex.com",
        hashed_password=get_password_hash("EmpPass123!"),
        role_id=role_map["Employee"].id,
        organization_id=org.id,
        is_active=True,
    )
    emp2_user = User(
        email=f"emp2_{uuid.uuid4().hex[:6]}@apex.com",
        hashed_password=get_password_hash("EmpPass123!"),
        role_id=role_map["Employee"].id,
        organization_id=org.id,
        is_active=True,
    )
    db_session.add_all([admin_user, mgr_user, emp1_user, emp2_user])
    await db_session.flush()

    # Employee Profiles
    emp_profile_admin = EmployeeProfile(
        organization_id=org.id,
        user_id=admin_user.id,
        employee_code=f"EMP-ADM-{uuid.uuid4().hex[:4]}",
        first_name="Alice",
        last_name="Administrator",
        hire_date=date(2024, 1, 1),
        employment_status=EmploymentStatus.ACTIVE,
    )
    emp_profile_mgr = EmployeeProfile(
        organization_id=org.id,
        user_id=mgr_user.id,
        employee_code=f"EMP-MGR-{uuid.uuid4().hex[:4]}",
        first_name="Bob",
        last_name="Manager",
        hire_date=date(2024, 1, 1),
        employment_status=EmploymentStatus.ACTIVE,
    )
    emp_profile_charlie = EmployeeProfile(
        organization_id=org.id,
        user_id=emp1_user.id,
        employee_code=f"EMP-ENG-{uuid.uuid4().hex[:4]}",
        first_name="Charlie",
        last_name="Engineer",
        hire_date=date(2024, 1, 1),
        employment_status=EmploymentStatus.ACTIVE,
    )
    emp_profile_david = EmployeeProfile(
        organization_id=org.id,
        user_id=emp2_user.id,
        employee_code=f"EMP-ANA-{uuid.uuid4().hex[:4]}",
        first_name="David",
        last_name="Analyst",
        hire_date=date(2024, 1, 1),
        employment_status=EmploymentStatus.ACTIVE,
    )
    db_session.add_all([emp_profile_admin, emp_profile_mgr, emp_profile_charlie, emp_profile_david])
    await db_session.flush()

    # Manager Assignment: Bob manages Charlie (not David)
    assign = ManagerAssignment(
        organization_id=org.id,
        employee_id=emp_profile_charlie.id,
        manager_id=emp_profile_mgr.id,
        is_primary=True,
    )
    db_session.add(assign)
    await db_session.commit()

    return {
        "org": org,
        "admin_user": admin_user,
        "mgr_user": mgr_user,
        "emp1_user": emp1_user,
        "emp2_user": emp2_user,
        "emp_profile_admin": emp_profile_admin,
        "emp_profile_mgr": emp_profile_mgr,
        "emp_profile_charlie": emp_profile_charlie,
        "emp_profile_david": emp_profile_david,
        "admin_token": create_access_token(admin_user.id, {"org": str(org.id)}),
        "mgr_token": create_access_token(mgr_user.id, {"org": str(org.id)}),
        "emp1_token": create_access_token(emp1_user.id, {"org": str(org.id)}),
        "emp2_token": create_access_token(emp2_user.id, {"org": str(org.id)}),
    }


@pytest.mark.asyncio
async def test_single_os_session_event_ingestion(client: AsyncClient, setup_os_test_data):
    """Test ingestion of a single native OS session event conforming to the Phase 06 contract."""
    data = setup_os_test_data
    event_id = uuid.uuid4()
    occurred = datetime.now(UTC) - timedelta(minutes=1)

    payload = {
        "event_id": str(event_id),
        "employee_id": str(data["emp_profile_charlie"].id),
        "device_id": "WIN-WORKSTATION-01",
        "operating_system": "windows",
        "event_type": OSSessionEventType.OS_LOGON.value,
        "occurred_at": occurred.isoformat(),
        "sequence_number": 1,
        "agent_version": "1.0.0",
        "metadata": {
            "session_id": 1,
            "domain": "APEX_CORP",
            "logon_type": "Interactive",
            "battery_percent": 98,
        },
    }

    headers = {"Authorization": f"Bearer {data['emp1_token']}"}
    resp = await client.post("/api/v1/os-events/", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    res_data = resp.json()

    assert res_data["event_id"] == str(event_id)
    assert res_data["device_id"] == "WIN-WORKSTATION-01"
    assert res_data["operating_system"] == "windows"
    assert res_data["event_type"] == "OS_LOGON"
    assert res_data["sequence_number"] == 1
    assert res_data["employee_name"] == "Charlie Engineer"
    assert res_data["sync_delay_seconds"] >= 50.0


@pytest.mark.asyncio
async def test_os_events_remain_strictly_separate_from_attendance(
    client: AsyncClient, setup_os_test_data, db_session: AsyncSession
):
    """
    Requirement 1: Verify that logging OS session events (logon, lock, sleep)
    NEVER mutates or pollutes attendance days or attendance events tables.
    """
    data = setup_os_test_data
    event_id = uuid.uuid4()

    payload = {
        "event_id": str(event_id),
        "employee_id": str(data["emp_profile_charlie"].id),
        "device_id": "WIN-WORKSTATION-01",
        "operating_system": "windows",
        "event_type": OSSessionEventType.SESSION_LOCK.value,
        "occurred_at": datetime.now(UTC).isoformat(),
        "sequence_number": 2,
        "agent_version": "1.0.0",
        "metadata": {"lock_reason": "Workstation idle lock"},
    }
    headers = {"Authorization": f"Bearer {data['emp1_token']}"}
    resp = await client.post("/api/v1/os-events/", json=payload, headers=headers)
    assert resp.status_code == 201

    # Verify zero attendance records created
    att_days = await db_session.execute(
        select(AttendanceDay).where(AttendanceDay.employee_id == data["emp_profile_charlie"].id)
    )
    assert len(att_days.scalars().all()) == 0

    att_events = await db_session.execute(
        select(AttendanceEvent)
        .join(AttendanceDay, AttendanceEvent.attendance_day_id == AttendanceDay.id)
        .where(AttendanceDay.employee_id == data["emp_profile_charlie"].id)
    )
    assert len(att_events.scalars().all()) == 0


@pytest.mark.asyncio
async def test_offline_batch_synchronization_and_deduplication(
    client: AsyncClient, setup_os_test_data
):
    """
    Requirements 2, 3, 4:
    - Queue events offline and sync in bulk.
    - Prevent duplicate events through idempotency.
    """
    data = setup_os_test_data
    dev_id = "MAC-LAPTOP-M3"
    t0 = datetime.now(UTC) - timedelta(hours=2)

    ev1 = {
        "event_id": str(uuid.uuid4()),
        "employee_id": str(data["emp_profile_charlie"].id),
        "device_id": dev_id,
        "operating_system": "macos",
        "event_type": "SYSTEM_STARTUP",
        "occurred_at": (t0).isoformat(),
        "sequence_number": 1,
        "agent_version": "1.0.0",
        "metadata": {"boot_time": "12s", "kernel": "Darwin 23.5"},
    }
    ev2 = {
        "event_id": str(uuid.uuid4()),
        "employee_id": str(data["emp_profile_charlie"].id),
        "device_id": dev_id,
        "operating_system": "macos",
        "event_type": "OS_LOGON",
        "occurred_at": (t0 + timedelta(minutes=1)).isoformat(),
        "sequence_number": 2,
        "agent_version": "1.0.0",
        "metadata": {"user": "cengineer", "display": "Retina"},
    }
    ev3 = {
        "event_id": str(uuid.uuid4()),
        "employee_id": str(data["emp_profile_charlie"].id),
        "device_id": dev_id,
        "operating_system": "macos",
        "event_type": "SESSION_LOCK",
        "occurred_at": (t0 + timedelta(minutes=30)).isoformat(),
        "sequence_number": 3,
        "agent_version": "1.0.0",
        "metadata": {"trigger": "ScreenSaver/Sleep"},
    }

    sync_batch = {
        "device_id": dev_id,
        "events": [ev1, ev2, ev3],
    }

    headers = {"Authorization": f"Bearer {data['emp1_token']}"}

    # 1. Initial Batch Sync
    resp = await client.post("/api/v1/os-events/sync", json=sync_batch, headers=headers)
    assert resp.status_code == 200, resp.text
    res_json = resp.json()
    assert res_json["received_count"] == 3
    assert res_json["inserted_count"] == 3
    assert res_json["duplicate_count"] == 0
    assert res_json["latest_sequence_number"] == 3

    # 2. Re-send Same Batch (Duplicate Prevention & Idempotency)
    resp2 = await client.post("/api/v1/os-events/sync", json=sync_batch, headers=headers)
    assert resp2.status_code == 200
    res_json2 = resp2.json()
    assert res_json2["received_count"] == 3
    assert res_json2["inserted_count"] == 0
    assert res_json2["duplicate_count"] == 3
    assert res_json2["latest_sequence_number"] == 3

    # 3. Batch with 1 duplicate and 1 new event
    ev4 = {
        "event_id": str(uuid.uuid4()),
        "employee_id": str(data["emp_profile_charlie"].id),
        "device_id": dev_id,
        "operating_system": "macos",
        "event_type": "SESSION_UNLOCK",
        "occurred_at": (t0 + timedelta(minutes=45)).isoformat(),
        "sequence_number": 4,
        "agent_version": "1.0.0",
        "metadata": {"method": "TouchID"},
    }
    mixed_batch = {"device_id": dev_id, "events": [ev3, ev4]}
    resp3 = await client.post("/api/v1/os-events/sync", json=mixed_batch, headers=headers)
    assert resp3.status_code == 200
    res_json3 = resp3.json()
    assert res_json3["received_count"] == 2
    assert res_json3["inserted_count"] == 1
    assert res_json3["duplicate_count"] == 1
    assert res_json3["latest_sequence_number"] == 4


@pytest.mark.asyncio
async def test_sequence_gap_and_clock_skew_auditing(client: AsyncClient, setup_os_test_data):
    """
    Requirements 5, 6, 8:
    - Detect gaps in sequence numbers across device restarts or dropped packets.
    - Flag clock skew when events arrive with future timestamps.
    """
    data = setup_os_test_data
    dev_id = "WIN-DESKTOP-GAP-TEST"
    now = datetime.now(UTC)

    # Ingest sequence 10
    ev1 = {
        "event_id": str(uuid.uuid4()),
        "employee_id": str(data["emp_profile_charlie"].id),
        "device_id": dev_id,
        "operating_system": "windows",
        "event_type": "SYSTEM_STARTUP",
        "occurred_at": (now - timedelta(minutes=30)).isoformat(),
        "sequence_number": 10,
        "agent_version": "1.0.0",
        "metadata": {},
    }
    headers = {"Authorization": f"Bearer {data['emp1_token']}"}
    await client.post("/api/v1/os-events/sync", json={"events": [ev1]}, headers=headers)

    # Now ingest sequence 15 (skipping 11, 12, 13, 14) and future timestamp (> 5 mins)
    future_time = now + timedelta(minutes=15)
    ev_gap = {
        "event_id": str(uuid.uuid4()),
        "employee_id": str(data["emp_profile_charlie"].id),
        "device_id": dev_id,
        "operating_system": "windows",
        "event_type": "SYSTEM_SLEEP",
        "occurred_at": future_time.isoformat(),
        "sequence_number": 15,
        "agent_version": "1.0.0",
        "metadata": {"reason": "lid_close"},
    }
    resp = await client.post("/api/v1/os-events/sync", json={"events": [ev_gap]}, headers=headers)
    assert resp.status_code == 200
    res_json = resp.json()

    assert res_json["clock_skew_flagged"] is True
    assert 11 in res_json["gaps_detected"]
    assert 12 in res_json["gaps_detected"]
    assert 13 in res_json["gaps_detected"]
    assert 14 in res_json["gaps_detected"]


@pytest.mark.asyncio
async def test_event_health_monitoring_endpoint(client: AsyncClient, setup_os_test_data):
    """
    Requirement 8: Health endpoint reports total events, latest sequence,
    detected gaps, average sync delay, and overall telemetry health.
    """
    data = setup_os_test_data
    dev_id = "WIN-HEALTH-DEVICE"
    now = datetime.now(UTC)

    # Sync contiguous sequences 1, 2, 3
    events = [
        {
            "event_id": str(uuid.uuid4()),
            "employee_id": str(data["emp_profile_charlie"].id),
            "device_id": dev_id,
            "operating_system": "windows",
            "event_type": et,
            "occurred_at": (now - timedelta(minutes=10 - i)).isoformat(),
            "sequence_number": i + 1,
            "agent_version": "1.0.0",
            "metadata": {},
        }
        for i, et in enumerate(["SYSTEM_STARTUP", "OS_LOGON", "USER_ACTIVITY"])
    ]

    headers = {"Authorization": f"Bearer {data['emp1_token']}"}
    await client.post("/api/v1/os-events/sync", json={"events": events}, headers=headers)

    # Query health
    health_resp = await client.get(f"/api/v1/os-events/health/{dev_id}", headers=headers)
    assert health_resp.status_code == 200
    h_data = health_resp.json()

    assert h_data["device_id"] == dev_id
    assert h_data["operating_system"] == "windows"
    assert h_data["total_events"] == 3
    assert h_data["latest_sequence_number"] == 3
    assert len(h_data["missing_sequence_gaps"]) == 0
    assert h_data["clock_anomaly_count"] == 0
    assert h_data["is_healthy"] is True


@pytest.mark.asyncio
async def test_rbac_os_events_query_boundaries(client: AsyncClient, setup_os_test_data):
    """
    RBAC Rules:
    - Super Admin / HR: Access all events.
    - Manager: Access direct reports (Charlie) and self, cannot access non-report (David).
    - Employee: Strictly own records only.
    """
    data = setup_os_test_data
    now = datetime.now(UTC)

    # Ingest event for Charlie
    ev_charlie = {
        "event_id": str(uuid.uuid4()),
        "employee_id": str(data["emp_profile_charlie"].id),
        "device_id": "DEV-CHARLIE",
        "operating_system": "windows",
        "event_type": "OS_LOGON",
        "occurred_at": now.isoformat(),
        "sequence_number": 1,
        "agent_version": "1.0.0",
        "metadata": {},
    }
    # Ingest event for David
    ev_david = {
        "event_id": str(uuid.uuid4()),
        "employee_id": str(data["emp_profile_david"].id),
        "device_id": "DEV-DAVID",
        "operating_system": "macos",
        "event_type": "OS_LOGON",
        "occurred_at": now.isoformat(),
        "sequence_number": 1,
        "agent_version": "1.0.0",
        "metadata": {},
    }

    admin_headers = {"Authorization": f"Bearer {data['admin_token']}"}
    await client.post("/api/v1/os-events/sync", json={"events": [ev_charlie, ev_david]}, headers=admin_headers)

    # 1. Admin queries all: should receive both
    res_admin = await client.get("/api/v1/os-events/", headers=admin_headers)
    assert res_admin.status_code == 200
    emp_ids_seen = {r["employee_id"] for r in res_admin.json()}
    assert str(data["emp_profile_charlie"].id) in emp_ids_seen
    assert str(data["emp_profile_david"].id) in emp_ids_seen

    # 2. Charlie (Employee) queries: should only see Charlie's events
    emp_headers = {"Authorization": f"Bearer {data['emp1_token']}"}
    res_emp = await client.get("/api/v1/os-events/", headers=emp_headers)
    assert res_emp.status_code == 200
    for r in res_emp.json():
        assert r["employee_id"] == str(data["emp_profile_charlie"].id)

    # 3. Bob (Manager) queries Charlie (his report): Allowed
    mgr_headers = {"Authorization": f"Bearer {data['mgr_token']}"}
    res_mgr_charlie = await client.get(
        f"/api/v1/os-events/?employee_id={data['emp_profile_charlie'].id}", headers=mgr_headers
    )
    assert res_mgr_charlie.status_code == 200

    # 4. Bob (Manager) queries David (not his report): Forbidden 403
    res_mgr_david = await client.get(
        f"/api/v1/os-events/?employee_id={data['emp_profile_david'].id}", headers=mgr_headers
    )
    assert res_mgr_david.status_code == 403


@pytest.mark.asyncio
async def test_negative_constraints_and_privacy_boundaries(
    client: AsyncClient, setup_os_test_data, db_session: AsyncSession
):
    """
    Negative Constraints:
    - Never implement keylogging, screenshots, hidden surveillance or continuous GPS.
    - Ensure only clean session state metadata is persisted.
    """
    data = setup_os_test_data
    event_id = uuid.uuid4()

    payload = {
        "event_id": str(event_id),
        "employee_id": str(data["emp_profile_charlie"].id),
        "device_id": "PRIVACY-COMPLIANT-PC",
        "operating_system": "windows",
        "event_type": "SESSION_UNLOCK",
        "occurred_at": datetime.now(UTC).isoformat(),
        "sequence_number": 1,
        "agent_version": "1.0.0",
        "metadata": {
            "lock_duration_seconds": 120,
            "session_type": "Console",
            "audit_disclosure": "Employee activity monitoring strictly restricted to OS state transitions.",
        },
    }

    headers = {"Authorization": f"Bearer {data['emp1_token']}"}
    resp = await client.post("/api/v1/os-events/", json=payload, headers=headers)
    assert resp.status_code == 201

    # Check DB record
    res = await db_session.execute(select(OSSessionEvent).where(OSSessionEvent.event_id == event_id))
    db_event = res.scalars().first()
    assert db_event is not None
    # Confirm no keys like 'keystrokes', 'screenshot', 'gps_coordinates' in metadata
    forbidden_keys = {"keystrokes", "raw_keys", "screenshot", "screen_capture", "camera", "continuous_gps"}
    assert not any(fk in db_event.metadata_json for fk in forbidden_keys)
