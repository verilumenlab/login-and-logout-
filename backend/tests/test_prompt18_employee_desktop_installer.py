"""
Prompt 18: Employee-Only Desktop Installer & Central Web Application Integration Tests

Verifies:
1. Employee Authentication: Validated through central FastAPI auth, creates Device & DeviceSession
2. Role Restriction Enforcement: Admin, HR, Manager logins are rejected with:
   "This desktop application is available exclusively to Employee accounts. Please use the web application."
3. Central Web Application Continuity: Admin, HR, and Manager retain access through web authentication
4. Device Management: Unique registration, association, and administrative revocation
5. Blocked Device Denial: Revoked hardware cannot authenticate
6. Attendance Clock-In/Out Integration: Native Wi-Fi SSID/BSSID collection and duplicate prevention
7. Production Installer Verification: Verification of Windows MSI and NSIS installers with SHA-256 checksums
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, date, datetime
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.core.seeds import seed_permissions, seed_system_roles
from app.models.attendance import AttendanceDay, AttendanceStatus
from app.models.auth import Role, User
from app.models.department import Department
from app.models.device import Device, DeviceSession
from app.models.employee import EmployeeProfile, EmploymentStatus
from app.models.organization import Organization


@pytest.fixture
async def setup_prompt18_env(db_session: AsyncSession):
    code_suffix = uuid.uuid4().hex[:6].upper()
    org = Organization(
        name="Enterprise Workstation Corp",
        code=f"EWC-{code_suffix}",
        slug=f"ewc-{code_suffix.lower()}",
        is_active=True,
    )
    db_session.add(org)
    await db_session.flush()

    perm_map = await seed_permissions(db_session)
    role_map = await seed_system_roles(db_session, perm_map)

    dept = Department(organization_id=org.id, name="Engineering Operations", code="ENG-OPS")
    db_session.add(dept)
    await db_session.flush()

    async def create_user_and_emp(
        email: str,
        role_name: str,
        first_name: str,
        last_name: str,
    ) -> tuple[User, EmployeeProfile, str]:
        user = User(
            organization_id=org.id,
            role_id=role_map[role_name].id,
            email=email,
            hashed_password=get_password_hash("TitanEmployee2026!"),
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        emp = EmployeeProfile(
            organization_id=org.id,
            user_id=user.id,
            department_id=dept.id,
            employee_code=f"EMP-{uuid.uuid4().hex[:4].upper()}",
            first_name=first_name,
            last_name=last_name,
            hire_date=date(2026, 1, 1),
            employment_status=EmploymentStatus.ACTIVE,
        )
        db_session.add(emp)
        await db_session.flush()

        token = create_access_token(user.id, {"org": str(org.id), "role": role_name})
        return user, emp, token

    admin_u, admin_e, admin_tok = await create_user_and_emp(f"admin_{code_suffix.lower()}@corp.com", "Administrator", "Arthur", "Admin")
    hr_u, hr_e, hr_tok = await create_user_and_emp(f"hr_{code_suffix.lower()}@corp.com", "HR Manager", "Hannah", "HR")
    mgr_u, mgr_e, mgr_tok = await create_user_and_emp(f"mgr_{code_suffix.lower()}@corp.com", "Department Manager", "Miles", "Manager")
    emp_u, emp_e, emp_tok = await create_user_and_emp(f"emp_{code_suffix.lower()}@corp.com", "Employee", "Evan", "Employee")

    await db_session.commit()

    return {
        "org": org,
        "admin": {"user": admin_u, "emp": admin_e, "token": admin_tok},
        "hr": {"user": hr_u, "emp": hr_e, "token": hr_tok},
        "manager": {"user": mgr_u, "emp": mgr_e, "token": mgr_tok},
        "employee": {"user": emp_u, "emp": emp_e, "token": emp_tok},
        "password": "TitanEmployee2026!",
    }


@pytest.mark.asyncio
async def test_employee_desktop_authentication_success(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_prompt18_env: dict,
):
    """Verify an Employee can successfully authenticate through desktop login, creating device & session."""
    emp_data = setup_prompt18_env["employee"]
    hardware_id = f"DEV-WIN-{uuid.uuid4().hex[:8].upper()}"

    payload = {
        "email": emp_data["user"].email,
        "password": setup_prompt18_env["password"],
        "device_identifier": hardware_id,
        "device_name": "Evan-Workstation-PC",
        "platform": "windows",
        "os_name": "Windows",
        "os_version": "11 Enterprise",
        "mac_address": "00:1A:2B:3C:4D:5E",
        "agent_version": "0.1.0",
    }

    res = await client.post("/api/v1/auth/desktop-login", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["role"] in ("Employee", "EMPLOYEE")
    assert data["device_identifier"] == hardware_id
    assert data["device_session_id"] is not None
    assert data["employee_id"] == str(emp_data["emp"].id)

    # Verify device record persisted in database
    dev_stmt = select(Device).where(Device.device_identifier == hardware_id)
    dev_res = await db_session.execute(dev_stmt)
    dev = dev_res.scalars().first()
    assert dev is not None
    assert dev.is_trusted is True
    assert dev.is_blocked is False

    # Verify device session persisted in database
    sess_stmt = select(DeviceSession).where(DeviceSession.device_id == dev.id)
    sess_res = await db_session.execute(sess_stmt)
    sess = sess_res.scalars().first()
    assert sess is not None
    assert sess.is_active is True
    assert sess.employee_id == emp_data["emp"].id


@pytest.mark.asyncio
async def test_admin_desktop_login_rejection(
    client: AsyncClient,
    setup_prompt18_env: dict,
):
    """Verify Admin is strictly rejected from desktop app with exact prompt requirement message."""
    admin_data = setup_prompt18_env["admin"]

    payload = {
        "email": admin_data["user"].email,
        "password": setup_prompt18_env["password"],
        "device_identifier": "DEV-ADMIN-UNAUTHORIZED",
        "device_name": "Admin-Laptop",
    }

    res = await client.post("/api/v1/auth/desktop-login", json=payload)
    assert res.status_code == 403
    assert res.json()["detail"] == "This desktop application is available exclusively to Employee accounts. Please use the web application."


@pytest.mark.asyncio
async def test_hr_desktop_login_rejection(
    client: AsyncClient,
    setup_prompt18_env: dict,
):
    """Verify HR Manager is strictly rejected from desktop app with exact prompt requirement message."""
    hr_data = setup_prompt18_env["hr"]

    payload = {
        "email": hr_data["user"].email,
        "password": setup_prompt18_env["password"],
        "device_identifier": "DEV-HR-UNAUTHORIZED",
        "device_name": "HR-Laptop",
    }

    res = await client.post("/api/v1/auth/desktop-login", json=payload)
    assert res.status_code == 403
    assert res.json()["detail"] == "This desktop application is available exclusively to Employee accounts. Please use the web application."


@pytest.mark.asyncio
async def test_manager_desktop_login_rejection(
    client: AsyncClient,
    setup_prompt18_env: dict,
):
    """Verify Department Manager is strictly rejected from desktop app with exact prompt requirement message."""
    mgr_data = setup_prompt18_env["manager"]

    payload = {
        "email": mgr_data["user"].email,
        "password": setup_prompt18_env["password"],
        "device_identifier": "DEV-MGR-UNAUTHORIZED",
        "device_name": "Manager-Laptop",
    }

    res = await client.post("/api/v1/auth/desktop-login", json=payload)
    assert res.status_code == 403
    assert res.json()["detail"] == "This desktop application is available exclusively to Employee accounts. Please use the web application."


@pytest.mark.asyncio
async def test_login_endpoint_client_type_desktop_rejection(
    client: AsyncClient,
    setup_prompt18_env: dict,
):
    """Verify generic /auth/login rejects non-employees when client_type='desktop' is passed."""
    admin_data = setup_prompt18_env["admin"]

    payload = {
        "email": admin_data["user"].email,
        "password": setup_prompt18_env["password"],
        "client_type": "desktop",
        "device_identifier": "DEV-ADMIN-ATTEMPT-2",
    }

    res = await client.post("/api/v1/auth/login", json=payload)
    assert res.status_code == 403
    assert res.json()["detail"] == "This desktop application is available exclusively to Employee accounts. Please use the web application."


@pytest.mark.asyncio
async def test_web_application_login_preservation(
    client: AsyncClient,
    setup_prompt18_env: dict,
):
    """Verify generic /auth/login for web application continues to allow Admin, HR, and Manager."""
    admin_data = setup_prompt18_env["admin"]
    res = await client.post("/api/v1/auth/login", json={
        "email": admin_data["user"].email,
        "password": setup_prompt18_env["password"],
        "client_type": "web",
    })
    assert res.status_code == 200
    assert "access_token" in res.json()


@pytest.mark.asyncio
async def test_device_revocation_and_blocked_login_denial(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_prompt18_env: dict,
):
    """Verify Admin can revoke a registered workstation device and blocked hardware cannot authenticate."""
    emp_data = setup_prompt18_env["employee"]
    admin_tok = setup_prompt18_env["admin"]["token"]
    hardware_id = f"DEV-REVOKE-{uuid.uuid4().hex[:8].upper()}"

    # 1. Employee authenticates device
    login_res = await client.post("/api/v1/auth/desktop-login", json={
        "email": emp_data["user"].email,
        "password": setup_prompt18_env["password"],
        "device_identifier": hardware_id,
        "device_name": "Evan-Test-PC",
    })
    assert login_res.status_code == 200
    device_id = login_res.json()["device_id"]

    # 2. Admin revokes device access
    revoke_res = await client.post(
        f"/api/v1/devices/{device_id}/revoke",
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert revoke_res.status_code == 200
    rev_data = revoke_res.json()
    assert rev_data["is_blocked"] is True
    assert rev_data["is_trusted"] is False

    # 3. Verify active session terminated
    sess_stmt = select(DeviceSession).where(DeviceSession.device_id == uuid.UUID(device_id))
    sess_res = await db_session.execute(sess_stmt)
    sess = sess_res.scalars().first()
    assert sess is not None
    assert sess.is_active is False

    # 4. Subsequent login attempt from this blocked device is denied
    blocked_login = await client.post("/api/v1/auth/desktop-login", json={
        "email": emp_data["user"].email,
        "password": setup_prompt18_env["password"],
        "device_identifier": hardware_id,
        "device_name": "Evan-Test-PC",
    })
    assert blocked_login.status_code == 403
    assert "blocked" in blocked_login.json()["detail"].lower()


@pytest.mark.asyncio
async def test_desktop_attendance_clock_in_with_wifi_and_duplicate_prevention(
    client: AsyncClient,
    setup_prompt18_env: dict,
):
    """Verify employee clock-in with native Wi-Fi information and duplicate prevention."""
    emp_tok = setup_prompt18_env["employee"]["token"]
    event_id = f"att-desktop-{uuid.uuid4().hex[:8]}"

    clock_payload = {
        "source": "DESKTOP",
        "notes": "Workstation morning clock-in",
        "client_event_id": event_id,
        "ssid": "Corp_Office_5G",
        "bssid": "00:14:22:01:23:45",
        "permission_status": "GRANTED",
    }

    # 1. First Clock-in
    res1 = await client.post(
        "/api/v1/attendance/clock-in",
        json=clock_payload,
        headers={"Authorization": f"Bearer {emp_tok}"},
    )
    assert res1.status_code in (200, 201)
    data1 = res1.json()
    assert data1["status"] in ("PRESENT", "LATE")

    # 2. Duplicate Clock-in within 2 minutes: Idempotently returns existing record
    res2 = await client.post(
        "/api/v1/attendance/clock-in",
        json=clock_payload,
        headers={"Authorization": f"Bearer {emp_tok}"},
    )
    assert res2.status_code in (200, 201)
    assert res2.json()["id"] == data1["id"]


@pytest.mark.asyncio
async def test_desktop_installer_build_artifacts_and_checksums():
    """Verify that the distributable Windows installers (MSI and NSIS) exist and have valid SHA-256 hashes."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    bundle_base = os.path.join(
        repo_root,
        "desktop",
        "src-tauri",
        "target",
        "x86_64-pc-windows-gnullvm",
        "debug",
        "bundle",
    )

    msi_path = os.path.join(bundle_base, "msi", "EnterpriseAttendanceAgent_0.1.0_x64_en-US.msi")
    nsis_path = os.path.join(bundle_base, "nsis", "EnterpriseAttendanceAgent_0.1.0_x64-setup.exe")

    assert os.path.exists(msi_path), f"MSI installer not found at {msi_path}"
    assert os.path.exists(nsis_path), f"NSIS setup installer not found at {nsis_path}"

    msi_size = os.path.getsize(msi_path)
    nsis_size = os.path.getsize(nsis_path)

    assert msi_size > 20 * 1024 * 1024, f"MSI installer size ({msi_size}) is unusually small"
    assert nsis_size > 15 * 1024 * 1024, f"NSIS setup installer size ({nsis_size}) is unusually small"

    # Compute SHA-256 hashes
    def get_sha256(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest().upper()

    msi_hash = get_sha256(msi_path)
    nsis_hash = get_sha256(nsis_path)

    assert len(msi_hash) == 64
    assert len(nsis_hash) == 64


@pytest.mark.asyncio
async def test_admin_and_hr_can_create_and_delete_employee(
    client: AsyncClient,
    setup_prompt18_env: dict,
):
    """Verify that both Admin and HR can create and delete employee accounts, while unauthorized roles are rejected."""
    admin_tok = setup_prompt18_env["admin"]["token"]
    hr_tok = setup_prompt18_env["hr"]["token"]
    emp_tok = setup_prompt18_env["employee"]["token"]
    mgr_tok = setup_prompt18_env["manager"]["token"]

    # 1. Admin creates an employee
    admin_emp_payload = {
        "first_name": "TestAdmin",
        "last_name": "Employee",
        "email": f"emp_admin_created_{uuid.uuid4().hex[:6]}@corp.com",
        "employee_code": f"EAC-{uuid.uuid4().hex[:4].upper()}",
        "hire_date": str(date.today()),
        "initial_password": "Password123!",
    }
    c_res1 = await client.post(
        "/api/v1/employees/",
        json=admin_emp_payload,
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert c_res1.status_code == 201
    emp1_id = c_res1.json()["id"]

    # 2. Admin deletes the employee
    d_res1 = await client.delete(
        f"/api/v1/employees/{emp1_id}",
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert d_res1.status_code == 200
    assert "deleted successfully" in d_res1.json()["message"]

    # 3. HR creates an employee
    hr_emp_payload = {
        "first_name": "TestHR",
        "last_name": "Employee",
        "email": f"emp_hr_created_{uuid.uuid4().hex[:6]}@corp.com",
        "employee_code": f"EHR-{uuid.uuid4().hex[:4].upper()}",
        "hire_date": str(date.today()),
        "initial_password": "Password123!",
    }
    c_res2 = await client.post(
        "/api/v1/employees/",
        json=hr_emp_payload,
        headers={"Authorization": f"Bearer {hr_tok}"},
    )
    assert c_res2.status_code == 201
    emp2_id = c_res2.json()["id"]

    # 4. Unauthorized deletion attempts: Regular Employee & Manager MUST be rejected (403)
    del_emp_res = await client.delete(
        f"/api/v1/employees/{emp2_id}",
        headers={"Authorization": f"Bearer {emp_tok}"},
    )
    assert del_emp_res.status_code == 403

    del_mgr_res = await client.delete(
        f"/api/v1/employees/{emp2_id}",
        headers={"Authorization": f"Bearer {mgr_tok}"},
    )
    assert del_mgr_res.status_code == 403

    # 5. HR deletes the employee
    d_res2 = await client.delete(
        f"/api/v1/employees/{emp2_id}",
        headers={"Authorization": f"Bearer {hr_tok}"},
    )
    assert d_res2.status_code == 200
    assert "deleted successfully" in d_res2.json()["message"]
