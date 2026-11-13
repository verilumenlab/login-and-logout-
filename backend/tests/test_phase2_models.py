"""
Phase 02 Architecture & Model Constraints Verification Test Suite
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.seeds import seed_organization_leave_types, seed_permissions, seed_system_roles
from app.models.attendance import (
    AttendanceDay,
    AttendanceStatus,
)
from app.models.auth import Role, User
from app.models.device import Device, DeviceSession, OSActivityEvent
from app.models.employee import EmployeeProfile
from app.models.leave import (
    LeaveCategory,
    LeaveRequest,
    LeaveType,
)
from app.models.organization import Organization


@pytest.mark.asyncio
async def test_uuid_generation_across_models(db_session: AsyncSession):
    org = Organization(name="UUID Test Org", slug="uuid-test-org", code="UUID_ORG")
    db_session.add(org)
    await db_session.flush()

    assert isinstance(org.id, uuid.UUID)
    assert org.created_at is not None
    assert org.updated_at is not None


@pytest.mark.asyncio
async def test_unique_employee_code_per_organization(db_session: AsyncSession):
    org1 = Organization(name="Org 1", slug="org-1", code="ORG1")
    org2 = Organization(name="Org 2", slug="org-2", code="ORG2")
    db_session.add_all([org1, org2])
    await db_session.flush()

    role1 = Role(organization_id=org1.id, name="Staff 1")
    role2 = Role(organization_id=org2.id, name="Staff 2")
    db_session.add_all([role1, role2])
    await db_session.flush()

    user1 = User(organization_id=org1.id, email="u1@org1.com", hashed_password="pw", role_id=role1.id)
    user2 = User(organization_id=org1.id, email="u2@org1.com", hashed_password="pw", role_id=role1.id)
    user3 = User(organization_id=org2.id, email="u3@org2.com", hashed_password="pw", role_id=role2.id)
    db_session.add_all([user1, user2, user3])
    await db_session.flush()

    # Same employee code "E-100" in org1
    emp1 = EmployeeProfile(
        organization_id=org1.id,
        user_id=user1.id,
        employee_code="E-100",
        first_name="First1",
        last_name="Last1",
        hire_date=date(2025, 1, 1),
    )
    db_session.add(emp1)
    await db_session.flush()

    # Same code in org2 is ALLOWED (tenant isolated)
    emp2 = EmployeeProfile(
        organization_id=org2.id,
        user_id=user3.id,
        employee_code="E-100",
        first_name="Other",
        last_name="Tenant",
        hire_date=date(2025, 1, 1),
    )
    db_session.add(emp2)
    await db_session.flush()
    assert emp1.employee_code == emp2.employee_code
    assert emp1.organization_id != emp2.organization_id

    # Duplicate code in org1 MUST FAIL
    emp_duplicate = EmployeeProfile(
        organization_id=org1.id,
        user_id=user2.id,
        employee_code="E-100",
        first_name="Duplicate",
        last_name="Code",
        hire_date=date(2025, 1, 1),
    )
    db_session.add(emp_duplicate)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_unique_attendance_day_per_employee_and_date(db_session: AsyncSession):
    org = Organization(name="Attend Org", slug="att-org", code="ATT_ORG")
    db_session.add(org)
    await db_session.flush()

    role = Role(organization_id=org.id, name="Staff")
    db_session.add(role)
    await db_session.flush()

    user = User(organization_id=org.id, email="staff_att@org.com", hashed_password="pw", role_id=role.id)
    db_session.add(user)
    await db_session.flush()

    emp = EmployeeProfile(
        organization_id=org.id,
        user_id=user.id,
        employee_code="ATT-1",
        first_name="Sam",
        last_name="Wilson",
        hire_date=date(2025, 1, 1),
    )
    db_session.add(emp)
    await db_session.flush()

    work_day = date(2026, 11, 12)
    day1 = AttendanceDay(
        organization_id=org.id,
        employee_id=emp.id,
        work_date=work_day,
        status=AttendanceStatus.PRESENT,
    )
    db_session.add(day1)
    await db_session.flush()

    # Second attendance record for same employee on same date MUST FAIL
    day2 = AttendanceDay(
        organization_id=org.id,
        employee_id=emp.id,
        work_date=work_day,
        status=AttendanceStatus.HALF_DAY,
    )
    db_session.add(day2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_unique_device_session_event_id(db_session: AsyncSession):
    org = Organization(name="Device Event Org", slug="dev-evt-org", code="DEV_EVT")
    db_session.add(org)
    await db_session.flush()

    role = Role(organization_id=org.id, name="Staff")
    db_session.add(role)
    await db_session.flush()

    user = User(organization_id=org.id, email="dev_evt_user@org.com", hashed_password="pw", role_id=role.id)
    db_session.add(user)
    await db_session.flush()

    emp = EmployeeProfile(
        organization_id=org.id,
        user_id=user.id,
        employee_code="DEVEVT-1",
        first_name="Dana",
        last_name="Scully",
        hire_date=date(2025, 1, 1),
    )
    db_session.add(emp)
    await db_session.flush()

    device = Device(
        organization_id=org.id,
        device_identifier="DEV-ID-UNIQUE-1",
        device_name="Dana-Laptop",
        os_name="macOS",
        os_version="14.5",
        platform="darwin",
        agent_version="2.0.0",
    )
    db_session.add(device)
    await db_session.flush()

    session = DeviceSession(
        device_id=device.id,
        employee_id=emp.id,
        session_token_hash="sess_hash_unique_1",
        start_time=datetime.now(UTC),
    )
    db_session.add(session)
    await db_session.flush()

    event_id = "client-uuid-001"
    evt1 = OSActivityEvent(
        device_session_id=session.id,
        device_event_id=event_id,
        application_name="Browser",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC),
    )
    db_session.add(evt1)
    await db_session.flush()

    # Ingesting same event_id for same device_session MUST FAIL (deduplication)
    evt2 = OSActivityEvent(
        device_session_id=session.id,
        device_event_id=event_id,
        application_name="Browser Duplicate",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC),
    )
    db_session.add(evt2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_leave_dates_check_constraint(db_session: AsyncSession):
    org = Organization(name="Constraint Org", slug="chk-org", code="CHK_ORG")
    db_session.add(org)
    await db_session.flush()

    role = Role(organization_id=org.id, name="Staff")
    db_session.add(role)
    await db_session.flush()

    user = User(organization_id=org.id, email="chk_user@org.com", hashed_password="pw", role_id=role.id)
    db_session.add(user)
    await db_session.flush()

    emp = EmployeeProfile(
        organization_id=org.id,
        user_id=user.id,
        employee_code="CHK-1",
        first_name="Fox",
        last_name="Mulder",
        hire_date=date(2025, 1, 1),
    )
    db_session.add(emp)
    await db_session.flush()

    leave_type = LeaveType(
        organization_id=org.id,
        name="Casual",
        code="CASUAL_CHK",
        category=LeaveCategory.CASUAL,
    )
    db_session.add(leave_type)
    await db_session.flush()

    # Invalid: end_date (Dec 1) is before start_date (Dec 5)
    invalid_leave = LeaveRequest(
        organization_id=org.id,
        employee_id=emp.id,
        leave_type_id=leave_type.id,
        start_date=date(2026, 12, 5),
        end_date=date(2026, 12, 1),
        total_days=1.0,
        reason="Erroneous dates",
    )
    db_session.add(invalid_leave)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_jsonb_metadata_operations(db_session: AsyncSession):
    org = Organization(
        name="JSONB Org",
        slug="jsonb-org",
        code="JSONB_ORG",
        settings_json={"fiscal_start_month": 4, "tracking_enabled": True, "geofence_meters": 150},
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    assert org.settings_json is not None
    assert org.settings_json["fiscal_start_month"] == 4
    assert org.settings_json["tracking_enabled"] is True


@pytest.mark.asyncio
async def test_seed_data_execution(db_session: AsyncSession):
    # Test seeding permissions
    perm_map = await seed_permissions(db_session)
    assert len(perm_map) >= 20
    assert "attendance:clock_in_out" in perm_map
    assert "leave:requests:approve" in perm_map

    # Test seeding system roles
    role_map = await seed_system_roles(db_session, perm_map)
    assert "Super Administrator" in role_map
    assert "HR Manager" in role_map
    assert "Employee" in role_map

    # Test seeding leave categories for an organization
    org = Organization(name="Seed Test Org", slug="seed-test-org", code="SEED_ORG")
    db_session.add(org)
    await db_session.flush()

    leave_types = await seed_organization_leave_types(db_session, org.id)
    assert len(leave_types) >= 6
    codes = [lt.code for lt in leave_types]
    assert "ANNUAL" in codes
    assert "SICK" in codes
    assert "MATERNITY" in codes
