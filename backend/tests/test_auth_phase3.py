"""
Comprehensive Phase 03 Test Suite:
Authentication, Argon2id Hashing, JWT Tokens, Refresh Token Rotation,
Replay Attack Detection, Session Management, Account Activation, Device Security,
and Strict RBAC & Organizational Scoping (Admin, HR, Manager, Employee).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    decode_access_token,
    get_password_hash,
    verify_password,
)
from app.core.seeds import seed_organization_leave_types, seed_permissions, seed_system_roles
from app.models.attendance import AttendanceDay, AttendanceStatus
from app.models.auth import LoginHistory, PasswordResetToken, Role, User
from app.models.employee import EmployeeProfile, ManagerAssignment
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.notification import EmailOutbox
from app.models.organization import Organization


@pytest.fixture
async def setup_auth_environment(db_session: AsyncSession):
    """
    Seeds permissions, roles, test organization, leave types,
    and 5 distinct user identities:
    1. super_admin
    2. hr_user
    3. manager_user
    4. emp1_user (assigned to manager)
    5. emp2_user (peer, NOT assigned to manager)
    """
    perm_map = await seed_permissions(db_session)
    role_map = await seed_system_roles(db_session, perm_map)

    uid_suffix = uuid.uuid4().hex[:8]

    org = Organization(
        name=f"Titan Tech Corp {uid_suffix}",
        slug=f"titan-tech-{uid_suffix}",
        code=f"TI_{uid_suffix}".upper()[:16],
        settings_json={"timezone": "UTC"},
    )
    db_session.add(org)
    await db_session.flush()

    leave_types = await seed_organization_leave_types(db_session, org.id)
    annual_leave = next(lt for lt in leave_types if lt.code == "ANNUAL")

    admin_email = f"admin_{uid_suffix}@titan.com"
    hr_email = f"hr_{uid_suffix}@titan.com"
    mgr_email = f"manager_{uid_suffix}@titan.com"
    emp1_email = f"emp1_{uid_suffix}@titan.com"
    emp2_email = f"emp2_{uid_suffix}@titan.com"

    # 1. Super Admin User
    admin_user = User(
        organization_id=org.id,
        email=admin_email,
        hashed_password=get_password_hash("AdminPass123!"),
        role_id=role_map["Administrator"].id,
        is_active=True,
        is_superuser=True,
    )
    db_session.add(admin_user)

    # 2. HR User
    hr_user = User(
        organization_id=org.id,
        email=hr_email,
        hashed_password=get_password_hash("HrPass123!"),
        role_id=role_map["HR Manager"].id,
        is_active=True,
    )
    db_session.add(hr_user)

    # 3. Manager User
    mgr_user = User(
        organization_id=org.id,
        email=mgr_email,
        hashed_password=get_password_hash("ManagerPass123!"),
        role_id=role_map["Department Manager"].id,
        is_active=True,
    )
    db_session.add(mgr_user)

    # 4. Employee 1 User (Assigned to Manager)
    emp1_user = User(
        organization_id=org.id,
        email=emp1_email,
        hashed_password=get_password_hash("EmpPass123!"),
        role_id=role_map["Employee"].id,
        is_active=True,
    )
    db_session.add(emp1_user)

    # 5. Employee 2 User (Peer, NOT assigned to Manager)
    emp2_user = User(
        organization_id=org.id,
        email=emp2_email,
        hashed_password=get_password_hash("EmpPass123!"),
        role_id=role_map["Employee"].id,
        is_active=True,
    )
    db_session.add(emp2_user)
    await db_session.flush()

    # Create Employee Profiles
    hr_profile = EmployeeProfile(
        organization_id=org.id,
        user_id=hr_user.id,
        employee_code=f"E-HR-{uid_suffix}"[:20],
        first_name="Helen",
        last_name="HR",
        hire_date=date(2024, 1, 1),
    )
    mgr_profile = EmployeeProfile(
        organization_id=org.id,
        user_id=mgr_user.id,
        employee_code=f"E-MG-{uid_suffix}"[:20],
        first_name="Marcus",
        last_name="Manager",
        hire_date=date(2024, 1, 1),
    )
    emp1_profile = EmployeeProfile(
        organization_id=org.id,
        user_id=emp1_user.id,
        employee_code=f"E-E1-{uid_suffix}"[:20],
        first_name="Edward",
        last_name="One",
        hire_date=date(2024, 1, 1),
    )
    emp2_profile = EmployeeProfile(
        organization_id=org.id,
        user_id=emp2_user.id,
        employee_code=f"E-E2-{uid_suffix}"[:20],
        first_name="Emma",
        last_name="Two",
        hire_date=date(2024, 1, 1),
    )
    db_session.add_all([hr_profile, mgr_profile, emp1_profile, emp2_profile])
    await db_session.flush()

    # Manager Assignment: Manager manages Employee 1 only
    assignment = ManagerAssignment(
        organization_id=org.id,
        employee_id=emp1_profile.id,
        manager_id=mgr_profile.id,
    )
    db_session.add(assignment)

    # Seed initial attendance days for Employee 1 and Employee 2
    today = datetime.now(UTC).date()
    att1 = AttendanceDay(
        organization_id=org.id,
        employee_id=emp1_profile.id,
        work_date=today,
        status=AttendanceStatus.PRESENT,
        shift_start=datetime.now(UTC),
    )
    att2 = AttendanceDay(
        organization_id=org.id,
        employee_id=emp2_profile.id,
        work_date=today,
        status=AttendanceStatus.PRESENT,
        shift_start=datetime.now(UTC),
    )
    db_session.add_all([att1, att2])

    # Seed leave request for Employee 1 and Employee 2
    leave1 = LeaveRequest(
        organization_id=org.id,
        employee_id=emp1_profile.id,
        leave_type_id=annual_leave.id,
        start_date=today + timedelta(days=5),
        end_date=today + timedelta(days=7),
        total_days=3.0,
        reason="Vacation trip",
        status=LeaveStatus.PENDING,
    )
    leave2 = LeaveRequest(
        organization_id=org.id,
        employee_id=emp2_profile.id,
        leave_type_id=annual_leave.id,
        start_date=today + timedelta(days=10),
        end_date=today + timedelta(days=12),
        total_days=3.0,
        reason="Personal leave",
        status=LeaveStatus.PENDING,
    )
    db_session.add_all([leave1, leave2])
    await db_session.commit()

    return {
        "org": org,
        "admin_user": admin_user,
        "hr_user": hr_user,
        "mgr_user": mgr_user,
        "emp1_user": emp1_user,
        "emp2_user": emp2_user,
        "admin_email": admin_email,
        "hr_email": hr_email,
        "mgr_email": mgr_email,
        "emp1_email": emp1_email,
        "emp2_email": emp2_email,
        "mgr_profile": mgr_profile,
        "emp1_profile": emp1_profile,
        "emp2_profile": emp2_profile,
        "leave1": leave1,
        "leave2": leave2,
        "annual_leave": annual_leave,
    }


# ============================================================================
# 1. Argon2id Password Hashing Tests
# ============================================================================


def test_argon2id_hashing_format_and_verification():
    raw_pass = "EnterpriseS3cur3!@#"
    hashed = get_password_hash(raw_pass)

    # Verify Argon2id specification parameters
    assert hashed.startswith("$argon2id$")
    assert "m=65536,t=3,p=4" in hashed
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPassword123", hashed) is False
    assert verify_password("", hashed) is False


# ============================================================================
# 2. Authentication Flow & Token Issuance Tests
# ============================================================================


@pytest.mark.asyncio
async def test_successful_login_returns_tokens_and_rbac_info(
    client: AsyncClient,
    setup_auth_environment: dict,
):
    email = setup_auth_environment["emp1_email"]
    web_res = await client.post("/api/v1/auth/login", json={"email": email, "password": "EmpPass123!"})
    assert web_res.status_code == 403
    assert "desktop app" in web_res.json()["detail"]
    token_res = await client.post("/api/v1/auth/token", data={"username": email, "password": "EmpPass123!"})
    assert token_res.status_code == 403

    res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "EmpPass123!", "client_type": "desktop"},
    )
    assert res.status_code == 200
    data = res.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0

    user_info = data["user"]
    assert user_info["email"] == email
    assert user_info["role"] == "Employee"
    assert "attendance:clock_in_out" in user_info["permissions"]
    assert "leave:requests:create" in user_info["permissions"]

    # Validate access token claims
    payload = decode_access_token(data["access_token"])
    assert payload is not None
    assert payload["sub"] == str(user_info["id"])
    assert payload["role"] == "Employee"


@pytest.mark.asyncio
async def test_incorrect_password_fails_and_audits_attempt(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_auth_environment: dict,
):
    email = setup_auth_environment["emp1_email"]
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword!"},
    )
    assert res.status_code == 401
    assert "Incorrect email or password" in res.json()["detail"]

    # Verify login history audit log
    stmt = select(LoginHistory).where(LoginHistory.email == email).order_by(LoginHistory.created_at.desc())
    history = (await db_session.execute(stmt)).scalars().first()
    assert history is not None
    assert history.is_success is False
    assert "Incorrect password" in history.failure_reason


# ============================================================================
# 3. Brute-Force Lockout Protection Tests
# ============================================================================


@pytest.mark.asyncio
async def test_brute_force_lockout_after_five_attempts(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_auth_environment: dict,
):
    email = setup_auth_environment["emp1_email"]

    # Attempts 1 to 4 should return 401
    for _ in range(4):
        res = await client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword"})
        assert res.status_code == 401

    # Attempt 5: triggers lockout
    res5 = await client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword"})
    assert res5.status_code == 401

    # Attempt 6: returns 429 Too Many Requests (Account is locked)
    res6 = await client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword"})
    assert res6.status_code == 429
    assert "Account is temporarily locked" in res6.json()["detail"]

    # Even providing the correct password while locked must be blocked
    res_correct = await client.post("/api/v1/auth/login", json={"email": email, "password": "EmpPass123!"})
    assert res_correct.status_code == 429


# ============================================================================
# 4. Refresh Token Rotation & Replay Attack Detection Tests
# ============================================================================


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_replay_detection(
    client: AsyncClient,
    setup_auth_environment: dict,
):
    email = setup_auth_environment["hr_email"]

    # 1. Initial Login
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "HrPass123!"},
    )
    assert login_res.status_code == 200
    token_1 = login_res.json()["refresh_token"]

    # 2. Legitimate Refresh -> Token 1 rotates to Token 2
    refresh_res = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token_1},
    )
    assert refresh_res.status_code == 200
    token_2 = refresh_res.json()["refresh_token"]
    assert token_2 != token_1

    # 3. Legitimate Refresh -> Token 2 rotates to Token 3
    refresh_res2 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token_2},
    )
    assert refresh_res2.status_code == 200
    token_3 = refresh_res2.json()["refresh_token"]
    assert token_3 != token_2

    # 4. REPLAY ATTACK: Attacker replays already-used Token 1
    replay_res = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token_1},
    )
    assert replay_res.status_code == 401
    assert "Token reuse detected" in replay_res.json()["detail"]

    # 5. VERIFY REPLAY DEFENSE: Legitimate Token 3 is now revoked because family was compromised!
    compromised_res = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token_3},
    )
    assert compromised_res.status_code == 401


# ============================================================================
# 5. Session Management & Remote Revocation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_active_session_listing_and_revocation(
    client: AsyncClient,
    setup_auth_environment: dict,
):
    email = setup_auth_environment["admin_email"]

    # Login to create session
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "AdminPass123!", "device_name": "MacBook Pro"},
    )
    tokens = login_res.json()
    auth_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # List active sessions
    sessions_res = await client.get("/api/v1/auth/sessions", headers=auth_headers)
    assert sessions_res.status_code == 200
    sessions = sessions_res.json()
    assert len(sessions) >= 1
    session_id = sessions[0]["id"]

    # Revoke single session
    del_res = await client.delete(f"/api/v1/auth/sessions/{session_id}", headers=auth_headers)
    assert del_res.status_code == 200
    assert "Session revoked successfully" in del_res.json()["message"]

    # Refreshing with the revoked session's token should now fail
    ref_res = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert ref_res.status_code == 401


# ============================================================================
# 6. Forgot Password, Email Outbox & OTP Reset Flow Tests
# ============================================================================


@pytest.mark.asyncio
async def test_forgot_password_and_otp_reset_flow(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_auth_environment: dict,
):
    email = setup_auth_environment["emp1_email"]

    # 1. Request forgot password: secrets must only be delivered by email, never in the response
    forgot_res = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert forgot_res.status_code == 200
    body = forgot_res.json()
    assert "otp_code" not in body and "reset_token" not in body

    user_id = setup_auth_environment["emp1_user"].id
    reset_entry = (
        await db_session.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == user_id))
    ).scalars().first()
    assert reset_entry is not None
    otp_code = reset_entry.otp_code
    assert otp_code is not None and len(otp_code) == 6

    # 2. Check that an EmailOutbox message was generated
    outbox_stmt = select(EmailOutbox).where(EmailOutbox.recipient_email == email)
    outbox_msg = (await db_session.execute(outbox_stmt)).scalars().first()
    assert outbox_msg is not None
    assert otp_code in outbox_msg.body_html

    new_password = "BrandNewSecurePassword123!"

    # 3. A bare OTP without the account email must be rejected
    unscoped_res = await client.post(
        "/api/v1/auth/reset-password",
        json={"token_or_otp": otp_code, "new_password": new_password},
    )
    assert unscoped_res.status_code == 400

    # 4. The OTP must not work for a different account
    wrong_account_res = await client.post(
        "/api/v1/auth/reset-password",
        json={"token_or_otp": otp_code, "new_password": new_password, "email": setup_auth_environment["emp2_email"]},
    )
    assert wrong_account_res.status_code == 400

    # 5. Reset password using 6-digit OTP scoped to the account
    reset_res = await client.post(
        "/api/v1/auth/reset-password",
        json={"token_or_otp": otp_code, "new_password": new_password, "email": email},
    )
    assert reset_res.status_code == 200
    assert "Password reset successfully" in reset_res.json()["message"]

    # 6. Old password must fail
    old_login = await client.post("/api/v1/auth/login", json={"email": email, "password": "EmpPass123!"})
    assert old_login.status_code == 401

    # 7. New password succeeds
    new_login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": new_password, "client_type": "desktop"}
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_register_requires_admin_and_blocks_privilege_escalation(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_auth_environment: dict,
):
    org = setup_auth_environment["org"]
    admin_role = (
        await db_session.execute(select(Role).where(Role.name == "Administrator", Role.organization_id.is_(None)))
    ).scalars().first()
    employee_role_id = setup_auth_environment["emp1_user"].role_id

    def new_user(**overrides):
        body = {
            "email": f"new_{uuid.uuid4().hex[:8]}@titan.com",
            "password": "NewUserPass123!",
            "organization_id": str(org.id),
            "role_id": str(employee_role_id),
        }
        body.update(overrides)
        return body

    # Anonymous callers cannot register accounts, let alone superusers
    anon_res = await client.post("/api/v1/auth/register", json=new_user(is_superuser=True, role_id=str(admin_role.id)))
    assert anon_res.status_code == 401

    # Non-admin roles are rejected
    hr_login = await client.post(
        "/api/v1/auth/login", json={"email": setup_auth_environment["hr_email"], "password": "HrPass123!"}
    )
    hr_headers = {"Authorization": f"Bearer {hr_login.json()['access_token']}"}
    hr_res = await client.post("/api/v1/auth/register", json=new_user(), headers=hr_headers)
    assert hr_res.status_code == 403

    # A non-superuser administrator is confined to their org and cannot mint superusers
    org_admin = User(
        organization_id=org.id,
        email=f"orgadmin_{uuid.uuid4().hex[:8]}@titan.com",
        hashed_password=get_password_hash("OrgAdminPass123!"),
        role_id=admin_role.id,
        is_active=True,
        is_superuser=False,
    )
    db_session.add(org_admin)
    await db_session.flush()
    admin_login = await client.post(
        "/api/v1/auth/login", json={"email": org_admin.email, "password": "OrgAdminPass123!"}
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    escalate_res = await client.post("/api/v1/auth/register", json=new_user(is_superuser=True), headers=admin_headers)
    assert escalate_res.status_code == 403

    cross_org_res = await client.post(
        "/api/v1/auth/register", json=new_user(organization_id=str(uuid.uuid4())), headers=admin_headers
    )
    assert cross_org_res.status_code == 403

    bad_role_res = await client.post("/api/v1/auth/register", json=new_user(role_id=str(uuid.uuid4())), headers=admin_headers)
    assert bad_role_res.status_code == 400

    ok_res = await client.post("/api/v1/auth/register", json=new_user(), headers=admin_headers)
    assert ok_res.status_code == 201
    assert ok_res.json()["is_superuser"] is False


@pytest.mark.asyncio
async def test_rate_limit_ignores_spoofed_x_forwarded_for(client: AsyncClient):
    email = f"nobody_{uuid.uuid4().hex[:8]}@titan.com"
    last = None
    for i in range(6):
        last = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": email},
            headers={"x-enforce-rate-limit": "true", "x-forwarded-for": f"203.0.113.{i}"},
        )
    assert last is not None and last.status_code == 429


# ============================================================================
# 7. Account Activation / Deactivation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_account_activation_and_deactivation_lifecycle(
    client: AsyncClient,
    setup_auth_environment: dict,
):
    admin = setup_auth_environment["admin_user"]
    emp = setup_auth_environment["emp2_user"]

    # Admin logins
    admin_login = await client.post("/api/v1/auth/login", json={"email": admin.email, "password": "AdminPass123!"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    # Employee logins before deactivation
    emp_login = await client.post(
        "/api/v1/auth/login", json={"email": emp.email, "password": "EmpPass123!", "client_type": "desktop"}
    )
    assert emp_login.status_code == 200
    emp_token = emp_login.json()["access_token"]
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Employee verifies active access
    me_res = await client.get("/api/v1/auth/me", headers=emp_headers)
    assert me_res.status_code == 200

    # Admin deactivates employee account
    deact_res = await client.post(
        f"/api/v1/auth/users/{emp.id}/status",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False

    # Deactivated employee immediately blocked from accessing protected routes
    blocked_me = await client.get("/api/v1/auth/me", headers=emp_headers)
    assert blocked_me.status_code == 403

    # Deactivated employee immediately blocked from new login
    blocked_login = await client.post("/api/v1/auth/login", json={"email": emp.email, "password": "EmpPass123!"})
    assert blocked_login.status_code == 403
    assert "Account is deactivated" in blocked_login.json()["detail"]


# ============================================================================
# 8. Device Authentication & Hardware Blocking Tests
# ============================================================================


@pytest.mark.asyncio
async def test_device_enrollment_and_administrative_blocking(
    client: AsyncClient,
    setup_auth_environment: dict,
):
    admin = setup_auth_environment["admin_user"]
    emp = setup_auth_environment["emp1_user"]

    admin_login = await client.post("/api/v1/auth/login", json={"email": admin.email, "password": "AdminPass123!"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    emp_login = await client.post(
        "/api/v1/auth/login", json={"email": emp.email, "password": "EmpPass123!", "client_type": "desktop"}
    )
    emp_headers = {"Authorization": f"Bearer {emp_login.json()['access_token']}"}

    # Desktop client enrolls workstation
    device_id_str = "HW-DESKTOP-99214A"
    auth_dev = await client.post(
        "/api/v1/auth/devices/authenticate",
        headers=emp_headers,
        json={
            "device_identifier": device_id_str,
            "device_name": "Workstation Dell XPS",
            "os_name": "Windows",
            "os_version": "11 Pro",
            "platform": "x86_64",
            "agent_version": "2.4.0",
        },
    )
    assert auth_dev.status_code == 200
    dev_data = auth_dev.json()
    assert dev_data["is_blocked"] is False
    db_device_id = dev_data["device_id"]

    # Admin blocks device
    block_res = await client.post(f"/api/v1/auth/devices/{db_device_id}/block", headers=admin_headers)
    assert block_res.status_code == 200

    # Workstation attempts authentication while blocked -> 403 Forbidden
    blocked_dev_auth = await client.post(
        "/api/v1/auth/devices/authenticate",
        headers=emp_headers,
        json={
            "device_identifier": device_id_str,
            "device_name": "Workstation Dell XPS",
            "os_name": "Windows",
            "os_version": "11 Pro",
            "platform": "x86_64",
            "agent_version": "2.4.0",
        },
    )
    assert blocked_dev_auth.status_code == 403
    assert "Device has been blocked" in blocked_dev_auth.json()["detail"]

    # Login attempt from blocked device identifier is also rejected
    blocked_login = await client.post(
        "/api/v1/auth/login",
        json={"email": emp.email, "password": "EmpPass123!", "device_identifier": device_id_str, "client_type": "desktop"},
    )
    assert blocked_login.status_code == 403
    assert "blocked by an administrator" in blocked_login.json()["detail"]


# ============================================================================
# 9. Strict RBAC & Organizational Scoping Tests
# Roles: Super Admin, HR, Manager, Employee
# Rules:
# - Admin: full organization access
# - HR: employee, attendance, leave, reporting access
# - Manager: assigned employees only
# - Employee: own records only
# ============================================================================


@pytest.mark.asyncio
async def test_rbac_admin_full_access(
    client: AsyncClient,
    setup_auth_environment: dict,
):
    admin = setup_auth_environment["admin_user"]
    emp1 = setup_auth_environment["emp1_profile"]
    emp2 = setup_auth_environment["emp2_profile"]
    leave1 = setup_auth_environment["leave1"]

    login = await client.post("/api/v1/auth/login", json={"email": admin.email, "password": "AdminPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Admin can view attendance for employee 1 and employee 2
    r1 = await client.get(f"/api/v1/attendance/employee/{emp1.id}", headers=headers)
    assert r1.status_code == 200
    r2 = await client.get(f"/api/v1/attendance/employee/{emp2.id}", headers=headers)
    assert r2.status_code == 200

    # Admin can view leaves for employee 1 and employee 2
    l1 = await client.get(f"/api/v1/leave/employee/{emp1.id}", headers=headers)
    assert l1.status_code == 200
    l2 = await client.get(f"/api/v1/leave/employee/{emp2.id}", headers=headers)
    assert l2.status_code == 200

    # Admin can approve leave requests
    appr = await client.post(f"/api/v1/leave/{leave1.id}/approve", headers=headers)
    assert appr.status_code == 200
    assert appr.json()["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_rbac_hr_organization_wide_access(
    client: AsyncClient,
    setup_auth_environment: dict,
):
    hr = setup_auth_environment["hr_user"]
    emp1 = setup_auth_environment["emp1_profile"]
    emp2 = setup_auth_environment["emp2_profile"]
    leave2 = setup_auth_environment["leave2"]

    login = await client.post("/api/v1/auth/login", json={"email": hr.email, "password": "HrPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # HR can inspect any employee's attendance and leaves in the company
    r1 = await client.get(f"/api/v1/attendance/employee/{emp1.id}", headers=headers)
    assert r1.status_code == 200
    r2 = await client.get(f"/api/v1/attendance/employee/{emp2.id}", headers=headers)
    assert r2.status_code == 200

    l1 = await client.get(f"/api/v1/leave/employee/{emp1.id}", headers=headers)
    assert l1.status_code == 200
    l2 = await client.get(f"/api/v1/leave/employee/{emp2.id}", headers=headers)
    assert l2.status_code == 200

    # HR can approve leave
    appr = await client.post(f"/api/v1/leave/{leave2.id}/approve", headers=headers)
    assert appr.status_code == 200
    assert appr.json()["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_rbac_manager_assigned_reports_only(
    client: AsyncClient,
    setup_auth_environment: dict,
):
    mgr = setup_auth_environment["mgr_user"]
    emp1 = setup_auth_environment["emp1_profile"]  # Assigned to manager
    emp2 = setup_auth_environment["emp2_profile"]  # NOT assigned to manager
    leave1 = setup_auth_environment["leave1"]
    leave2 = setup_auth_environment["leave2"]

    login = await client.post("/api/v1/auth/login", json={"email": mgr.email, "password": "ManagerPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Manager CAN access assigned subordinate (emp1)
    r1 = await client.get(f"/api/v1/attendance/employee/{emp1.id}", headers=headers)
    assert r1.status_code == 200

    l1 = await client.get(f"/api/v1/leave/employee/{emp1.id}", headers=headers)
    assert l1.status_code == 200

    # Manager CAN approve assigned subordinate's leave
    appr1 = await client.post(f"/api/v1/leave/{leave1.id}/approve", headers=headers)
    assert appr1.status_code == 200
    assert appr1.json()["status"] == "APPROVED"

    # ================= UNAUTHORIZED MANAGER ACCESS TESTS =================
    # Manager CANNOT access unassigned employee (emp2) attendance
    unauth_att = await client.get(f"/api/v1/attendance/employee/{emp2.id}", headers=headers)
    assert unauth_att.status_code == 403
    assert "Access denied" in unauth_att.json()["detail"]

    # Manager CANNOT access unassigned employee (emp2) leave
    unauth_leave = await client.get(f"/api/v1/leave/employee/{emp2.id}", headers=headers)
    assert unauth_leave.status_code == 403
    assert "Access denied" in unauth_leave.json()["detail"]

    # Manager CANNOT approve unassigned employee (emp2) leave
    unauth_appr = await client.post(f"/api/v1/leave/{leave2.id}/approve", headers=headers)
    assert unauth_appr.status_code == 403
    assert "assigned team members" in unauth_appr.json()["detail"]


@pytest.mark.asyncio
async def test_rbac_employee_own_records_only(
    client: AsyncClient,
    setup_auth_environment: dict,
):
    emp1 = setup_auth_environment["emp1_user"]
    emp1_prof = setup_auth_environment["emp1_profile"]
    emp2_prof = setup_auth_environment["emp2_profile"]
    leave1 = setup_auth_environment["leave1"]

    login = await client.post(
        "/api/v1/auth/login", json={"email": emp1.email, "password": "EmpPass123!", "client_type": "desktop"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Employee CAN access own attendance and leaves
    own_att = await client.get(f"/api/v1/attendance/employee/{emp1_prof.id}", headers=headers)
    assert own_att.status_code == 200

    own_leaves = await client.get(f"/api/v1/leave/employee/{emp1_prof.id}", headers=headers)
    assert own_leaves.status_code == 200

    # ================= UNAUTHORIZED EMPLOYEE ACCESS TESTS =================
    # Employee CANNOT access peer's attendance (403 Forbidden)
    peer_att = await client.get(f"/api/v1/attendance/employee/{emp2_prof.id}", headers=headers)
    assert peer_att.status_code == 403
    assert "Access denied" in peer_att.json()["detail"]

    # Employee CANNOT access peer's leaves (403 Forbidden)
    peer_leave = await client.get(f"/api/v1/leave/employee/{emp2_prof.id}", headers=headers)
    assert peer_leave.status_code == 403
    assert "Access denied" in peer_leave.json()["detail"]

    # Employee CANNOT approve leaves (403 Forbidden)
    unauth_appr = await client.post(f"/api/v1/leave/{leave1.id}/approve", headers=headers)
    assert unauth_appr.status_code == 403

    # Employee CANNOT toggle account status (403 Forbidden)
    unauth_toggle = await client.post(
        f"/api/v1/auth/users/{emp1.id}/status",
        headers=headers,
        json={"is_active": False},
    )
    assert unauth_toggle.status_code == 403
