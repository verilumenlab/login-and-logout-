"""
Department Management Endpoints with RBAC & Audit Trails
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user, require_role
from app.models.auth import AuditLog, User
from app.models.department import Department
from app.models.employee import EmployeeProfile
from app.schemas.department import DepartmentCreate, DepartmentResponse, DepartmentUpdate

router = APIRouter()


@router.get("/", response_model=list[DepartmentResponse])
async def list_departments(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DepartmentResponse]:
    """List all departments in authenticated user's organization with member counts."""
    # Query departments and count associated employees
    stmt = (
        select(
            Department,
            func.count(EmployeeProfile.id).label("emp_count"),
        )
        .outerjoin(EmployeeProfile, EmployeeProfile.department_id == Department.id)
        .where(Department.organization_id == current_user.organization_id)
        .group_by(Department.id)
        .order_by(Department.name.asc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    departments: list[DepartmentResponse] = []
    for dept, count in rows:
        departments.append(
            DepartmentResponse(
                id=dept.id,
                organization_id=dept.organization_id,
                name=dept.name,
                code=dept.code,
                parent_id=dept.parent_id,
                is_active=dept.is_active,
                employee_count=count,
                created_at=dept.created_at,
                updated_at=dept.updated_at,
            )
        )
    return departments


@router.post("/", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
async def create_department(
    payload: DepartmentCreate,
    request: Request,
    current_user: Annotated[
        User, Depends(require_role("Super Administrator", "Administrator", "HR Manager", "Admin", "HR"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DepartmentResponse:
    """Create a new department within the organization."""
    # Check duplicate code within organization
    existing = await db.execute(
        select(Department).where(
            Department.organization_id == current_user.organization_id,
            Department.code == payload.code.strip().upper(),
        )
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Department with code '{payload.code.strip().upper()}' already exists.",
        )

    # Validate parent_id if supplied
    if payload.parent_id:
        parent_res = await db.execute(
            select(Department).where(
                Department.id == payload.parent_id,
                Department.organization_id == current_user.organization_id,
            )
        )
        if not parent_res.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent department not found in your organization.",
            )

    dept = Department(
        organization_id=current_user.organization_id,
        name=payload.name.strip(),
        code=payload.code.strip().upper(),
        parent_id=payload.parent_id,
        is_active=payload.is_active,
    )
    db.add(dept)
    await db.flush()

    # Audit Log
    client_ip = request.client.host if request.client else None
    audit = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="CREATE",
        entity_type="department",
        entity_id=str(dept.id),
        ip_address=client_ip,
        diff_json={"name": dept.name, "code": dept.code, "is_active": dept.is_active},
    )
    db.add(audit)
    await db.commit()
    await db.refresh(dept)

    return DepartmentResponse(
        id=dept.id,
        organization_id=dept.organization_id,
        name=dept.name,
        code=dept.code,
        parent_id=dept.parent_id,
        is_active=dept.is_active,
        employee_count=0,
        created_at=dept.created_at,
        updated_at=dept.updated_at,
    )


@router.get("/{department_id}", response_model=DepartmentResponse)
async def get_department(
    department_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DepartmentResponse:
    """Get single department details."""
    stmt = (
        select(
            Department,
            func.count(EmployeeProfile.id).label("emp_count"),
        )
        .outerjoin(EmployeeProfile, EmployeeProfile.department_id == Department.id)
        .where(
            Department.id == department_id,
            Department.organization_id == current_user.organization_id,
        )
        .group_by(Department.id)
    )
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    dept, count = row
    return DepartmentResponse(
        id=dept.id,
        organization_id=dept.organization_id,
        name=dept.name,
        code=dept.code,
        parent_id=dept.parent_id,
        is_active=dept.is_active,
        employee_count=count,
        created_at=dept.created_at,
        updated_at=dept.updated_at,
    )


@router.put("/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: uuid.UUID,
    payload: DepartmentUpdate,
    request: Request,
    current_user: Annotated[
        User, Depends(require_role("Super Administrator", "Administrator", "HR Manager", "Admin", "HR"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DepartmentResponse:
    """Update department details with audit logging."""
    stmt = select(Department).where(
        Department.id == department_id,
        Department.organization_id == current_user.organization_id,
    )
    result = await db.execute(stmt)
    dept = result.scalars().first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    diff: dict[str, object] = {}

    if payload.code is not None and payload.code.strip().upper() != dept.code:
        new_code = payload.code.strip().upper()
        existing = await db.execute(
            select(Department).where(
                Department.organization_id == current_user.organization_id,
                Department.code == new_code,
                Department.id != department_id,
            )
        )
        if existing.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Department code '{new_code}' already in use."
            )
        diff["code"] = {"old": dept.code, "new": new_code}
        dept.code = new_code

    if payload.name is not None and payload.name.strip() != dept.name:
        diff["name"] = {"old": dept.name, "new": payload.name.strip()}
        dept.name = payload.name.strip()

    if payload.parent_id is not None:
        if payload.parent_id == dept.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department cannot be its own parent.")
        diff["parent_id"] = {"old": str(dept.parent_id) if dept.parent_id else None, "new": str(payload.parent_id)}
        dept.parent_id = payload.parent_id

    if payload.is_active is not None and payload.is_active != dept.is_active:
        diff["is_active"] = {"old": dept.is_active, "new": payload.is_active}
        dept.is_active = payload.is_active

    # Audit log
    client_ip = request.client.host if request.client else None
    audit = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="UPDATE",
        entity_type="department",
        entity_id=str(dept.id),
        ip_address=client_ip,
        diff_json=diff,
    )
    db.add(audit)
    await db.commit()
    await db.refresh(dept)

    # Count
    count_res = await db.execute(select(func.count(EmployeeProfile.id)).where(EmployeeProfile.department_id == dept.id))
    count = count_res.scalar_one()

    return DepartmentResponse(
        id=dept.id,
        organization_id=dept.organization_id,
        name=dept.name,
        code=dept.code,
        parent_id=dept.parent_id,
        is_active=dept.is_active,
        employee_count=count,
        created_at=dept.created_at,
        updated_at=dept.updated_at,
    )


@router.delete("/{department_id}")
async def delete_department(
    department_id: uuid.UUID,
    request: Request,
    current_user: Annotated[
        User, Depends(require_role("Super Administrator", "Administrator", "HR Manager", "Admin", "HR"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Deactivate or remove empty department."""
    stmt = select(Department).where(
        Department.id == department_id,
        Department.organization_id == current_user.organization_id,
    )
    result = await db.execute(stmt)
    dept = result.scalars().first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    # Check assigned employees
    count_res = await db.execute(select(func.count(EmployeeProfile.id)).where(EmployeeProfile.department_id == dept.id))
    count = count_res.scalar_one()
    if count > 0:
        # Soft-deactivate if employees are assigned
        dept.is_active = False
        action = "DEACTIVATE"
    else:
        await db.delete(dept)
        action = "DELETE"

    client_ip = request.client.host if request.client else None
    audit = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action=action,
        entity_type="department",
        entity_id=str(department_id),
        ip_address=client_ip,
        diff_json={"action": action, "employee_count": count},
    )
    db.add(audit)
    await db.commit()
    return {"message": f"Department successfully {'deactivated' if count > 0 else 'deleted'}."}
