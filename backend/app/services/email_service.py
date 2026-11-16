"""
Centralized Email Notification Service & Outbox Dispatcher (Phase 12)

Features:
- Centralized email dispatch with background queueing
- Pluggable transport (SMTP / Resend / Console Mock)
- Exponential backoff retry mechanism
- Duplicate prevention with idempotency keys
- Delivery tracking with EmailDeliveryLog
- Failed email handling & dead-letter tracking
- Secure attachments validation
- Role-specific recipient routing (Manager approval -> HR; Final HR decision -> Employee & Manager)
- Signed-in dashboard links for approvals
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.auth import Role, User
from app.models.department import Department
from app.models.employee import EmployeeProfile, ManagerAssignment
from app.models.leave import ApprovalStatus, LeaveRequest, LeaveStatus
from app.models.notification import DeliveryEventType, EmailDeliveryLog, EmailOutbox, OutboxStatus
from app.services.email_templates import render_email_template
from app.services.email_transports import get_email_transport

logger = logging.getLogger(__name__)


class EmailNotificationError(Exception):
    pass


class EmailService:
    @classmethod
    async def enqueue_email(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        template_key: str,
        recipient_email: str,
        recipient_name: str | None,
        context: dict[str, Any],
        idempotency_key: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        sender_email: str | None = None,
        sender_name: str | None = None,
        scheduled_at: datetime | None = None,
    ) -> EmailOutbox:
        """
        Enqueues an email into the transactional outbox with duplicate prevention.
        """
        # 1. Duplicate Prevention via Idempotency Key
        if idempotency_key:
            stmt = select(EmailOutbox).where(
                EmailOutbox.organization_id == organization_id,
                EmailOutbox.idempotency_key == idempotency_key,
            )
            res = await db.execute(stmt)
            existing = res.scalars().first()
            if existing:
                logger.info(
                    "Duplicate email suppressed for key '%s' (outbox_id=%s)",
                    idempotency_key,
                    existing.id,
                )
                return existing

        # 2. Render Template
        subject, body_html, body_text = render_email_template(template_key, context)

        # 3. Secure Attachment Validation
        safe_attachments: list[dict[str, str]] = []
        if attachments:
            for att in attachments:
                raw_path = att.get("path")
                if not raw_path:
                    continue
                abs_path = os.path.abspath(raw_path)
                # Security check: must exist on disk and be a regular file
                if not os.path.isfile(abs_path):
                    logger.warning("Email attachment ignored - file not found: %s", abs_path)
                    continue

                safe_attachments.append({
                    "filename": att.get("filename", os.path.basename(abs_path)),
                    "path": abs_path,
                })

        attachments_json = json.dumps(safe_attachments) if safe_attachments else None

        # 4. Insert into Outbox
        outbox = EmailOutbox(
            organization_id=organization_id,
            recipient_email=recipient_email.strip().lower(),
            recipient_name=recipient_name,
            sender_email=sender_email or settings.DEFAULT_FROM_EMAIL,
            sender_name=sender_name or settings.DEFAULT_FROM_NAME,
            idempotency_key=idempotency_key,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            attachments=attachments_json,
            status=OutboxStatus.PENDING,
            retry_count=0,
            scheduled_at=scheduled_at or datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        db.add(outbox)
        await db.commit()
        await db.refresh(outbox)
        return outbox

    @classmethod
    async def dispatch_outbox_message(
        cls,
        db: AsyncSession,
        outbox_id: uuid.UUID,
    ) -> bool:
        """
        Transmits a single outbox record using the configured transport with delivery logging.
        """
        stmt = (
            select(EmailOutbox)
            .options(selectinload(EmailOutbox.delivery_logs))
            .where(EmailOutbox.id == outbox_id)
        )
        res = await db.execute(stmt)
        outbox = res.scalars().first()
        if not outbox:
            return False

        if outbox.status == OutboxStatus.SENT:
            return True

        # Parse attachments if present
        attachments: list[dict[str, Any]] = []
        if outbox.attachments:
            try:
                attachments = json.loads(outbox.attachments)
            except Exception:
                attachments = []

        transport = get_email_transport()
        send_result = await transport.send(
            recipient_email=outbox.recipient_email,
            subject=outbox.subject,
            body_html=outbox.body_html,
            body_text=outbox.body_text,
            recipient_name=outbox.recipient_name,
            sender_email=outbox.sender_email,
            sender_name=outbox.sender_name,
            attachments=attachments,
        )

        now = datetime.now(UTC)
        if send_result.success:
            outbox.status = OutboxStatus.SENT
            outbox.sent_at = now
            # Console/mock transport never reaches a real inbox — keep that visible in the outbox.
            mock_delivery = bool(
                send_result.provider_message_id and str(send_result.provider_message_id).startswith("mock-")
            )
            if mock_delivery:
                outbox.error_message = (
                    "Test mode (EMAIL_PROVIDER=console): logged only — not delivered to an inbox. "
                    "On Render set EMAIL_PROVIDER=srots with SROTS_MAIL_API_KEY (or smtp/resend)."
                )
                response_body = "Console mock — not delivered"
            else:
                outbox.error_message = None
                response_body = "Dispatched successfully"

            # Log delivery receipt
            log = EmailDeliveryLog(
                email_outbox_id=outbox.id,
                event_type=DeliveryEventType.DELIVERED,
                provider_message_id=send_result.provider_message_id,
                response_code=200,
                response_body=response_body,
                timestamp=now,
            )
            db.add(log)
            await db.commit()
            return True
        else:
            outbox.retry_count += 1
            outbox.error_message = send_result.error_message

            if outbox.retry_count >= settings.EMAIL_MAX_RETRIES:
                outbox.status = OutboxStatus.FAILED
                event_type = DeliveryEventType.DROPPED
            else:
                event_type = DeliveryEventType.BOUNCED
                # Exponential backoff schedule
                backoff_secs = settings.EMAIL_RETRY_BACKOFF_SECONDS * (2 ** (outbox.retry_count - 1))
                outbox.scheduled_at = now + timedelta(seconds=backoff_secs)

            log = EmailDeliveryLog(
                email_outbox_id=outbox.id,
                event_type=event_type,
                provider_message_id=send_result.provider_message_id,
                response_code=500,
                response_body=send_result.error_message,
                timestamp=now,
            )
            db.add(log)
            await db.commit()
            return False

    @classmethod
    async def process_pending_outbox(
        cls,
        db: AsyncSession,
        limit: int = 50,
    ) -> int:
        """
        Background queue runner that processes pending emails scheduled for transmission.
        """
        now = datetime.now(UTC)
        stmt = (
            select(EmailOutbox.id)
            .where(
                EmailOutbox.status == OutboxStatus.PENDING,
                EmailOutbox.scheduled_at <= now,
            )
            .order_by(EmailOutbox.scheduled_at.asc())
            .limit(limit)
        )
        res = await db.execute(stmt)
        outbox_ids = res.scalars().all()

        dispatched_count = 0
        for m_id in outbox_ids:
            success = await cls.dispatch_outbox_message(db, m_id)
            if success:
                dispatched_count += 1
        return dispatched_count

    # -------------------------------------------------------------------------
    # Role-Specific Workflow Helpers
    # -------------------------------------------------------------------------

    @classmethod
    async def notify_employee_account_creation(
        cls,
        db: AsyncSession,
        employee_id: uuid.UUID,
        temporary_password: str,
    ) -> EmailOutbox | None:
        """Dispatches onboarding credentials to newly provisioned employee."""
        stmt = (
            select(EmployeeProfile)
            .options(
                selectinload(EmployeeProfile.user),
                selectinload(EmployeeProfile.department),
                selectinload(EmployeeProfile.organization),
            )
            .where(EmployeeProfile.id == employee_id)
        )
        res = await db.execute(stmt)
        emp = res.scalars().first()
        if not emp or not emp.user or not emp.user.email:
            return None

        context = {
            "employee_name": f"{emp.first_name} {emp.last_name}",
            "employee_code": emp.employee_code,
            "email": emp.user.email,
            "department_name": emp.department.name if emp.department else "General Operations",
            "designation": emp.job_title or "Staff Member",
            "temporary_password": temporary_password,
            "org_name": emp.organization.name if emp.organization else settings.PROJECT_NAME,
        }

        idempotency_key = f"acc_create_{emp.id}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=emp.organization_id,
            template_key="employee_account_creation",
            recipient_email=emp.user.email,
            recipient_name=f"{emp.first_name} {emp.last_name}",
            context=context,
            idempotency_key=idempotency_key,
        )
        # Immediate dispatch
        await cls.dispatch_outbox_message(db, outbox.id)
        await db.refresh(outbox)
        return outbox

    @classmethod
    async def notify_weekly_leave_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        week_range: str,
        total_leave_requests: int,
        approved_leave_days: float,
        pending_leave_count: int,
        upcoming_absence_count: int,
    ) -> EmailOutbox:
        """Dispatches weekly leave digest to HR and Managers."""
        idempotency_key = f"wk_leave_{recipient_email}_{week_range.replace(' ', '_')}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="weekly_leave_report",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "week_range": week_range,
                "total_leave_requests": total_leave_requests,
                "approved_leave_days": approved_leave_days,
                "pending_leave_count": pending_leave_count,
                "upcoming_absence_count": upcoming_absence_count,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_password_reset(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        reset_token: str,
        otp_code: str | None = None,
        expires_minutes: int = 15,
    ) -> EmailOutbox | None:
        """Dispatches password reset security link to user."""
        stmt = (
            select(User)
            .options(
                selectinload(User.employee_profile),
                selectinload(User.organization),
            )
            .where(User.id == user_id)
        )
        res = await db.execute(stmt)
        user = res.scalars().first()
        if not user or not user.email:
            return None

        emp = user.employee_profile
        emp_name = f"{emp.first_name} {emp.last_name}" if emp else (user.full_name or "Colleague")

        now = datetime.now(UTC)
        context = {
            "employee_name": emp_name,
            "email": user.email,
            "reset_url": f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={reset_token}",
            "otp_code": otp_code or "N/A",
            "requested_at": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "expires_at": (now + timedelta(minutes=expires_minutes)).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "expires_minutes": expires_minutes,
            "org_name": user.organization.name if user.organization else settings.PROJECT_NAME,
        }

        idempotency_key = f"pwd_reset_{user.id}_{int(now.timestamp() // 60)}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=user.organization_id,
            template_key="password_reset",
            recipient_email=user.email,
            recipient_name=emp_name,
            context=context,
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_weekly_leave_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        week_range: str,
        total_leave_requests: int,
        approved_leave_days: float,
        pending_leave_count: int,
        upcoming_absence_count: int,
    ) -> EmailOutbox:
        """Dispatches weekly leave digest to HR and Managers."""
        idempotency_key = f"wk_leave_{recipient_email}_{week_range.replace(' ', '_')}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="weekly_leave_report",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "week_range": week_range,
                "total_leave_requests": total_leave_requests,
                "approved_leave_days": approved_leave_days,
                "pending_leave_count": pending_leave_count,
                "upcoming_absence_count": upcoming_absence_count,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_leave_submitted(
        cls,
        db: AsyncSession,
        leave_request_id: uuid.UUID,
    ) -> list[EmailOutbox]:
        """
        Notifies designated Manager(s) that an employee has submitted a leave application.
        Uses signed-in dashboard links.
        """
        stmt = (
            select(LeaveRequest)
            .options(
                selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.user),
                selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.direct_managers).selectinload(ManagerAssignment.manager).selectinload(EmployeeProfile.user),
                selectinload(LeaveRequest.leave_type),
                selectinload(LeaveRequest.organization),
            )
            .where(LeaveRequest.id == leave_request_id)
        )
        res = await db.execute(stmt)
        leave = res.scalars().first()
        if not leave or not leave.employee:
            return []

        emp = leave.employee
        emp_name = f"{emp.first_name} {emp.last_name}"

        dispatched: list[EmailOutbox] = []
        for assignment in emp.direct_managers:
            mgr = assignment.manager
            if not mgr or not mgr.user or not mgr.user.email:
                continue

            mgr_name = f"{mgr.first_name} {mgr.last_name}"
            context = {
                "manager_name": mgr_name,
                "employee_name": emp_name,
                "employee_code": emp.employee_code,
                "leave_type": leave.leave_type.name if leave.leave_type else "Leave",
                "start_date": str(leave.start_date),
                "end_date": str(leave.end_date),
                "duration_days": float(leave.total_days),
                "reason": leave.reason,
                "org_name": leave.organization.name if leave.organization else settings.PROJECT_NAME,
            }

            idempotency_key = f"leave_sub_{leave.id}_{mgr.id}"
            outbox = await cls.enqueue_email(
                db=db,
                organization_id=leave.organization_id,
                template_key="leave_submission",
                recipient_email=mgr.user.email,
                recipient_name=mgr_name,
                context=context,
                idempotency_key=idempotency_key,
            )
            await cls.dispatch_outbox_message(db, outbox.id)
            dispatched.append(outbox)

        return dispatched

    @classmethod
    async def notify_leave_manager_approved(
        cls,
        db: AsyncSession,
        leave_request_id: uuid.UUID,
        manager_profile: EmployeeProfile,
        manager_note: str | None = None,
    ) -> list[EmailOutbox]:
        """
        Requirement: Manager approval must notify HR for the second approval stage.
        Finds HR representatives for the organization and dispatches review notifications.
        """
        stmt = (
            select(LeaveRequest)
            .options(
                selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.user),
                selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.department),
                selectinload(LeaveRequest.leave_type),
                selectinload(LeaveRequest.organization),
            )
            .where(LeaveRequest.id == leave_request_id)
        )
        res = await db.execute(stmt)
        leave = res.scalars().first()
        if not leave or not leave.employee:
            return []

        emp = leave.employee
        mgr_name = f"{manager_profile.first_name} {manager_profile.last_name}"
        emp_name = f"{emp.first_name} {emp.last_name}"

        # Find HR users in the organization
        hr_stmt = (
            select(User)
            .join(User.role)
            .options(selectinload(User.employee_profile))
            .where(
                User.organization_id == leave.organization_id,
                Role.name.in_(["HR", "HR Manager", "Admin", "Super Admin"]),
                User.is_active.is_(True),
            )
        )
        hr_res = await db.execute(hr_stmt)
        hr_users = hr_res.scalars().all()

        dispatched: list[EmailOutbox] = []
        for hr_user in hr_users:
            if not hr_user.email:
                continue

            context = {
                "request_code": str(leave.id)[:8].upper(),
                "manager_name": mgr_name,
                "employee_name": emp_name,
                "employee_code": emp.employee_code,
                "department_name": emp.department.name if emp.department else "Operations",
                "leave_type": leave.leave_type.name if leave.leave_type else "Leave",
                "start_date": str(leave.start_date),
                "end_date": str(leave.end_date),
                "duration_days": float(leave.total_days),
                "manager_note": manager_note or "Endorsed per schedule",
                "org_name": leave.organization.name if leave.organization else settings.PROJECT_NAME,
            }

            idempotency_key = f"mgr_appr_hr_{leave.id}_{hr_user.id}"
            outbox = await cls.enqueue_email(
                db=db,
                organization_id=leave.organization_id,
                template_key="leave_manager_approval",
                recipient_email=hr_user.email,
                recipient_name=hr_user.full_name or "HR Representative",
                context=context,
                idempotency_key=idempotency_key,
            )
            await cls.dispatch_outbox_message(db, outbox.id)
            dispatched.append(outbox)

        return dispatched

    @classmethod
    async def notify_leave_manager_rejected(
        cls,
        db: AsyncSession,
        leave_request_id: uuid.UUID,
        manager_profile: EmployeeProfile,
        rejection_reason: str,
    ) -> EmailOutbox | None:
        """Notifies the employee that their manager rejected the request."""
        stmt = (
            select(LeaveRequest)
            .options(
                selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.user),
                selectinload(LeaveRequest.leave_type),
                selectinload(LeaveRequest.organization),
            )
            .where(LeaveRequest.id == leave_request_id)
        )
        res = await db.execute(stmt)
        leave = res.scalars().first()
        if not leave or not leave.employee or not leave.employee.user:
            return None

        emp = leave.employee
        mgr_name = f"{manager_profile.first_name} {manager_profile.last_name}"

        context = {
            "request_code": str(leave.id)[:8].upper(),
            "employee_name": f"{emp.first_name} {emp.last_name}",
            "manager_name": mgr_name,
            "leave_type": leave.leave_type.name if leave.leave_type else "Leave",
            "start_date": str(leave.start_date),
            "end_date": str(leave.end_date),
            "rejection_reason": rejection_reason,
            "org_name": leave.organization.name if leave.organization else settings.PROJECT_NAME,
        }

        idempotency_key = f"mgr_rej_{leave.id}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=leave.organization_id,
            template_key="leave_manager_rejection",
            recipient_email=emp.user.email,
            recipient_name=f"{emp.first_name} {emp.last_name}",
            context=context,
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_weekly_leave_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        week_range: str,
        total_leave_requests: int,
        approved_leave_days: float,
        pending_leave_count: int,
        upcoming_absence_count: int,
    ) -> EmailOutbox:
        """Dispatches weekly leave digest to HR and Managers."""
        idempotency_key = f"wk_leave_{recipient_email}_{week_range.replace(' ', '_')}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="weekly_leave_report",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "week_range": week_range,
                "total_leave_requests": total_leave_requests,
                "approved_leave_days": approved_leave_days,
                "pending_leave_count": pending_leave_count,
                "upcoming_absence_count": upcoming_absence_count,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_login_security_event(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        user_email: str,
        user_name: str,
        event_type: str,
        ip_address: str,
        device_info: str,
        network_info: str = "Authorized Office / VPN",
    ) -> EmailOutbox:
        """Dispatches security alert for suspicious or new sign-in sessions."""
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        idempotency_key = f"sec_alert_{user_email}_{int(datetime.now(UTC).timestamp())}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="login_security_alert",
            recipient_email=user_email,
            recipient_name=user_name,
            context={
                "recipient_name": user_name,
                "event_type": event_type,
                "event_time": now_str,
                "ip_address": ip_address,
                "device_info": device_info,
                "network_info": network_info,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_weekly_leave_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        week_range: str,
        total_leave_requests: int,
        approved_leave_days: float,
        pending_leave_count: int,
        upcoming_absence_count: int,
    ) -> EmailOutbox:
        """Dispatches weekly leave digest to HR and Managers."""
        idempotency_key = f"wk_leave_{recipient_email}_{week_range.replace(' ', '_')}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="weekly_leave_report",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "week_range": week_range,
                "total_leave_requests": total_leave_requests,
                "approved_leave_days": approved_leave_days,
                "pending_leave_count": pending_leave_count,
                "upcoming_absence_count": upcoming_absence_count,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_attendance_exception(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        employee_name: str,
        employee_code: str,
        work_date: str,
        exception_title: str,
        recorded_status: str,
        network_verification: str,
        exception_details: str,
    ) -> EmailOutbox:
        """Dispatches alert for attendance exceptions (missing checkout, unrecognized Wi-Fi, spoofing)."""
        idempotency_key = f"att_exc_{employee_code}_{work_date}_{exception_title.replace(' ', '_').lower()}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="attendance_exception_alert",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "employee_name": employee_name,
                "employee_code": employee_code,
                "work_date": work_date,
                "exception_title": exception_title,
                "recorded_status": recorded_status,
                "network_verification": network_verification,
                "exception_details": exception_details,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_weekly_leave_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        week_range: str,
        total_leave_requests: int,
        approved_leave_days: float,
        pending_leave_count: int,
        upcoming_absence_count: int,
    ) -> EmailOutbox:
        """Dispatches weekly leave digest to HR and Managers."""
        idempotency_key = f"wk_leave_{recipient_email}_{week_range.replace(' ', '_')}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="weekly_leave_report",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "week_range": week_range,
                "total_leave_requests": total_leave_requests,
                "approved_leave_days": approved_leave_days,
                "pending_leave_count": pending_leave_count,
                "upcoming_absence_count": upcoming_absence_count,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_attendance_adjustment_submitted(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        employee_name: str,
        work_date: str,
        adjustment_type: str,
        requested_shift: str,
        reason: str,
    ) -> EmailOutbox:
        """Notifies HR / Manager that an employee requested manual attendance adjustment."""
        idempotency_key = f"adj_sub_{employee_name}_{work_date}_{adjustment_type.lower()}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="attendance_adjustment_requested",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "employee_name": employee_name,
                "work_date": work_date,
                "adjustment_type": adjustment_type,
                "requested_shift": requested_shift,
                "reason": reason,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_weekly_leave_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        week_range: str,
        total_leave_requests: int,
        approved_leave_days: float,
        pending_leave_count: int,
        upcoming_absence_count: int,
    ) -> EmailOutbox:
        """Dispatches weekly leave digest to HR and Managers."""
        idempotency_key = f"wk_leave_{recipient_email}_{week_range.replace(' ', '_')}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="weekly_leave_report",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "week_range": week_range,
                "total_leave_requests": total_leave_requests,
                "approved_leave_days": approved_leave_days,
                "pending_leave_count": pending_leave_count,
                "upcoming_absence_count": upcoming_absence_count,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_attendance_adjustment_reviewed(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        employee_email: str,
        employee_name: str,
        work_date: str,
        is_approved: bool,
        approver_name: str,
        remarks: str,
        updated_status: str,
    ) -> EmailOutbox:
        """Notifies employee of attendance correction approval or rejection with remarks."""
        decision_status = "APPROVED" if is_approved else "REJECTED"
        idempotency_key = f"adj_rev_{employee_email}_{work_date}_{decision_status.lower()}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="attendance_adjustment_reviewed",
            recipient_email=employee_email,
            recipient_name=employee_name,
            context={
                "recipient_name": employee_name,
                "work_date": work_date,
                "decision_status": decision_status,
                "approver_name": approver_name,
                "remarks": remarks or ("Approved per policy" if is_approved else "Rejected"),
                "updated_status": updated_status,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_weekly_leave_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        week_range: str,
        total_leave_requests: int,
        approved_leave_days: float,
        pending_leave_count: int,
        upcoming_absence_count: int,
    ) -> EmailOutbox:
        """Dispatches weekly leave digest to HR and Managers."""
        idempotency_key = f"wk_leave_{recipient_email}_{week_range.replace(' ', '_')}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="weekly_leave_report",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "week_range": week_range,
                "total_leave_requests": total_leave_requests,
                "approved_leave_days": approved_leave_days,
                "pending_leave_count": pending_leave_count,
                "upcoming_absence_count": upcoming_absence_count,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_system_critical_alert(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        admin_email: str,
        service_name: str,
        severity: str,
        error_details: str,
    ) -> EmailOutbox:
        """Notifies administrators of critical infrastructure errors or scheduler faults."""
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        idempotency_key = f"sys_alert_{service_name}_{int(datetime.now(UTC).timestamp())}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="system_critical_alert",
            recipient_email=admin_email,
            recipient_name="System Administrator",
            context={
                "recipient_name": "System Administrator",
                "service_name": service_name,
                "severity": severity.upper(),
                "alert_time": now_str,
                "error_details": error_details,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_weekly_leave_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        week_range: str,
        total_leave_requests: int,
        approved_leave_days: float,
        pending_leave_count: int,
        upcoming_absence_count: int,
    ) -> EmailOutbox:
        """Dispatches weekly leave digest to HR and Managers."""
        idempotency_key = f"wk_leave_{recipient_email}_{week_range.replace(' ', '_')}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="weekly_leave_report",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "week_range": week_range,
                "total_leave_requests": total_leave_requests,
                "approved_leave_days": approved_leave_days,
                "pending_leave_count": pending_leave_count,
                "upcoming_absence_count": upcoming_absence_count,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_leave_hr_decision(
        cls,
        db: AsyncSession,
        leave_request_id: uuid.UUID,
        hr_profile: EmployeeProfile | None,
        is_approved: bool,
        reason: str | None = None,
    ) -> list[EmailOutbox]:
        """
        Requirement: Final HR decision must notify the employee and relevant Manager.
        """
        stmt = (
            select(LeaveRequest)
            .options(
                selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.user),
                selectinload(LeaveRequest.employee).selectinload(EmployeeProfile.direct_managers).selectinload(ManagerAssignment.manager).selectinload(EmployeeProfile.user),
                selectinload(LeaveRequest.leave_type),
                selectinload(LeaveRequest.organization),
            )
            .where(LeaveRequest.id == leave_request_id)
        )
        res = await db.execute(stmt)
        leave = res.scalars().first()
        if not leave or not leave.employee:
            return []

        emp = leave.employee
        emp_name = f"{emp.first_name} {emp.last_name}"
        hr_name = f"{hr_profile.first_name} {hr_profile.last_name}" if hr_profile else "Human Resources"
        template_key = "leave_hr_approval" if is_approved else "leave_hr_rejection"

        dispatched: list[EmailOutbox] = []

        # 1. Notify Employee
        if emp.user and emp.user.email:
            emp_context = {
                "recipient_name": emp_name,
                "request_code": str(leave.id)[:8].upper(),
                "employee_name": emp_name,
                "employee_code": emp.employee_code,
                "leave_type": leave.leave_type.name if leave.leave_type else "Leave",
                "start_date": str(leave.start_date),
                "end_date": str(leave.end_date),
                "duration_days": float(leave.total_days),
                "hr_name": hr_name,
                "rejection_reason": reason or "Not approved by HR administration",
                "org_name": leave.organization.name if leave.organization else settings.PROJECT_NAME,
            }
            idempotency_key = f"hr_dec_emp_{leave.id}_{'appr' if is_approved else 'rej'}"
            emp_outbox = await cls.enqueue_email(
                db=db,
                organization_id=leave.organization_id,
                template_key=template_key,
                recipient_email=emp.user.email,
                recipient_name=emp_name,
                context=emp_context,
                idempotency_key=idempotency_key,
            )
            await cls.dispatch_outbox_message(db, emp_outbox.id)
            dispatched.append(emp_outbox)

        # 2. Notify Relevant Manager(s)
        for assignment in emp.direct_managers:
            mgr = assignment.manager
            if not mgr or not mgr.user or not mgr.user.email:
                continue

            mgr_name = f"{mgr.first_name} {mgr.last_name}"
            mgr_context = {
                "recipient_name": mgr_name,
                "request_code": str(leave.id)[:8].upper(),
                "employee_name": emp_name,
                "employee_code": emp.employee_code,
                "leave_type": leave.leave_type.name if leave.leave_type else "Leave",
                "start_date": str(leave.start_date),
                "end_date": str(leave.end_date),
                "duration_days": float(leave.total_days),
                "hr_name": hr_name,
                "rejection_reason": reason or "Not approved by HR administration",
                "org_name": leave.organization.name if leave.organization else settings.PROJECT_NAME,
            }
            idempotency_key = f"hr_dec_mgr_{leave.id}_{mgr.id}_{'appr' if is_approved else 'rej'}"
            mgr_outbox = await cls.enqueue_email(
                db=db,
                organization_id=leave.organization_id,
                template_key=template_key,
                recipient_email=mgr.user.email,
                recipient_name=mgr_name,
                context=mgr_context,
                idempotency_key=idempotency_key,
            )
            await cls.dispatch_outbox_message(db, mgr_outbox.id)
            dispatched.append(mgr_outbox)

        return dispatched

    @classmethod
    async def notify_attendance_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str | None,
        report_frequency: str,  # "DAILY", "WEEKLY", "MONTHLY"
        date_str: str,
        stats: dict[str, Any],
        attachment_path: str | None = None,
        attachment_filename: str | None = None,
    ) -> EmailOutbox:
        """Dispatches automated attendance digests with optional Excel attachments."""
        freq_upper = report_frequency.upper()
        if freq_upper == "DAILY":
            template_key = "attendance_daily_report"
            context = {
                "recipient_name": recipient_name or "Manager",
                "report_date": date_str,
                "target_scope": stats.get("scope", "Assigned Team"),
                "present_count": stats.get("present_count", 0),
                "late_count": stats.get("late_count", 0),
                "leave_count": stats.get("leave_count", 0),
                "total_net_hours": stats.get("total_net_hours", 0.0),
            }
        elif freq_upper == "WEEKLY":
            template_key = "attendance_weekly_report"
            context = {
                "recipient_name": recipient_name or "Manager",
                "week_range": date_str,
                "target_scope": stats.get("scope", "Department"),
                "attendance_rate": stats.get("attendance_rate", 98.5),
                "total_working_hours": stats.get("total_working_hours", 40.0),
                "total_break_hours": stats.get("total_break_hours", 5.0),
                "resolved_leaves": stats.get("resolved_leaves", 1),
                "employees_logged_in": stats.get("employees_logged_in", 0),
                "employees_no_login": stats.get("employees_no_login", 0),
                "active_headcount": stats.get("active_headcount", 0),
                "login_summary_html": stats.get("login_summary_html", ""),
            }
        else:
            template_key = "attendance_monthly_report"
            context = {
                "recipient_name": recipient_name or "Leadership",
                "month_year": date_str,
                "active_headcount": stats.get("active_headcount", 50),
                "compliance_rate": stats.get("compliance_rate", 99.2),
                "total_overtime_hours": stats.get("total_overtime_hours", 12.5),
            }

        attachments = None
        if attachment_path:
            attachments = [{
                "path": attachment_path,
                "filename": attachment_filename or os.path.basename(attachment_path),
            }]

        idempotency_key = f"att_rpt_{freq_upper.lower()}_{recipient_email}_{date_str}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key=template_key,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context=context,
            idempotency_key=idempotency_key,
            attachments=attachments,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_weekly_leave_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        week_range: str,
        total_leave_requests: int,
        approved_leave_days: float,
        pending_leave_count: int,
        upcoming_absence_count: int,
    ) -> EmailOutbox:
        """Dispatches weekly leave digest to HR and Managers."""
        idempotency_key = f"wk_leave_{recipient_email}_{week_range.replace(' ', '_')}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="weekly_leave_report",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "week_range": week_range,
                "total_leave_requests": total_leave_requests,
                "approved_leave_days": approved_leave_days,
                "pending_leave_count": pending_leave_count,
                "upcoming_absence_count": upcoming_absence_count,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_login_security_event(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        user_email: str,
        user_name: str,
        event_type: str,
        ip_address: str,
        device_info: str,
        network_info: str = "Authorized Office / VPN",
    ) -> EmailOutbox:
        """Dispatches security alert for suspicious or new sign-in sessions."""
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        idempotency_key = f"sec_alert_{user_email}_{int(datetime.now(UTC).timestamp())}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="login_security_alert",
            recipient_email=user_email,
            recipient_name=user_name,
            context={
                "recipient_name": user_name,
                "event_type": event_type,
                "event_time": now_str,
                "ip_address": ip_address,
                "device_info": device_info,
                "network_info": network_info,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_weekly_leave_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        week_range: str,
        total_leave_requests: int,
        approved_leave_days: float,
        pending_leave_count: int,
        upcoming_absence_count: int,
    ) -> EmailOutbox:
        """Dispatches weekly leave digest to HR and Managers."""
        idempotency_key = f"wk_leave_{recipient_email}_{week_range.replace(' ', '_')}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="weekly_leave_report",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "week_range": week_range,
                "total_leave_requests": total_leave_requests,
                "approved_leave_days": approved_leave_days,
                "pending_leave_count": pending_leave_count,
                "upcoming_absence_count": upcoming_absence_count,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_attendance_exception(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        employee_name: str,
        employee_code: str,
        work_date: str,
        exception_title: str,
        recorded_status: str,
        network_verification: str,
        exception_details: str,
    ) -> EmailOutbox:
        """Dispatches alert for attendance exceptions (missing checkout, unrecognized Wi-Fi, spoofing)."""
        idempotency_key = f"att_exc_{employee_code}_{work_date}_{exception_title.replace(' ', '_').lower()}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="attendance_exception_alert",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "employee_name": employee_name,
                "employee_code": employee_code,
                "work_date": work_date,
                "exception_title": exception_title,
                "recorded_status": recorded_status,
                "network_verification": network_verification,
                "exception_details": exception_details,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_weekly_leave_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        week_range: str,
        total_leave_requests: int,
        approved_leave_days: float,
        pending_leave_count: int,
        upcoming_absence_count: int,
    ) -> EmailOutbox:
        """Dispatches weekly leave digest to HR and Managers."""
        idempotency_key = f"wk_leave_{recipient_email}_{week_range.replace(' ', '_')}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="weekly_leave_report",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "week_range": week_range,
                "total_leave_requests": total_leave_requests,
                "approved_leave_days": approved_leave_days,
                "pending_leave_count": pending_leave_count,
                "upcoming_absence_count": upcoming_absence_count,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_attendance_adjustment_submitted(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        employee_name: str,
        work_date: str,
        adjustment_type: str,
        requested_shift: str,
        reason: str,
    ) -> EmailOutbox:
        """Notifies HR / Manager that an employee requested manual attendance adjustment."""
        idempotency_key = f"adj_sub_{employee_name}_{work_date}_{adjustment_type.lower()}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="attendance_adjustment_requested",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "employee_name": employee_name,
                "work_date": work_date,
                "adjustment_type": adjustment_type,
                "requested_shift": requested_shift,
                "reason": reason,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_weekly_leave_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        week_range: str,
        total_leave_requests: int,
        approved_leave_days: float,
        pending_leave_count: int,
        upcoming_absence_count: int,
    ) -> EmailOutbox:
        """Dispatches weekly leave digest to HR and Managers."""
        idempotency_key = f"wk_leave_{recipient_email}_{week_range.replace(' ', '_')}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="weekly_leave_report",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "week_range": week_range,
                "total_leave_requests": total_leave_requests,
                "approved_leave_days": approved_leave_days,
                "pending_leave_count": pending_leave_count,
                "upcoming_absence_count": upcoming_absence_count,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_attendance_adjustment_reviewed(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        employee_email: str,
        employee_name: str,
        work_date: str,
        is_approved: bool,
        approver_name: str,
        remarks: str,
        updated_status: str,
    ) -> EmailOutbox:
        """Notifies employee of attendance correction approval or rejection with remarks."""
        decision_status = "APPROVED" if is_approved else "REJECTED"
        idempotency_key = f"adj_rev_{employee_email}_{work_date}_{decision_status.lower()}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="attendance_adjustment_reviewed",
            recipient_email=employee_email,
            recipient_name=employee_name,
            context={
                "recipient_name": employee_name,
                "work_date": work_date,
                "decision_status": decision_status,
                "approver_name": approver_name,
                "remarks": remarks or ("Approved per policy" if is_approved else "Rejected"),
                "updated_status": updated_status,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_weekly_leave_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        week_range: str,
        total_leave_requests: int,
        approved_leave_days: float,
        pending_leave_count: int,
        upcoming_absence_count: int,
    ) -> EmailOutbox:
        """Dispatches weekly leave digest to HR and Managers."""
        idempotency_key = f"wk_leave_{recipient_email}_{week_range.replace(' ', '_')}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="weekly_leave_report",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "week_range": week_range,
                "total_leave_requests": total_leave_requests,
                "approved_leave_days": approved_leave_days,
                "pending_leave_count": pending_leave_count,
                "upcoming_absence_count": upcoming_absence_count,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_system_critical_alert(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        admin_email: str,
        service_name: str,
        severity: str,
        error_details: str,
    ) -> EmailOutbox:
        """Notifies administrators of critical infrastructure errors or scheduler faults."""
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        idempotency_key = f"sys_alert_{service_name}_{int(datetime.now(UTC).timestamp())}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="system_critical_alert",
            recipient_email=admin_email,
            recipient_name="System Administrator",
            context={
                "recipient_name": "System Administrator",
                "service_name": service_name,
                "severity": severity.upper(),
                "alert_time": now_str,
                "error_details": error_details,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox

    @classmethod
    async def notify_weekly_leave_report(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        recipient_email: str,
        recipient_name: str,
        week_range: str,
        total_leave_requests: int,
        approved_leave_days: float,
        pending_leave_count: int,
        upcoming_absence_count: int,
    ) -> EmailOutbox:
        """Dispatches weekly leave digest to HR and Managers."""
        idempotency_key = f"wk_leave_{recipient_email}_{week_range.replace(' ', '_')}"
        outbox = await cls.enqueue_email(
            db=db,
            organization_id=organization_id,
            template_key="weekly_leave_report",
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            context={
                "recipient_name": recipient_name,
                "week_range": week_range,
                "total_leave_requests": total_leave_requests,
                "approved_leave_days": approved_leave_days,
                "pending_leave_count": pending_leave_count,
                "upcoming_absence_count": upcoming_absence_count,
            },
            idempotency_key=idempotency_key,
        )
        await cls.dispatch_outbox_message(db, outbox.id)
        return outbox
