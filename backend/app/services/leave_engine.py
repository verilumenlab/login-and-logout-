"""
Leave Management Workflow Engine (Phase 09)
Implements:
1. Multi-tier approval: EMPLOYEE -> MANAGER -> HR -> FINAL APPROVAL
2. Mandatory Manager approval before HR approval
3. Immediate closure on rejection at any stage
4. Strict self-approval prevention
5. Overlapping leave validation
6. Weekend and holiday handling via organization schedules
7. Half-day calculation (0.5 days)
8. Transaction-safe balance reservations and deductions
9. Automatic AttendanceDay population/update upon final approval
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.attendance import AttendanceDay, AttendanceStatus
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
from app.models.schedule import Holiday, WorkSchedule

logger = logging.getLogger("enterprise.leave_engine")


class LeaveEngineError(Exception):
    """Base exception for leave business rule violations."""
    pass


class LeaveEngine:
    """Enterprise leave calculation, policy validation, and approval workflow engine."""

    @staticmethod
    async def get_working_days_and_dates(
        db: AsyncSession,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        is_half_day: bool,
        include_weekends: bool,
    ) -> tuple[float, list[date]]:
        """
        Calculates working days in the leave range, accounting for weekends
        and recognized organization holidays.
        """
        if start_date > end_date:
            raise LeaveEngineError("End date cannot be earlier than start date.")

        if is_half_day and start_date != end_date:
            raise LeaveEngineError("Half-day leave must start and end on the exact same date.")

        # Query holidays in the date span
        holiday_stmt = select(Holiday.holiday_date).where(
            Holiday.organization_id == organization_id,
            Holiday.holiday_date >= start_date,
            Holiday.holiday_date <= end_date,
        )
        holiday_res = await db.execute(holiday_stmt)
        holiday_dates = set(holiday_res.scalars().all())

        if is_half_day:
            if not include_weekends and start_date.weekday() in (5, 6):
                raise LeaveEngineError("Cannot apply for half-day leave on a weekend.")
            if start_date in holiday_dates:
                raise LeaveEngineError(f"Cannot apply for leave on a recognized organization holiday ({start_date}).")
            return 0.5, [start_date]

        working_dates: list[date] = []
        curr = start_date
        while curr <= end_date:
            is_weekend = curr.weekday() in (5, 6)
            is_holiday = curr in holiday_dates

            if is_weekend and not include_weekends:
                curr += timedelta(days=1)
                continue

            if is_holiday:
                curr += timedelta(days=1)
                continue

            working_dates.append(curr)
            curr += timedelta(days=1)

        if not working_dates:
            raise LeaveEngineError("The selected date range contains no working days (all days are weekends or holidays).")

        return float(len(working_dates)), working_dates

    @staticmethod
    async def check_overlap(
        db: AsyncSession,
        employee_id: uuid.UUID,
        start_date: date,
        end_date: date,
        is_half_day: bool = False,
        half_day_period: str | None = None,
        exclude_request_id: uuid.UUID | None = None,
    ) -> None:
        """
        Ensures the employee does not have another active (PENDING or APPROVED)
        leave request overlapping the target dates.
        """
        stmt = select(LeaveRequest).where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.in_([LeaveStatus.PENDING, LeaveStatus.APPROVED]),
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
        if exclude_request_id:
            stmt = stmt.where(LeaveRequest.id != exclude_request_id)

        result = await db.execute(stmt)
        overlapping = result.scalars().all()

        for req in overlapping:
            # Check half-day compatibility on the exact same date
            if is_half_day and req.is_half_day and start_date == req.start_date:
                if half_day_period and req.half_day_period and half_day_period != req.half_day_period:
                    continue  # Morning + Afternoon on the same day is acceptable
            raise LeaveEngineError(
                f"An active leave request ({req.status.value}) already exists from "
                f"{req.start_date} to {req.end_date}."
            )

    @staticmethod
    async def get_or_create_balance(
        db: AsyncSession,
        organization_id: uuid.UUID,
        employee_id: uuid.UUID,
        leave_type: LeaveType,
        year: int,
    ) -> LeaveBalance:
        """
        Retrieves or initializes the employee's LeaveBalance for the target year.
        """
        stmt = (
            select(LeaveBalance)
            .where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type.id,
                LeaveBalance.year == year,
            )
            .with_for_update()
        )
        result = await db.execute(stmt)
        balance = result.scalars().first()

        if not balance:
            balance = LeaveBalance(
                organization_id=organization_id,
                employee_id=employee_id,
                leave_type_id=leave_type.id,
                year=year,
                allocated_days=float(leave_type.annual_allowance),
                used_days=0.0,
                pending_days=0.0,
                carryover_days=0.0,
            )
            db.add(balance)
            await db.flush()
        else:
            # Align allocation with current leave-type policy when HR updates allowances.
            target = float(leave_type.annual_allowance)
            if balance.allocated_days != target:
                balance.allocated_days = target
                await db.flush()

        return balance

    @classmethod
    async def apply_for_leave(
        cls,
        db: AsyncSession,
        employee: EmployeeProfile,
        leave_type_id: uuid.UUID,
        start_date: date,
        end_date: date,
        reason: str,
        is_half_day: bool = False,
        half_day_period: str | None = None,
        emergency_contact: str | None = None,
    ) -> LeaveRequest:
        """
        Validates leave request, reserves pending balance, and creates PENDING request.
        """
        # 1. Fetch leave type
        lt_stmt = select(LeaveType).where(
            LeaveType.id == leave_type_id,
            LeaveType.organization_id == employee.organization_id,
            LeaveType.is_active.is_(True),
        )
        lt_res = await db.execute(lt_stmt)
        leave_type = lt_res.scalars().first()
        if not leave_type:
            raise LeaveEngineError("Leave policy not found or inactive for this organization.")

        # 2. Check overlap
        await cls.check_overlap(
            db=db,
            employee_id=employee.id,
            start_date=start_date,
            end_date=end_date,
            is_half_day=is_half_day,
            half_day_period=half_day_period,
        )

        # 3. Calculate working days
        total_days, _ = await cls.get_working_days_and_dates(
            db=db,
            organization_id=employee.organization_id,
            start_date=start_date,
            end_date=end_date,
            is_half_day=is_half_day,
            include_weekends=leave_type.include_weekends,
        )

        # 4. Check & reserve balance
        balance = await cls.get_or_create_balance(
            db=db,
            organization_id=employee.organization_id,
            employee_id=employee.id,
            leave_type=leave_type,
            year=start_date.year,
        )

        available_days = balance.allocated_days + balance.carryover_days - balance.used_days - balance.pending_days
        if leave_type.category != LeaveCategory.UNPAID and total_days > available_days:
            raise LeaveEngineError(
                f"Insufficient leave balance. Requested: {total_days} days, "
                f"Available: {available_days} days."
            )

        # Reserve pending days
        balance.pending_days += total_days

        # 5. Create request
        leave_request = LeaveRequest(
            organization_id=employee.organization_id,
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            start_date=start_date,
            end_date=end_date,
            total_days=total_days,
            is_half_day=is_half_day,
            half_day_period=half_day_period if is_half_day else None,
            reason=reason,
            emergency_contact=emergency_contact,
            status=LeaveStatus.PENDING,
            manager_approval_status=ApprovalStatus.PENDING,
            hr_approval_status=ApprovalStatus.PENDING,
        )
        db.add(leave_request)
        await db.commit()
        await db.refresh(leave_request)

        # Notify direct managers (Phase 12 Centralized Notification)
        try:
            from app.services.email_service import EmailService
            await EmailService.notify_leave_submitted(db, leave_request.id)
        except Exception as e:
            logger.warning("Failed to dispatch leave submission notification: %s", e)

        return leave_request

    @classmethod
    async def withdraw_leave(
        cls,
        db: AsyncSession,
        leave_id: uuid.UUID,
        employee_id: uuid.UUID,
    ) -> LeaveRequest:
        """
        Allows an employee to cancel an active pending request, releasing reserved days.
        """
        stmt = select(LeaveRequest).where(
            LeaveRequest.id == leave_id,
            LeaveRequest.employee_id == employee_id,
        )
        res = await db.execute(stmt)
        leave = res.scalars().first()

        if not leave:
            raise LeaveEngineError("Leave request not found or does not belong to you.")

        if leave.status != LeaveStatus.PENDING:
            raise LeaveEngineError(f"Cannot withdraw leave request in '{leave.status.value}' status.")

        leave.status = LeaveStatus.CANCELLED
        leave.withdrawn_at = datetime.now(UTC)

        # Restore reserved pending days
        bal_stmt = select(LeaveBalance).where(
            LeaveBalance.employee_id == leave.employee_id,
            LeaveBalance.leave_type_id == leave.leave_type_id,
            LeaveBalance.year == leave.start_date.year,
        )
        bal_res = await db.execute(bal_stmt)
        balance = bal_res.scalars().first()
        if balance:
            balance.pending_days = max(0.0, balance.pending_days - leave.total_days)

        await db.commit()
        await db.refresh(leave)
        return leave

    @classmethod
    async def process_manager_review(
        cls,
        db: AsyncSession,
        leave_id: uuid.UUID,
        approver: EmployeeProfile,
        action: str,  # "APPROVE" or "REJECT"
        comments: str | None = None,
        is_admin: bool = False,
    ) -> LeaveRequest:
        """
        Tier 1 Workflow: Manager Review.
        - Strict check: Approver cannot approve their own leave.
        - Strict check: Approver must be assigned manager (unless admin).
        - If REJECT: Immediately closes request and releases pending days.
        - If APPROVE: Marks manager_approval_status=APPROVED, leaves status=PENDING for HR.
        """
        stmt = (
            select(LeaveRequest)
            .options(selectinload(LeaveRequest.leave_type))
            .where(LeaveRequest.id == leave_id)
        )
        res = await db.execute(stmt)
        leave = res.scalars().first()

        if not leave:
            raise LeaveEngineError("Leave request not found.")

        # Rule 1: No self-approval
        if leave.employee_id == approver.id:
            raise LeaveEngineError("Employees cannot approve or review their own leave applications.")

        # Rule 2: Manager assignment check (if not admin)
        if not is_admin:
            assign_stmt = select(ManagerAssignment).where(
                ManagerAssignment.manager_id == approver.id,
                ManagerAssignment.employee_id == leave.employee_id,
            )
            assign_res = await db.execute(assign_stmt)
            if not assign_res.scalars().first():
                raise LeaveEngineError("Access denied: You are not the designated manager for this employee.")

        # Rule 3: Valid state check
        if leave.status != LeaveStatus.PENDING or leave.manager_approval_status != ApprovalStatus.PENDING:
            raise LeaveEngineError("This leave request is not pending manager review.")

        now = datetime.now(UTC)
        action_upper = action.strip().upper()

        if action_upper == "REJECT":
            if not comments or not comments.strip():
                raise LeaveEngineError("Rejection remarks are mandatory.")
            leave.manager_approval_status = ApprovalStatus.REJECTED
            leave.status = LeaveStatus.REJECTED

            # Release reserved pending days
            bal_stmt = select(LeaveBalance).where(
                LeaveBalance.employee_id == leave.employee_id,
                LeaveBalance.leave_type_id == leave.leave_type_id,
                LeaveBalance.year == leave.start_date.year,
            )
            bal_res = await db.execute(bal_stmt)
            balance = bal_res.scalars().first()
            if balance:
                balance.pending_days = max(0.0, balance.pending_days - leave.total_days)

            approval = LeaveApproval(
                leave_request_id=leave.id,
                approver_id=approver.id,
                step_order=1,
                stage="MANAGER",
                status=ApprovalStatus.REJECTED,
                comments=comments or "Rejected by manager",
                decided_at=now,
            )
            db.add(approval)

        elif action_upper == "APPROVE":
            leave.manager_approval_status = ApprovalStatus.APPROVED
            # Status remains PENDING until HR approves

            approval = LeaveApproval(
                leave_request_id=leave.id,
                approver_id=approver.id,
                step_order=1,
                stage="MANAGER",
                status=ApprovalStatus.APPROVED,
                comments=comments or "Approved by manager",
                decided_at=now,
            )
            db.add(approval)
        else:
            raise LeaveEngineError(f"Invalid review action '{action}'. Must be 'APPROVE' or 'REJECT'.")

        await db.commit()
        await db.refresh(leave)

        # Phase 12 Requirement: Manager approval must notify HR for the second approval stage.
        # Manager rejection notifies the employee.
        try:
            from app.services.email_service import EmailService
            if action_upper == "APPROVE":
                await EmailService.notify_leave_manager_approved(db, leave.id, approver, comments)
            elif action_upper == "REJECT":
                await EmailService.notify_leave_manager_rejected(
                    db, leave.id, approver, comments or "Declined by reporting manager"
                )
        except Exception as e:
            logger.warning("Failed to dispatch manager review email: %s", e)

        return leave

    @classmethod
    async def process_hr_review(
        cls,
        db: AsyncSession,
        leave_id: uuid.UUID,
        approver: EmployeeProfile,
        action: str,  # "APPROVE" or "REJECT"
        comments: str | None = None,
        is_admin: bool = False,
    ) -> LeaveRequest:
        """
        Tier 2 Workflow: HR Review & Final Approval.
        - Strict check: Approver cannot approve their own leave.
        - Mandatory check: Manager approval MUST be approved first.
        - If REJECT: Immediately closes request and releases pending days.
        - If APPROVE:
          - Marks hr_approval_status=APPROVED, status=APPROVED (FINAL APPROVAL)
          - Balance: pending_days -> used_days
          - Attendance: Creates/updates AttendanceDay for all working days in range.
        """
        stmt = (
            select(LeaveRequest)
            .options(selectinload(LeaveRequest.leave_type))
            .where(LeaveRequest.id == leave_id)
        )
        res = await db.execute(stmt)
        leave = res.scalars().first()

        if not leave:
            raise LeaveEngineError("Leave request not found.")

        # Rule 1: No self-approval
        if leave.employee_id == approver.id:
            raise LeaveEngineError("Employees cannot approve or review their own leave applications.")

        # Rule 2: Mandatory manager approval first
        if leave.manager_approval_status != ApprovalStatus.APPROVED:
            raise LeaveEngineError("Manager approval is mandatory before HR can review this leave request.")

        # Rule 3: Valid state check
        if leave.status != LeaveStatus.PENDING or leave.hr_approval_status != ApprovalStatus.PENDING:
            raise LeaveEngineError("This leave request is not pending HR review.")

        now = datetime.now(UTC)
        action_upper = action.strip().upper()

        if action_upper == "REJECT":
            if not comments or not comments.strip():
                raise LeaveEngineError("Rejection remarks are mandatory.")
            leave.hr_approval_status = ApprovalStatus.REJECTED
            leave.status = LeaveStatus.REJECTED

            # Release reserved pending days
            bal_stmt = select(LeaveBalance).where(
                LeaveBalance.employee_id == leave.employee_id,
                LeaveBalance.leave_type_id == leave.leave_type_id,
                LeaveBalance.year == leave.start_date.year,
            )
            bal_res = await db.execute(bal_stmt)
            balance = bal_res.scalars().first()
            if balance:
                balance.pending_days = max(0.0, balance.pending_days - leave.total_days)

            approval = LeaveApproval(
                leave_request_id=leave.id,
                approver_id=approver.id,
                step_order=2,
                stage="HR",
                status=ApprovalStatus.REJECTED,
                comments=comments or "Rejected by HR",
                decided_at=now,
            )
            db.add(approval)

        elif action_upper == "APPROVE":
            leave.hr_approval_status = ApprovalStatus.APPROVED
            leave.status = LeaveStatus.APPROVED  # FINAL APPROVAL!

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

            approval = LeaveApproval(
                leave_request_id=leave.id,
                approver_id=approver.id,
                step_order=2,
                stage="HR",
                status=ApprovalStatus.APPROVED,
                comments=comments or "Approved by HR (Final)",
                decided_at=now,
            )
            db.add(approval)

            # ---------------------------------------------------------
            # Synchronize with Attendance Engine: Populate AttendanceDays
            # ---------------------------------------------------------
            _, working_dates = await cls.get_working_days_and_dates(
                db=db,
                organization_id=leave.organization_id,
                start_date=leave.start_date,
                end_date=leave.end_date,
                is_half_day=leave.is_half_day,
                include_weekends=leave.leave_type.include_weekends if leave.leave_type else False,
            )

            target_status = AttendanceStatus.HALF_DAY if leave.is_half_day else AttendanceStatus.ON_LEAVE

            for w_date in working_dates:
                day_stmt = select(AttendanceDay).where(
                    AttendanceDay.employee_id == leave.employee_id,
                    AttendanceDay.work_date == w_date,
                )
                day_res = await db.execute(day_stmt)
                att_day = day_res.scalars().first()

                meta = {
                    "leave_request_id": str(leave.id),
                    "leave_type_id": str(leave.leave_type_id),
                    "is_half_day": leave.is_half_day,
                    "half_day_period": leave.half_day_period,
                    "auto_generated_from_leave": True,
                }

                if att_day:
                    att_day.status = target_status
                    att_day.metadata_json = {**(att_day.metadata_json or {}), **meta}
                else:
                    new_day = AttendanceDay(
                        organization_id=leave.organization_id,
                        employee_id=leave.employee_id,
                        work_date=w_date,
                        status=target_status,
                        metadata_json=meta,
                    )
                    db.add(new_day)

        else:
            raise LeaveEngineError(f"Invalid review action '{action}'. Must be 'APPROVE' or 'REJECT'.")

        await db.commit()
        await db.refresh(leave)

        # Phase 12 Requirement: Final HR decision must notify the employee and relevant Manager.
        try:
            from app.services.email_service import EmailService
            if action_upper == "APPROVE":
                await EmailService.notify_leave_hr_decision(db, leave.id, approver, is_approved=True)
            elif action_upper == "REJECT":
                await EmailService.notify_leave_hr_decision(
                    db, leave.id, approver, is_approved=False, reason=comments
                )
        except Exception as e:
            logger.warning("Failed to dispatch HR decision email: %s", e)

        return leave

    @classmethod
    async def process_admin_override(
        cls,
        db: AsyncSession,
        leave_id: uuid.UUID,
        admin_user_id: uuid.UUID,
        admin_name: str,
        action: str,  # "APPROVE" or "REJECT"
        remarks: str,
        organization_id: uuid.UUID,
    ) -> LeaveRequest:
        """
        Prompt 17 Administrative Override:
        Allows System Administrator to bypass or override sequential manager/HR workflow
        with mandatory remarks and dedicated AuditLog tracking (action='ADMIN_OVERRIDE').
        """
        from app.models.auth import AuditLog

        if not remarks or not remarks.strip():
            raise LeaveEngineError("Administrative override reason and remarks are mandatory.")

        stmt = (
            select(LeaveRequest)
            .options(
                selectinload(LeaveRequest.leave_type),
                selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.department),
            )
            .where(
                LeaveRequest.id == leave_id,
                LeaveRequest.organization_id == organization_id,
            )
        )
        res = await db.execute(stmt)
        leave = res.scalars().first()
        if not leave:
            raise LeaveEngineError("Leave request not found.")

        old_status = leave.status.value
        now = datetime.now(UTC)
        action_upper = action.strip().upper()

        if action_upper == "REJECT":
            leave.manager_approval_status = ApprovalStatus.REJECTED
            leave.hr_approval_status = ApprovalStatus.REJECTED
            leave.status = LeaveStatus.REJECTED

            # Release reserved pending balance if was pending
            if old_status == "PENDING":
                bal_stmt = select(LeaveBalance).where(
                    LeaveBalance.employee_id == leave.employee_id,
                    LeaveBalance.leave_type_id == leave.leave_type_id,
                    LeaveBalance.year == leave.start_date.year,
                )
                bal_res = await db.execute(bal_stmt)
                balance = bal_res.scalars().first()
                if balance:
                    balance.pending_days = max(0.0, balance.pending_days - leave.total_days)

        elif action_upper == "APPROVE":
            leave.manager_approval_status = ApprovalStatus.APPROVED
            leave.hr_approval_status = ApprovalStatus.APPROVED
            leave.status = LeaveStatus.APPROVED

            # Balance update — never double-count an already-approved request.
            bal_stmt = select(LeaveBalance).where(
                LeaveBalance.employee_id == leave.employee_id,
                LeaveBalance.leave_type_id == leave.leave_type_id,
                LeaveBalance.year == leave.start_date.year,
            )
            bal_res = await db.execute(bal_stmt)
            balance = bal_res.scalars().first()
            if balance and old_status != "APPROVED":
                if old_status == "PENDING":
                    balance.pending_days = max(0.0, balance.pending_days - leave.total_days)
                balance.used_days += leave.total_days

            # Populate attendance days
            _, working_dates = await cls.get_working_days_and_dates(
                db=db,
                organization_id=leave.organization_id,
                start_date=leave.start_date,
                end_date=leave.end_date,
                is_half_day=leave.is_half_day,
                include_weekends=leave.leave_type.include_weekends if leave.leave_type else False,
            )
            target_status = AttendanceStatus.HALF_DAY if leave.is_half_day else AttendanceStatus.ON_LEAVE

            for w_date in working_dates:
                att_stmt = select(AttendanceDay).where(
                    AttendanceDay.employee_id == leave.employee_id,
                    AttendanceDay.work_date == w_date,
                )
                att_res = await db.execute(att_stmt)
                att_day = att_res.scalars().first()

                meta = {
                    "leave_request_id": str(leave.id),
                    "leave_type": leave.leave_type.name if leave.leave_type else "Leave",
                    "admin_override": True,
                    "override_by": admin_name,
                }
                if att_day:
                    att_day.status = target_status
                    att_day.metadata_json = {**(att_day.metadata_json or {}), **meta}
                else:
                    new_day = AttendanceDay(
                        organization_id=leave.organization_id,
                        employee_id=leave.employee_id,
                        work_date=w_date,
                        status=target_status,
                        metadata_json=meta,
                    )
                    db.add(new_day)
        else:
            raise LeaveEngineError("Action must be 'APPROVE' or 'REJECT'.")

        # Record dedicated administrative override audit log
        audit = AuditLog(
            organization_id=organization_id,
            user_id=admin_user_id,
            action="ADMIN_OVERRIDE",
            entity_type="leave_request",
            entity_id=str(leave.id),
            diff_json={
                "previous_status": old_status,
                "new_status": leave.status.value,
                "action": action_upper,
                "remarks": remarks.strip(),
                "admin_name": admin_name,
            },
        )
        db.add(audit)

        await db.commit()
        await db.refresh(leave)
        return leave

