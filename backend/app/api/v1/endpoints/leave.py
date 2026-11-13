"""
Leave Management Endpoints (Phase 09)
Enterprise leave endpoints implementing:
- Leave application with working day and weekend/holiday deduction
- Multi-tier approvals: Manager -> HR -> Final Approval
- Self-approval prohibition
- Withdrawal workflow
- Leave policies (Leave Types) and real-time balances
- Manager & HR approval dashboards
- Supporting document uploads
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.file_security import sanitize_filename
from app.core.dependencies import (
    check_employee_record_access,
    get_current_active_user,
    require_employee_access,
    require_permission,
    require_role,
)
from app.models.auth import User
from app.models.employee import EmployeeProfile, ManagerAssignment
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
from app.schemas.leave import (
    LeaveApplyRequest,
    LeaveApprovalResponse,
    LeaveBalanceResponse,
    LeaveCreate,
    LeaveDashboardSummary,
    LeaveDocumentCreate,
    LeaveDocumentResponse,
    LeaveResponse,
    LeaveReviewRequest,
    LeaveTypeCreate,
    LeaveTypeResponse,
    LeaveTypeUpdate,
)
from app.services.leave_engine import LeaveEngine, LeaveEngineError

router = APIRouter()


async def get_current_employee_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> EmployeeProfile:
    result = await db.execute(
        select(EmployeeProfile)
        .options(selectinload(EmployeeProfile.department))
        .where(EmployeeProfile.user_id == current_user.id)
    )
    profile = result.scalars().first()
    if not profile:
        raise HTTPException(status_code=400, detail="User does not have an active employee profile")
    return profile


def _serialize_leave_response(leave: LeaveRequest) -> LeaveResponse:
    import sqlalchemy as sa

    insp = sa.inspect(leave)
    unloaded = insp.unloaded if insp else set()

    emp = leave.employee if "employee" not in unloaded else None
    emp_name = f"{emp.first_name} {emp.last_name}".strip() if emp else None
    emp_code = emp.employee_code if emp else None
    dept_name = None
    if emp and "department" not in sa.inspect(emp).unloaded and emp.department:
        dept_name = emp.department.name

    lt = leave.leave_type if "leave_type" not in unloaded else None
    lt_name = lt.name if lt else None
    lt_code = lt.code if lt else None

    approvals = []
    if "approvals" not in unloaded and leave.approvals:
        for a in leave.approvals:
            a_insp = sa.inspect(a)
            a_unloaded = a_insp.unloaded if a_insp else set()
            appr_name = None
            if "approver" not in a_unloaded and getattr(a, "approver", None):
                appr_name = f"{a.approver.first_name} {a.approver.last_name}".strip()
            approvals.append(
                LeaveApprovalResponse(
                    id=a.id,
                    leave_request_id=a.leave_request_id,
                    approver_id=a.approver_id,
                    approver_name=appr_name,
                    step_order=a.step_order,
                    stage=a.stage,
                    status=a.status,
                    comments=a.comments,
                    decided_at=a.decided_at,
                    created_at=a.created_at,
                )
            )

    docs = []
    if "documents" not in unloaded and leave.documents:
        for d in leave.documents:
            docs.append(
                LeaveDocumentResponse(
                    id=d.id,
                    leave_request_id=d.leave_request_id,
                    file_name=d.file_name,
                    file_url=d.file_url,
                    file_size_bytes=d.file_size_bytes,
                    mime_type=d.mime_type,
                    uploaded_at=d.uploaded_at,
                )
            )

    return LeaveResponse(
        id=leave.id,
        organization_id=leave.organization_id,
        employee_id=leave.employee_id,
        employee_name=emp_name,
        employee_code=emp_code,
        department_name=dept_name,
        leave_type_id=leave.leave_type_id,
        leave_type_name=lt_name,
        leave_type_code=lt_code,
        start_date=leave.start_date,
        end_date=leave.end_date,
        total_days=leave.total_days,
        is_half_day=leave.is_half_day,
        half_day_period=leave.half_day_period,
        reason=leave.reason,
        status=leave.status,
        manager_approval_status=leave.manager_approval_status,
        hr_approval_status=leave.hr_approval_status,
        withdrawn_at=leave.withdrawn_at,
        emergency_contact=leave.emergency_contact,
        created_at=leave.created_at,
        updated_at=leave.updated_at,
        approvals=approvals,
        documents=docs,
    )


# ==========================================
# Leave Types / Policies
# ==========================================

@router.get("/types", response_model=list[LeaveTypeResponse])
async def list_leave_types(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[LeaveType]:
    """Retrieve all available leave categories & policies for the organization."""
    stmt = (
        select(LeaveType)
        .where(
            LeaveType.organization_id == current_user.organization_id,
            LeaveType.is_active.is_(True),
        )
        .order_by(LeaveType.name)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/types", response_model=LeaveTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_leave_type(
    payload: LeaveTypeCreate,
    current_user: User = Depends(require_role(["Admin", "Super Admin", "HR"])),
    db: AsyncSession = Depends(get_db),
) -> LeaveType:
    """Create a new leave policy (Admin/HR only)."""
    leave_type = LeaveType(
        organization_id=current_user.organization_id,
        name=payload.name,
        code=payload.code.upper(),
        category=payload.category,
        is_paid=payload.is_paid,
        annual_allowance=payload.annual_allowance,
        carryover_max_days=payload.carryover_max_days,
        requires_attachment=payload.requires_attachment,
        include_weekends=payload.include_weekends,
        is_active=payload.is_active,
    )
    db.add(leave_type)
    await db.commit()
    await db.refresh(leave_type)
    return leave_type


# ==========================================
# Balances
# ==========================================

@router.get("/balances", response_model=list[LeaveBalanceResponse])
async def get_my_leave_balances(
    year: int = Query(default_factory=lambda: datetime.now(UTC).year),
    current_emp: EmployeeProfile = Depends(get_current_employee_profile),
    db: AsyncSession = Depends(get_db),
) -> list[LeaveBalanceResponse]:
    """Retrieve the authenticated employee's leave balance entitlements for the current year."""
    # Ensure all active leave types have initialized balances
    lt_stmt = select(LeaveType).where(
        LeaveType.organization_id == current_emp.organization_id,
        LeaveType.is_active.is_(True),
    )
    lt_res = await db.execute(lt_stmt)
    leave_types = lt_res.scalars().all()

    for lt in leave_types:
        await LeaveEngine.get_or_create_balance(
            db=db,
            organization_id=current_emp.organization_id,
            employee_id=current_emp.id,
            leave_type=lt,
            year=year,
        )
    await db.commit()

    # Query all balances for this employee
    bal_stmt = (
        select(LeaveBalance)
        .options(selectinload(LeaveBalance.leave_type))
        .where(
            LeaveBalance.employee_id == current_emp.id,
            LeaveBalance.year == year,
        )
    )
    bal_res = await db.execute(bal_stmt)
    balances = bal_res.scalars().all()

    output: list[LeaveBalanceResponse] = []
    for b in balances:
        output.append(
            LeaveBalanceResponse(
                id=b.id,
                organization_id=b.organization_id,
                employee_id=b.employee_id,
                leave_type_id=b.leave_type_id,
                leave_type_name=b.leave_type.name if b.leave_type else None,
                leave_type_code=b.leave_type.code if b.leave_type else None,
                year=b.year,
                allocated_days=b.allocated_days,
                used_days=b.used_days,
                pending_days=b.pending_days,
                carryover_days=b.carryover_days,
            )
        )
    return output


# ==========================================
# Leave Application & History
# ==========================================

@router.post("/apply", response_model=LeaveResponse, status_code=status.HTTP_201_CREATED)
async def apply_for_leave(
    payload: LeaveApplyRequest,
    current_emp: EmployeeProfile = Depends(get_current_employee_profile),
    current_user: User = Depends(require_permission("leave:requests:create")),
    db: AsyncSession = Depends(get_db),
) -> LeaveResponse:
    """Submit a new leave application with policy verification and balance reservation."""
    try:
        leave = await LeaveEngine.apply_for_leave(
            db=db,
            employee=current_emp,
            leave_type_id=payload.leave_type_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            reason=payload.reason,
            is_half_day=payload.is_half_day,
            half_day_period=payload.half_day_period,
            emergency_contact=payload.emergency_contact,
        )
    except LeaveEngineError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Reload with relations
    stmt = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.department),
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.approvals),
            selectinload(LeaveRequest.documents),
        )
        .where(LeaveRequest.id == leave.id)
    )
    res = await db.execute(stmt)
    full_leave = res.scalars().first()
    return _serialize_leave_response(full_leave)


@router.post("/", response_model=LeaveResponse, status_code=status.HTTP_201_CREATED)
async def create_leave_request_legacy(
    payload: LeaveCreate,
    current_emp: EmployeeProfile = Depends(get_current_employee_profile),
    current_user: User = Depends(require_permission("leave:requests:create")),
    db: AsyncSession = Depends(get_db),
) -> LeaveResponse:
    """Legacy backward-compatible leave creation route."""
    try:
        leave = await LeaveEngine.apply_for_leave(
            db=db,
            employee=current_emp,
            leave_type_id=payload.leave_type_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            reason=payload.reason,
            is_half_day=payload.is_half_day,
            half_day_period=payload.half_day_period,
            emergency_contact=payload.emergency_contact,
        )
    except LeaveEngineError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    stmt = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.department),
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.approvals),
            selectinload(LeaveRequest.documents),
        )
        .where(LeaveRequest.id == leave.id)
    )
    res = await db.execute(stmt)
    full_leave = res.scalars().first()
    return _serialize_leave_response(full_leave)


@router.post("/{leave_id}/withdraw", response_model=LeaveResponse)
async def withdraw_leave(
    leave_id: uuid.UUID,
    current_emp: EmployeeProfile = Depends(get_current_employee_profile),
    db: AsyncSession = Depends(get_db),
) -> LeaveResponse:
    """Withdraw an active pending leave request and restore reserved days."""
    try:
        leave = await LeaveEngine.withdraw_leave(
            db=db,
            leave_id=leave_id,
            employee_id=current_emp.id,
        )
    except LeaveEngineError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    stmt = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.department),
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.approvals),
            selectinload(LeaveRequest.documents),
        )
        .where(LeaveRequest.id == leave.id)
    )
    res = await db.execute(stmt)
    full_leave = res.scalars().first()
    return _serialize_leave_response(full_leave)


@router.get("/", response_model=list[LeaveResponse])
async def list_user_leaves(
    current_emp: EmployeeProfile = Depends(get_current_employee_profile),
    db: AsyncSession = Depends(get_db),
) -> list[LeaveResponse]:
    """List all leave requests for the authenticated employee."""
    stmt = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.department),
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.approvals).selectinload(LeaveApproval.approver),
            selectinload(LeaveRequest.documents),
        )
        .where(LeaveRequest.employee_id == current_emp.id)
        .order_by(desc(LeaveRequest.created_at))
    )
    result = await db.execute(stmt)
    leaves = result.scalars().all()
    return [_serialize_leave_response(item) for item in leaves]


@router.get("/employee/{employee_id}", response_model=list[LeaveResponse])
async def get_employee_leaves(
    employee_id: uuid.UUID,
    target_emp_id: uuid.UUID = Depends(require_employee_access),
    db: AsyncSession = Depends(get_db),
) -> list[LeaveResponse]:
    """Retrieve leave requests for a specific employee with role-based scoping."""
    stmt = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.department),
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.approvals).selectinload(LeaveApproval.approver),
            selectinload(LeaveRequest.documents),
        )
        .where(LeaveRequest.employee_id == target_emp_id)
        .order_by(desc(LeaveRequest.created_at))
    )
    result = await db.execute(stmt)
    leaves = result.scalars().all()
    return [_serialize_leave_response(item) for item in leaves]


# ==========================================
# Multi-Tier Review Endpoints
# ==========================================

@router.post("/{leave_id}/manager-review", response_model=LeaveResponse)
async def review_leave_manager(
    leave_id: uuid.UUID,
    payload: LeaveReviewRequest,
    current_emp: EmployeeProfile = Depends(get_current_employee_profile),
    current_user: User = Depends(require_permission("leave:requests:approve")),
    db: AsyncSession = Depends(get_db),
) -> LeaveResponse:
    """
    Tier 1 Workflow: Manager review.
    - Prohibits self-approval.
    - Ensures manager is assigned to employee (unless admin).
    - If REJECT: closes request immediately.
    - If APPROVE: marks manager approval, awaits HR.
    """
    is_admin = bool(current_user.is_superuser or (current_user.role and "admin" in current_user.role.name.lower()))
    try:
        leave = await LeaveEngine.process_manager_review(
            db=db,
            leave_id=leave_id,
            approver=current_emp,
            action=payload.action,
            comments=payload.comments,
            is_admin=is_admin,
        )
    except LeaveEngineError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    stmt = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.department),
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.approvals).selectinload(LeaveApproval.approver),
            selectinload(LeaveRequest.documents),
        )
        .where(LeaveRequest.id == leave.id)
    )
    res = await db.execute(stmt)
    full_leave = res.scalars().first()
    return _serialize_leave_response(full_leave)


@router.post("/{leave_id}/hr-review", response_model=LeaveResponse)
async def review_leave_hr(
    leave_id: uuid.UUID,
    payload: LeaveReviewRequest,
    current_emp: EmployeeProfile = Depends(get_current_employee_profile),
    current_user: User = Depends(require_role(["Admin", "Super Admin", "HR"])),
    db: AsyncSession = Depends(get_db),
) -> LeaveResponse:
    """
    Tier 2 Workflow: HR review and Final Approval.
    - Mandatory manager approval check.
    - Prohibits self-approval.
    - If REJECT: closes request immediately.
    - If APPROVE: finalizes balance, updates AttendanceDay records.
    """
    is_admin = bool(current_user.is_superuser or (current_user.role and "admin" in current_user.role.name.lower()))
    try:
        leave = await LeaveEngine.process_hr_review(
            db=db,
            leave_id=leave_id,
            approver=current_emp,
            action=payload.action,
            comments=payload.comments,
            is_admin=is_admin,
        )
    except LeaveEngineError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    stmt = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.department),
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.approvals).selectinload(LeaveApproval.approver),
            selectinload(LeaveRequest.documents),
        )
        .where(LeaveRequest.id == leave.id)
    )
    res = await db.execute(stmt)
    full_leave = res.scalars().first()
    return _serialize_leave_response(full_leave)


class LeaveAdminOverrideRequest(BaseModel):
    action: str  # "APPROVE" or "REJECT"
    remarks: str


@router.post("/{leave_id}/admin-override", response_model=LeaveResponse)
async def admin_override_leave(
    leave_id: uuid.UUID,
    payload: LeaveAdminOverrideRequest,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> LeaveResponse:
    """
    Administrative override for leave approvals/rejections with mandatory remarks
    and dedicated AuditLog entry (action='ADMIN_OVERRIDE').
    """
    admin_name = current_user.full_name or current_user.email
    try:
        leave = await LeaveEngine.process_admin_override(
            db=db,
            leave_id=leave_id,
            admin_user_id=current_user.id,
            admin_name=admin_name,
            action=payload.action,
            remarks=payload.remarks,
            organization_id=current_user.organization_id,
        )
    except LeaveEngineError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    stmt = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.department),
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.approvals).selectinload(LeaveApproval.approver),
            selectinload(LeaveRequest.documents),
        )
        .where(LeaveRequest.id == leave.id)
    )
    res = await db.execute(stmt)
    full_leave = res.scalars().first()
    return _serialize_leave_response(full_leave)


@router.post("/{leave_id}/approve", response_model=LeaveResponse)
async def approve_leave_request_legacy(
    leave_id: uuid.UUID,
    current_user: User = Depends(require_permission("leave:requests:approve")),
    db: AsyncSession = Depends(get_db),
) -> LeaveResponse:
    """
    Legacy approval endpoint for backward compatibility with earlier tests.
    Enforces authorization scoping:
    - Super Admin / Admin / HR: Authorized across tenant organization.
    - Manager: Authorized ONLY if the employee is an assigned direct report.
    - Employee: Blocked by permission.
    """
    stmt = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.department),
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.approvals),
            selectinload(LeaveRequest.documents),
        )
        .where(LeaveRequest.id == leave_id)
    )
    if not current_user.is_superuser:
        stmt = stmt.where(LeaveRequest.organization_id == current_user.organization_id)

    result = await db.execute(stmt)
    leave = result.scalars().first()

    if not leave:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found")

    user_role = current_user.role.name.strip().lower() if current_user.role else ""
    is_admin_or_hr = current_user.is_superuser or any(r in user_role for r in ["admin", "super administrator", "hr"])

    # Check manager hierarchy if user is a manager (and not admin or HR)
    if not is_admin_or_hr:
        if not current_user.employee_profile:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approver has no employee profile")

        # Check if the leave's employee is assigned to this manager
        assignment_stmt = select(ManagerAssignment).where(
            ManagerAssignment.manager_id == current_user.employee_profile.id,
            ManagerAssignment.employee_id == leave.employee_id,
        )
        as_res = await db.execute(assignment_stmt)
        assignment = as_res.scalars().first()
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only approve leave requests for your assigned team members.",
            )

    leave.status = LeaveStatus.APPROVED
    leave.manager_approval_status = ApprovalStatus.APPROVED
    leave.hr_approval_status = ApprovalStatus.APPROVED
    now = datetime.now(UTC)

    approver_emp_id = current_user.employee_profile.id if current_user.employee_profile else None
    if approver_emp_id:
        approval = LeaveApproval(
            leave_request_id=leave.id,
            approver_id=approver_emp_id,
            step_order=1,
            stage="MANAGER" if not is_admin_or_hr else "HR",
            status=ApprovalStatus.APPROVED,
            decided_at=now,
            comments="Approved by authorized manager/HR",
        )
        db.add(approval)

    # Update balance: pending -> used
    bal_stmt = select(LeaveBalance).where(
        LeaveBalance.employee_id == leave.employee_id,
        LeaveBalance.leave_type_id == leave.leave_type_id,
        LeaveBalance.year == leave.start_date.year,
    )
    bal_res = await db.execute(bal_stmt)
    balance = bal_res.scalars().first()
    if balance:
        balance.pending_days = max(0.0, balance.pending_days - leave.total_days)
        balance.used_days += leave.total_days

    await db.commit()
    await db.refresh(leave)
    return _serialize_leave_response(leave)


# ==========================================
# Dashboards & Summaries
# ==========================================

@router.get("/dashboard/manager", response_model=LeaveDashboardSummary)
async def get_manager_leave_dashboard(
    current_emp: EmployeeProfile = Depends(get_current_employee_profile),
    current_user: User = Depends(require_permission("leave:requests:approve")),
    db: AsyncSession = Depends(get_db),
) -> LeaveDashboardSummary:
    """Dashboard view for Managers: shows pending requests from assigned team members."""
    # Find direct subordinates
    sub_stmt = select(ManagerAssignment.employee_id).where(
        ManagerAssignment.manager_id == current_emp.id
    )
    sub_res = await db.execute(sub_stmt)
    sub_ids = list(sub_res.scalars().all())

    if not sub_ids:
        return LeaveDashboardSummary(
            pending_manager_reviews=0,
            pending_hr_reviews=0,
            my_pending_requests=0,
            my_approved_requests=0,
            recent_requests=[],
        )

    stmt = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.department),
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.approvals).selectinload(LeaveApproval.approver),
            selectinload(LeaveRequest.documents),
        )
        .where(
            LeaveRequest.employee_id.in_(sub_ids),
            LeaveRequest.status == LeaveStatus.PENDING,
            LeaveRequest.manager_approval_status == ApprovalStatus.PENDING,
        )
        .order_by(LeaveRequest.created_at)
    )
    res = await db.execute(stmt)
    pending_items = res.scalars().all()

    return LeaveDashboardSummary(
        pending_manager_reviews=len(pending_items),
        pending_hr_reviews=0,
        my_pending_requests=0,
        my_approved_requests=0,
        recent_requests=[_serialize_leave_response(r) for r in pending_items],
    )


@router.get("/dashboard/hr", response_model=LeaveDashboardSummary)
async def get_hr_leave_dashboard(
    current_user: User = Depends(require_role(["Admin", "Super Admin", "HR"])),
    db: AsyncSession = Depends(get_db),
) -> LeaveDashboardSummary:
    """Dashboard view for HR: shows all requests that have manager approval and await HR final approval."""
    stmt = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.department),
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.approvals).selectinload(LeaveApproval.approver),
            selectinload(LeaveRequest.documents),
        )
        .where(
            LeaveRequest.organization_id == current_user.organization_id,
            LeaveRequest.status == LeaveStatus.PENDING,
            LeaveRequest.manager_approval_status == ApprovalStatus.APPROVED,
            LeaveRequest.hr_approval_status == ApprovalStatus.PENDING,
        )
        .order_by(LeaveRequest.created_at)
    )
    res = await db.execute(stmt)
    pending_items = res.scalars().all()

    return LeaveDashboardSummary(
        pending_manager_reviews=0,
        pending_hr_reviews=len(pending_items),
        my_pending_requests=0,
        my_approved_requests=0,
        recent_requests=[_serialize_leave_response(r) for r in pending_items],
    )


# ==========================================
# Supporting Documents
# ==========================================

@router.post("/{leave_id}/documents", response_model=LeaveDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_supporting_document(
    leave_id: uuid.UUID,
    payload: LeaveDocumentCreate,
    current_emp: EmployeeProfile = Depends(get_current_employee_profile),
    db: AsyncSession = Depends(get_db),
) -> LeaveDocument:
    """Attach supporting evidence (medical certificate, travel doc) to a leave request."""
    stmt = select(LeaveRequest).where(
        LeaveRequest.id == leave_id,
        LeaveRequest.employee_id == current_emp.id,
    )
    res = await db.execute(stmt)
    leave = res.scalars().first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found or not owned by you.")

    doc = LeaveDocument(
        leave_request_id=leave.id,
        file_name=sanitize_filename(payload.file_name),
        file_url=payload.file_url,
        file_size_bytes=payload.file_size_bytes,
        mime_type=payload.mime_type,
        uploaded_at=datetime.now(UTC),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get("/{leave_id}/documents", response_model=list[LeaveDocumentResponse])
async def list_leave_documents(
    leave_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[LeaveDocument]:
    """Retrieve supporting documents for a leave request with strict authorization verification."""
    stmt = select(LeaveRequest).where(LeaveRequest.id == leave_id)
    res = await db.execute(stmt)
    leave = res.scalars().first()
    if not leave:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found.")

    allowed = await check_employee_record_access(leave.employee_id, current_user, db)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to view documents for this leave request.",
        )

    doc_stmt = select(LeaveDocument).where(LeaveDocument.leave_request_id == leave_id)
    doc_res = await db.execute(doc_stmt)
    return list(doc_res.scalars().all())
