"""
Employee desktop presence: app login/logout + Wi-Fi connect/disconnect drive attendance,
the login & logout table, and the dashboard summary.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.core.seeds import seed_organization_leave_types, seed_permissions, seed_system_roles
from app.models.auth import User
from app.models.employee import EmployeeProfile, ManagerAssignment
from app.models.leave import ApprovalStatus, LeaveRequest, LeaveStatus
from app.models.organization import Organization


@pytest.fixture
async def employee_env(db_session: AsyncSession, client: AsyncClient) -> dict:
    perm_map = await seed_permissions(db_session)
    role_map = await seed_system_roles(db_session, perm_map)
    suffix = uuid.uuid4().hex[:8]

    org = Organization(name=f"Presence Org {suffix}", slug=f"presence-{suffix}", code=f"PR_{suffix}".upper()[:16])
    db_session.add(org)
    await db_session.flush()
    leave_types = await seed_organization_leave_types(db_session, org.id)

    email = f"worker_{suffix}@presence.com"
    user = User(
        organization_id=org.id,
        email=email,
        hashed_password=get_password_hash("WorkerPass123!"),
        role_id=role_map["Employee"].id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    profile = EmployeeProfile(
        organization_id=org.id,
        user_id=user.id,
        employee_code=f"PR-{suffix}",
        first_name="Priya",
        last_name="Worker",
        hire_date=date(2024, 1, 1),
    )
    db_session.add(profile)
    await db_session.flush()

    login = await client.post(
        "/api/v1/auth/desktop-login",
        json={"email": email, "password": "WorkerPass123!", "device_identifier": f"WIN-{suffix}"},
    )
    assert login.status_code == 200, login.text
    return {
        "org": org,
        "roles": role_map,
        "suffix": suffix,
        "profile": profile,
        "leave_type": next(lt for lt in leave_types if lt.code == "ANNUAL"),
        "headers": {"Authorization": f"Bearer {login.json()['access_token']}"},
    }


def _at(day: date, hh: int, mm: int = 0) -> str:
    return datetime.combine(day, time(hh, mm), tzinfo=UTC).isoformat()


def _event(event_type: str, occurred_at: str, **extra) -> dict:
    return {"client_event_id": f"{event_type}-{uuid.uuid4().hex}", "event_type": event_type, "occurred_at": occurred_at, **extra}


@pytest.mark.asyncio
async def test_earliest_login_and_latest_logout_win(client: AsyncClient, employee_env: dict):
    headers = employee_env["headers"]
    day = datetime.now(UTC).date() - timedelta(days=1)

    # App login arrives in the same batch as an earlier Wi-Fi connection: the Wi-Fi time is the login.
    wifi_in = _event("WIFI_CONNECTED", _at(day, 3, 25), ssid="Office-5G")
    app_in = _event("APP_LOGIN", _at(day, 3, 40))
    res = await client.post("/api/v1/presence/events", json={"events": [app_in, wifi_in]}, headers=headers)
    assert res.status_code == 200, res.text
    by_id = {r["client_event_id"]: r for r in res.json()["results"]}
    assert by_id[wifi_in["client_event_id"]]["attendance_action"] == "CLOCK_IN"
    assert by_id[app_in["client_event_id"]]["attendance_action"] == "NONE"

    # Re-sending the same event is idempotent.
    dup = await client.post("/api/v1/presence/events", json={"events": [wifi_in]}, headers=headers)
    assert dup.json()["results"][0]["status"] == "DUPLICATE"

    # App logout then a later Wi-Fi disconnect: the later one becomes the logout time.
    out = await client.post(
        "/api/v1/presence/events",
        json={"events": [_event("APP_LOGOUT", _at(day, 12, 0)), _event("WIFI_DISCONNECTED", _at(day, 12, 30), ssid="Office-5G")]},
        headers=headers,
    )
    actions = [r["attendance_action"] for r in out.json()["results"]]
    assert actions == ["CLOCK_OUT", "CLOCK_OUT"]
    assert out.json()["is_logged_in"] is False
    mid = await client.get(
        "/api/v1/presence/my-history", params={"start_date": str(day), "end_date": str(day)}, headers=headers
    )
    assert mid.json()["days"][0]["last_logout"].startswith(f"{day}T12:30")

    # Reconnecting later the same day re-opens the session; disconnecting closes it again.
    await client.post(
        "/api/v1/presence/events",
        json={"events": [_event("WIFI_CONNECTED", _at(day, 13, 0), ssid="Office-5G"), _event("WIFI_DISCONNECTED", _at(day, 14, 0))]},
        headers=headers,
    )

    history = await client.get(
        "/api/v1/presence/my-history", params={"start_date": str(day), "end_date": str(day)}, headers=headers
    )
    assert history.status_code == 200, history.text
    row = history.json()["days"][0]
    assert row["work_date"] == str(day)
    assert row["first_login"].startswith(f"{day}T03:25")
    assert row["last_logout"].startswith(f"{day}T14:00")
    assert row["worked_minutes"] == (14 * 60) - (3 * 60 + 25)
    assert row["first_wifi_connected_at"].startswith(f"{day}T03:25")
    assert row["wifi_networks"] == ["Office-5G"]
    assert [e["event_type"] for e in row["events"]] == [
        "WIFI_CONNECTED",
        "APP_LOGIN",
        "APP_LOGOUT",
        "WIFI_DISCONNECTED",
        "WIFI_CONNECTED",
        "WIFI_DISCONNECTED",
    ]


@pytest.mark.asyncio
async def test_late_synced_earlier_wifi_connect_moves_login_earlier(client: AsyncClient, employee_env: dict):
    headers = employee_env["headers"]
    day = datetime.now(UTC).date() - timedelta(days=1)

    await client.post("/api/v1/presence/events", json={"events": [_event("APP_LOGIN", _at(day, 4, 0))]}, headers=headers)
    res = await client.post(
        "/api/v1/presence/events",
        json={"events": [_event("WIFI_CONNECTED", _at(day, 3, 30), ssid="Office-5G")]},
        headers=headers,
    )
    assert res.json()["results"][0]["attendance_action"] == "CLOCK_IN"
    assert res.json()["is_logged_in"] is True

    history = await client.get(
        "/api/v1/presence/my-history", params={"start_date": str(day), "end_date": str(day)}, headers=headers
    )
    row = history.json()["days"][0]
    assert row["first_login"].startswith(f"{day}T03:30")
    assert row["is_logged_in"] is True


@pytest.mark.asyncio
async def test_rejects_future_old_and_naive_timestamps(client: AsyncClient, employee_env: dict):
    headers = employee_env["headers"]
    now = datetime.now(UTC)
    res = await client.post(
        "/api/v1/presence/events",
        json={
            "events": [
                _event("APP_LOGIN", (now + timedelta(hours=2)).isoformat()),
                _event("APP_LOGIN", (now - timedelta(days=10)).isoformat()),
            ]
        },
        headers=headers,
    )
    assert [r["status"] for r in res.json()["results"]] == ["REJECTED", "REJECTED"]
    assert res.json()["is_logged_in"] is False

    naive = await client.post(
        "/api/v1/presence/events",
        json={"events": [_event("APP_LOGIN", now.replace(tzinfo=None).isoformat())]},
        headers=headers,
    )
    assert naive.status_code == 422


@pytest.mark.asyncio
async def test_missing_logout_is_closed_at_last_signal_before_next_login(client: AsyncClient, employee_env: dict):
    headers = employee_env["headers"]
    today = datetime.now(UTC).date()
    day1 = today - timedelta(days=2)
    day2 = today - timedelta(days=1)

    await client.post(
        "/api/v1/presence/events",
        json={"events": [_event("APP_LOGIN", _at(day1, 4)), _event("WIFI_CONNECTED", _at(day1, 9), ssid="Cafe")]},
        headers=headers,
    )
    res = await client.post("/api/v1/presence/events", json={"events": [_event("APP_LOGIN", _at(day2, 4))]}, headers=headers)
    assert res.json()["results"][0]["attendance_action"] == "CLOCK_IN"
    assert res.json()["is_logged_in"] is True

    history = await client.get(
        "/api/v1/presence/my-history", params={"start_date": str(day1), "end_date": str(day2)}, headers=headers
    )
    rows = {r["work_date"]: r for r in history.json()["days"]}
    assert rows[str(day1)]["last_logout"].startswith(f"{day1}T09:00")
    assert rows[str(day1)]["is_logged_in"] is False
    assert rows[str(day2)]["is_logged_in"] is True


@pytest.mark.asyncio
async def test_month_summary_counts_present_leave_and_login_time(
    client: AsyncClient, db_session: AsyncSession, employee_env: dict
):
    headers = employee_env["headers"]
    today = datetime.now(UTC).date()
    worked_day = today - timedelta(days=1)

    await client.post(
        "/api/v1/presence/events",
        json={"events": [_event("APP_LOGIN", _at(worked_day, 3)), _event("APP_LOGOUT", _at(worked_day, 11))]},
        headers=headers,
    )

    db_session.add(
        LeaveRequest(
            organization_id=employee_env["org"].id,
            employee_id=employee_env["profile"].id,
            leave_type_id=employee_env["leave_type"].id,
            start_date=today,
            end_date=today,
            total_days=1.0,
            reason="Family function",
            status=LeaveStatus.APPROVED,
            manager_approval_status=ApprovalStatus.APPROVED,
            hr_approval_status=ApprovalStatus.APPROVED,
        )
    )
    await db_session.flush()

    res = await client.get("/api/v1/presence/my-summary", params={"month": f"{today:%Y-%m}"}, headers=headers)
    assert res.status_code == 200, res.text
    summary = res.json()
    present_expected = 1 if worked_day.month == today.month else 0
    leave_expected = 1.0 if today.isoweekday() <= 5 else 0.0
    assert summary["present_days"] == present_expected
    assert summary["leave_days"] == leave_expected
    if present_expected:
        assert summary["total_worked_minutes"] == 8 * 60
    assert summary["today"]["work_date"] == str(today)
    assert summary["absent_days"] >= 0

    bad = await client.get("/api/v1/presence/my-summary", params={"month": "2026-13"}, headers=headers)
    assert bad.status_code == 422

    me = await client.get("/api/v1/presence/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["first_name"] == "Priya"
    assert me.json()["employee_code"] == employee_env["profile"].employee_code


async def _add_person(db: AsyncSession, env: dict, role: str, first_name: str) -> tuple[EmployeeProfile, str]:
    email = f"{first_name.lower()}_{env['suffix']}@presence.com"
    user = User(
        organization_id=env["org"].id,
        email=email,
        hashed_password=get_password_hash("PersonPass123!"),
        role_id=env["roles"][role].id,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    profile = EmployeeProfile(
        organization_id=env["org"].id,
        user_id=user.id,
        employee_code=f"{first_name[:3].upper()}-{env['suffix']}",
        first_name=first_name,
        last_name="Test",
        hire_date=date(2024, 1, 1),
    )
    db.add(profile)
    await db.flush()
    return profile, email


async def _web_headers(client: AsyncClient, email: str) -> dict:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": "PersonPass123!"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.mark.asyncio
async def test_team_board_scopes_hr_to_org_and_manager_to_direct_reports(
    client: AsyncClient, db_session: AsyncSession, employee_env: dict
):
    env = employee_env
    today = datetime.now(UTC).date()
    priya = env["profile"]
    ravi, _ = await _add_person(db_session, env, "Employee", "Ravi")
    manager, manager_email = await _add_person(db_session, env, "Department Manager", "Mona")
    _, hr_email = await _add_person(db_session, env, "HR Manager", "Hema")
    db_session.add(ManagerAssignment(organization_id=env["org"].id, employee_id=priya.id, manager_id=manager.id))
    db_session.add(
        LeaveRequest(
            organization_id=env["org"].id,
            employee_id=ravi.id,
            leave_type_id=env["leave_type"].id,
            start_date=today,
            end_date=today,
            total_days=1.0,
            reason="Medical appointment",
            status=LeaveStatus.APPROVED,
            manager_approval_status=ApprovalStatus.APPROVED,
            hr_approval_status=ApprovalStatus.APPROVED,
        )
    )
    await db_session.flush()

    login_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    await client.post(
        "/api/v1/presence/events",
        json={"events": [_event("WIFI_CONNECTED", login_at, ssid="Office-5G")]},
        headers=env["headers"],
    )

    hr_headers = await _web_headers(client, hr_email)
    hr = await client.get("/api/v1/presence/team", headers=hr_headers)
    assert hr.status_code == 200, hr.text
    board = hr.json()
    assert board["scope"] == "ORGANIZATION"
    rows = {r["full_name"]: r for r in board["rows"]}
    assert set(rows) == {"Priya Worker", "Ravi Test"}  # managers and HR are not tracked by the desktop app
    assert rows["Priya Worker"]["status"] == "LOGGED_IN"
    assert rows["Priya Worker"]["wifi_networks"] == ["Office-5G"]
    assert rows["Ravi Test"]["status"] == "ON_LEAVE"
    assert rows["Ravi Test"]["leave_type_name"] == "Annual Leave"
    assert board["counts"] == {"total": 2, "logged_in": 1, "logged_out": 0, "on_leave": 1, "not_logged_in": 0}

    manager_headers = await _web_headers(client, manager_email)
    mgr = await client.get("/api/v1/presence/team", headers=manager_headers)
    assert mgr.status_code == 200, mgr.text
    assert mgr.json()["scope"] == "TEAM"
    assert [r["full_name"] for r in mgr.json()["rows"]] == ["Priya Worker"]

    own_team = await client.get(f"/api/v1/presence/employee/{priya.id}/history", headers=manager_headers)
    assert own_team.status_code == 200, own_team.text
    assert own_team.json()["days"][0]["is_logged_in"] is True
    other_team = await client.get(f"/api/v1/presence/employee/{ravi.id}/history", headers=manager_headers)
    assert other_team.status_code == 403

    assert (await client.get("/api/v1/presence/team", headers=env["headers"])).status_code == 403
    assert (await client.get("/api/v1/leave/team-requests", headers=env["headers"])).status_code == 403
    future = await client.get(
        "/api/v1/presence/team", params={"date": str(today + timedelta(days=2))}, headers=hr_headers
    )
    assert future.status_code == 400


@pytest.mark.asyncio
async def test_leave_review_queue_scoping_and_hr_handles_employee_without_manager(
    client: AsyncClient, db_session: AsyncSession, employee_env: dict
):
    env = employee_env
    priya = env["profile"]
    ravi, ravi_email = await _add_person(db_session, env, "Employee", "Ravi")
    manager, manager_email = await _add_person(db_session, env, "Department Manager", "Mona")
    _, hr_email = await _add_person(db_session, env, "HR Manager", "Hema")
    db_session.add(ManagerAssignment(organization_id=env["org"].id, employee_id=priya.id, manager_id=manager.id))
    await db_session.flush()

    ravi_login = await client.post(
        "/api/v1/auth/desktop-login",
        json={"email": ravi_email, "password": "PersonPass123!", "device_identifier": f"WIN-R-{env['suffix']}"},
    )
    ravi_headers = {"Authorization": f"Bearer {ravi_login.json()['access_token']}"}
    today = datetime.now(UTC).date()
    monday = today + timedelta(days=14 - today.weekday())
    payload = {
        "leave_type_id": str(env["leave_type"].id),
        "start_date": str(monday),
        "end_date": str(monday),
        "reason": "Personal work",
    }
    priya_leave = await client.post("/api/v1/leave/apply", json=payload, headers=env["headers"])
    ravi_leave = await client.post("/api/v1/leave/apply", json=payload, headers=ravi_headers)
    assert priya_leave.status_code == 201, priya_leave.text
    assert ravi_leave.status_code == 201, ravi_leave.text

    hr_headers = await _web_headers(client, hr_email)
    hr_queue = await client.get("/api/v1/leave/team-requests", params={"status": "PENDING"}, headers=hr_headers)
    assert {r["employee_name"] for r in hr_queue.json()} == {"Priya Worker", "Ravi Test"}

    manager_headers = await _web_headers(client, manager_email)
    mgr_queue = await client.get("/api/v1/leave/team-requests", headers=manager_headers)
    assert [r["employee_name"] for r in mgr_queue.json()] == ["Priya Worker"]

    # Ravi has no manager, so HR may take the manager step and then give final approval.
    ravi_id = ravi_leave.json()["id"]
    step1 = await client.post(f"/api/v1/leave/{ravi_id}/manager-review", json={"action": "APPROVE"}, headers=hr_headers)
    assert step1.status_code == 200, step1.text
    step2 = await client.post(f"/api/v1/leave/{ravi_id}/hr-review", json={"action": "APPROVE"}, headers=hr_headers)
    assert step2.status_code == 200, step2.text
    assert step2.json()["status"] == "APPROVED"

    # Priya has a manager: HR cannot skip them.
    priya_id = priya_leave.json()["id"]
    skip = await client.post(f"/api/v1/leave/{priya_id}/manager-review", json={"action": "APPROVE"}, headers=hr_headers)
    assert skip.status_code == 400

    missing = await client.post(
        f"/api/v1/leave/{uuid.uuid4()}/manager-review", json={"action": "APPROVE"}, headers=manager_headers
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_suspend_resume_are_audit_only_not_clock(client: AsyncClient, employee_env: dict):
    """Sleep/wake stay on the presence timeline but do not clock out/in (breaks handle that)."""
    from app.models.presence import LOGIN_EVENT_TYPES, LOGOUT_EVENT_TYPES, PresenceEventType

    assert PresenceEventType.SYSTEM_SUSPEND not in LOGOUT_EVENT_TYPES
    assert PresenceEventType.SYSTEM_RESUME not in LOGIN_EVENT_TYPES

    headers = employee_env["headers"]
    day = datetime.now(UTC).date() - timedelta(days=1)

    login = await client.post(
        "/api/v1/presence/events",
        json={"events": [_event("APP_LOGIN", _at(day, 9, 0))]},
        headers=headers,
    )
    assert login.status_code == 200
    assert login.json()["is_logged_in"] is True

    power = await client.post(
        "/api/v1/presence/events",
        json={
            "events": [
                _event("SYSTEM_SUSPEND", _at(day, 13, 0)),
                _event("SYSTEM_RESUME", _at(day, 13, 45)),
            ]
        },
        headers=headers,
    )
    assert power.status_code == 200
    results = {r["client_event_id"]: r for r in power.json()["results"]}
    for r in results.values():
        assert r["status"] == "RECORDED"
        assert r["attendance_action"] == "NONE"
    assert power.json()["is_logged_in"] is True
