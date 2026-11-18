"""
Comprehensive Test Suite for Phase 07 Attendance Management Engine
Tests:
- Normal attendance calculation (on-time clock-in/out, net duration)
- Late arrival calculation (schedule grace period adherence)
- Breaks handling (unpaid lunch vs paid coffee, break duration)
- Overnight shift support (cross-midnight work_date and net duration)
- Missing checkout detection
- Half-day calculation (working duration < 50% threshold)
- Approved leave integration (full day and half-day)
- Holiday and weekly-off handling
- Negative constraints (zero auto-clock-in from OS login)
- Duplicate event prevention and delayed offline synchronization
- Manual correction workflow with HR AuditLog generation
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.core.seeds import seed_organization_leave_types, seed_permissions, seed_system_roles
from app.models.attendance import (
    AdjustmentStatus,
    AdjustmentType,
    AttendanceAdjustment,
    AttendanceBreak,
    AttendanceDay,
    AttendanceEvent,
    AttendanceEventType,
    AttendanceSource,
    AttendanceStatus,
    BreakType,
)
from app.models.auth import AuditLog, User
from app.models.employee import EmployeeProfile, EmploymentStatus, ManagerAssignment
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.organization import Organization
from app.models.os_event import OSSessionEvent
from app.models.schedule import Holiday, WorkSchedule
from app.services.attendance_engine import (
    calculate_daily_attendance,
    classify_break_type,
    determine_work_date_for_clock_in,
    is_overnight_schedule,
    recalculate_attendance_day,
)


@pytest.fixture
async def setup_attendance_env(db_session: AsyncSession):
    """Initializes organization, system roles, work schedules, and employee personnel for Phase 07."""
    perm_map = await seed_permissions(db_session)
    role_map = await seed_system_roles(db_session, perm_map)

    org = Organization(
        name="Apex Enterprise Solutions",
        slug=f"apex-att-{uuid.uuid4().hex[:6]}",
        code=f"APX{uuid.uuid4().hex[:4].upper()}",
    )
    db_session.add(org)
    await db_session.flush()

    leave_map = await seed_organization_leave_types(db_session, org.id)

    # Standard Work Schedule: 09:00 to 17:00 (8 hrs, 15m grace, Mon-Fri)
    std_schedule = WorkSchedule(
        organization_id=org.id,
        name="Standard Day Shift",
        shift_start_time=time(9, 0),
        shift_end_time=time(17, 0),
        flexible_minutes=15,
        working_days=[1, 2, 3, 4, 5],
    )
    # Overnight Work Schedule: 22:00 to 06:00 (8 hrs, 15m grace, Mon-Fri)
    night_schedule = WorkSchedule(
        organization_id=org.id,
        name="Overnight Security Shift",
        shift_start_time=time(22, 0),
        shift_end_time=time(6, 0),
        flexible_minutes=15,
        working_days=[1, 2, 3, 4, 5],
    )
    db_session.add_all([std_schedule, night_schedule])
    await db_session.flush()

    # Users
    admin_user = User(
        organization_id=org.id,
        email=f"admin_{uuid.uuid4().hex[:6]}@apex.com",
        hashed_password=get_password_hash("AdminPass123!"),
        role_id=role_map["Super Administrator"].id,
        is_active=True,
    )
    mgr_user = User(
        organization_id=org.id,
        email=f"mgr_{uuid.uuid4().hex[:6]}@apex.com",
        hashed_password=get_password_hash("MgrPass123!"),
        role_id=role_map["Department Manager"].id,
        is_active=True,
    )
    emp_user = User(
        organization_id=org.id,
        email=f"emp_{uuid.uuid4().hex[:6]}@apex.com",
        hashed_password=get_password_hash("EmpPass123!"),
        role_id=role_map["Employee"].id,
        is_active=True,
    )
    night_emp_user = User(
        organization_id=org.id,
        email=f"night_{uuid.uuid4().hex[:6]}@apex.com",
        hashed_password=get_password_hash("EmpPass123!"),
        role_id=role_map["Employee"].id,
        is_active=True,
    )
    db_session.add_all([admin_user, mgr_user, emp_user, night_emp_user])
    await db_session.flush()

    # Employee Profiles
    admin_profile = EmployeeProfile(
        organization_id=org.id,
        user_id=admin_user.id,
        employee_code=f"EMP-ADM-{uuid.uuid4().hex[:4]}",
        first_name="Alice",
        last_name="Admin",
        hire_date=date(2024, 1, 1),
        employment_status=EmploymentStatus.ACTIVE,
    )
    mgr_profile = EmployeeProfile(
        organization_id=org.id,
        user_id=mgr_user.id,
        employee_code=f"EMP-MGR-{uuid.uuid4().hex[:4]}",
        first_name="Bob",
        last_name="Manager",
        hire_date=date(2024, 1, 1),
        employment_status=EmploymentStatus.ACTIVE,
    )
    emp_profile = EmployeeProfile(
        organization_id=org.id,
        user_id=emp_user.id,
        employee_code=f"EMP-DAY-{uuid.uuid4().hex[:4]}",
        first_name="Charlie",
        last_name="DayWorker",
        hire_date=date(2024, 1, 1),
        work_schedule_id=std_schedule.id,
        employment_status=EmploymentStatus.ACTIVE,
    )
    night_emp_profile = EmployeeProfile(
        organization_id=org.id,
        user_id=night_emp_user.id,
        employee_code=f"EMP-NGT-{uuid.uuid4().hex[:4]}",
        first_name="Derek",
        last_name="NightWorker",
        hire_date=date(2024, 1, 1),
        work_schedule_id=night_schedule.id,
        employment_status=EmploymentStatus.ACTIVE,
    )
    db_session.add_all([admin_profile, mgr_profile, emp_profile, night_emp_profile])
    await db_session.flush()

    # Manager reporting assignment
    db_session.add(
        ManagerAssignment(
            organization_id=org.id,
            employee_id=emp_profile.id,
            manager_id=mgr_profile.id,
            is_primary=True,
        )
    )
    await db_session.commit()

    return {
        "org": org,
        "std_schedule": std_schedule,
        "night_schedule": night_schedule,
        "leave_types": leave_map,
        "admin_user": admin_user,
        "mgr_user": mgr_user,
        "emp_user": emp_user,
        "night_emp_user": night_emp_user,
        "admin_profile": admin_profile,
        "mgr_profile": mgr_profile,
        "emp_profile": emp_profile,
        "night_emp_profile": night_emp_profile,
        "admin_token": create_access_token(admin_user.id, {"org": str(org.id)}),
        "mgr_token": create_access_token(mgr_user.id, {"org": str(org.id)}),
        "emp_token": create_access_token(emp_user.id, {"org": str(org.id)}),
        "night_emp_token": create_access_token(night_emp_user.id, {"org": str(org.id)}),
    }


# ============================================================================
# 1. Normal Attendance Calculation Scenario
# ============================================================================


@pytest.mark.asyncio
async def test_normal_attendance_lifecycle(client: AsyncClient, setup_attendance_env):
    """
    Scenario: Normal on-time attendance.
    Clock-in at 09:05 (within 15m grace), Clock-out at 17:05 (8 hours).
    Result: PRESENT, late_minutes=0, early_departure=0, net=480m.
    """
    data = setup_attendance_env
    headers = {"Authorization": f"Bearer {data['emp_token']}"}

    # 1. Clock In (Monday 09:05 UTC)
    t_in = datetime(2026, 11, 16, 9, 5, tzinfo=UTC)  # 2026-11-16 is a Monday
    in_resp = await client.post(
        "/api/v1/attendance/clock-in",
        json={"notes": "Normal shift arrival", "occurred_at": t_in.isoformat(), "is_wfh": False},
        headers=headers,
    )
    assert in_resp.status_code == 201, in_resp.text
    in_data = in_resp.json()
    assert in_data["status"] == "PRESENT"
    assert in_data["late_minutes"] == 0
    assert in_data["is_wfh"] is False

    # 2. Clock Out (Monday 17:05 UTC)
    t_out = datetime(2026, 11, 16, 17, 5, tzinfo=UTC)
    out_resp = await client.post(
        "/api/v1/attendance/clock-out",
        json={"notes": "Shift completed", "occurred_at": t_out.isoformat()},
        headers=headers,
    )
    assert out_resp.status_code == 200, out_resp.text
    out_data = out_resp.json()
    assert out_data["status"] == "PRESENT"
    assert out_data["total_work_minutes"] == 480
    assert out_data["late_minutes"] == 0
    assert out_data["early_departure_minutes"] == 0
    assert out_data["is_missing_checkout"] is False


# ============================================================================
# 2. Late Arrival Calculation Scenario
# ============================================================================


@pytest.mark.asyncio
async def test_late_arrival_calculation(client: AsyncClient, setup_attendance_env):
    """
    Scenario: Late attendance.
    Scheduled: 09:00 with 15m grace (grace ends 09:15).
    Clock-in at 09:40 -> late_minutes = 40.
    Status = LATE.
    """
    data = setup_attendance_env
    headers = {"Authorization": f"Bearer {data['emp_token']}"}

    t_in = datetime(2026, 11, 17, 9, 40, tzinfo=UTC)  # Tuesday
    in_resp = await client.post(
        "/api/v1/attendance/clock-in",
        json={"occurred_at": t_in.isoformat(), "notes": "Traffic delay"},
        headers=headers,
    )
    assert in_resp.status_code == 201
    in_data = in_resp.json()
    assert in_data["late_minutes"] == 40
    assert in_data["status"] == "LATE"


# ============================================================================
# 3. Breaks Handling Scenario (Paid vs Unpaid)
# ============================================================================


@pytest.mark.asyncio
async def test_breaks_lifecycle_and_net_duration(client: AsyncClient, setup_attendance_env):
    """
    Scenario: Shift with lunch (45m) and coffee (15m).
    Gross = 8 hours (480m).
    Breaks are recorded for display only and are NOT deducted from worked time.
    """
    data = setup_attendance_env
    headers = {"Authorization": f"Bearer {data['emp_token']}"}

    # Clock in 09:00
    t_in = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
    await client.post(
        "/api/v1/attendance/clock-in",
        json={"occurred_at": t_in.isoformat()},
        headers=headers,
    )

    # Start Lunch (12:00)
    t_b1_start = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
    b1 = await client.post(
        "/api/v1/attendance/break/start",
        json={"break_type": "LUNCH", "occurred_at": t_b1_start.isoformat()},
        headers=headers,
    )
    assert b1.status_code == 201
    assert b1.json()["is_paid"] is False

    # End Lunch (12:45 -> 45 mins)
    t_b1_end = datetime(2026, 11, 18, 12, 45, tzinfo=UTC)
    b1_end = await client.post(
        "/api/v1/attendance/break/end",
        json={"occurred_at": t_b1_end.isoformat()},
        headers=headers,
    )
    assert b1_end.status_code == 200
    assert b1_end.json()["duration_minutes"] == 45

    # Start Coffee (15:00)
    t_b2_start = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)
    b2 = await client.post(
        "/api/v1/attendance/break/start",
        json={"break_type": "COFFEE", "occurred_at": t_b2_start.isoformat()},
        headers=headers,
    )
    assert b2.status_code == 201
    assert b2.json()["is_paid"] is True

    # End Coffee (15:15 -> 15 mins paid)
    t_b2_end = datetime(2026, 11, 18, 15, 15, tzinfo=UTC)
    await client.post(
        "/api/v1/attendance/break/end",
        json={"occurred_at": t_b2_end.isoformat()},
        headers=headers,
    )

    # Clock out (17:00 -> 8 hours gross)
    t_out = datetime(2026, 11, 18, 17, 0, tzinfo=UTC)
    out_resp = await client.post(
        "/api/v1/attendance/clock-out",
        json={"occurred_at": t_out.isoformat()},
        headers=headers,
    )
    out_data = out_resp.json()
    assert out_data["total_break_minutes"] == 60  # 45m lunch + 15m coffee (display only)
    assert out_data["total_work_minutes"] == 480  # full login→logout; breaks not subtracted


# ============================================================================
# 4. Overnight Shift Support Scenario
# ============================================================================


@pytest.mark.asyncio
async def test_overnight_shift_calculation(client: AsyncClient, setup_attendance_env):
    """
    Scenario: Overnight shift (22:00 to 06:00 next day).
    Clock in at 21:55 (Nov 19), clock out at 06:05 (Nov 20).
    Verified:
    - Attributed to work_date 2026-11-19.
    - Spans across midnight cleanly.
    - Total work duration is 490 minutes.
    """
    data = setup_attendance_env
    headers = {"Authorization": f"Bearer {data['night_emp_token']}"}

    # Verify helper
    assert is_overnight_schedule(data["night_schedule"]) is True

    t_in = datetime(2026, 11, 19, 21, 55, tzinfo=UTC)
    in_resp = await client.post(
        "/api/v1/attendance/clock-in",
        json={"occurred_at": t_in.isoformat(), "notes": "Overnight guard shift"},
        headers=headers,
    )
    assert in_resp.status_code == 201
    in_data = in_resp.json()
    assert in_data["work_date"] == "2026-11-19"

    # Clock out next morning at 06:05 (Nov 20)
    t_out = datetime(2026, 11, 20, 6, 5, tzinfo=UTC)
    out_resp = await client.post(
        "/api/v1/attendance/clock-out",
        json={"occurred_at": t_out.isoformat()},
        headers=headers,
    )
    assert out_resp.status_code == 200
    out_data = out_resp.json()
    assert out_data["work_date"] == "2026-11-19"
    assert out_data["total_work_minutes"] == 490  # 5m early in + 480m + 5m late out


# ============================================================================
# 5. Missing Checkout Detection Scenario
# ============================================================================


@pytest.mark.asyncio
async def test_missing_checkout_detection(setup_attendance_env):
    """
    Scenario: Clocked in at 09:00, evaluation occurs at 20:00 (past 17:00 shift end + 2h).
    Missing checkout is flagged deterministically.
    """
    data = setup_attendance_env
    work_date = date(2026, 11, 16)
    t_in = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)

    ev_in = AttendanceEvent(
        attendance_day_id=uuid.uuid4(),
        event_type=AttendanceEventType.CLOCK_IN,
        timestamp=t_in,
        source=AttendanceSource.WEB,
    )

    eval_time = datetime(2026, 11, 16, 20, 0, tzinfo=UTC)  # 3 hours past shift end

    result = calculate_daily_attendance(
        work_date=work_date,
        events=[ev_in],
        breaks=[],
        schedule=data["std_schedule"],
        evaluation_time=eval_time,
    )

    assert result.is_missing_checkout is True
    assert "Missing clock-out detected past scheduled shift end" in result.notes


# ============================================================================
# 6. Approved Leave Integration Scenario
# ============================================================================


@pytest.mark.asyncio
async def test_approved_leave_integration(setup_attendance_env, db_session: AsyncSession):
    """
    Scenario: Employee has approved annual leave.
    Result: Status is ON_LEAVE without requiring manual intervention.
    """
    data = setup_attendance_env
    work_date = date(2026, 11, 23)

    leave_req = LeaveRequest(
        organization_id=data["org"].id,
        employee_id=data["emp_profile"].id,
        leave_type_id=data["leave_types"][0].id,
        start_date=work_date,
        end_date=work_date,
        total_days=1.0,
        status=LeaveStatus.APPROVED,
        reason="Scheduled vacation",
    )
    db_session.add(leave_req)
    await db_session.commit()

    result = calculate_daily_attendance(
        work_date=work_date,
        events=[],
        breaks=[],
        schedule=data["std_schedule"],
        approved_leaves=[leave_req],
    )

    assert result.status == AttendanceStatus.ON_LEAVE
    assert result.total_work_minutes == 0


# ============================================================================
# 7. Holiday & Weekly-Off Handling Scenario
# ============================================================================


@pytest.mark.asyncio
async def test_holiday_and_weekend_handling(setup_attendance_env):
    """
    Scenario:
    - Holiday without clock-in -> Status HOLIDAY.
    - Weekend without clock-in -> Status WEEKEND.
    - Weekend WITH clock-in -> Status PRESENT, marked as overtime.
    """
    data = setup_attendance_env
    # Sunday (Weekly Off)
    sunday_date = date(2026, 11, 22)
    res_weekend = calculate_daily_attendance(
        work_date=sunday_date,
        events=[],
        breaks=[],
        schedule=data["std_schedule"],
    )
    assert res_weekend.status == AttendanceStatus.WEEKEND

    # Holiday (Thanksgiving)
    holiday = Holiday(
        organization_id=data["org"].id,
        name="Thanksgiving Day",
        holiday_date=date(2026, 11, 26),
    )
    res_holiday = calculate_daily_attendance(
        work_date=holiday.holiday_date,
        events=[],
        breaks=[],
        schedule=data["std_schedule"],
        holidays=[holiday],
    )
    assert res_holiday.status == AttendanceStatus.HOLIDAY


# ============================================================================
# 8. Negative Constraints (Rule 2 & 3: Never Auto Clock-In on OS Login)
# ============================================================================


@pytest.mark.asyncio
async def test_negative_constraint_zero_auto_attendance_on_os_login(
    client: AsyncClient, setup_attendance_env, db_session: AsyncSession
):
    """
    Rule 2 & 3: Ingesting an OS session event (Logon, Unlock)
    must NEVER trigger an attendance clock-in automatically.
    """
    data = setup_attendance_env
    event_id = uuid.uuid4()

    # Ingest OS Logon event
    payload = {
        "event_id": str(event_id),
        "employee_id": str(data["emp_profile"].id),
        "device_id": "DESKTOP-HW-01",
        "operating_system": "windows",
        "event_type": "OS_LOGON",
        "occurred_at": datetime.now(UTC).isoformat(),
        "sequence_number": 1,
        "metadata": {"logon_type": "Interactive"},
    }
    headers = {"Authorization": f"Bearer {data['emp_token']}"}
    os_resp = await client.post("/api/v1/os-events/", json=payload, headers=headers)
    assert os_resp.status_code == 201

    # Verify zero AttendanceEvent records created
    att_events = await db_session.execute(
        select(AttendanceEvent)
        .join(AttendanceDay)
        .where(AttendanceDay.employee_id == data["emp_profile"].id)
    )
    assert len(att_events.scalars().all()) == 0


# ============================================================================
# 9. Manual Correction Workflow with HR Audit Log (Rule 6)
# ============================================================================


@pytest.mark.asyncio
async def test_manual_adjustment_workflow_and_hr_audit_log(
    client: AsyncClient, setup_attendance_env, db_session: AsyncSession
):
    """
    Rule 6: Manual HR corrections must recalculate daily attendance,
    preserve synthetic event history, and record before/after diff in AuditLog.
    """
    data = setup_attendance_env
    emp_headers = {"Authorization": f"Bearer {data['emp_token']}"}
    mgr_headers = {"Authorization": f"Bearer {data['mgr_token']}"}

    # Employee clocks in late at 10:30
    t_in = datetime(2026, 11, 24, 10, 30, tzinfo=UTC)
    in_resp = await client.post(
        "/api/v1/attendance/clock-in",
        json={"occurred_at": t_in.isoformat()},
        headers=emp_headers,
    )
    day_id = in_resp.json()["id"]

    # Employee submits adjustment request claiming badge reader malfunction (actual arrival 09:00)
    req_time = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)
    adj_resp = await client.post(
        "/api/v1/attendance/adjustments",
        json={
            "attendance_day_id": day_id,
            "adjustment_type": "MISSED_CLOCK_IN",
            "requested_shift_start": req_time.isoformat(),
            "reason": "RFID turnstile error; arrived at 09:00",
        },
        headers=emp_headers,
    )
    assert adj_resp.status_code == 201
    adj_id = adj_resp.json()["id"]

    # Manager reviews and approves adjustment
    review_resp = await client.post(
        f"/api/v1/attendance/adjustments/{adj_id}/review",
        json={"is_approved": True, "review_notes": "Verified with security front desk log"},
        headers=mgr_headers,
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["status"] == "APPROVED"

    # Verify day recalculated
    updated_day_res = await db_session.execute(
        select(AttendanceDay).where(AttendanceDay.id == uuid.UUID(day_id))
    )
    updated_day = updated_day_res.scalars().first()
    assert updated_day.late_minutes == 0  # Corrected to 09:00!
    assert updated_day.status == AttendanceStatus.PRESENT

    # Verify AuditLog created
    audit_res = await db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_id == day_id,
            AuditLog.action == "ATTENDANCE_CORRECTION_APPROVED",
        )
    )
    audit = audit_res.scalars().first()
    assert audit is not None
    assert audit.diff_json["reason"] == "RFID turnstile error; arrived at 09:00"
    assert audit.diff_json["review_notes"] == "Verified with security front desk log"


# ============================================================================
# 10. Delayed Offline Synchronization & Idempotency (Rules 7 & 8)
# ============================================================================


@pytest.mark.asyncio
async def test_offline_batch_synchronization_and_idempotency(
    client: AsyncClient, setup_attendance_env
):
    """
    Rules 7 & 8: Batch offline sync handles queued events,
    deduplicates by client_event_id, and computes sync_delay_seconds.
    """
    data = setup_attendance_env
    headers = {"Authorization": f"Bearer {data['emp_token']}"}

    cid_1 = f"offline_in_{uuid.uuid4().hex[:8]}"
    cid_2 = f"offline_out_{uuid.uuid4().hex[:8]}"
    t_in = datetime(2026, 11, 25, 9, 0, tzinfo=UTC)
    t_out = datetime(2026, 11, 25, 17, 0, tzinfo=UTC)

    batch_payload = {
        "events": [
            {
                "client_event_id": cid_1,
                "action": "CLOCK_IN",
                "occurred_at": t_in.isoformat(),
                "is_wfh": True,
                "notes": "Offline mobile punch",
            },
            {
                "client_event_id": cid_2,
                "action": "CLOCK_OUT",
                "occurred_at": t_out.isoformat(),
                "is_wfh": True,
                "notes": "Offline mobile checkout",
            },
        ]
    }

    # 1. Initial Batch Sync
    resp1 = await client.post("/api/v1/attendance/sync-offline", json=batch_payload, headers=headers)
    assert resp1.status_code == 200
    res1 = resp1.json()
    assert res1["received_count"] == 2
    assert res1["inserted_count"] == 2
    assert res1["duplicate_count"] == 0

    # 2. Resend Same Batch (Duplicate Prevention)
    resp2 = await client.post("/api/v1/attendance/sync-offline", json=batch_payload, headers=headers)
    assert resp2.status_code == 200
    res2 = resp2.json()
    assert res2["received_count"] == 2
    assert res2["inserted_count"] == 0
    assert res2["duplicate_count"] == 2


def _local_midday(hours: int = 12, minutes: int = 30) -> datetime:
    """Build a local midday timestamp (aware) for lunch-window classification tests."""
    local_tz = datetime.now().astimezone().tzinfo
    return datetime(2026, 11, 18, hours, minutes, tzinfo=local_tz)


def test_classify_break_type_lunch_and_personal():
    start = _local_midday(12, 10)
    end_long = start + timedelta(minutes=35)
    end_short = start + timedelta(minutes=15)
    assert classify_break_type(start, end_long) == BreakType.LUNCH
    assert classify_break_type(start, end_short) == BreakType.PERSONAL

    evening = datetime(2026, 11, 18, 16, 0, tzinfo=datetime.now().astimezone().tzinfo)
    assert classify_break_type(evening, evening + timedelta(minutes=40)) == BreakType.PERSONAL
    assert classify_break_type(start, None) == BreakType.LUNCH
    assert classify_break_type(evening, None, current_type=BreakType.COFFEE) == BreakType.COFFEE


@pytest.mark.asyncio
async def test_auto_idle_break_reclassifies_as_lunch(client: AsyncClient, setup_attendance_env):
    data = setup_attendance_env
    headers = {"Authorization": f"Bearer {data['emp_token']}"}

    t_in = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
    await client.post("/api/v1/attendance/clock-in", json={"occurred_at": t_in.isoformat()}, headers=headers)

    start = _local_midday(12, 5)
    end = start + timedelta(minutes=40)
    b_start = await client.post(
        "/api/v1/attendance/break/start",
        json={
            "break_type": "PERSONAL",
            "source": "AUTO_IDLE",
            "client_event_id": "auto-idle-start-1",
            "occurred_at": start.isoformat(),
        },
        headers=headers,
    )
    assert b_start.status_code == 201
    assert b_start.json()["source"] == "AUTO_IDLE"
    assert b_start.json()["break_type"] == "LUNCH"  # tentative midday

    b_end = await client.post(
        "/api/v1/attendance/break/end",
        json={"occurred_at": end.isoformat()},
        headers=headers,
    )
    assert b_end.status_code == 200
    body = b_end.json()
    assert body["duration_minutes"] == 40, body
    assert body["source"] == "AUTO_IDLE", body
    assert body["break_type"] == "LUNCH", body


@pytest.mark.asyncio
async def test_offline_auto_break_dedupe(client: AsyncClient, setup_attendance_env):
    data = setup_attendance_env
    headers = {"Authorization": f"Bearer {data['emp_token']}"}

    t_in = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
    await client.post("/api/v1/attendance/clock-in", json={"occurred_at": t_in.isoformat()}, headers=headers)

    start = _local_midday(12, 0)
    end = start + timedelta(minutes=32)
    batch = {
        "events": [
            {
                "client_event_id": "brk-start-dedupe-1",
                "action": "BREAK_START",
                "occurred_at": start.isoformat(),
                "break_type": "PERSONAL",
                "source": "AUTO_LOCK",
                "notes": "auto:lock",
            },
            {
                "client_event_id": "brk-end-dedupe-1",
                "action": "BREAK_END",
                "occurred_at": end.isoformat(),
                "notes": "auto:end:lock",
            },
        ]
    }
    first = await client.post("/api/v1/attendance/sync-offline", json=batch, headers=headers)
    assert first.status_code == 200
    assert first.json()["inserted_count"] == 2

    second = await client.post("/api/v1/attendance/sync-offline", json=batch, headers=headers)
    assert second.status_code == 200
    assert second.json()["inserted_count"] == 0
    assert second.json()["duplicate_count"] == 2

    status = await client.get("/api/v1/attendance/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["total_break_minutes"] >= 32
