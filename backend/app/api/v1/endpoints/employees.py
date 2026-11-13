"""
Employee Lifecycle, Directory, Bulk Import & Profile Management Endpoints
"""

from __future__ import annotations

import csv
import io
import secrets
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel
from openpyxl import load_workbook
from sqlalchemy import delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.file_security import sanitize_filename, validate_file_content
from app.core.dependencies import (
    check_employee_record_access,
    get_current_active_user,
    require_role,
)
from app.core.security import get_password_hash
from app.models.auth import AuditLog, RefreshToken, Role, User
from app.models.department import Department
from app.models.employee import EmployeeProfile, EmploymentStatus, ManagerAssignment
from app.models.schedule import WorkSchedule
from app.schemas.employee import (
    DepartmentBrief,
    EmployeeCreate,
    EmployeeImportResult,
    EmployeeImportRowError,
    EmployeeManagerInfo,
    EmployeePagination,
    EmployeeResponse,
    EmployeeUpdate,
    WorkScheduleBrief,
)

router = APIRouter()


async def _resolve_employee_response(emp: EmployeeProfile, db: AsyncSession) -> EmployeeResponse:
    """Helper to transform EmployeeProfile ORM instance into full EmployeeResponse."""
    full_name = f"{emp.first_name} {emp.last_name}".strip()

    # Department
    dept_brief = None
    if emp.department:
        dept_brief = DepartmentBrief(
            id=emp.department.id,
            name=emp.department.name,
            code=emp.department.code,
        )

    # Work Schedule
    sched_brief = None
    if emp.work_schedule:
        sched_brief = WorkScheduleBrief(
            id=emp.work_schedule.id,
            name=emp.work_schedule.name,
            shift_start_time=emp.work_schedule.shift_start_time.strftime("%H:%M"),
            shift_end_time=emp.work_schedule.shift_end_time.strftime("%H:%M"),
        )

    # Manager
    mgr_info = None
    mgr_stmt = (
        select(EmployeeProfile)
        .join(ManagerAssignment, ManagerAssignment.manager_id == EmployeeProfile.id)
        .options(selectinload(EmployeeProfile.user))
        .where(
            ManagerAssignment.employee_id == emp.id,
        )
        .order_by(desc(ManagerAssignment.is_primary))
    )
    mgr_res = await db.execute(mgr_stmt)
    mgr_profile = mgr_res.scalars().first()
    if mgr_profile:
        mgr_info = EmployeeManagerInfo(
            id=mgr_profile.id,
            employee_code=mgr_profile.employee_code,
            first_name=mgr_profile.first_name,
            last_name=mgr_profile.last_name,
            email=mgr_profile.user.email if mgr_profile.user else None,
            job_title=mgr_profile.job_title,
        )

    # HR Representative
    hr_info = None
    hr_rep_id_raw = (emp.metadata_json or {}).get("hr_rep_id")
    if hr_rep_id_raw:
        try:
            hr_rep_id = uuid.UUID(str(hr_rep_id_raw))
            hr_res = await db.execute(
                select(EmployeeProfile)
                .options(selectinload(EmployeeProfile.user))
                .where(EmployeeProfile.id == hr_rep_id)
            )
            hr_prof = hr_res.scalars().first()
            if hr_prof:
                hr_info = EmployeeManagerInfo(
                    id=hr_prof.id,
                    employee_code=hr_prof.employee_code,
                    first_name=hr_prof.first_name,
                    last_name=hr_prof.last_name,
                    email=hr_prof.user.email if hr_prof.user else None,
                    job_title=hr_prof.job_title,
                )
        except (ValueError, TypeError):
            pass

    return EmployeeResponse(
        id=emp.id,
        user_id=emp.user_id,
        organization_id=emp.organization_id,
        employee_code=emp.employee_code,
        first_name=emp.first_name,
        last_name=emp.last_name,
        full_name=full_name,
        email=emp.user.email if emp.user else "",
        phone=emp.phone,
        job_title=emp.job_title,
        department_id=emp.department_id,
        department=dept_brief,
        work_schedule_id=emp.work_schedule_id,
        work_schedule=sched_brief,
        hire_date=emp.hire_date,
        termination_date=emp.termination_date,
        employment_status=emp.employment_status,
        is_active=emp.user.is_active if emp.user else True,
        manager=mgr_info,
        hr_rep=hr_info,
        metadata_json=emp.metadata_json,
        created_at=emp.created_at,
        updated_at=emp.updated_at,
    )


@router.get("/", response_model=EmployeePagination)
async def list_employees(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(default=None, description="Search by name, email, employee code, or job title"),
    department_id: uuid.UUID | None = Query(default=None, description="Filter by department"),
    employment_status: EmploymentStatus | None = Query(default=None, description="Filter by employment status"),
    is_active: bool | None = Query(default=None, description="Filter by user active status"),
    manager_id: uuid.UUID | None = Query(default=None, description="Filter by assigned direct manager"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
) -> EmployeePagination:
    """
    Search, filter, and paginate organizational personnel directory.
    Supports multi-criteria filtering and full-text substring matching.
    """
    base_query = (
        select(EmployeeProfile)
        .join(User, User.id == EmployeeProfile.user_id)
        .options(
            selectinload(EmployeeProfile.user),
            selectinload(EmployeeProfile.department),
            selectinload(EmployeeProfile.work_schedule),
            selectinload(EmployeeProfile.direct_managers)
            .selectinload(ManagerAssignment.manager)
            .selectinload(EmployeeProfile.user),
        )
        .where(EmployeeProfile.organization_id == current_user.organization_id)
    )

    count_query = (
        select(func.count(EmployeeProfile.id))
        .join(User, User.id == EmployeeProfile.user_id)
        .where(EmployeeProfile.organization_id == current_user.organization_id)
    )

    # 1. Search Filter
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        search_filter = or_(
            func.lower(EmployeeProfile.first_name).like(term),
            func.lower(EmployeeProfile.last_name).like(term),
            func.lower(EmployeeProfile.employee_code).like(term),
            func.lower(EmployeeProfile.job_title).like(term),
            func.lower(User.email).like(term),
        )
        base_query = base_query.where(search_filter)
        count_query = count_query.where(search_filter)

    # 2. Department Filter
    if department_id:
        base_query = base_query.where(EmployeeProfile.department_id == department_id)
        count_query = count_query.where(EmployeeProfile.department_id == department_id)

    # 3. Employment Status Filter
    if employment_status:
        base_query = base_query.where(EmployeeProfile.employment_status == employment_status)
        count_query = count_query.where(EmployeeProfile.employment_status == employment_status)

    # 4. User Active Filter
    if is_active is not None:
        base_query = base_query.where(User.is_active == is_active)
        count_query = count_query.where(User.is_active == is_active)

    # 5. Manager Subordinates Filter
    if manager_id:
        base_query = base_query.join(
            ManagerAssignment,
            ManagerAssignment.employee_id == EmployeeProfile.id,
        ).where(ManagerAssignment.manager_id == manager_id)
        count_query = count_query.join(
            ManagerAssignment,
            ManagerAssignment.employee_id == EmployeeProfile.id,
        ).where(ManagerAssignment.manager_id == manager_id)

    # Execute Count
    total = (await db.execute(count_query)).scalar_one()

    # Apply Pagination & Ordering
    offset = (page - 1) * page_size
    paged_query = base_query.order_by(desc(EmployeeProfile.created_at)).offset(offset).limit(page_size)
    records = (await db.execute(paged_query)).scalars().all()

    items: list[EmployeeResponse] = []
    for emp in records:
        items.append(await _resolve_employee_response(emp, db))

    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

    return EmployeePagination(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    payload: EmployeeCreate,
    request: Request,
    current_user: Annotated[
        User, Depends(require_role("Super Administrator", "Administrator", "HR Manager", "Admin", "HR"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeResponse:
    """
    Onboard a new employee with user credentials, profile attributes,
    department, work schedule, manager, and HR representative assignments.
    """
    clean_email = payload.email.strip().lower()
    clean_code = payload.employee_code.strip().upper()

    # 1. Validate Email Uniqueness in Organization
    email_check = await db.execute(
        select(User).where(
            User.organization_id == current_user.organization_id,
            func.lower(User.email) == clean_email,
        )
    )
    if email_check.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An account with email '{clean_email}' already exists in this organization.",
        )

    # 2. Validate Employee Code Uniqueness in Organization
    code_check = await db.execute(
        select(EmployeeProfile).where(
            EmployeeProfile.organization_id == current_user.organization_id,
            func.upper(EmployeeProfile.employee_code) == clean_code,
        )
    )
    if code_check.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Employee code '{clean_code}' is already assigned to another staff member.",
        )

    # 3. Validate Department (if provided)
    if payload.department_id:
        dept_check = await db.execute(
            select(Department).where(
                Department.id == payload.department_id,
                Department.organization_id == current_user.organization_id,
            )
        )
        if not dept_check.scalars().first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected department was not found.")

    # 4. Validate Work Schedule (if provided)
    if payload.work_schedule_id:
        sched_check = await db.execute(
            select(WorkSchedule).where(
                WorkSchedule.id == payload.work_schedule_id,
                WorkSchedule.organization_id == current_user.organization_id,
            )
        )
        if not sched_check.scalars().first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected work schedule was not found.")

    # 5. Validate Manager (if provided)
    if payload.manager_id:
        mgr_check = await db.execute(
            select(EmployeeProfile).where(
                EmployeeProfile.id == payload.manager_id,
                EmployeeProfile.organization_id == current_user.organization_id,
            )
        )
        if not mgr_check.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Selected reporting manager was not found."
            )

    # 6. Validate HR Representative (if provided)
    if payload.hr_rep_id:
        hr_check = await db.execute(
            select(EmployeeProfile).where(
                EmployeeProfile.id == payload.hr_rep_id,
                EmployeeProfile.organization_id == current_user.organization_id,
            )
        )
        if not hr_check.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Selected HR representative was not found."
            )

    # 7. Resolve Role for User Account
    raw_role = (payload.role_name or "Employee").strip()
    alias_map = {
        "admin": "Administrator",
        "administrator": "Administrator",
        "hr": "HR Manager",
        "hr manager": "HR Manager",
        "manager": "Department Manager",
        "department manager": "Department Manager",
        "employee": "Employee",
        "staff": "Employee",
    }
    role_target_name = alias_map.get(raw_role.lower(), raw_role)
    role_stmt = select(Role).where(
        or_(
            Role.organization_id == current_user.organization_id,
            Role.organization_id.is_(None),
        ),
        func.lower(Role.name) == role_target_name.strip().lower(),
    )
    role_res = await db.execute(role_stmt)
    role = role_res.scalars().first()
    if not role:
        # Fallback to any default employee role
        fb_res = await db.execute(select(Role).where(func.lower(Role.name) == "employee"))
        role = fb_res.scalars().first()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Default role not configured."
            )

    # 8. Create User Account (Argon2id password)
    raw_password = payload.initial_password or "ChangeMe123!"
    user = User(
        organization_id=current_user.organization_id,
        email=clean_email,
        hashed_password=get_password_hash(raw_password),
        role_id=role.id,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # 9. Create Employee Profile
    meta: dict[str, Any] = {}
    if payload.hr_rep_id:
        meta["hr_rep_id"] = str(payload.hr_rep_id)

    profile = EmployeeProfile(
        organization_id=current_user.organization_id,
        user_id=user.id,
        employee_code=clean_code,
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        phone=payload.phone.strip() if payload.phone else None,
        job_title=payload.job_title.strip() if payload.job_title else None,
        department_id=payload.department_id,
        work_schedule_id=payload.work_schedule_id,
        hire_date=payload.hire_date,
        employment_status=payload.employment_status,
        metadata_json=meta,
    )
    db.add(profile)
    await db.flush()

    # 10. Manager Assignment
    if payload.manager_id:
        mgr_link = ManagerAssignment(
            organization_id=current_user.organization_id,
            employee_id=profile.id,
            manager_id=payload.manager_id,
            is_primary=True,
        )
        db.add(mgr_link)

    # 11. Audit Logging
    client_ip = request.client.host if request.client else None
    audit = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="CREATE",
        entity_type="employee_profile",
        entity_id=str(profile.id),
        ip_address=client_ip,
        diff_json={
            "employee_code": profile.employee_code,
            "email": clean_email,
            "name": f"{profile.first_name} {profile.last_name}",
            "job_title": profile.job_title,
            "hire_date": str(profile.hire_date),
            "department_id": str(profile.department_id) if profile.department_id else None,
            "manager_id": str(payload.manager_id) if payload.manager_id else None,
        },
    )
    db.add(audit)
    # Enqueue onboarding credentials notification
    try:
        from app.services.email_service import EmailService
        await EmailService.notify_employee_account_creation(
            db=db,
            employee_id=profile.id,
            temporary_password=raw_password,
        )
    except Exception:
        pass
    await db.commit()

    # Reload full profile with relationships
    stmt = (
        select(EmployeeProfile)
        .options(
            selectinload(EmployeeProfile.user),
            selectinload(EmployeeProfile.department),
            selectinload(EmployeeProfile.work_schedule),
            selectinload(EmployeeProfile.direct_managers)
            .selectinload(ManagerAssignment.manager)
            .selectinload(EmployeeProfile.user),
        )
        .where(EmployeeProfile.id == profile.id)
    )
    reloaded = (await db.execute(stmt)).scalars().first()
    if not reloaded:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reload created record")
    return await _resolve_employee_response(reloaded, db)


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee_details(
    employee_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeResponse:
    """Retrieve full employee profile by employee UUID."""
    stmt = (
        select(EmployeeProfile)
        .options(
            selectinload(EmployeeProfile.user),
            selectinload(EmployeeProfile.department),
            selectinload(EmployeeProfile.work_schedule),
            selectinload(EmployeeProfile.direct_managers)
            .selectinload(ManagerAssignment.manager)
            .selectinload(EmployeeProfile.user),
        )
        .where(
            EmployeeProfile.id == employee_id,
            EmployeeProfile.organization_id == current_user.organization_id,
        )
    )
    res = await db.execute(stmt)
    emp = res.scalars().first()
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    return await _resolve_employee_response(emp, db)


@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
    request: Request,
    current_user: Annotated[
        User, Depends(require_role("Super Administrator", "Administrator", "HR Manager", "Admin", "HR"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeResponse:
    """Edit personnel record, reporting managers, schedule, and activation status."""
    stmt = (
        select(EmployeeProfile)
        .options(
            selectinload(EmployeeProfile.user),
            selectinload(EmployeeProfile.department),
            selectinload(EmployeeProfile.work_schedule),
            selectinload(EmployeeProfile.direct_managers),
        )
        .where(
            EmployeeProfile.id == employee_id,
            EmployeeProfile.organization_id == current_user.organization_id,
        )
    )
    res = await db.execute(stmt)
    emp = res.scalars().first()
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    diff: dict[str, object] = {}

    # 1. Update Employee Code
    if payload.employee_code is not None:
        new_code = payload.employee_code.strip().upper()
        if new_code != emp.employee_code:
            code_check = await db.execute(
                select(EmployeeProfile).where(
                    EmployeeProfile.organization_id == current_user.organization_id,
                    func.upper(EmployeeProfile.employee_code) == new_code,
                    EmployeeProfile.id != employee_id,
                )
            )
            if code_check.scalars().first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Employee code '{new_code}' is already assigned to another employee.",
                )
            diff["employee_code"] = {"old": emp.employee_code, "new": new_code}
            emp.employee_code = new_code

    # 2. Personal & Job Details
    if payload.first_name is not None and payload.first_name.strip() != emp.first_name:
        diff["first_name"] = {"old": emp.first_name, "new": payload.first_name.strip()}
        emp.first_name = payload.first_name.strip()

    if payload.last_name is not None and payload.last_name.strip() != emp.last_name:
        diff["last_name"] = {"old": emp.last_name, "new": payload.last_name.strip()}
        emp.last_name = payload.last_name.strip()

    if payload.phone is not None and payload.phone != emp.phone:
        diff["phone"] = {"old": emp.phone, "new": payload.phone}
        emp.phone = payload.phone.strip() if payload.phone else None

    if payload.job_title is not None and payload.job_title != emp.job_title:
        diff["job_title"] = {"old": emp.job_title, "new": payload.job_title}
        emp.job_title = payload.job_title.strip() if payload.job_title else None

    # 3. Department
    if payload.department_id is not None:
        if payload.department_id != emp.department_id:
            dept_res = await db.execute(
                select(Department).where(
                    Department.id == payload.department_id,
                    Department.organization_id == current_user.organization_id,
                )
            )
            new_dept = dept_res.scalars().first()
            if not new_dept:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department not found")
            diff["department_id"] = {
                "old": str(emp.department_id) if emp.department_id else None,
                "new": str(payload.department_id),
            }
            emp.department_id = payload.department_id
            emp.department = new_dept

    # 4. Work Schedule
    if payload.work_schedule_id is not None:
        if payload.work_schedule_id != emp.work_schedule_id:
            sched_res = await db.execute(
                select(WorkSchedule).where(
                    WorkSchedule.id == payload.work_schedule_id,
                    WorkSchedule.organization_id == current_user.organization_id,
                )
            )
            new_sched = sched_res.scalars().first()
            if not new_sched:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Work schedule not found")
            diff["work_schedule_id"] = {
                "old": str(emp.work_schedule_id) if emp.work_schedule_id else None,
                "new": str(payload.work_schedule_id),
            }
            emp.work_schedule_id = payload.work_schedule_id
            emp.work_schedule = new_sched

    # 5. Dates & Status
    if payload.hire_date is not None and payload.hire_date != emp.hire_date:
        diff["hire_date"] = {"old": str(emp.hire_date), "new": str(payload.hire_date)}
        emp.hire_date = payload.hire_date

    if payload.termination_date is not None and payload.termination_date != emp.termination_date:
        diff["termination_date"] = {
            "old": str(emp.termination_date) if emp.termination_date else None,
            "new": str(payload.termination_date),
        }
        emp.termination_date = payload.termination_date

    if payload.employment_status is not None and payload.employment_status != emp.employment_status:
        diff["employment_status"] = {"old": emp.employment_status, "new": payload.employment_status}
        emp.employment_status = payload.employment_status

    # 6. Manager Assignment Update
    if payload.manager_id is not None:
        if payload.manager_id == emp.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee cannot be their own manager.")

        mgr_res = await db.execute(
            select(EmployeeProfile).where(
                EmployeeProfile.id == payload.manager_id,
                EmployeeProfile.organization_id == current_user.organization_id,
            )
        )
        if not mgr_res.scalars().first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reporting manager not found")

        # Upsert manager assignment
        existing_mgr_link = next((m for m in emp.direct_managers if m.is_primary), None)
        if existing_mgr_link:
            diff["manager_id"] = {"old": str(existing_mgr_link.manager_id), "new": str(payload.manager_id)}
            existing_mgr_link.manager_id = payload.manager_id
        else:
            diff["manager_id"] = {"old": None, "new": str(payload.manager_id)}
            new_mgr_link = ManagerAssignment(
                organization_id=current_user.organization_id,
                employee_id=emp.id,
                manager_id=payload.manager_id,
                is_primary=True,
            )
            db.add(new_mgr_link)

    # 7. HR Representative Update in metadata
    if payload.hr_rep_id is not None:
        hr_res = await db.execute(
            select(EmployeeProfile).where(
                EmployeeProfile.id == payload.hr_rep_id,
                EmployeeProfile.organization_id == current_user.organization_id,
            )
        )
        if not hr_res.scalars().first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="HR representative not found")

        current_meta = dict(emp.metadata_json or {})
        old_hr = current_meta.get("hr_rep_id")
        current_meta["hr_rep_id"] = str(payload.hr_rep_id)
        diff["hr_rep_id"] = {"old": old_hr, "new": str(payload.hr_rep_id)}
        emp.metadata_json = current_meta

    # 8. User Activation State Toggle
    if payload.is_active is not None and emp.user:
        if payload.is_active != emp.user.is_active:
            diff["is_active"] = {"old": emp.user.is_active, "new": payload.is_active}
            emp.user.is_active = payload.is_active
            if not payload.is_active:
                # Invalidate user sessions immediately
                await db.execute(
                    update(RefreshToken)
                    .where(RefreshToken.user_id == emp.user.id, RefreshToken.is_revoked.is_(False))
                    .values(is_revoked=True, revoked_at=datetime.now(UTC), revocation_reason="Employee deactivated")
                )

    # 9. Audit Logging
    client_ip = request.client.host if request.client else None
    audit = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="UPDATE",
        entity_type="employee_profile",
        entity_id=str(emp.id),
        ip_address=client_ip,
        diff_json=diff,
    )
    db.add(audit)
    await db.commit()

    # Reload and respond
    stmt = (
        select(EmployeeProfile)
        .options(
            selectinload(EmployeeProfile.user),
            selectinload(EmployeeProfile.department),
            selectinload(EmployeeProfile.work_schedule),
            selectinload(EmployeeProfile.direct_managers)
            .selectinload(ManagerAssignment.manager)
            .selectinload(EmployeeProfile.user),
        )
        .where(EmployeeProfile.id == emp.id)
    )
    updated_emp = (await db.execute(stmt)).scalars().first()
    if not updated_emp:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reload updated record")
    return await _resolve_employee_response(updated_emp, db)


@router.post("/{employee_id}/status")
async def toggle_employee_status(
    employee_id: uuid.UUID,
    is_active: bool,
    request: Request,
    current_user: Annotated[
        User, Depends(require_role("Super Administrator", "Administrator", "HR Manager", "Admin", "HR"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    """Activate or deactivate employee account and revoke active sessions."""
    stmt = (
        select(EmployeeProfile)
        .options(selectinload(EmployeeProfile.user))
        .where(
            EmployeeProfile.id == employee_id,
            EmployeeProfile.organization_id == current_user.organization_id,
        )
    )
    emp = (await db.execute(stmt)).scalars().first()
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    if emp.user:
        emp.user.is_active = is_active
        if not is_active:
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == emp.user.id, RefreshToken.is_revoked.is_(False))
                .values(is_revoked=True, revoked_at=datetime.now(UTC), revocation_reason="Deactivated by administrator")
            )

    emp.employment_status = EmploymentStatus.ACTIVE if is_active else EmploymentStatus.TERMINATED

    client_ip = request.client.host if request.client else None
    audit = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="STATUS_TOGGLE",
        entity_type="employee_profile",
        entity_id=str(emp.id),
        ip_address=client_ip,
        diff_json={"is_active": is_active, "status": emp.employment_status},
    )
    db.add(audit)
    await db.commit()

    return {
        "employee_id": str(emp.id),
        "is_active": is_active,
        "employment_status": emp.employment_status,
        "message": f"Employee {emp.first_name} {emp.last_name} has been {'activated' if is_active else 'deactivated'}.",
    }


@router.delete("/{employee_id}")
async def delete_employee(
    employee_id: uuid.UUID,
    current_user: Annotated[
        User, Depends(require_role("Super Administrator", "Administrator", "HR Manager", "Admin", "HR"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """
    Permanently delete an employee profile and associated user account.
    Restricted to Administrator and HR Manager roles.
    """
    stmt = (
        select(EmployeeProfile)
        .options(selectinload(EmployeeProfile.user))
        .where(
            EmployeeProfile.id == employee_id,
            EmployeeProfile.organization_id == current_user.organization_id,
        )
    )
    res = await db.execute(stmt)
    emp = res.scalars().first()
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    user_to_delete = emp.user
    emp_name = f"{emp.first_name} {emp.last_name}"
    emp_code = emp.employee_code

    # Remove direct manager assignments
    await db.execute(
        delete(ManagerAssignment).where(
            or_(
                ManagerAssignment.employee_id == emp.id,
                ManagerAssignment.manager_id == emp.id,
            )
        )
    )

    # Delete employee profile and associated user
    await db.delete(emp)
    if user_to_delete:
        await db.delete(user_to_delete)

    audit_entry = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="EMPLOYEE_DELETED",
        entity_type="EmployeeProfile",
        entity_id=str(employee_id),
        diff_json={"employee_name": emp_name, "employee_code": emp_code},
    )
    db.add(audit_entry)

    await db.commit()
    return {"message": f"Employee {emp_name} ({emp_code}) and associated account deleted successfully"}


@router.post("/import", response_model=EmployeeImportResult)
async def import_employees(
    request: Request,
    current_user: Annotated[
        User, Depends(require_role("Super Administrator", "Administrator", "HR Manager", "Admin", "HR"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
) -> EmployeeImportResult:
    """
    Bulk import employee records from validated Excel (.xlsx) or CSV (.csv) file.
    Validates required columns, duplicate employee codes, email uniqueness,
    department mappings, and hierarchical reporting links.
    """
    filename = sanitize_filename(file.filename or "upload.csv")
    contents = await file.read()
    validate_file_content(contents, filename)

    rows: list[dict[str, Any]] = []

    # Parse CSV or Excel
    if filename.endswith(".csv"):
        try:
            decoded = contents.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(decoded))
            for r in reader:
                # Normalize keys to lower snake_case
                normalized = {k.strip().lower().replace(" ", "_"): (v.strip() if v else "") for k, v in r.items() if k}
                rows.append(normalized)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to parse CSV file: {str(e)}")
    elif filename.endswith(".xlsx"):
        try:
            wb = load_workbook(io.BytesIO(contents), data_only=True)
            sheet = wb.active
            iter_rows = list(sheet.iter_rows(values_only=True))
            if not iter_rows:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Excel file is empty")
            headers = [str(h).strip().lower().replace(" ", "_") for h in iter_rows[0] if h is not None]
            for raw_row in iter_rows[1:]:
                if not any(raw_row):
                    continue
                row_dict = {}
                for idx, h in enumerate(headers):
                    val = raw_row[idx] if idx < len(raw_row) else None
                    if isinstance(val, (datetime, date)):
                        row_dict[h] = val.strftime("%Y-%m-%d")
                    else:
                        row_dict[h] = str(val).strip() if val is not None else ""
                rows.append(row_dict)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to parse Excel file: {str(e)}")
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload a .csv or .xlsx file.",
        )

    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No data rows found in uploaded file.")

    # Cache existing departments and roles for batch mapping
    dept_res = await db.execute(select(Department).where(Department.organization_id == current_user.organization_id))
    dept_map = {d.code.upper(): d.id for d in dept_res.scalars().all()}
    dept_name_map = {d.name.lower(): d.id for d in dept_res.scalars().all()}

    emp_role_res = await db.execute(select(Role).where(func.lower(Role.name) == "employee"))
    emp_role = emp_role_res.scalars().first()
    if not emp_role:
        raise HTTPException(status_code=500, detail="Employee role not found.")

    errors: list[EmployeeImportRowError] = []
    created_records: list[EmployeeProfile] = []
    seen_codes_in_batch: set[str] = set()
    seen_emails_in_batch: set[str] = set()

    for idx, row in enumerate(rows, start=2):  # Header is row 1
        row_errors: list[str] = []

        first_name = row.get("first_name") or row.get("firstname") or ""
        last_name = row.get("last_name") or row.get("lastname") or ""
        email = (row.get("email") or "").lower().strip()
        code = (row.get("employee_code") or row.get("emp_code") or row.get("employee_id") or "").upper().strip()
        hire_date_str = row.get("hire_date") or row.get("joining_date") or ""
        job_title = row.get("job_title") or row.get("title") or None
        phone = row.get("phone") or None
        dept_ident = row.get("department") or row.get("department_code") or row.get("dept") or ""
        manager_code = (row.get("manager_code") or row.get("manager_employee_code") or "").upper().strip()

        # Validation checks
        if not first_name:
            row_errors.append("First name is required.")
        if not last_name:
            row_errors.append("Last name is required.")
        if not email or "@" not in email:
            row_errors.append("Valid email address is required.")
        if not code:
            row_errors.append("Employee code is required.")
        if not hire_date_str:
            row_errors.append("Hire date is required.")

        # Batch duplicate checks
        if code in seen_codes_in_batch:
            row_errors.append(f"Duplicate employee code '{code}' in upload file.")
        else:
            seen_codes_in_batch.add(code)

        if email in seen_emails_in_batch:
            row_errors.append(f"Duplicate email '{email}' in upload file.")
        else:
            seen_emails_in_batch.add(email)

        # Database duplicate checks
        existing_code = await db.execute(
            select(EmployeeProfile).where(
                EmployeeProfile.organization_id == current_user.organization_id,
                func.upper(EmployeeProfile.employee_code) == code,
            )
        )
        if existing_code.scalars().first():
            row_errors.append(f"Employee code '{code}' already exists in database.")

        existing_user = await db.execute(
            select(User).where(
                User.organization_id == current_user.organization_id,
                func.lower(User.email) == email,
            )
        )
        if existing_user.scalars().first():
            row_errors.append(f"User email '{email}' already registered.")

        # Parse date
        parsed_hire_date: date | None = None
        if hire_date_str:
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    parsed_hire_date = datetime.strptime(hire_date_str, fmt).date()
                    break
                except ValueError:
                    continue
            if not parsed_hire_date:
                row_errors.append(f"Invalid hire date '{hire_date_str}'. Expected format YYYY-MM-DD.")

        # Department resolution
        resolved_dept_id: uuid.UUID | None = None
        if dept_ident:
            resolved_dept_id = dept_map.get(dept_ident.upper()) or dept_name_map.get(dept_ident.lower())
            if not resolved_dept_id:
                row_errors.append(f"Department '{dept_ident}' not recognized.")

        if row_errors:
            errors.append(
                EmployeeImportRowError(
                    row=idx,
                    employee_code=code,
                    email=email,
                    errors=row_errors,
                )
            )
            continue

        # Create User & EmployeeProfile
        new_user = User(
            organization_id=current_user.organization_id,
            email=email,
            hashed_password=get_password_hash("WelcomeTitan123!"),
            role_id=emp_role.id,
            is_active=True,
        )
        db.add(new_user)
        await db.flush()

        new_profile = EmployeeProfile(
            organization_id=current_user.organization_id,
            user_id=new_user.id,
            employee_code=code,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            job_title=job_title,
            department_id=resolved_dept_id,
            hire_date=parsed_hire_date,
            employment_status=EmploymentStatus.ACTIVE,
        )
        db.add(new_profile)
        await db.flush()

        # Manager link resolution if specified
        if manager_code:
            mgr_res = await db.execute(
                select(EmployeeProfile).where(
                    EmployeeProfile.organization_id == current_user.organization_id,
                    func.upper(EmployeeProfile.employee_code) == manager_code,
                )
            )
            mgr_p = mgr_res.scalars().first()
            if mgr_p:
                mgr_link = ManagerAssignment(
                    organization_id=current_user.organization_id,
                    employee_id=new_profile.id,
                    manager_id=mgr_p.id,
                    is_primary=True,
                )
                db.add(mgr_link)

        created_records.append(new_profile)

    # Audit bulk import
    if created_records:
        client_ip = request.client.host if request and request.client else None
        audit = AuditLog(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="BULK_IMPORT",
            entity_type="employee_profile",
            ip_address=client_ip,
            diff_json={
                "filename": filename,
                "imported_count": len(created_records),
                "error_count": len(errors),
            },
        )
        db.add(audit)
        await db.commit()

    # Form response items
    imported_responses: list[EmployeeResponse] = []
    for ep in created_records:
        stmt = (
            select(EmployeeProfile)
            .options(
                selectinload(EmployeeProfile.user),
                selectinload(EmployeeProfile.department),
                selectinload(EmployeeProfile.work_schedule),
                selectinload(EmployeeProfile.direct_managers)
                .selectinload(ManagerAssignment.manager)
                .selectinload(EmployeeProfile.user),
            )
            .where(EmployeeProfile.id == ep.id)
        )
        reloaded = (await db.execute(stmt)).scalars().first()
        if reloaded:
            imported_responses.append(await _resolve_employee_response(reloaded, db))

    return EmployeeImportResult(
        success_count=len(created_records),
        error_count=len(errors),
        imported_employees=imported_responses,
        errors=errors,
    )


# ==========================================
# Prompt 17: Admin Password Reset & Login History
# ==========================================

class AdminPasswordResetRequest(BaseModel):
    temporary_password: str | None = None
    notify_email: bool = True


@router.post("/{employee_id}/reset-password")
async def reset_employee_password(
    employee_id: uuid.UUID,
    payload: AdminPasswordResetRequest | None = None,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Allows Admin to reset an employee's password, invalidating current sessions
    and dispatching secure reset notification to the employee.
    """
    stmt = (
        select(EmployeeProfile)
        .options(selectinload(EmployeeProfile.user))
        .where(
            EmployeeProfile.id == employee_id,
            EmployeeProfile.organization_id == current_user.organization_id,
        )
    )
    res = await db.execute(stmt)
    emp = res.scalars().first()

    if not emp or not emp.user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee account not found in this organization.",
        )

    # Generate new temporary password
    temp_pwd = (payload.temporary_password.strip() if payload and payload.temporary_password else f"Reset@{secrets.token_hex(4)}A1!")
    emp.user.hashed_password = get_password_hash(temp_pwd)

    # Invalidate active refresh tokens
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == emp.user.id)
        .values(is_revoked=True)
    )

    # Dedicated audit log
    audit = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="ADMIN_PASSWORD_RESET",
        entity_type="user",
        entity_id=str(emp.user.id),
        diff_json={
            "employee_id": str(emp.id),
            "employee_code": emp.employee_code,
            "reset_by": current_user.email,
            "session_revoked": True,
        },
    )
    db.add(audit)
    await db.commit()

    # Dispatch email notification
    should_notify = payload.notify_email if payload else True
    if should_notify and emp.user.email:
        try:
            from app.services.email_service import EmailService
            await EmailService.notify_password_reset(
                db=db,
                user_id=emp.user.id,
                reset_token=temp_pwd,
                otp_code="ADMIN-RESET",
                expires_minutes=60,
            )
        except Exception:
            pass

    return {
        "status": "SUCCESS",
        "message": f"Password reset successfully for {emp.first_name} {emp.last_name} ({emp.employee_code}). Active sessions revoked.",
        "temporary_password": temp_pwd,
        "email": emp.user.email,
    }


@router.get("/{employee_id}/login-history")
async def get_employee_login_history(
    employee_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Inspect sign-in and session events for an employee.
    Authorized for Admin, HR, assigned reporting Manager, or the Employee themselves.
    """
    # Permission verification
    has_access = await check_employee_record_access(employee_id, current_user, db)
    if not has_access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    stmt = select(EmployeeProfile).options(selectinload(EmployeeProfile.user)).where(EmployeeProfile.id == employee_id)
    emp = (await db.execute(stmt)).scalars().first()
    if not emp or not emp.user:
        return []

    audit_stmt = (
        select(AuditLog)
        .where(
            AuditLog.organization_id == current_user.organization_id,
            AuditLog.user_id == emp.user.id,
            AuditLog.action.in_(["USER_LOGIN", "OS_LOGON", "SESSION_LOCK", "SESSION_UNLOCK", "ADMIN_PASSWORD_RESET"]),
        )
        .order_by(desc(AuditLog.created_at))
        .limit(limit)
    )
    res = await db.execute(audit_stmt)
    logs = res.scalars().all()

    return [
        {
            "id": str(log.id),
            "action": log.action,
            "timestamp": log.created_at.isoformat(),
            "ip_address": log.ip_address or "Authorized Office Network",
            "details": log.diff_json or {},
        }
        for log in logs
    ]
