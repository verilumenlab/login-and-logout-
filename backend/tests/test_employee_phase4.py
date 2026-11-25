"""
Phase 04 Test Suite:
Employee Lifecycle Management, Department Administration, Manager & HR Assignments,
Search, Filter & Pagination, CSV/Excel Bulk Ingestion, Role Permissions & Audit Logging.
"""

from __future__ import annotations

import io
import uuid
from datetime import date, datetime

import pytest
from httpx import AsyncClient
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.core.seeds import seed_permissions, seed_system_roles
from app.models.auth import AuditLog, User
from app.models.department import Department
from app.models.employee import EmployeeProfile, EmploymentStatus
from app.models.organization import Organization
from app.models.schedule import WorkSchedule


@pytest.fixture
async def setup_employee_env(db_session: AsyncSession):
    """Sets up an isolated test tenant organization with Admin, HR, Manager, and Employee users."""
    perm_map = await seed_permissions(db_session)
    role_map = await seed_system_roles(db_session, perm_map)

    uid = uuid.uuid4().hex[:8]
    org = Organization(
        name=f"Vanguard Industries {uid}",
        slug=f"vanguard-{uid}",
        code=f"VNG_{uid}".upper()[:16],
    )
    db_session.add(org)
    await db_session.flush()

    # Create Work Schedule
    schedule = WorkSchedule(
        organization_id=org.id,
        name="Standard Office Hours",
        shift_start_time=datetime.strptime("09:00", "%H:%M").time(),
        shift_end_time=datetime.strptime("17:00", "%H:%M").time(),
    )
    db_session.add(schedule)

    # Create Department
    engineering_dept = Department(
        organization_id=org.id,
        name="Engineering Division",
        code=f"ENG_{uid}".upper()[:16],
    )
    product_dept = Department(
        organization_id=org.id,
        name="Product Division",
        code=f"PRD_{uid}".upper()[:16],
    )
    db_session.add_all([engineering_dept, product_dept])
    await db_session.flush()

    admin_email = f"admin_{uid}@vanguard.com"
    hr_email = f"hr_{uid}@vanguard.com"
    mgr_email = f"manager_{uid}@vanguard.com"
    emp_email = f"employee_{uid}@vanguard.com"

    admin_user = User(
        organization_id=org.id,
        email=admin_email,
        hashed_password=get_password_hash("AdminPass123!"),
        role_id=role_map["Administrator"].id,
        is_active=True,
        is_superuser=True,
    )
    hr_user = User(
        organization_id=org.id,
        email=hr_email,
        hashed_password=get_password_hash("HrPass123!"),
        role_id=role_map["HR Manager"].id,
        is_active=True,
    )
    mgr_user = User(
        organization_id=org.id,
        email=mgr_email,
        hashed_password=get_password_hash("MgrPass123!"),
        role_id=role_map["Department Manager"].id,
        is_active=True,
    )
    emp_user = User(
        organization_id=org.id,
        email=emp_email,
        hashed_password=get_password_hash("EmpPass123!"),
        role_id=role_map["Employee"].id,
        is_active=True,
    )
    db_session.add_all([admin_user, hr_user, mgr_user, emp_user])
    await db_session.flush()

    # Profiles for HR and Manager
    hr_profile = EmployeeProfile(
        organization_id=org.id,
        user_id=hr_user.id,
        employee_code=f"HR-{uid}"[:20],
        first_name="Harriet",
        last_name="Reed",
        hire_date=date(2024, 1, 1),
        department_id=engineering_dept.id,
    )
    mgr_profile = EmployeeProfile(
        organization_id=org.id,
        user_id=mgr_user.id,
        employee_code=f"MG-{uid}"[:20],
        first_name="Miles",
        last_name="Garrison",
        hire_date=date(2024, 1, 1),
        department_id=engineering_dept.id,
    )
    emp_profile = EmployeeProfile(
        organization_id=org.id,
        user_id=emp_user.id,
        employee_code=f"EM-{uid}"[:20],
        first_name="Evan",
        last_name="Porter",
        hire_date=date(2024, 1, 1),
        department_id=engineering_dept.id,
    )
    db_session.add_all([hr_profile, mgr_profile, emp_profile])
    await db_session.commit()

    return {
        "org": org,
        "uid": uid,
        "schedule": schedule,
        "eng_dept": engineering_dept,
        "prd_dept": product_dept,
        "admin_user": admin_user,
        "hr_user": hr_user,
        "mgr_user": mgr_user,
        "emp_user": emp_user,
        "admin_email": admin_email,
        "hr_email": hr_email,
        "mgr_email": mgr_email,
        "emp_email": emp_email,
        "hr_profile": hr_profile,
        "mgr_profile": mgr_profile,
        "emp_profile": emp_profile,
    }


# ============================================================================
# 1. Department Management Tests
# ============================================================================


@pytest.mark.asyncio
async def test_department_lifecycle(client: AsyncClient, setup_employee_env: dict):
    env = setup_employee_env
    login = await client.post("/api/v1/auth/login", json={"email": env["hr_email"], "password": "HrPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # 1. List departments
    list_res = await client.get("/api/v1/departments/", headers=headers)
    assert list_res.status_code == 200
    depts = list_res.json()
    assert len(depts) >= 2

    # 2. Create department
    new_code = f"FIN_{env['uid']}".upper()[:16]
    create_res = await client.post(
        "/api/v1/departments/",
        headers=headers,
        json={"name": "Finance Department", "code": new_code},
    )
    assert create_res.status_code == 201
    created_dept = create_res.json()
    assert created_dept["name"] == "Finance Department"
    assert created_dept["code"] == new_code

    # 3. Duplicate code rejected
    dup_res = await client.post(
        "/api/v1/departments/",
        headers=headers,
        json={"name": "Duplicate Finance", "code": new_code},
    )
    assert dup_res.status_code == 400

    # 4. Update department
    dept_id = created_dept["id"]
    upd_res = await client.put(
        f"/api/v1/departments/{dept_id}",
        headers=headers,
        json={"name": "Global Finance & Accounting"},
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["name"] == "Global Finance & Accounting"

    # 5. Delete empty department
    del_res = await client.delete(f"/api/v1/departments/{dept_id}", headers=headers)
    assert del_res.status_code == 200


# ============================================================================
# 2. Add Employee & Assign IDs, Departments, Managers, HR & Schedules
# ============================================================================


@pytest.mark.asyncio
async def test_add_employee_with_full_assignments_and_audit_log(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_employee_env: dict,
):
    env = setup_employee_env
    login = await client.post("/api/v1/auth/login", json={"email": env["admin_email"], "password": "AdminPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    emp_code = f"E-{env['uid']}-101".upper()
    emp_email = f"jdoe_{env['uid']}@vanguard.com"

    payload = {
        "first_name": "John",
        "last_name": "Doe",
        "email": emp_email,
        "employee_code": emp_code,
        "phone": "+1-555-0199",
        "job_title": "Senior Staff Architect",
        "department_id": str(env["eng_dept"].id),
        "manager_id": str(env["mgr_profile"].id),
        "hr_rep_id": str(env["hr_profile"].id),
        "work_schedule_id": str(env["schedule"].id),
        "hire_date": "2025-03-01",
        "employment_status": "ACTIVE",
        "initial_password": "NewEmployeeP@ss1",
    }

    res = await client.post("/api/v1/employees/", headers=headers, json=payload)
    assert res.status_code == 201
    data = res.json()

    assert data["employee_code"] == emp_code
    assert data["first_name"] == "John"
    assert data["last_name"] == "Doe"
    assert data["full_name"] == "John Doe"
    assert data["email"] == emp_email
    assert data["department"]["id"] == str(env["eng_dept"].id)
    assert data["work_schedule"]["id"] == str(env["schedule"].id)
    assert data["manager"]["id"] == str(env["mgr_profile"].id)
    assert data["hr_rep"]["id"] == str(env["hr_profile"].id)
    assert data["is_active"] is True
    assert data["temporary_password"] == "NewEmployeeP@ss1"
    assert data["credentials_email_sent"] is False
    assert data["credentials_email_error"]

    # Verify audit log was recorded
    audit_stmt = select(AuditLog).where(
        AuditLog.action == "CREATE",
        AuditLog.entity_type == "employee_profile",
        AuditLog.entity_id == str(data["id"]),
    )
    audit = (await db_session.execute(audit_stmt)).scalars().first()
    assert audit is not None
    assert audit.diff_json["employee_code"] == emp_code

    # Verify employee can log in with initial credentials
    login_emp = await client.post(
        "/api/v1/auth/login", json={"email": emp_email, "password": "NewEmployeeP@ss1", "client_type": "desktop"}
    )
    assert login_emp.status_code == 200


@pytest.mark.asyncio
async def test_add_employee_validation_failures(client: AsyncClient, setup_employee_env: dict):
    env = setup_employee_env
    login = await client.post("/api/v1/auth/login", json={"email": env["hr_email"], "password": "HrPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # 1. Duplicate email rejection
    dup_email_payload = {
        "first_name": "Duplicate",
        "last_name": "Email",
        "email": env["emp_email"],  # already used
        "employee_code": f"DUP-{env['uid']}",
        "hire_date": "2025-01-01",
    }
    r1 = await client.post("/api/v1/employees/", headers=headers, json=dup_email_payload)
    assert r1.status_code == 400
    assert "already exists" in r1.json()["detail"]

    # 2. Duplicate employee code rejection
    dup_code_payload = {
        "first_name": "Duplicate",
        "last_name": "Code",
        "email": f"unique_{env['uid']}@vanguard.com",
        "employee_code": env["emp_profile"].employee_code,  # already used
        "hire_date": "2025-01-01",
    }
    r2 = await client.post("/api/v1/employees/", headers=headers, json=dup_code_payload)
    assert r2.status_code == 400
    assert "already assigned" in r2.json()["detail"]


# ============================================================================
# 3. Edit Employee Profile & Manager/HR Updates
# ============================================================================


@pytest.mark.asyncio
async def test_edit_employee_profile_and_manager_assignment(
    client: AsyncClient,
    db_session: AsyncSession,
    setup_employee_env: dict,
):
    env = setup_employee_env
    login = await client.post("/api/v1/auth/login", json={"email": env["admin_email"], "password": "AdminPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    emp_id = env["emp_profile"].id

    update_payload = {
        "job_title": "Lead Software Engineer",
        "phone": "+1-555-9876",
        "department_id": str(env["prd_dept"].id),
        "manager_id": str(env["mgr_profile"].id),
        "hr_rep_id": str(env["hr_profile"].id),
    }

    upd_res = await client.put(f"/api/v1/employees/{emp_id}", headers=headers, json=update_payload)
    assert upd_res.status_code == 200
    data = upd_res.json()

    assert data["job_title"] == "Lead Software Engineer"
    assert data["phone"] == "+1-555-9876"
    assert data["department"]["id"] == str(env["prd_dept"].id)
    assert data["manager"]["id"] == str(env["mgr_profile"].id)

    # Verify audit log
    audit_stmt = select(AuditLog).where(
        AuditLog.action == "UPDATE",
        AuditLog.entity_type == "employee_profile",
        AuditLog.entity_id == str(emp_id),
    )
    audit = (await db_session.execute(audit_stmt)).scalars().first()
    assert audit is not None
    assert "job_title" in audit.diff_json


@pytest.mark.asyncio
async def test_admin_can_change_employee_email(client: AsyncClient, setup_employee_env: dict):
    env = setup_employee_env
    login = await client.post("/api/v1/auth/login", json={"email": env["admin_email"], "password": "AdminPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    emp_id = env["emp_profile"].id

    # Address already used by another account is rejected
    dup = await client.put(f"/api/v1/employees/{emp_id}", headers=headers, json={"email": env["hr_email"]})
    assert dup.status_code == 400
    assert "already exists" in dup.json()["detail"]

    # Invalid address is rejected
    bad = await client.put(f"/api/v1/employees/{emp_id}", headers=headers, json={"email": "not-an-email"})
    assert bad.status_code == 422

    # New address is saved (lower-cased) and returned
    new_email = f"New.Address_{env['uid']}@vanguard.com"
    ok = await client.put(f"/api/v1/employees/{emp_id}", headers=headers, json={"email": new_email})
    assert ok.status_code == 200
    assert ok.json()["email"] == new_email.lower()

    # Saved on the account: the detail view shows the new address
    detail = await client.get(f"/api/v1/employees/{emp_id}", headers=headers)
    assert detail.json()["email"] == new_email.lower()


@pytest.mark.asyncio
async def test_admin_assigns_portal_roles(client: AsyncClient, setup_employee_env: dict):
    env = setup_employee_env
    login = await client.post("/api/v1/auth/login", json={"email": env["admin_email"], "password": "AdminPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    emp_id = env["emp_profile"].id

    detail = await client.get(f"/api/v1/employees/{emp_id}", headers=headers)
    assert detail.json()["role_name"] == "Employee"

    promote = await client.put(f"/api/v1/employees/{emp_id}", headers=headers, json={"role_name": "HR Manager"})
    assert promote.status_code == 200
    assert promote.json()["role_name"] == "HR Manager"

    # The promoted account can now use the web portal's HR features.
    hr_login = await client.post("/api/v1/auth/login", json={"email": env["emp_email"], "password": "EmpPass123!"})
    assert hr_login.status_code == 200
    assert hr_login.json()["user"]["role"] == "HR Manager"

    created = await client.post(
        "/api/v1/employees/",
        headers=headers,
        json={
            "first_name": "Maya",
            "last_name": "Lead",
            "email": f"maya_{env['uid']}@vanguard.com",
            "employee_code": f"ML-{env['uid']}",
            "hire_date": "2025-01-01",
            "role_name": "Department Manager",
        },
    )
    assert created.status_code == 201
    assert created.json()["role_name"] == "Department Manager"

    unknown = await client.put(f"/api/v1/employees/{emp_id}", headers=headers, json={"role_name": "Wizard"})
    assert unknown.status_code == 400


@pytest.mark.asyncio
async def test_hr_cannot_grant_admin_or_change_own_role(client: AsyncClient, setup_employee_env: dict):
    env = setup_employee_env
    login = await client.post("/api/v1/auth/login", json={"email": env["hr_email"], "password": "HrPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    escalate = await client.put(
        f"/api/v1/employees/{env['emp_profile'].id}", headers=headers, json={"role_name": "Administrator"}
    )
    assert escalate.status_code == 403

    create_admin = await client.post(
        "/api/v1/employees/",
        headers=headers,
        json={
            "first_name": "Sneaky",
            "last_name": "Admin",
            "email": f"sneaky_{env['uid']}@vanguard.com",
            "employee_code": f"SA-{env['uid']}",
            "hire_date": "2025-01-01",
            "role_name": "Administrator",
        },
    )
    assert create_admin.status_code == 403

    own = await client.put(
        f"/api/v1/employees/{env['hr_profile'].id}", headers=headers, json={"role_name": "Department Manager"}
    )
    assert own.status_code == 403

    promote_mgr = await client.put(
        f"/api/v1/employees/{env['emp_profile'].id}", headers=headers, json={"role_name": "Department Manager"}
    )
    assert promote_mgr.status_code == 200
    assert promote_mgr.json()["role_name"] == "Department Manager"


# ============================================================================
# 4. Activate & Deactivate Employee Lifecycle
# ============================================================================


@pytest.mark.asyncio
async def test_activate_and_deactivate_employee(client: AsyncClient, setup_employee_env: dict):
    env = setup_employee_env
    admin_login = await client.post("/api/v1/auth/login", json={"email": env["admin_email"], "password": "AdminPass123!"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    emp_id = env["emp_profile"].id

    # 1. Deactivate employee
    deact_res = await client.post(
        f"/api/v1/employees/{emp_id}/status?is_active=false",
        headers=admin_headers,
    )
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False

    # 2. Deactivated employee cannot log in
    emp_login = await client.post(
        "/api/v1/auth/login", json={"email": env["emp_email"], "password": "EmpPass123!", "client_type": "desktop"}
    )
    assert emp_login.status_code == 403
    assert "deactivated" in emp_login.json()["detail"]

    # 3. Reactivate employee
    act_res = await client.post(
        f"/api/v1/employees/{emp_id}/status?is_active=true",
        headers=admin_headers,
    )
    assert act_res.status_code == 200
    assert act_res.json()["is_active"] is True

    # 4. Reactivated employee can log in again
    emp_login2 = await client.post(
        "/api/v1/auth/login", json={"email": env["emp_email"], "password": "EmpPass123!", "client_type": "desktop"}
    )
    assert emp_login2.status_code == 200


# ============================================================================
# 5. Search, Filter, and Pagination Tests
# ============================================================================


@pytest.mark.asyncio
async def test_search_filter_and_pagination(client: AsyncClient, setup_employee_env: dict):
    env = setup_employee_env
    login = await client.post("/api/v1/auth/login", json={"email": env["admin_email"], "password": "AdminPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # 1. Substring search by first name
    r_search = await client.get("/api/v1/employees/?search=Evan", headers=headers)
    assert r_search.status_code == 200
    data = r_search.json()
    assert data["total"] >= 1
    assert any(emp["first_name"] == "Evan" for emp in data["items"])

    # 2. Filter by department
    r_dept = await client.get(f"/api/v1/employees/?department_id={env['eng_dept'].id}", headers=headers)
    assert r_dept.status_code == 200
    assert r_dept.json()["total"] >= 1

    # 3. Filter by employment status
    r_status = await client.get("/api/v1/employees/?employment_status=ACTIVE", headers=headers)
    assert r_status.status_code == 200
    assert r_status.json()["total"] >= 1

    # 4. Pagination
    r_page = await client.get("/api/v1/employees/?page=1&page_size=2", headers=headers)
    assert r_page.status_code == 200
    pdata = r_page.json()
    assert len(pdata["items"]) <= 2
    assert pdata["page"] == 1
    assert pdata["page_size"] == 2


# ============================================================================
# 6. Bulk Import via CSV & Excel Tests
# ============================================================================


@pytest.mark.asyncio
async def test_bulk_import_via_csv(client: AsyncClient, setup_employee_env: dict):
    env = setup_employee_env
    login = await client.post("/api/v1/auth/login", json={"email": env["hr_email"], "password": "HrPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    csv_content = f"""first_name,last_name,email,employee_code,hire_date,job_title,department_code
Alice,Smith,alice_{env['uid']}@vanguard.com,E-CSV-1_{env['uid']},2025-01-15,Frontend Engineer,{env['eng_dept'].code}
Bob,Jones,bob_{env['uid']}@vanguard.com,E-CSV-2_{env['uid']},2025-02-01,QA Engineer,{env['eng_dept'].code}
"""

    files = {"file": ("employees.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = await client.post("/api/v1/employees/import", headers=headers, files=files)
    assert res.status_code == 200
    data = res.json()

    assert data["success_count"] == 2
    assert data["error_count"] == 0
    assert len(data["imported_employees"]) == 2


@pytest.mark.asyncio
async def test_bulk_import_via_excel(client: AsyncClient, setup_employee_env: dict):
    env = setup_employee_env
    login = await client.post("/api/v1/auth/login", json={"email": env["admin_email"], "password": "AdminPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Generate in-memory Excel file
    wb = Workbook()
    ws = wb.active
    ws.title = "Employees"
    ws.append(["first_name", "last_name", "email", "employee_code", "hire_date", "job_title", "department_code"])
    ws.append(["Charlie", "Brown", f"charlie_{env['uid']}@vanguard.com", f"E-XLS-1_{env['uid']}", "2025-03-01", "DevOps Engineer", env["eng_dept"].code])
    ws.append(["Diana", "Prince", f"diana_{env['uid']}@vanguard.com", f"E-XLS-2_{env['uid']}", "2025-03-15", "Security Analyst", env["eng_dept"].code])

    excel_buffer = io.BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)

    files = {"file": ("employees.xlsx", excel_buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    res = await client.post("/api/v1/employees/import", headers=headers, files=files)
    assert res.status_code == 200
    data = res.json()

    assert data["success_count"] == 2
    assert data["error_count"] == 0
    assert len(data["imported_employees"]) == 2


@pytest.mark.asyncio
async def test_bulk_import_validation_errors(client: AsyncClient, setup_employee_env: dict):
    env = setup_employee_env
    login = await client.post("/api/v1/auth/login", json={"email": env["hr_email"], "password": "HrPass123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Invalid rows: missing code, duplicate email, invalid date
    bad_csv = f"""first_name,last_name,email,employee_code,hire_date
NoCode,User,nocode_{env['uid']}@vanguard.com,,2025-01-01
Duplicate,User,{env['emp_email']},BAD-01,2025-01-01
BadDate,User,baddate_{env['uid']}@vanguard.com,BAD-02,not-a-date
"""
    files = {"file": ("bad_employees.csv", io.BytesIO(bad_csv.encode("utf-8")), "text/csv")}
    res = await client.post("/api/v1/employees/import", headers=headers, files=files)
    assert res.status_code == 200
    data = res.json()

    assert data["success_count"] == 0
    assert data["error_count"] == 3
    assert len(data["errors"]) == 3


# ============================================================================
# 7. Role Permissions & Unauthorized Access Enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_unauthorized_employee_cannot_manage_personnel(client: AsyncClient, setup_employee_env: dict):
    env = setup_employee_env
    emp_login = await client.post(
        "/api/v1/auth/login", json={"email": env["emp_email"], "password": "EmpPass123!", "client_type": "desktop"}
    )
    emp_headers = {"Authorization": f"Bearer {emp_login.json()['access_token']}"}

    # 1. Standard employee CANNOT create employee
    payload = {
        "first_name": "Rogue",
        "last_name": "Create",
        "email": f"rogue_{env['uid']}@vanguard.com",
        "employee_code": f"ROGUE-{env['uid']}",
        "hire_date": "2025-01-01",
    }
    r_create = await client.post("/api/v1/employees/", headers=emp_headers, json=payload)
    assert r_create.status_code == 403

    # 2. Standard employee CANNOT update employee
    r_update = await client.put(f"/api/v1/employees/{env['emp_profile'].id}", headers=emp_headers, json={"job_title": "CEO"})
    assert r_update.status_code == 403

    # 3. Standard employee CANNOT toggle employee status
    r_status = await client.post(f"/api/v1/employees/{env['emp_profile'].id}/status?is_active=false", headers=emp_headers)
    assert r_status.status_code == 403

    # 4. Standard employee CANNOT import employees
    dummy_csv = "first_name,last_name,email,employee_code,hire_date\nA,B,c@d.com,E-1,2025-01-01\n"
    r_import = await client.post(
        "/api/v1/employees/import",
        headers=emp_headers,
        files={"file": ("test.csv", io.BytesIO(dummy_csv.encode("utf-8")), "text/csv")},
    )
    assert r_import.status_code == 403

    # 5. Standard employee CANNOT create department
    r_dept = await client.post("/api/v1/departments/", headers=emp_headers, json={"name": "Hacked Dept", "code": "HACK"})
    assert r_dept.status_code == 403


@pytest.mark.asyncio
async def test_hr_cannot_see_or_assign_system_administrator(
    client: AsyncClient, db_session: AsyncSession, setup_employee_env: dict
):
    """System Administrator (is_superuser) is hidden from HR directory and create pickers."""
    env = setup_employee_env
    admin_profile = EmployeeProfile(
        organization_id=env["org"].id,
        user_id=env["admin_user"].id,
        employee_code="ADMIN-001",
        first_name="System",
        last_name="Administrator",
        hire_date=date(2024, 1, 1),
        employment_status=EmploymentStatus.ACTIVE,
    )
    db_session.add(admin_profile)
    await db_session.commit()
    await db_session.refresh(admin_profile)

    hr_login = await client.post("/api/v1/auth/login", json={"email": env["hr_email"], "password": "HrPass123!"})
    hr_headers = {"Authorization": f"Bearer {hr_login.json()['access_token']}"}

    listed = await client.get("/api/v1/employees/?page_size=100", headers=hr_headers)
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()["items"]}
    assert str(admin_profile.id) not in ids
    assert str(env["emp_profile"].id) in ids
    assert all(item["employee_code"] != "ADMIN-001" for item in listed.json()["items"])

    detail = await client.get(f"/api/v1/employees/{admin_profile.id}", headers=hr_headers)
    assert detail.status_code == 404

    assign = await client.post(
        "/api/v1/employees/",
        headers=hr_headers,
        json={
            "first_name": "New",
            "last_name": "Hire",
            "email": f"newhire_{env['uid']}@vanguard.com",
            "employee_code": f"NH-{env['uid']}",
            "hire_date": "2025-06-01",
            "manager_id": str(admin_profile.id),
        },
    )
    assert assign.status_code == 400
    assert "System Administrator" in assign.json()["detail"]

    admin_login = await client.post(
        "/api/v1/auth/login", json={"email": env["admin_email"], "password": "AdminPass123!"}
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    admin_list = await client.get("/api/v1/employees/?page_size=100", headers=admin_headers)
    assert admin_list.status_code == 200
    admin_ids = {item["id"] for item in admin_list.json()["items"]}
    assert str(env["emp_profile"].id) in admin_ids
    assert str(admin_profile.id) in admin_ids
    emp_role = next(i for i in admin_list.json()["items"] if i["id"] == str(env["emp_profile"].id))
    assert emp_role["role_name"] == "Employee"

    emp_detail = await client.get(f"/api/v1/employees/{env['emp_profile'].id}", headers=admin_headers)
    assert emp_detail.status_code == 200
    assert emp_detail.json()["full_name"].startswith("Evan")
