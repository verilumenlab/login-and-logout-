"""
Authentication & RBAC Authorization Dependencies and Access Middleware
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.auth import Role, RolePermission, User
from app.models.employee import EmployeeProfile

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False,
)

ROLE_ALIASES: dict[str, set[str]] = {
    "super admin": {"super admin", "super administrator"},
    "admin": {"admin", "administrator", "super admin", "super administrator"},
    # Manager is treated as equal to HR for portal / org-wide access.
    "hr": {
        "hr",
        "hr manager",
        "human resources",
        "manager",
        "department manager",
        "admin",
        "administrator",
        "super admin",
        "super administrator",
    },
    "manager": {
        "manager",
        "department manager",
        "team lead",
        "hr",
        "hr manager",
        "admin",
        "administrator",
        "super admin",
        "super administrator",
    },
    "employee": {
        "employee",
        "manager",
        "department manager",
        "team lead",
        "hr",
        "hr manager",
        "admin",
        "administrator",
        "super admin",
        "super administrator",
    },
}


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Authenticate user via Bearer JWT, eager-loading role, permissions, and employee profile.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id_raw = payload.get("sub")
    if user_id_raw is None:
        raise credentials_exception

    try:
        user_id = uuid.UUID(str(user_id_raw))
    except ValueError:
        raise credentials_exception

    stmt = (
        select(User)
        .options(
            selectinload(User.role).selectinload(Role.role_permissions).selectinload(RolePermission.permission),
            selectinload(User.employee_profile),
        )
        .where(User.id == user_id)
    )
    result = await db.execute(stmt)
    user = result.scalars().first()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure authenticated user is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )
    return current_user


def get_user_permissions(user: User) -> set[str]:
    """Helper to extract granted permission codes from user's assigned role."""
    if user.is_superuser:
        return {"*"}
    if not user.role or not user.role.role_permissions:
        return set()
    return {rp.permission.code for rp in user.role.role_permissions if rp.permission and rp.permission.code}


def require_role(*allowed_roles: Any) -> Callable:
    """
    RBAC dependency factory that validates current user against permissible roles.
    Super Admins and organization Administrators are automatically granted access.
    """
    flat_roles: list[str] = []
    for r in allowed_roles:
        if isinstance(r, (list, tuple, set)):
            flat_roles.extend(str(item) for item in r)
        else:
            flat_roles.append(str(r))
    normalized_allowed = {r.strip().lower() for r in flat_roles}

    async def _role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.is_superuser:
            return current_user

        if not current_user.role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no assigned role",
            )

        user_role = current_user.role.name.strip().lower()

        # Direct match
        if user_role in normalized_allowed:
            return current_user

        # Match against aliases / hierarchies
        for target in normalized_allowed:
            target_alias = ROLE_ALIASES.get(target, {target})
            if user_role in target_alias:
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Required role in {list(allowed_roles)}. Current role: '{current_user.role.name}'",
        )

    return _role_checker


def require_permission(*required_permissions: str) -> Callable:
    """
    Granular permission dependency factory.
    Verifies that user possesses all required permissions (or superuser wildcard).
    """

    async def _permission_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.is_superuser:
            return current_user

        granted = get_user_permissions(current_user)
        if "*" in granted:
            return current_user

        missing = [p for p in required_permissions if p not in granted]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Missing required permission(s): {missing}",
            )
        return current_user

    return _permission_checker


async def check_employee_record_access(
    target_employee_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> bool:
    """
    Strict authorization rule evaluator:
    - Super Admin / Admin: full organization access.
    - HR / Manager: employee, attendance, leave and reporting access across the organization.
    - Employee: own records only.
    """
    # 1. Superuser
    if current_user.is_superuser:
        return True

    user_role = current_user.role.name.strip().lower() if current_user.role else ""

    # 2. Admin / HR / Manager — full org visibility (manager matches HR)
    if any(
        r in user_role
        for r in ("admin", "super administrator", "hr", "human resources", "manager", "lead", "supervisor")
    ):
        stmt = select(EmployeeProfile).where(
            EmployeeProfile.id == target_employee_id,
            EmployeeProfile.organization_id == current_user.organization_id,
        )
        res = await db.execute(stmt)
        target = res.scalars().first()
        return target is not None

    # Load current user's employee profile
    current_emp = current_user.employee_profile
    if not current_emp:
        return False

    # 3. Own record access (always permitted)
    if current_emp.id == target_employee_id:
        return True

    # Standard Employee can only access own records
    return False


async def require_employee_access(
    employee_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> uuid.UUID:
    """
    Dependency that enforces hierarchical and role-based record scoping.
    Raises 403 Forbidden if current user is not authorized to access target employee's record.
    Matches path parameter {employee_id}.
    """
    allowed = await check_employee_record_access(employee_id, current_user, db)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to access this employee's records",
        )
    return employee_id
