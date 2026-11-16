"""
Initial Seed Data for Roles, Permissions, and Standard Leave Categories
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import Permission, Role, RolePermission
from app.models.leave import LeaveBalance, LeaveCategory, LeaveType

# 1. System Permissions Definitions
PERMISSIONS_DATA: list[dict[str, str]] = [
    # Auth & Administration
    {
        "code": "auth:roles:read",
        "name": "View Roles",
        "module": "auth",
        "description": "View system and organization roles",
    },
    {
        "code": "auth:roles:write",
        "name": "Manage Roles",
        "module": "auth",
        "description": "Create and edit custom roles",
    },
    {"code": "auth:users:read", "name": "View Users", "module": "auth", "description": "View user directory"},
    {
        "code": "auth:users:write",
        "name": "Manage Users",
        "module": "auth",
        "description": "Create, invite, and update users",
    },
    # Employee Management
    {
        "code": "employee:profiles:read",
        "name": "View Employee Profiles",
        "module": "employee",
        "description": "View personnel directory and details",
    },
    {
        "code": "employee:profiles:write",
        "name": "Manage Employee Profiles",
        "module": "employee",
        "description": "Add, modify, and terminate employee records",
    },
    {
        "code": "employee:managers:manage",
        "name": "Manage Reporting Lines",
        "module": "employee",
        "description": "Assign managers and direct reports",
    },
    # Attendance Tracking
    {
        "code": "attendance:clock_in_out",
        "name": "Clock In/Out",
        "module": "attendance",
        "description": "Log daily shift attendance timestamps",
    },
    {
        "code": "attendance:view_own",
        "name": "View Own Attendance",
        "module": "attendance",
        "description": "Inspect individual attendance records",
    },
    {
        "code": "attendance:view_team",
        "name": "View Team Attendance",
        "module": "attendance",
        "description": "Inspect subordinate attendance records",
    },
    {
        "code": "attendance:view_all",
        "name": "View Organization Attendance",
        "module": "attendance",
        "description": "Inspect company-wide attendance",
    },
    {
        "code": "attendance:adjust",
        "name": "Request Attendance Adjustment",
        "module": "attendance",
        "description": "Submit missed shift correction requests",
    },
    {
        "code": "attendance:approve",
        "name": "Approve Attendance Adjustments",
        "module": "attendance",
        "description": "Approve or reject employee shift adjustments",
    },
    # Activity Telemetry
    {
        "code": "activity:telemetry:ingest",
        "name": "Ingest Desktop Telemetry",
        "module": "activity",
        "description": "Upload client activity telemetry packets",
    },
    {
        "code": "activity:telemetry:view_own",
        "name": "View Own Activity",
        "module": "activity",
        "description": "View individual productivity metrics",
    },
    {
        "code": "activity:telemetry:view_team",
        "name": "View Team Activity",
        "module": "activity",
        "description": "View team productivity breakdowns",
    },
    {
        "code": "activity:telemetry:view_all",
        "name": "View Organization Activity",
        "module": "activity",
        "description": "View enterprise-wide activity analytics",
    },
    # Leave Management
    {
        "code": "leave:types:manage",
        "name": "Manage Leave Types",
        "module": "leave",
        "description": "Configure organizational leave policies",
    },
    {
        "code": "leave:balances:manage",
        "name": "Manage Leave Balances",
        "module": "leave",
        "description": "Credit, deduct, or adjust leave allowances",
    },
    {
        "code": "leave:requests:create",
        "name": "Submit Leave Request",
        "module": "leave",
        "description": "Apply for time off",
    },
    {
        "code": "leave:requests:view_own",
        "name": "View Own Leave Requests",
        "module": "leave",
        "description": "View individual leave history",
    },
    {
        "code": "leave:requests:view_team",
        "name": "View Team Leave Requests",
        "module": "leave",
        "description": "Inspect subordinate leave applications",
    },
    {
        "code": "leave:requests:view_all",
        "name": "View Organization Leave",
        "module": "leave",
        "description": "Inspect company-wide leave calendar",
    },
    {
        "code": "leave:requests:approve",
        "name": "Approve Leave Requests",
        "module": "leave",
        "description": "Authorize or deny time-off applications",
    },
    # Offices & Geofencing
    {
        "code": "office:manage",
        "name": "Manage Offices",
        "module": "office",
        "description": "Configure office locations and timezones",
    },
    {
        "code": "office:geofence:manage",
        "name": "Manage Geofences",
        "module": "office",
        "description": "Define GPS coordinates and radius boundaries",
    },
    {
        "code": "office:network:manage",
        "name": "Manage Office Networks",
        "module": "office",
        "description": "Authorize office IPs and subnet CIDRs",
    },
    # Devices & Agents
    {
        "code": "devices:register",
        "name": "Enroll Device",
        "module": "devices",
        "description": "Pair and register employee desktop agents",
    },
    {
        "code": "devices:manage",
        "name": "Manage Devices",
        "module": "devices",
        "description": "Inspect trusted hardware list and agent versions",
    },
    {
        "code": "devices:block",
        "name": "Block Device",
        "module": "devices",
        "description": "Revoke device session access",
    },
    # Reporting
    {
        "code": "reports:generate",
        "name": "Generate Reports",
        "module": "reports",
        "description": "Queue background analytical reports",
    },
    {
        "code": "reports:view",
        "name": "View Reports",
        "module": "reports",
        "description": "View generated analytical summaries",
    },
    {
        "code": "reports:download",
        "name": "Download Report Files",
        "module": "reports",
        "description": "Download generated spreadsheets and PDFs",
    },
    # Audit & Compliance
    {
        "code": "audit:view",
        "name": "View Audit Logs",
        "module": "audit",
        "description": "Inspect immutable historical system activity",
    },
    {
        "code": "audit:export",
        "name": "Export Audit Logs",
        "module": "audit",
        "description": "Export compliance audit trails",
    },
]

# 2. System Default Roles Definitions
ROLES_DATA: list[dict[str, Any]] = [
    {
        "name": "Super Administrator",
        "description": "Full unconstrained administrative privileges across entire platform",
        "is_system": True,
        "permissions": [p["code"] for p in PERMISSIONS_DATA],
    },
    {
        "name": "Administrator",
        "description": "Full administrative control within the tenant organization",
        "is_system": True,
        "permissions": [p["code"] for p in PERMISSIONS_DATA],
    },
    {
        "name": "HR Manager",
        "description": "Employee directory, leave policy, attendance auditing, and workforce reporting",
        "is_system": True,
        "permissions": [
            "employee:profiles:read",
            "employee:profiles:write",
            "employee:managers:manage",
            "attendance:view_all",
            "attendance:approve",
            "leave:types:manage",
            "leave:balances:manage",
            "leave:requests:view_all",
            "leave:requests:approve",
            "office:manage",
            "office:geofence:manage",
            "office:network:manage",
            "reports:generate",
            "reports:view",
            "reports:download",
            "audit:view",
        ],
    },
    {
        "name": "Department Manager",
        "description": "Same organization-wide access as HR: employees, leave, attendance, and workforce reporting",
        "is_system": True,
        "permissions": [
            "employee:profiles:read",
            "employee:profiles:write",
            "employee:managers:manage",
            "attendance:clock_in_out",
            "attendance:view_own",
            "attendance:view_team",
            "attendance:view_all",
            "attendance:adjust",
            "attendance:approve",
            "activity:telemetry:view_own",
            "activity:telemetry:view_team",
            "leave:types:manage",
            "leave:balances:manage",
            "leave:requests:create",
            "leave:requests:view_own",
            "leave:requests:view_team",
            "leave:requests:view_all",
            "leave:requests:approve",
            "office:manage",
            "office:geofence:manage",
            "office:network:manage",
            "reports:generate",
            "reports:view",
            "reports:download",
            "audit:view",
        ],
    },
    {
        "name": "Team Lead",
        "description": "Direct team supervisor with visibility into member attendance and leave status",
        "is_system": True,
        "permissions": [
            "employee:profiles:read",
            "attendance:clock_in_out",
            "attendance:view_own",
            "attendance:view_team",
            "attendance:adjust",
            "activity:telemetry:view_own",
            "activity:telemetry:view_team",
            "leave:requests:create",
            "leave:requests:view_own",
            "leave:requests:view_team",
        ],
    },
    {
        "name": "Employee",
        "description": "Standard personnel account with clocking, own activity view, and leave application",
        "is_system": True,
        "permissions": [
            "attendance:clock_in_out",
            "attendance:view_own",
            "attendance:adjust",
            "activity:telemetry:ingest",
            "activity:telemetry:view_own",
            "leave:requests:create",
            "leave:requests:view_own",
            "devices:register",
        ],
    },
    {
        "name": "Compliance Auditor",
        "description": "Read-only access to audit logs, attendance summaries, and export archives",
        "is_system": True,
        "permissions": [
            "employee:profiles:read",
            "attendance:view_all",
            "activity:telemetry:view_all",
            "leave:requests:view_all",
            "reports:view",
            "reports:download",
            "audit:view",
            "audit:export",
        ],
    },
]

# 3. Standard Leave Categories Data (Template for Organizations)
DEFAULT_LEAVE_TYPES_DATA: list[dict[str, Any]] = [
    {
        "name": "Annual Leave",
        "code": "ANNUAL",
        "category": LeaveCategory.ANNUAL,
        "is_paid": True,
        "annual_allowance": 24,
        "carryover_max_days": 5,
        "requires_attachment": False,
    },
    {
        "name": "Sick Leave",
        "code": "SICK",
        "category": LeaveCategory.SICK,
        "is_paid": True,
        "annual_allowance": 12,
        "carryover_max_days": 0,
        "requires_attachment": True,
    },
    {
        "name": "Casual Leave",
        "code": "CASUAL",
        "category": LeaveCategory.CASUAL,
        "is_paid": True,
        "annual_allowance": 12,
        "carryover_max_days": 0,
        "requires_attachment": False,
    },
]

# Soft-deactivate these codes when syncing existing organizations.
DEPRECATED_LEAVE_TYPE_CODES: frozenset[str] = frozenset(
    {"MATERNITY", "PATERNITY", "BEREAVEMENT", "COMP_OFF", "UNPAID"}
)


async def seed_permissions(db: AsyncSession) -> dict[str, Permission]:
    """Ensures all standard permissions exist in the database."""
    permission_map: dict[str, Permission] = {}

    for p_data in PERMISSIONS_DATA:
        result = await db.execute(select(Permission).where(Permission.code == p_data["code"]))
        perm = result.scalars().first()
        if not perm:
            perm = Permission(
                code=p_data["code"],
                name=p_data["name"],
                module=p_data["module"],
                description=p_data["description"],
            )
            db.add(perm)
            await db.flush()
        permission_map[p_data["code"]] = perm

    return permission_map


async def seed_system_roles(db: AsyncSession, permission_map: dict[str, Permission] | None = None) -> dict[str, Role]:
    """Ensures all default system roles and their permission links exist."""
    if not permission_map:
        permission_map = await seed_permissions(db)

    role_map: dict[str, Role] = {}

    for r_data in ROLES_DATA:
        result = await db.execute(select(Role).where(Role.name == r_data["name"], Role.organization_id.is_(None)))
        role = result.scalars().first()
        if not role:
            role = Role(
                name=r_data["name"],
                description=r_data["description"],
                is_system=True,
                organization_id=None,
            )
            db.add(role)
            await db.flush()

        role_map[r_data["name"]] = role

        # Ensure permission bindings
        for perm_code in r_data["permissions"]:
            perm = permission_map.get(perm_code)
            if perm:
                binding_res = await db.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == perm.id,
                    )
                )
                if not binding_res.scalars().first():
                    db.add(RolePermission(role_id=role.id, permission_id=perm.id))

    await db.flush()
    return role_map


async def seed_organization_leave_types(db: AsyncSession, organization_id: uuid.UUID) -> list[LeaveType]:
    """Create or sync standard leave categories for an organization.

    - Ensures default types exist with current allowances and are active.
    - Soft-deactivates deprecated leave type codes.
    - Updates current-year leave balance allocations when allowances change.
    """
    leave_types: list[LeaveType] = []
    current_year = datetime.now(UTC).year

    for lt_data in DEFAULT_LEAVE_TYPES_DATA:
        result = await db.execute(
            select(LeaveType).where(
                LeaveType.organization_id == organization_id,
                LeaveType.code == lt_data["code"],
            )
        )
        lt = result.scalars().first()
        if not lt:
            lt = LeaveType(
                organization_id=organization_id,
                name=lt_data["name"],
                code=lt_data["code"],
                category=lt_data["category"],
                is_paid=lt_data["is_paid"],
                annual_allowance=lt_data["annual_allowance"],
                carryover_max_days=lt_data["carryover_max_days"],
                requires_attachment=lt_data["requires_attachment"],
                is_active=True,
            )
            db.add(lt)
            await db.flush()
        else:
            lt.name = lt_data["name"]
            lt.category = lt_data["category"]
            lt.is_paid = lt_data["is_paid"]
            lt.annual_allowance = lt_data["annual_allowance"]
            lt.carryover_max_days = lt_data["carryover_max_days"]
            lt.requires_attachment = lt_data["requires_attachment"]
            lt.is_active = True
            await db.flush()

        # Keep current-year allocations aligned with policy (Annual 24 / Sick 12 / Casual 12).
        bal_result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.leave_type_id == lt.id,
                LeaveBalance.year == current_year,
            )
        )
        target_allocation = float(lt_data["annual_allowance"])
        for balance in bal_result.scalars().all():
            if balance.allocated_days != target_allocation:
                balance.allocated_days = target_allocation
        await db.flush()

        leave_types.append(lt)

    for code in DEPRECATED_LEAVE_TYPE_CODES:
        result = await db.execute(
            select(LeaveType).where(
                LeaveType.organization_id == organization_id,
                LeaveType.code == code,
            )
        )
        deprecated = result.scalars().first()
        if deprecated and deprecated.is_active:
            deprecated.is_active = False
            await db.flush()

    return leave_types
