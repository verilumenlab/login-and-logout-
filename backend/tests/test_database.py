"""
Database Models & Integration Tests for Enterprise Schema
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.attendance import AttendanceDay, AttendanceEvent, AttendanceEventType, AttendanceStatus
from app.models.auth import Role, User
from app.models.device import Device, DeviceSession, OSActivityEvent
from app.models.employee import EmployeeProfile, EmploymentStatus
from app.models.leave import LeaveCategory, LeaveRequest, LeaveStatus, LeaveType
from app.models.organization import Organization


@pytest.mark.asyncio
async def test_organization_and_user_creation(db_session: AsyncSession):
    org = Organization(
        name="Acme Enterprise Corp",
        slug="acme-corp",
        code="ACME",
        settings_json={"timezone": "UTC", "currency": "USD"},
    )
    db_session.add(org)
    await db_session.flush()
    assert isinstance(org.id, uuid.UUID)

    role = Role(
        organization_id=org.id,
        name="Engineer Role",
        description="Engineering staff member",
    )
    db_session.add(role)
    await db_session.flush()

    user = User(
        organization_id=org.id,
        email="engineer@acme.com",
        hashed_password=get_password_hash("SecureP@ss123"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert isinstance(user.id, uuid.UUID)
    assert user.email == "engineer@acme.com"

    # Query back
    result = await db_session.execute(select(User).where(User.email == "engineer@acme.com"))
    fetched = result.scalars().first()
    assert fetched is not None
    assert fetched.organization_id == org.id


@pytest.mark.asyncio
async def test_employee_and_attendance_lifecycle(db_session: AsyncSession):
    org = Organization(name="Attend Corp", slug="attend-corp", code="ATTEND")
    db_session.add(org)
    await db_session.flush()

    role = Role(organization_id=org.id, name="Staff Role")
    db_session.add(role)
    await db_session.flush()

    user = User(
        organization_id=org.id,
        email="att_staff@acme.com",
        hashed_password=get_password_hash("Pass123!"),
        role_id=role.id,
    )
    db_session.add(user)
    await db_session.flush()

    emp = EmployeeProfile(
        organization_id=org.id,
        user_id=user.id,
        employee_code="EMP-1001",
        first_name="Alice",
        last_name="Smith",
        hire_date=date(2025, 1, 15),
        employment_status=EmploymentStatus.ACTIVE,
    )
    db_session.add(emp)
    await db_session.flush()

    today = date(2026, 11, 12)
    now = datetime.now(UTC)

    att_day = AttendanceDay(
        organization_id=org.id,
        employee_id=emp.id,
        work_date=today,
        status=AttendanceStatus.PRESENT,
        shift_start=now,
    )
    db_session.add(att_day)
    await db_session.flush()

    event = AttendanceEvent(
        attendance_day_id=att_day.id,
        event_type=AttendanceEventType.CLOCK_IN,
        timestamp=now,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(att_day)

    assert isinstance(att_day.id, uuid.UUID)
    assert att_day.employee_id == emp.id
    assert att_day.status == AttendanceStatus.PRESENT


@pytest.mark.asyncio
async def test_device_telemetry_lifecycle(db_session: AsyncSession):
    org = Organization(name="Device Corp", slug="device-corp", code="DEV_CORP")
    db_session.add(org)
    await db_session.flush()

    role = Role(organization_id=org.id, name="Dev Role")
    db_session.add(role)
    await db_session.flush()

    user = User(
        organization_id=org.id,
        email="dev_user@acme.com",
        hashed_password=get_password_hash("Pass123!"),
        role_id=role.id,
    )
    db_session.add(user)
    await db_session.flush()

    emp = EmployeeProfile(
        organization_id=org.id,
        user_id=user.id,
        employee_code="DEV-001",
        first_name="Bob",
        last_name="Jones",
        hire_date=date(2025, 2, 1),
    )
    db_session.add(emp)
    await db_session.flush()

    device = Device(
        organization_id=org.id,
        device_identifier="HW-UUID-998877",
        device_name="Bob-Workstation",
        os_name="Windows",
        os_version="11.0",
        platform="win32",
        agent_version="2.0.0",
    )
    db_session.add(device)
    await db_session.flush()

    session = DeviceSession(
        device_id=device.id,
        employee_id=emp.id,
        session_token_hash="hash_token_abc_123",
        start_time=datetime.now(UTC),
    )
    db_session.add(session)
    await db_session.flush()

    event = OSActivityEvent(
        device_session_id=session.id,
        device_event_id=str(uuid.uuid4()),
        application_name="Code",
        window_title="models.py - enterprise",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC),
        duration_seconds=60,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    assert isinstance(event.id, uuid.UUID)
    assert event.application_name == "Code"


@pytest.mark.asyncio
async def test_leave_request_lifecycle(db_session: AsyncSession):
    org = Organization(name="Leave Corp", slug="leave-corp", code="LEAVE_CORP")
    db_session.add(org)
    await db_session.flush()

    role = Role(organization_id=org.id, name="Leave Staff")
    db_session.add(role)
    await db_session.flush()

    user = User(
        organization_id=org.id,
        email="leave_tester@acme.com",
        hashed_password=get_password_hash("Pass123!"),
        role_id=role.id,
    )
    db_session.add(user)
    await db_session.flush()

    emp = EmployeeProfile(
        organization_id=org.id,
        user_id=user.id,
        employee_code="LVE-100",
        first_name="Charlie",
        last_name="Brown",
        hire_date=date(2025, 3, 1),
    )
    db_session.add(emp)
    await db_session.flush()

    leave_type = LeaveType(
        organization_id=org.id,
        name="Annual Vacation",
        code="ANNUAL_TEST",
        category=LeaveCategory.ANNUAL,
        is_paid=True,
    )
    db_session.add(leave_type)
    await db_session.flush()

    leave = LeaveRequest(
        organization_id=org.id,
        employee_id=emp.id,
        leave_type_id=leave_type.id,
        start_date=date(2026, 12, 20),
        end_date=date(2026, 12, 25),
        total_days=5.0,
        reason="Winter vacation",
        status=LeaveStatus.PENDING,
    )
    db_session.add(leave)
    await db_session.commit()
    await db_session.refresh(leave)

    assert isinstance(leave.id, uuid.UUID)
    assert leave.status == LeaveStatus.PENDING
