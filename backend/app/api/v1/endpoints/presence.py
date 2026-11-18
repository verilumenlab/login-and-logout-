"""
Employee Presence Endpoints

- GET  /presence/me          : signed-in employee's name, code and department
- POST /presence/events      : app login/logout and Wi-Fi connect/disconnect signals (batch, idempotent)
- GET  /presence/my-history  : login & logout table for the signed-in employee
- GET  /presence/my-summary  : dashboard totals (working days vs leave, total login time)
- GET  /presence/team        : one day's login & logout board for HR/Admin (organization) or a manager (team)
- GET  /presence/employee/{id}/history : one employee's login & logout table (same access rules as attendance)
- GET  /presence/export.csv  : weekly (Mon–Fri) or monthly combined HR attendance CSV
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.attendance import get_current_employee_profile
from app.core.database import get_db
from app.core.dependencies import get_current_active_user, require_employee_access, require_permission
from app.models.auth import User
from app.models.department import Department
from app.models.employee import EmployeeProfile, ManagerAssignment
from app.models.organization import Organization
from app.schemas.presence import (
    AdminForceLogoutRequest,
    AdminForceLogoutResponse,
    AttendanceRepairResponse,
    PresenceHistoryResponse,
    PresenceMonthSummary,
    PresenceProfile,
    PresenceSyncRequest,
    PresenceSyncResponse,
    TeamPresenceResponse,
)
from app.services import presence_service
from app.services.attendance_csv_export import build_attendance_csv, period_range
from app.services.attendance_engine import local_work_date
from app.services.report_dataset import build_report_dataset

router = APIRouter()

MAX_HISTORY_DAYS = 92
ExportPeriod = Literal["weekly", "monthly"]


def _today_local() -> date:
    return local_work_date(datetime.now(UTC))


def _team_scope_employee_ids(
    current_user: User,
    role_name: str,
) -> tuple[str, list[uuid.UUID] | None]:
    """Admin / HR / Manager → organization (None filter); else 403."""
    if current_user.is_superuser or "admin" in role_name or "hr" in role_name or role_name == "human resources":
        return "ORGANIZATION", None
    # Managers match HR: full organization Login & Logout / CSV export.
    if any(word in role_name for word in ("manager", "lead", "supervisor")):
        return "ORGANIZATION", None
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only managers, HR and administrators can export login records",
    )


def _history_range(start_date: date | None, end_date: date | None) -> tuple[date, date]:
    end = end_date or _today_local()
    start = start_date or end - timedelta(days=13)
    if start > end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_date must be before end_date")
    if (end - start).days >= MAX_HISTORY_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Date range cannot exceed {MAX_HISTORY_DAYS} days",
        )
    return start, end


@router.post("/events", response_model=PresenceSyncResponse)
async def sync_presence_events(
    payload: PresenceSyncRequest,
    current_user: Annotated[User, Depends(require_permission("attendance:clock_in_out"))],
    current_emp: Annotated[EmployeeProfile, Depends(get_current_employee_profile)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PresenceSyncResponse:
    """Records presence signals in time order so the earliest login / latest logout wins."""
    ordered = sorted(payload.events, key=lambda e: e.occurred_at)
    results = [await presence_service.record_presence_event(db, current_emp, ev) for ev in ordered]
    return PresenceSyncResponse(
        results=results,
        is_logged_in=await presence_service.is_logged_in(db, current_emp.id),
    )


@router.get("/me", response_model=PresenceProfile)
async def get_my_profile(
    current_emp: Annotated[EmployeeProfile, Depends(get_current_employee_profile)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PresenceProfile:
    department_name = None
    if current_emp.department_id:
        department_name = await db.scalar(select(Department.name).where(Department.id == current_emp.department_id))
    return PresenceProfile(
        employee_id=current_emp.id,
        employee_code=current_emp.employee_code,
        first_name=current_emp.first_name,
        last_name=current_emp.last_name,
        job_title=current_emp.job_title,
        department_name=department_name,
    )


@router.get("/my-history", response_model=PresenceHistoryResponse)
async def get_my_presence_history(
    current_emp: Annotated[EmployeeProfile, Depends(get_current_employee_profile)],
    db: Annotated[AsyncSession, Depends(get_db)],
    start_date: date | None = None,
    end_date: date | None = None,
) -> PresenceHistoryResponse:
    start, end = _history_range(start_date, end_date)
    days = await presence_service.get_presence_days(db, current_emp, start, end)
    return PresenceHistoryResponse(start_date=start, end_date=end, days=days)


@router.post("/admin-force-logout", response_model=AdminForceLogoutResponse)
async def admin_force_logout(
    payload: AdminForceLogoutRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminForceLogoutResponse:
    """
    Admin/HR: clock out everyone still Active today except keep-list people.
    Use when staff left but the desktop tray kept them logged in.
    """
    role_name = (current_user.role.name if current_user.role else "").strip().lower()
    if not (
        current_user.is_superuser
        or "admin" in role_name
        or "hr" in role_name
        or role_name == "human resources"
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or HR only")

    result = await presence_service.admin_force_logout_open_sessions(
        db,
        organization_id=current_user.organization_id,
        keep_employee_codes=payload.keep_employee_codes,
        keep_name_substrings=payload.keep_name_substrings,
        note=payload.note
        or "Admin force logout — employee left; desktop still running in background",
    )
    return AdminForceLogoutResponse(**result)


@router.post("/repair-history", response_model=AttendanceRepairResponse)
async def repair_attendance_history(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=14)] = 3,
) -> AttendanceRepairResponse:
    """
    Backend audit: read each employee's Attendance history presence events for the last N days,
    set correct logout (office Wi-Fi disconnect / sleep / shutdown / 6:30 fallback),
    recalculate hours, persist so Login & Logout table shows correct values.
    """
    role_name = (current_user.role.name if current_user.role else "").strip().lower()
    if not (
        current_user.is_superuser
        or "admin" in role_name
        or "hr" in role_name
        or role_name == "human resources"
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or HR only")
    result = await presence_service.repair_organization_history(
        db,
        organization_id=current_user.organization_id,
        days=days,
    )
    return AttendanceRepairResponse(**result)


@router.get("/team", response_model=TeamPresenceResponse)
async def get_team_presence(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    work_date: Annotated[date | None, Query(alias="date")] = None,
) -> TeamPresenceResponse:
    """
    Login & logout board for one day.
    Admin / HR / Manager see every employee in the organization.
    """
    role_name = (current_user.role.name if current_user.role else "").strip().lower()
    day = work_date or _today_local()
    # Browsers east of UTC (e.g. IST) are a calendar day ahead for part of the night.
    if day > _today_local() + timedelta(days=1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Date cannot be in the future")

    scope, employee_ids = _team_scope_employee_ids(current_user, role_name)
    if scope == "TEAM":
        manager_profile = current_user.employee_profile
        employee_ids = []
        if manager_profile is not None:
            employee_ids = list(
                (
                    await db.execute(
                        select(ManagerAssignment.employee_id).where(
                            ManagerAssignment.manager_id == manager_profile.id,
                            ManagerAssignment.organization_id == current_user.organization_id,
                        )
                    )
                ).scalars().all()
            )

    rows, counts, pending = await presence_service.get_team_presence(
        db, current_user.organization_id, employee_ids, day
    )
    return TeamPresenceResponse(work_date=day, scope=scope, counts=counts, pending_leave_requests=pending, rows=rows)


@router.get("/export.csv")
async def export_attendance_csv(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period: Annotated[ExportPeriod, Query(description="weekly = Mon–Fri; monthly = full calendar month")],
    work_date: Annotated[date | None, Query(alias="date")] = None,
) -> Response:
    """
    Combined HR attendance CSV for the week or month containing `date`.
    Same visibility as the Login & Logout board (org for Admin/HR/Manager).
    """
    role_name = (current_user.role.name if current_user.role else "").strip().lower()
    ref = work_date or _today_local()
    if ref > _today_local() + timedelta(days=1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Date cannot be in the future")

    scope, employee_ids = _team_scope_employee_ids(current_user, role_name)
    if scope == "TEAM":
        manager_profile = current_user.employee_profile
        employee_ids = []
        if manager_profile is not None:
            employee_ids = list(
                (
                    await db.execute(
                        select(ManagerAssignment.employee_id).where(
                            ManagerAssignment.manager_id == manager_profile.id,
                            ManagerAssignment.organization_id == current_user.organization_id,
                        )
                    )
                ).scalars().all()
            )

    start, end = period_range(period, ref)
    org = await db.get(Organization, current_user.organization_id)
    tz_name = "UTC"
    if org and isinstance(org.settings_json, dict):
        tz_name = str(org.settings_json.get("timezone") or "UTC")

    dataset = await build_report_dataset(
        db,
        current_user.organization_id,
        start,
        end,
        tz_name,
        include_all_calendar_days=(period == "monthly"),
    )
    if scope == "TEAM":
        id_set = {str(eid) for eid in (employee_ids or [])}
        dataset = dataset.for_employees(id_set)

    filename, payload = build_attendance_csv(dataset, period, start, end)
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/employee/{employee_id}/history", response_model=PresenceHistoryResponse)
async def get_employee_presence_history(
    employee_id: uuid.UUID,
    target_emp_id: Annotated[uuid.UUID, Depends(require_employee_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
    start_date: date | None = None,
    end_date: date | None = None,
) -> PresenceHistoryResponse:
    """Day-by-day login, logout and Wi-Fi events of one employee (HR/Admin: anyone; manager: direct reports)."""
    start, end = _history_range(start_date, end_date)
    employee = await db.get(EmployeeProfile, target_emp_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    days = await presence_service.get_presence_days(db, employee, start, end)
    return PresenceHistoryResponse(start_date=start, end_date=end, days=days)


@router.get("/my-summary", response_model=PresenceMonthSummary)
async def get_my_presence_summary(
    current_emp: Annotated[EmployeeProfile, Depends(get_current_employee_profile)],
    db: Annotated[AsyncSession, Depends(get_db)],
    month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
) -> PresenceMonthSummary:
    if month:
        year, month_num = (int(part) for part in month.split("-"))
    else:
        today = _today_local()
        year, month_num = today.year, today.month
    return await presence_service.get_month_summary(db, current_emp, year, month_num)
