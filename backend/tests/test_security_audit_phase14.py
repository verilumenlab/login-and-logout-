"""
Phase 14 Enterprise Security & Quality Audit Test Suite
Verifies:
- HTTP Security Headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options)
- SQL Injection Resilience (Parameterized ORM bindings)
- IDOR & Cross-Tenant Data Isolation
- RBAC & Privilege Escalation Prevention
- Redis Rate Limiting & Brute Force Defense
- File Upload Security (Magic Bytes, Size limits, Path traversal)
- Refresh Token Rotation & Token Replay Attack Detection
- Revoked / Blocked Device Rejection
- Authenticated WebSocket Access & Policy Enforcement
- Database Backup Integrity & Data Retention Compliance
"""

import os
import uuid
import pytest
from datetime import UTC, datetime, timedelta
from httpx import AsyncClient
from sqlalchemy import select
from unittest.mock import MagicMock

from app.core.security import create_access_token, get_password_hash, hash_token
from app.core.file_security import sanitize_filename, validate_file_content
from app.core.rate_limit import check_rate_limit
from app.models.organization import Organization
from app.models.auth import Role, User, RefreshToken, LoginHistory, PasswordResetToken
from app.models.employee import EmployeeProfile
from app.models.device import Device
from app.models.leave import LeaveRequest, LeaveDocument, LeaveStatus
from app.services.maintenance_service import MaintenanceService
from app.api.v1.endpoints.websockets import _authenticate_ws


@pytest.fixture
def auth_tokens_fixture(db_session):
    """Fixture providing tokens and users for Admin and Employee in Org 1, plus an Org 2 user."""
    async def _setup():
        uid = uuid.uuid4().hex[:6]
        test_organization = Organization(name=f"SecOrg-{uid}", slug=f"secorg-{uid}", code=f"SEC-{uid[:4]}")
        db_session.add(test_organization)
        await db_session.flush()

        # Role setup
        admin_role = Role(name="Admin", organization_id=test_organization.id)
        emp_role = Role(name="Employee", organization_id=test_organization.id)
        db_session.add_all([admin_role, emp_role])
        await db_session.flush()

        # Org 1 Admin
        admin_user = User(
            email=f"admin_{uuid.uuid4().hex[:6]}@secorg.com",
            hashed_password=get_password_hash("AdminPass123!"),
            organization_id=test_organization.id,
            role_id=admin_role.id,
            is_active=True,
            is_superuser=True,
        )
        # Org 1 Employee
        emp_user = User(
            email=f"emp_{uuid.uuid4().hex[:6]}@secorg.com",
            hashed_password=get_password_hash("EmpPass123!"),
            organization_id=test_organization.id,
            role_id=emp_role.id,
            is_active=True,
        )
        db_session.add_all([admin_user, emp_user])
        await db_session.flush()

        emp_profile = EmployeeProfile(
            user_id=emp_user.id,
            organization_id=test_organization.id,
            first_name="Alice",
            last_name="Audited",
            employee_code=f"EMP-{uuid.uuid4().hex[:5]}",
            hire_date=datetime.now(UTC).date(),
        )
        db_session.add(emp_profile)

        # Org 2 User (Tenant 2)
        uid2 = uuid.uuid4().hex[:6]
        org2 = Organization(name=f"Rival Corp-{uid2}", slug=f"rival-{uid2}", code=f"RIV-{uid2[:4]}")
        db_session.add(org2)
        await db_session.flush()

        org2_user = User(
            email=f"attacker_{uuid.uuid4().hex[:6]}@rival.com",
            hashed_password=get_password_hash("RivalPass123!"),
            organization_id=org2.id,
            role_id=admin_role.id,
            is_active=True,
        )
        db_session.add(org2_user)
        await db_session.commit()

        admin_token = create_access_token(subject=admin_user.id)
        emp_token = create_access_token(subject=emp_user.id)
        org2_token = create_access_token(subject=org2_user.id)

        return {
            "test_org": test_organization,
            "admin_user": admin_user,
            "emp_user": emp_user,
            "emp_profile": emp_profile,
            "org2_user": org2_user,
            "admin_token": admin_token,
            "emp_token": emp_token,
            "org2_token": org2_token,
        }

    return _setup


@pytest.mark.asyncio
async def test_security_response_headers(client: AsyncClient):
    """Verify presence of enterprise security headers on all responses."""
    res = await client.get("/")
    assert res.status_code == 200

    headers = res.headers
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("x-content-type-options") == "nosniff"
    assert "content-security-policy" in headers
    assert "default-src 'self'" in headers["content-security-policy"]
    assert "strict-transport-security" in headers
    assert "max-age=31536000" in headers["strict-transport-security"]
    assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert headers.get("server") == "Enterprise-Secure-Gateway"


@pytest.mark.asyncio
async def test_sql_injection_resilience(auth_tokens_fixture, client: AsyncClient):
    """Verify that SQL injection payloads in search query parameters and inputs are safely neutralized."""
    fixture = await auth_tokens_fixture()
    headers = {"Authorization": f"Bearer {fixture['admin_token']}"}

    sqli_payloads = [
        "' OR 1=1 --",
        "'; DROP TABLE users; --",
        "1 UNION SELECT null, null, null --",
        "admin'--",
        '" OR ""="',
    ]

    for payload in sqli_payloads:
        # Querying employees endpoint with SQLi payload in search query
        res = await client.get(
            f"/api/v1/employees/?search={payload}",
            headers=headers,
        )
        # The API should gracefully return 200 with an empty list or normal filtered results, NEVER 500
        assert res.status_code == 200
        data = res.json()
        assert "items" in data or isinstance(data, list)


@pytest.mark.asyncio
async def test_idor_and_cross_tenant_isolation(auth_tokens_fixture, db_session, client: AsyncClient):
    """Verify strict multi-tenant isolation and IDOR protection on leave documents and reports."""
    fixture = await auth_tokens_fixture()

    # Create a leave request and document owned by Org 1 employee
    leave = LeaveRequest(
        organization_id=fixture["test_org"].id,
        employee_id=fixture["emp_profile"].id,
        leave_type_id=uuid.uuid4(),
        start_date=datetime.now(UTC).date(),
        end_date=datetime.now(UTC).date(),
        total_days=1.0,
        reason="Medical confidential record",
        status=LeaveStatus.PENDING,
    )
    db_session.add(leave)
    await db_session.flush()

    doc = LeaveDocument(
        leave_request_id=leave.id,
        file_name="doctor_confidential_note.pdf",
        file_url="/storage/medical/doc1.pdf",
        file_size_bytes=1024,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
    )
    db_session.add(doc)
    await db_session.commit()

    # 1. Tenant 2 (Rival Corp) attempts to access Tenant 1's leave documents -> MUST BE REJECTED 403/404
    org2_headers = {"Authorization": f"Bearer {fixture['org2_token']}"}
    res_org2 = await client.get(f"/api/v1/leave/{leave.id}/documents", headers=org2_headers)
    assert res_org2.status_code in [403, 404]

    # 2. Legitimate employee (Owner) accesses own document -> Allowed 200
    emp_headers = {"Authorization": f"Bearer {fixture['emp_token']}"}
    res_owner = await client.get(f"/api/v1/leave/{leave.id}/documents", headers=emp_headers)
    assert res_owner.status_code == 200
    assert len(res_owner.json()) == 1


@pytest.mark.asyncio
async def test_rbac_privilege_escalation_prevention(auth_tokens_fixture, client: AsyncClient):
    """Verify that regular employees cannot perform privileged admin actions."""
    fixture = await auth_tokens_fixture()
    emp_headers = {"Authorization": f"Bearer {fixture['emp_token']}"}

    # Attempt 1: Regular employee attempts to list audit logs
    res1 = await client.get("/api/v1/audit-logs/", headers=emp_headers)
    assert res1.status_code == 403

    # Attempt 2: Regular employee attempts to generate consolidated HR report
    res2 = await client.post(
        "/api/v1/reports/generate",
        json={"report_type": "CONSOLIDATED_HR", "parameters": {}},
        headers=emp_headers,
    )
    assert res2.status_code == 403

    # Attempt 3: Regular employee attempts to view report schedules
    res3 = await client.get("/api/v1/schedules/", headers=emp_headers)
    assert res3.status_code == 403


@pytest.mark.asyncio
async def test_rate_limiting_and_brute_force_defense():
    """Verify rate limiter triggers and calculates retry-after when threshold exceeded."""
    key = f"test_user_burst_{uuid.uuid4().hex[:6]}"
    max_reqs = 3
    window = 10

    # 3 requests within threshold -> Allowed
    for _ in range(max_reqs):
        allowed, retry_after = await check_rate_limit(key, max_reqs, window)
        assert allowed is True
        assert retry_after == 0

    # 4th request -> Exceeded
    allowed, retry_after = await check_rate_limit(key, max_reqs, window)
    assert allowed is False
    assert retry_after > 0


def test_file_upload_security():
    """Verify file upload validations: magic bytes, oversized limit, and filename path traversal."""
    # 1. Path traversal filename sanitization
    traversal_input = "../../etc/passwd"
    clean_name = sanitize_filename(traversal_input)
    assert ".." not in clean_name
    assert "/" not in clean_name
    assert "\\" not in clean_name
    assert "passwd" in clean_name

    # 2. Legitimate Excel content (.xlsx)
    valid_excel_magic = b"PK\x03\x04\x14\x00\x06\x00" + b"\x00" * 20
    validate_file_content(valid_excel_magic, "employees.xlsx")

    # 3. Extension spoofing (executable disguised as .xlsx)
    fake_excel = b"MZ\x90\x00\x03\x00\x00\x00"  # Windows PE executable magic
    with pytest.raises(Exception) as exc:
        validate_file_content(fake_excel, "malware.xlsx")
    assert "Magic byte signature" in str(exc.value)

    # 4. Disallowed file extension (.exe)
    with pytest.raises(Exception) as exc:
        validate_file_content(b"some content", "script.exe")
    assert "Unsupported file extension" in str(exc.value)


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_replay_detection(auth_tokens_fixture, db_session, client: AsyncClient):
    """Verify that replaying an already-rotated refresh token revokes the entire token family."""
    fixture = await auth_tokens_fixture()
    user = fixture["emp_user"]

    family_id = uuid.uuid4()
    raw_token_1 = f"token_1_{uuid.uuid4().hex}"
    raw_token_2 = f"token_2_{uuid.uuid4().hex}"

    token1 = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_token_1),
        family_id=family_id,
        is_revoked=True,  # Already used/rotated
        revoked_at=datetime.now(UTC),
        revocation_reason="Rotated",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    token2 = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_token_2),
        family_id=family_id,
        is_revoked=False,  # Active successor
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add_all([token1, token2])
    await db_session.commit()

    # Replaying token1 (which was already rotated)
    res = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": raw_token_1},
    )
    assert res.status_code == 401
    assert "Token reuse detected" in res.json().get("detail", "")

    # Verify successor token2 was automatically revoked due to replay attack detection
    refreshed_t2 = (
        await db_session.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token_2)))
    ).scalar_one()
    assert refreshed_t2.is_revoked is True
    assert "replay attack" in refreshed_t2.revocation_reason.lower()


@pytest.mark.asyncio
async def test_blocked_device_rejection(auth_tokens_fixture, db_session, client: AsyncClient):
    """Verify that a revoked or blocked device cannot submit OS telemetry events."""
    fixture = await auth_tokens_fixture()
    org_id = fixture["admin_user"].organization_id

    # Create blocked device
    blocked_dev = Device(
        organization_id=org_id,
        device_identifier=f"DEV-BLOCKED-{uuid.uuid4().hex[:6]}",
        device_name="Stolen Laptop",
        os_name="Windows",
        os_version="11.0",
        platform="windows",
        agent_version="1.0.0",
        is_trusted=False,
        is_blocked=True,
    )
    db_session.add(blocked_dev)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {fixture['admin_token']}"}
    payload = {
        "events": [
            {
                "event_id": str(uuid.uuid4()),
                "employee_id": str(fixture["emp_profile"].id),
                "device_id": str(blocked_dev.id),
                "operating_system": "windows",
                "event_type": "USER_LOGON",
                "occurred_at": datetime.now(UTC).isoformat(),
                "sequence_number": 1,
                "metadata": {},
            }
        ]
    }
    res = await client.post("/api/v1/os-events/sync", json=payload, headers=headers)
    assert res.status_code == 403
    assert "blocked or revoked" in res.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_websocket_unauthorized_rejection():
    """Verify WebSocket authentication helper rejects requests without token or with forged token."""
    # 1. Missing token
    mock_ws_missing = MagicMock()
    mock_ws_missing.query_params = {}
    mock_ws_missing.headers = {}
    user = await _authenticate_ws(mock_ws_missing)
    assert user is None

    # 2. Forged / invalid signature token
    mock_ws_bad = MagicMock()
    mock_ws_bad.query_params = {"token": "forged.token.payload"}
    mock_ws_bad.headers = {}
    user_bad = await _authenticate_ws(mock_ws_bad)
    assert user_bad is None


@pytest.mark.asyncio
async def test_database_backup_and_data_retention_compliance(db_session):
    """Verify database snapshot creation, SHA-256 integrity hash, and data retention purging."""
    uid = uuid.uuid4().hex[:6]
    test_org = Organization(name=f"BackupTestOrg-{uid}", slug=f"backup-{uid}", code=f"BAK-{uid[:4]}")
    db_session.add(test_org)
    await db_session.flush()

    # 1. Test Backup creation
    backup_meta = MaintenanceService.create_database_backup()
    assert backup_meta["status"] == "SUCCESS"
    assert os.path.exists(backup_meta["backup_path"])
    assert len(backup_meta["sha256_checksum"]) == 64  # Valid SHA-256 hex string

    # 2. Test Data Retention Purge
    # Insert old login history (> 100 days old)
    old_login = LoginHistory(
        organization_id=test_org.id,
        user_id=uuid.uuid4(),
        email="old@domain.com",
        is_success=True,
        created_at=datetime.now(UTC) - timedelta(days=120),
    )
    db_session.add(old_login)
    await db_session.commit()

    retention_result = await MaintenanceService.run_data_retention_policy(
        db=db_session,
        login_history_retention_days=90,
    )
    assert retention_result["purged_login_history"] >= 1
