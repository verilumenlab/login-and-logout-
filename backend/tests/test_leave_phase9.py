"""
Comprehensive Verification Tests for Phase 09: Leave Management Engine & Workflow
Tests:
1. Multi-tier Approval Workflow: EMPLOYEE -> MANAGER -> HR -> FINAL APPROVAL
2. Mandatory Manager Approval before HR Review
3. Immediate Request Closure on Manager Rejection
4. Immediate Request Closure on HR Rejection
5. Strict Prohibition of Self-Approval
6. Unauthorized Approver Prevention (Unassigned Manager)
7. Overlapping Leave Request Prevention
8. Weekend and Holiday Deduction Rules
9. Half-Day Leave Workflow (0.5 Days, FIRST_HALF / SECOND_HALF)
10. Employee Withdrawal and Balance Restoration
11. Attendance Synchronization (AttendanceDay ON_LEAVE and HALF_DAY)
12. Supporting Document Attachment
13. Manager and HR Approval Dashboards
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
from app.models.attendance import AttendanceDay, AttendanceStatus
from app.models.auth import Role, User
from app.models.department import Department
from app.models.employee import EmployeeProfile, EmploymentStatus, ManagerAssignment
from app.models.leave import (
    ApprovalStatus,
    LeaveApproval,
    LeaveBalance,
    LeaveCategory,
    LeaveDocument,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
)
from app.models.organization import Organization
from app.models.schedule import Holiday


@pytest.fixture
async def setup_leave_env(db_session: AsyncSession):
    """
    Sets up an enterprise test organization with:
    - Admin, HR, Manager 1, Manager 2, and Employee
    - Leave types (Annual, Sick, Unpaid)
    - Initialized LeaveBalances
    - Assigned manager hierarchy: Manager 1 manages Employee
    - A recognized public holiday
    """
    code_suffix = uuid.uuid4().hex[:6].upper()
    org = Organization(
        name="Apex Leave Test Corp",
        code=f"ALTC-{code_suffix}",
        slug=f"altc-{code_suffix.lower()}",
        is_active=True,
    )
    db_session.add(org)
    await db_session.flush()

    # Seed roles & permissions
    perm_map = await seed_permissions(db_session)
    role_map = await seed_system_roles(db_session, perm_map)

    # Department
    dept = Department(organization_id=org.id, name="Engineering", code="ENG")
    db_session.add(dept)
    await db_session.flush()

    # Helper to create user + employee
    async def create_user_emp(email: str, role_name: str, first_name: str, last_name: str) -> tuple[User, EmployeeProfile, str]:
        user = User(
            organization_id=org.id,
            role_id=role_map[role_name].id,
            email=email,
            hashed_password=get_password_hash("SecurePass123!"),
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

    admin_user, admin_emp, admin_token = await create_user_emp(
        f"admin_{uuid.uuid4().hex[:4]}@altc.corp", "Administrator", "Alice", "Admin"
    )
    hr_user, hr_emp, hr_token = await create_user_emp(
        f"hr_{uuid.uuid4().hex[:4]}@altc.corp", "HR Manager", "Hannah", "HR"
    )
    mgr1_user, mgr1_emp, mgr1_token = await create_user_emp(
        f"mgr1_{uuid.uuid4().hex[:4]}@altc.corp", "Department Manager", "Mark", "Manager1"
    )
    mgr2_user, mgr2_emp, mgr2_token = await create_user_emp(
        f"mgr2_{uuid.uuid4().hex[:4]}@altc.corp", "Department Manager", "Mike", "Manager2"
    )
    sub_user, sub_emp, sub_token = await create_user_emp(
        f"emp_{uuid.uuid4().hex[:4]}@altc.corp", "Employee", "Edward", "Employee"
    )

    # Manager 1 manages Employee Edward
    assignment = ManagerAssignment(
        organization_id=org.id,
        manager_id=mgr1_emp.id,
        employee_id=sub_emp.id,
        is_primary=True,
    )
    db_session.add(assignment)

    # Leave Types
    annual_leave = LeaveType(
        organization_id=org.id,
        name="Annual Leave",
        code="ANNUAL",
        category=LeaveCategory.ANNUAL,
        annual_allowance=15,
        carryover_max_days=5,
        include_weekends=False,
        is_active=True,
    )
    sick_leave = LeaveType(
        organization_id=org.id,
        name="Sick Leave",
        code="SICK",
        category=LeaveCategory.SICK,
        annual_allowance=10,
        carryover_max_days=0,
        include_weekends=False,
        is_active=True,
    )
    unpaid_leave = LeaveType(
        organization_id=org.id,
        name="Unpaid Leave",
        code="UNPAID",
        category=LeaveCategory.UNPAID,
        annual_allowance=0,
        carryover_max_days=0,
        include_weekends=True,
        is_active=True,
    )
    db_session.add_all([annual_leave, sick_leave, unpaid_leave])
    await db_session.flush()

    # Pre-seed leave balance for Edward (2026)
    bal_annual = LeaveBalance(
        organization_id=org.id,
        employee_id=sub_emp.id,
        leave_type_id=annual_leave.id,
        year=2026,
        allocated_days=15.0,
        used_days=0.0,
        pending_days=0.0,
        carryover_days=0.0,
    )
    bal_sick = LeaveBalance(
        organization_id=org.id,
        employee_id=sub_emp.id,
        leave_type_id=sick_leave.id,
        year=2026,
        allocated_days=10.0,
        used_days=0.0,
        pending_days=0.0,
        carryover_days=0.0,
    )
    db_session.add_all([bal_annual, bal_sick])

    # Add a company holiday: 2026-11-20 (Friday)
    holiday = Holiday(
        organization_id=org.id,
        name="Founders Day Holiday",
        holiday_date=date(2026, 11, 20),
        is_optional=False,
    )
    db_session.add(holiday)

    await db_session.commit()

    return {
        "org": org,
        "dept": dept,
        "admin": {"user": admin_user, "emp": admin_emp, "token": admin_token},
        "hr": {"user": hr_user, "emp": hr_emp, "token": hr_token},
        "mgr1": {"user": mgr1_user, "emp": mgr1_emp, "token": mgr1_token},
        "mgr2": {"user": mgr2_user, "emp": mgr2_emp, "token": mgr2_token},
        "emp": {"user": sub_user, "emp": sub_emp, "token": sub_token},
        "annual_leave": annual_leave,
        "sick_leave": sick_leave,
        "unpaid_leave": unpaid_leave,
        "holiday": holiday,
    }


# ============================================================================
# 1. End-to-End Multi-Tier Approval Workflow & Attendance Sync
# ============================================================================

@pytest.mark.asyncio
async def test_full_approval_workflow_and_attendance_sync(client: AsyncClient, setup_leave_env, db_session: AsyncSession):
    """
    Validates complete multi-tier flow:
    1. Employee applies (start: 2026-11-16 Mon, end: 2026-11-18 Wed -> 3 working days).
    2. Pending days in balance increment from 0 to 3.
    3. Manager 1 approves -> status remains PENDING, manager_approval_status is APPROVED.
    4. HR approves -> final status APPROVED, pending days decrease to 0, used days become 3.
    5. AttendanceDay records automatically populated for each day with ON_LEAVE status.
    """
    env = setup_leave_env
    emp_token = env["emp"]["token"]
    mgr1_token = env["mgr1"]["token"]
    hr_token = env["hr"]["token"]
    annual_id = str(env["annual_leave"].id)

    # Step 1: Employee applies
    apply_payload = {
        "leave_type_id": annual_id,
        "start_date": "2026-11-16",
        "end_date": "2026-11-18",
        "reason": "Family vacation",
        "is_half_day": False,
    }
    res = await client.post(
        "/api/v1/leave/apply",
        json=apply_payload,
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res.status_code == 201, res.text
    leave_data = res.json()
    leave_id = leave_data["id"]
    assert leave_data["total_days"] == 3.0
    assert leave_data["status"] == "PENDING"
    assert leave_data["manager_approval_status"] == "PENDING"
    assert leave_data["hr_approval_status"] == "PENDING"

    # Verify balance reservation (pending_days = 3.0)
    bal_res = await client.get("/api/v1/leave/balances", headers={"Authorization": f"Bearer {emp_token}"})
    assert bal_res.status_code == 200
    annual_bal = next(b for b in bal_res.json() if b["leave_type_id"] == annual_id)
    assert annual_bal["pending_days"] == 3.0
    assert annual_bal["used_days"] == 0.0
    assert annual_bal["available_days"] == 12.0

    # Step 2: Manager 1 reviews and APPROVES
    mgr_review = await client.post(
        f"/api/v1/leave/{leave_id}/manager-review",
        json={"action": "APPROVE", "comments": "Approved by engineering manager"},
        headers={"Authorization": f"Bearer {mgr1_token}"},
    )
    assert mgr_review.status_code == 200, mgr_review.text
    mgr_data = mgr_review.json()
    assert mgr_data["manager_approval_status"] == "APPROVED"
    assert mgr_data["hr_approval_status"] == "PENDING"
    assert mgr_data["status"] == "PENDING"  # Not final yet!

    # Step 3: HR reviews and APPROVES (Final Approval)
    hr_review = await client.post(
        f"/api/v1/leave/{leave_id}/hr-review",
        json={"action": "APPROVE", "comments": "Final HR approval granted"},
        headers={"Authorization": f"Bearer {hr_token}"},
    )
    assert hr_review.status_code == 200, hr_review.text
    hr_data = hr_review.json()
    assert hr_data["hr_approval_status"] == "APPROVED"
    assert hr_data["status"] == "APPROVED"

    # Step 4: Verify balance deduction (pending_days = 0, used_days = 3)
    bal_res2 = await client.get("/api/v1/leave/balances", headers={"Authorization": f"Bearer {emp_token}"})
    annual_bal2 = next(b for b in bal_res2.json() if b["leave_type_id"] == annual_id)
    assert annual_bal2["pending_days"] == 0.0
    assert annual_bal2["used_days"] == 3.0
    assert annual_bal2["available_days"] == 12.0

    # Step 5: Verify Attendance synchronization for all 3 dates
    for check_date in [date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 18)]:
        att_stmt = select(AttendanceDay).where(
            AttendanceDay.employee_id == env["emp"]["emp"].id,
            AttendanceDay.work_date == check_date,
        )
        att_res = await db_session.execute(att_stmt)
        day_record = att_res.scalars().first()
        assert day_record is not None, f"Missing AttendanceDay for {check_date}"
        assert day_record.status == AttendanceStatus.ON_LEAVE
        assert day_record.metadata_json.get("auto_generated_from_leave") is True


# ============================================================================
# 2. Rejection Workflows (Manager & HR Immediate Closure)
# ============================================================================

@pytest.mark.asyncio
async def test_manager_rejection_immediately_closes_and_releases_balance(client: AsyncClient, setup_leave_env):
    """Verifies that manager rejection immediately marks status REJECTED and releases pending balance."""
    env = setup_leave_env
    emp_token = env["emp"]["token"]
    mgr1_token = env["mgr1"]["token"]
    annual_id = str(env["annual_leave"].id)

    # Apply for 2 days (2026-11-23 to 2026-11-24)
    res = await client.post(
        "/api/v1/leave/apply",
        json={"leave_type_id": annual_id, "start_date": "2026-11-23", "end_date": "2026-11-24", "reason": "Short break"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res.status_code == 201
    leave_id = res.json()["id"]

    # Manager rejects
    rej_res = await client.post(
        f"/api/v1/leave/{leave_id}/manager-review",
        json={"action": "REJECT", "comments": "Project deadline collision"},
        headers={"Authorization": f"Bearer {mgr1_token}"},
    )
    assert rej_res.status_code == 200
    data = rej_res.json()
    assert data["status"] == "REJECTED"
    assert data["manager_approval_status"] == "REJECTED"

    # Verify pending days released back
    bal_res = await client.get("/api/v1/leave/balances", headers={"Authorization": f"Bearer {emp_token}"})
    annual_bal = next(b for b in bal_res.json() if b["leave_type_id"] == annual_id)
    assert annual_bal["pending_days"] == 0.0


@pytest.mark.asyncio
async def test_hr_rejection_immediately_closes_and_releases_balance(client: AsyncClient, setup_leave_env):
    """Verifies that HR rejection after manager approval marks status REJECTED and releases balance."""
    env = setup_leave_env
    emp_token = env["emp"]["token"]
    mgr1_token = env["mgr1"]["token"]
    hr_token = env["hr"]["token"]
    sick_id = str(env["sick_leave"].id)

    # Apply for 1 day
    res = await client.post(
        "/api/v1/leave/apply",
        json={"leave_type_id": sick_id, "start_date": "2026-11-25", "end_date": "2026-11-25", "reason": "Dental checkup"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res.status_code == 201
    leave_id = res.json()["id"]

    # Manager approves
    await client.post(
        f"/api/v1/leave/{leave_id}/manager-review",
        json={"action": "APPROVE"},
        headers={"Authorization": f"Bearer {mgr1_token}"},
    )

    # HR rejects
    rej_res = await client.post(
        f"/api/v1/leave/{leave_id}/hr-review",
        json={"action": "REJECT", "comments": "Insufficient supporting documentation"},
        headers={"Authorization": f"Bearer {hr_token}"},
    )
    assert rej_res.status_code == 200
    data = rej_res.json()
    assert data["status"] == "REJECTED"
    assert data["hr_approval_status"] == "REJECTED"

    # Verify pending days released
    bal_res = await client.get("/api/v1/leave/balances", headers={"Authorization": f"Bearer {emp_token}"})
    sick_bal = next(b for b in bal_res.json() if b["leave_type_id"] == sick_id)
    assert sick_bal["pending_days"] == 0.0


# ============================================================================
# 3. Security, Authorization & Self-Approval Prevention
# ============================================================================

@pytest.mark.asyncio
async def test_self_approval_is_strictly_prohibited(client: AsyncClient, setup_leave_env):
    """Ensures managers or HR representatives cannot approve their own leave requests."""
    env = setup_leave_env
    mgr1_token = env["mgr1"]["token"]
    annual_id = str(env["annual_leave"].id)

    # Manager 1 applies for leave
    apply_res = await client.post(
        "/api/v1/leave/apply",
        json={"leave_type_id": annual_id, "start_date": "2026-12-01", "end_date": "2026-12-02", "reason": "Manager PTO"},
        headers={"Authorization": f"Bearer {mgr1_token}"},
    )
    assert apply_res.status_code == 201
    leave_id = apply_res.json()["id"]

    # Manager 1 attempts to approve their OWN leave -> MUST BE FORBIDDEN / BAD REQUEST
    review_res = await client.post(
        f"/api/v1/leave/{leave_id}/manager-review",
        json={"action": "APPROVE", "comments": "Approving my own leave"},
        headers={"Authorization": f"Bearer {mgr1_token}"},
    )
    assert review_res.status_code == 400
    assert "cannot approve" in review_res.text.lower() or "self" in review_res.text.lower()


@pytest.mark.asyncio
async def test_unassigned_manager_cannot_review_subordinate(client: AsyncClient, setup_leave_env):
    """Ensures Manager 2 cannot approve leave for Employee who is assigned to Manager 1."""
    env = setup_leave_env
    emp_token = env["emp"]["token"]
    mgr2_token = env["mgr2"]["token"]
    annual_id = str(env["annual_leave"].id)

    res = await client.post(
        "/api/v1/leave/apply",
        json={"leave_type_id": annual_id, "start_date": "2026-12-03", "end_date": "2026-12-04", "reason": "Testing hierarchy"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res.status_code == 201
    leave_id = res.json()["id"]

    # Manager 2 attempts to review
    m2_res = await client.post(
        f"/api/v1/leave/{leave_id}/manager-review",
        json={"action": "APPROVE"},
        headers={"Authorization": f"Bearer {mgr2_token}"},
    )
    assert m2_res.status_code == 400
    assert "not the designated manager" in m2_res.text.lower() or "access denied" in m2_res.text.lower()


@pytest.mark.asyncio
async def test_hr_cannot_review_before_manager_approval(client: AsyncClient, setup_leave_env):
    """Ensures HR cannot bypass or review a leave request before the manager has approved it."""
    env = setup_leave_env
    emp_token = env["emp"]["token"]
    hr_token = env["hr"]["token"]
    annual_id = str(env["annual_leave"].id)

    res = await client.post(
        "/api/v1/leave/apply",
        json={"leave_type_id": annual_id, "start_date": "2026-12-07", "end_date": "2026-12-08", "reason": "Order test"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res.status_code == 201
    leave_id = res.json()["id"]

    # HR attempts review immediately (before manager)
    hr_res = await client.post(
        f"/api/v1/leave/{leave_id}/hr-review",
        json={"action": "APPROVE"},
        headers={"Authorization": f"Bearer {hr_token}"},
    )
    assert hr_res.status_code == 400
    assert "mandatory before hr" in hr_res.text.lower()


# ============================================================================
# 4. Business Rules: Overlaps, Weekends, Holidays, and Half-Days
# ============================================================================

@pytest.mark.asyncio
async def test_overlapping_leave_request_prevention(client: AsyncClient, setup_leave_env):
    """Ensures employee cannot submit overlapping leave applications."""
    env = setup_leave_env
    emp_token = env["emp"]["token"]
    annual_id = str(env["annual_leave"].id)

    # First request: 2026-12-14 to 2026-12-16
    r1 = await client.post(
        "/api/v1/leave/apply",
        json={"leave_type_id": annual_id, "start_date": "2026-12-14", "end_date": "2026-12-16", "reason": "Trip 1"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert r1.status_code == 201

    # Overlapping request: 2026-12-15 to 2026-12-18
    r2 = await client.post(
        "/api/v1/leave/apply",
        json={"leave_type_id": annual_id, "start_date": "2026-12-15", "end_date": "2026-12-18", "reason": "Trip 2"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert r2.status_code == 400
    assert "already exists" in r2.text.lower()


@pytest.mark.asyncio
async def test_weekends_and_holidays_excluded_from_duration(client: AsyncClient, setup_leave_env):
    """
    Validates calculation:
    Range: Thursday 2026-11-19 to Monday 2026-11-23.
    Total calendar days: 5.
    - 2026-11-19: Thursday (Working day -> 1)
    - 2026-11-20: Friday (Company Holiday -> 0)
    - 2026-11-21: Saturday (Weekend -> 0)
    - 2026-11-22: Sunday (Weekend -> 0)
    - 2026-11-23: Monday (Working day -> 1)
    Total charged leave days must equal EXACTLY 2.0.
    """
    env = setup_leave_env
    emp_token = env["emp"]["token"]
    annual_id = str(env["annual_leave"].id)

    res = await client.post(
        "/api/v1/leave/apply",
        json={
            "leave_type_id": annual_id,
            "start_date": "2026-11-19",
            "end_date": "2026-11-23",
            "reason": "Long weekend with holiday",
        },
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["total_days"] == 2.0


@pytest.mark.asyncio
async def test_half_day_leave_workflow_and_attendance(client: AsyncClient, setup_leave_env, db_session: AsyncSession):
    """
    Validates half-day application:
    - total_days = 0.5
    - must start and end on same day
    - AttendanceDay gets status HALF_DAY upon final approval
    """
    env = setup_leave_env
    emp_token = env["emp"]["token"]
    mgr1_token = env["mgr1"]["token"]
    hr_token = env["hr"]["token"]
    sick_id = str(env["sick_leave"].id)

    # Valid half-day application on Tuesday 2026-12-22
    half_day_date = "2026-12-22"
    res = await client.post(
        "/api/v1/leave/apply",
        json={
            "leave_type_id": sick_id,
            "start_date": half_day_date,
            "end_date": half_day_date,
            "is_half_day": True,
            "half_day_period": "FIRST_HALF",
            "reason": "Doctor appointment morning",
        },
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res.status_code == 201, res.text
    leave_id = res.json()["id"]
    assert res.json()["total_days"] == 0.5
    assert res.json()["is_half_day"] is True
    assert res.json()["half_day_period"] == "FIRST_HALF"

    # Manager approves -> HR approves
    await client.post(f"/api/v1/leave/{leave_id}/manager-review", json={"action": "APPROVE"}, headers={"Authorization": f"Bearer {mgr1_token}"})
    await client.post(f"/api/v1/leave/{leave_id}/hr-review", json={"action": "APPROVE"}, headers={"Authorization": f"Bearer {hr_token}"})

    # Verify AttendanceDay status is HALF_DAY
    att_stmt = select(AttendanceDay).where(
        AttendanceDay.employee_id == env["emp"]["emp"].id,
        AttendanceDay.work_date == date(2026, 12, 22),
    )
    att_res = await db_session.execute(att_stmt)
    att_day = att_res.scalars().first()
    assert att_day is not None
    assert att_day.status == AttendanceStatus.HALF_DAY


# ============================================================================
# 5. Withdrawal & Supporting Documents
# ============================================================================

@pytest.mark.asyncio
async def test_employee_withdrawal_restores_balance(client: AsyncClient, setup_leave_env):
    """Validates that employee can cancel a pending leave and restore reserved days."""
    env = setup_leave_env
    emp_token = env["emp"]["token"]
    annual_id = str(env["annual_leave"].id)

    # Apply for 3 days
    res = await client.post(
        "/api/v1/leave/apply",
        json={"leave_type_id": annual_id, "start_date": "2026-12-28", "end_date": "2026-12-30", "reason": "End of year"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res.status_code == 201
    leave_id = res.json()["id"]

    # Withdraw
    w_res = await client.post(
        f"/api/v1/leave/{leave_id}/withdraw",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert w_res.status_code == 200
    assert w_res.json()["status"] == "CANCELLED"
    assert w_res.json()["withdrawn_at"] is not None

    # Verify pending days cleared
    bal_res = await client.get("/api/v1/leave/balances", headers={"Authorization": f"Bearer {emp_token}"})
    bal = next(b for b in bal_res.json() if b["leave_type_id"] == annual_id)
    assert bal["pending_days"] == 0.0


@pytest.mark.asyncio
async def test_supporting_document_upload_and_listing(client: AsyncClient, setup_leave_env):
    """Validates attaching medical certificate / document to leave request."""
    env = setup_leave_env
    emp_token = env["emp"]["token"]
    sick_id = str(env["sick_leave"].id)

    # Apply
    res = await client.post(
        "/api/v1/leave/apply",
        json={"leave_type_id": sick_id, "start_date": "2026-12-31", "end_date": "2026-12-31", "reason": "Hospitalization"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    leave_id = res.json()["id"]

    # Attach document
    doc_payload = {
        "file_name": "medical_certificate_dr_smith.pdf",
        "file_url": "https://storage.altc.corp/docs/med_123.pdf",
        "file_size_bytes": 1048576,
        "mime_type": "application/pdf",
    }
    doc_res = await client.post(
        f"/api/v1/leave/{leave_id}/documents",
        json=doc_payload,
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert doc_res.status_code == 201, doc_res.text
    doc_data = doc_res.json()
    assert doc_data["file_name"] == doc_payload["file_name"]
    assert doc_data["leave_request_id"] == leave_id

    # List documents
    list_res = await client.get(
        f"/api/v1/leave/{leave_id}/documents",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1


# ============================================================================
# 6. Dashboards
# ============================================================================

@pytest.mark.asyncio
async def test_manager_and_hr_dashboards(client: AsyncClient, setup_leave_env):
    """
    Validates dashboard data partitioning:
    - Manager dashboard shows subordinate's request pending manager approval.
    - HR dashboard shows request once manager has approved and it awaits HR approval.
    """
    env = setup_leave_env
    emp_token = env["emp"]["token"]
    mgr1_token = env["mgr1"]["token"]
    mgr2_token = env["mgr2"]["token"]
    hr_token = env["hr"]["token"]
    annual_id = str(env["annual_leave"].id)

    # Employee submits request for next year
    r = await client.post(
        "/api/v1/leave/apply",
        json={"leave_type_id": annual_id, "start_date": "2026-11-26", "end_date": "2026-11-27", "reason": "Dash check"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    leave_id = r.json()["id"]

    # Manager 1 (designated manager) checks dashboard -> sees 1 pending review
    m1_dash = await client.get("/api/v1/leave/dashboard/manager", headers={"Authorization": f"Bearer {mgr1_token}"})
    assert m1_dash.status_code == 200
    assert m1_dash.json()["pending_manager_reviews"] >= 1

    # Manager 2 (not their manager) checks dashboard -> sees 0
    m2_dash = await client.get("/api/v1/leave/dashboard/manager", headers={"Authorization": f"Bearer {mgr2_token}"})
    assert m2_dash.status_code == 200
    assert m2_dash.json()["pending_manager_reviews"] == 0

    # HR checks dashboard before manager approval -> sees 0 pending HR reviews
    hr_dash_before = await client.get("/api/v1/leave/dashboard/hr", headers={"Authorization": f"Bearer {hr_token}"})
    assert hr_dash_before.status_code == 200
    assert not any(item["id"] == leave_id for item in hr_dash_before.json()["recent_requests"])

    # Manager 1 approves
    await client.post(f"/api/v1/leave/{leave_id}/manager-review", json={"action": "APPROVE"}, headers={"Authorization": f"Bearer {mgr1_token}"})

    # HR checks dashboard after manager approval -> sees this request now pending HR review!
    hr_dash_after = await client.get("/api/v1/leave/dashboard/hr", headers={"Authorization": f"Bearer {hr_token}"})
    assert hr_dash_after.status_code == 200
    assert any(item["id"] == leave_id for item in hr_dash_after.json()["recent_requests"])
