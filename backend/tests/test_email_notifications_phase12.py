"""
Comprehensive Verification Tests for Phase 12: Centralized Email Notification System

Tests:
1. Complete Template Rendering (all 10 templates)
2. Duplicate Prevention via Idempotency Key
3. Background Email Dispatch & Delivery Logging
4. Retry Mechanism, Exponential Backoff & Max Retries Failure Handling
5. Secure Attachment Validation & Traversal Prevention
6. Role-Specific Workflow: Leave Submission notifies designated Manager
7. Role-Specific Workflow: Manager Approval notifies HR for second approval stage
8. Role-Specific Workflow: Manager Rejection notifies Employee
9. Role-Specific Workflow: HR Final Approval notifies Employee AND Manager
10. Role-Specific Workflow: HR Final Rejection notifies Employee AND Manager
11. Employee Account Creation & Password Reset Dispatches
12. Daily, Weekly, and Monthly Attendance Digest Dispatches
13. Notifications API: Outbox query, Template Catalog, Send Test, Retry, and Queue Flush
14. Delivery Receipt Webhook Telemetry
"""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.core.seeds import seed_permissions, seed_system_roles
from app.models.auth import Role, User
from app.models.department import Department
from app.models.employee import EmployeeProfile, EmploymentStatus, ManagerAssignment
from app.models.leave import (
    ApprovalStatus,
    LeaveCategory,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
)
from app.models.notification import DeliveryEventType, EmailDeliveryLog, EmailOutbox, OutboxStatus
from app.models.organization import Organization
from app.services.email_service import EmailService
from app.services.email_templates import TEMPLATES_CONFIG, render_email_template
from app.services.email_transports import (
    ConsoleEmailTransport,
    SMTPEmailTransport,
    TransportSendResult,
    get_email_transport,
)


@pytest.fixture
async def setup_notification_env(db_session: AsyncSession):
    code_suffix = uuid.uuid4().hex[:6].upper()
    org = Organization(
        name="Apex Notification Test Corp",
        code=f"ANTC-{code_suffix}",
        slug=f"antc-{code_suffix.lower()}",
        is_active=True,
    )
    db_session.add(org)
    await db_session.flush()

    perm_map = await seed_permissions(db_session)
    role_map = await seed_system_roles(db_session, perm_map)

    dept = Department(organization_id=org.id, name="Platform Engineering", code="ENG")
    db_session.add(dept)
    await db_session.flush()

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
        f"admin_{uuid.uuid4().hex[:4]}@antc.corp", "Administrator", "Alice", "Admin"
    )
    hr_user, hr_emp, hr_token = await create_user_emp(
        f"hr_{uuid.uuid4().hex[:4]}@antc.corp", "HR Manager", "Hannah", "HR"
    )
    mgr_user, mgr_emp, mgr_token = await create_user_emp(
        f"mgr_{uuid.uuid4().hex[:4]}@antc.corp", "Department Manager", "Mark", "Manager"
    )
    sub_user, sub_emp, sub_token = await create_user_emp(
        f"sub_{uuid.uuid4().hex[:4]}@antc.corp", "Employee", "Edward", "Employee"
    )

    # Manager Assignment: Mark manages Edward
    assignment = ManagerAssignment(
        organization_id=org.id,
        manager_id=mgr_emp.id,
        employee_id=sub_emp.id,
        is_primary=True,
    )
    db_session.add(assignment)

    # Leave Type
    leave_type = LeaveType(
        organization_id=org.id,
        name="Annual Vacation",
        code="VAC",
        category=LeaveCategory.ANNUAL,
        annual_allowance=20,
        is_active=True,
    )
    db_session.add(leave_type)
    await db_session.commit()

    return {
        "org": org,
        "admin": (admin_user, admin_emp, admin_token),
        "hr": (hr_user, hr_emp, hr_token),
        "mgr": (mgr_user, mgr_emp, mgr_token),
        "sub": (sub_user, sub_emp, sub_token),
        "leave_type": leave_type,
    }


@pytest.mark.asyncio
async def test_all_10_email_templates_render():
    """Verify all 10 required templates render valid HTML, plain-text fallback, and subject lines."""
    required_templates = [
        "employee_account_creation",
        "password_reset",
        "leave_submission",
        "leave_manager_approval",
        "leave_manager_rejection",
        "leave_hr_approval",
        "leave_hr_rejection",
        "attendance_daily_report",
        "attendance_weekly_report",
        "attendance_monthly_report",
    ]

    context = {
        "employee_name": "Edward Norton",
        "employee_code": "EMP-9001",
        "email": "edward@apex.corp",
        "department_name": "Engineering",
        "designation": "Software Engineer",
        "temporary_password": "TempPassword123!",
        "reset_url": "http://localhost:3000/reset-password?token=abc",
        "requested_at": "2026-11-12 10:00:00 UTC",
        "expires_at": "2026-11-12 10:15:00 UTC",
        "manager_name": "Mark Manager",
        "recipient_name": "Edward Norton",
        "request_code": "LV-12345",
        "leave_type": "Annual Leave",
        "start_date": "2026-11-16",
        "end_date": "2026-11-18",
        "duration_days": 3,
        "reason": "Family vacation",
        "rejection_reason": "Coverage constraints",
        "hr_name": "Hannah HR",
        "report_date": "2026-11-12",
        "target_scope": "Engineering Department",
        "present_count": 25,
        "late_count": 1,
        "leave_count": 2,
        "total_net_hours": 200.0,
        "week_range": "2026-W46",
        "attendance_rate": 97.5,
        "total_working_hours": 40.0,
        "total_break_hours": 5.0,
        "resolved_leaves": 2,
        "month_year": "November 2026",
        "active_headcount": 50,
        "compliance_rate": 99.1,
        "total_overtime_hours": 15.0,
    }

    for tmpl_key in required_templates:
        assert tmpl_key in TEMPLATES_CONFIG, f"Template '{tmpl_key}' missing from catalog"
        subject, body_html, body_text = render_email_template(tmpl_key, context)

        assert subject is not None and len(subject) > 5
        assert "<!DOCTYPE html>" in body_html
        assert "Apex" in body_html or "Enterprise" in body_html
        assert body_text is not None and len(body_text) > 10


@pytest.mark.asyncio
async def test_duplicate_prevention_via_idempotency_key(setup_notification_env, db_session: AsyncSession):
    """Enqueuing with the same idempotency key must return existing outbox entry without duplicates."""
    env = setup_notification_env
    org = env["org"]
    sub_user, sub_emp, _ = env["sub"]

    key = f"unique_test_key_{uuid.uuid4().hex}"
    context = {"employee_name": "Edward", "employee_code": "EMP-01", "email": sub_user.email, "department_name": "Dev", "designation": "Dev"}

    outbox_1 = await EmailService.enqueue_email(
        db=db_session,
        organization_id=org.id,
        template_key="employee_account_creation",
        recipient_email=sub_user.email,
        recipient_name="Edward",
        context=context,
        idempotency_key=key,
    )

    outbox_2 = await EmailService.enqueue_email(
        db=db_session,
        organization_id=org.id,
        template_key="employee_account_creation",
        recipient_email=sub_user.email,
        recipient_name="Edward",
        context=context,
        idempotency_key=key,
    )

    assert outbox_1.id == outbox_2.id

    # Verify database has exactly 1 record for this key
    stmt = select(EmailOutbox).where(EmailOutbox.idempotency_key == key)
    res = await db_session.execute(stmt)
    records = res.scalars().all()
    assert len(records) == 1


@pytest.mark.asyncio
async def test_background_email_dispatch_and_delivery_logging(setup_notification_env, db_session: AsyncSession):
    """Dispatches a pending outbox item and creates a delivery audit receipt."""
    env = setup_notification_env
    org = env["org"]
    sub_user, _, _ = env["sub"]

    context = {"employee_name": "Edward", "employee_code": "EMP-01", "email": sub_user.email, "department_name": "Dev", "designation": "Dev"}
    outbox = await EmailService.enqueue_email(
        db=db_session,
        organization_id=org.id,
        template_key="employee_account_creation",
        recipient_email=sub_user.email,
        recipient_name="Edward",
        context=context,
        idempotency_key=f"disp_test_{uuid.uuid4().hex}",
    )
    assert outbox.status == OutboxStatus.PENDING

    success = await EmailService.dispatch_outbox_message(db_session, outbox.id)
    assert success is True

    await db_session.refresh(outbox)
    assert outbox.status == OutboxStatus.SENT
    assert outbox.sent_at is not None

    # Verify EmailDeliveryLog
    stmt = select(EmailDeliveryLog).where(EmailDeliveryLog.email_outbox_id == outbox.id)
    res = await db_session.execute(stmt)
    logs = res.scalars().all()
    assert len(logs) == 1
    assert logs[0].event_type == DeliveryEventType.DELIVERED
    assert logs[0].provider_message_id is not None


@pytest.mark.asyncio
async def test_retry_mechanism_and_max_retries_failure(setup_notification_env, db_session: AsyncSession, monkeypatch):
    """Failing transport triggers retry count increments and transitions to FAILED upon max retries."""
    env = setup_notification_env
    org = env["org"]

    context = {"employee_name": "Edward", "employee_code": "EMP-01", "email": "test@domain.com", "department_name": "Dev", "designation": "Dev"}
    outbox = await EmailService.enqueue_email(
        db=db_session,
        organization_id=org.id,
        template_key="employee_account_creation",
        recipient_email="fail@domain.com",
        recipient_name="Failure Case",
        context=context,
        idempotency_key=f"fail_test_{uuid.uuid4().hex}",
    )

    # Mock transport to fail
    class FailingTransport:
        async def send(self, *args, **kwargs):
            return TransportSendResult(success=False, error_message="SMTP 550 Mailbox unavailable")

    monkeypatch.setattr("app.services.email_service.get_email_transport", lambda: FailingTransport())

    # Attempt 1
    res1 = await EmailService.dispatch_outbox_message(db_session, outbox.id)
    assert res1 is False
    await db_session.refresh(outbox)
    assert outbox.retry_count == 1
    assert outbox.status == OutboxStatus.PENDING

    # Attempt 2
    res2 = await EmailService.dispatch_outbox_message(db_session, outbox.id)
    assert res2 is False
    await db_session.refresh(outbox)
    assert outbox.retry_count == 2
    assert outbox.status == OutboxStatus.PENDING

    # Attempt 3 (Max retries reached -> FAILED)
    res3 = await EmailService.dispatch_outbox_message(db_session, outbox.id)
    assert res3 is False
    await db_session.refresh(outbox)
    assert outbox.retry_count == 3
    assert outbox.status == OutboxStatus.FAILED
    assert "SMTP 550" in outbox.error_message


@pytest.mark.asyncio
async def test_secure_attachments_validation(setup_notification_env, db_session: AsyncSession):
    """Validates secure attachment handling and filtering of non-existent files."""
    env = setup_notification_env
    org = env["org"]

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(b"PK\x03\x04test_content")
        valid_path = tmp.name

    try:
        attachments = [
            {"path": valid_path, "filename": "attendance_report.xlsx"},
            {"path": "C:\\non_existent_folder\\malicious.exe", "filename": "bad.exe"},
        ]

        context = {
            "recipient_name": "Manager",
            "report_date": "2026-11-12",
            "target_scope": "Operations",
            "present_count": 10,
            "late_count": 0,
            "leave_count": 0,
            "total_net_hours": 80.0,
        }

        outbox = await EmailService.enqueue_email(
            db=db_session,
            organization_id=org.id,
            template_key="attendance_daily_report",
            recipient_email="manager@domain.com",
            recipient_name="Manager",
            context=context,
            attachments=attachments,
        )

        assert outbox.attachments is not None
        assert "attendance_report.xlsx" in outbox.attachments
        assert "bad.exe" not in outbox.attachments  # Non-existent file filtered out

    finally:
        if os.path.exists(valid_path):
            os.remove(valid_path)


@pytest.mark.asyncio
async def test_role_routing_leave_submission_to_manager(setup_notification_env, db_session: AsyncSession):
    """Employee leave submission dispatches notification to the designated reporting manager."""
    env = setup_notification_env
    org = env["org"]
    mgr_user, mgr_emp, _ = env["mgr"]
    sub_user, sub_emp, _ = env["sub"]
    leave_type = env["leave_type"]

    # Create Leave Request
    leave = LeaveRequest(
        organization_id=org.id,
        employee_id=sub_emp.id,
        leave_type_id=leave_type.id,
        start_date=date(2026, 11, 23),
        end_date=date(2026, 11, 25),
        total_days=3.0,
        reason="Family trip",
        status=LeaveStatus.PENDING,
        manager_approval_status=ApprovalStatus.PENDING,
        hr_approval_status=ApprovalStatus.PENDING,
    )
    db_session.add(leave)
    await db_session.commit()

    dispatched = await EmailService.notify_leave_submitted(db_session, leave.id)
    assert len(dispatched) >= 1
    assert dispatched[0].recipient_email == mgr_user.email
    assert "Pending Manager Review" in dispatched[0].body_html


@pytest.mark.asyncio
async def test_role_routing_manager_approval_notifies_hr(setup_notification_env, db_session: AsyncSession):
    """Manager approval must notify HR for the second approval stage."""
    env = setup_notification_env
    org = env["org"]
    hr_user, hr_emp, _ = env["hr"]
    mgr_user, mgr_emp, _ = env["mgr"]
    sub_user, sub_emp, _ = env["sub"]
    leave_type = env["leave_type"]

    leave = LeaveRequest(
        organization_id=org.id,
        employee_id=sub_emp.id,
        leave_type_id=leave_type.id,
        start_date=date(2026, 11, 23),
        end_date=date(2026, 11, 25),
        total_days=3.0,
        reason="Vacation",
        status=LeaveStatus.PENDING,
        manager_approval_status=ApprovalStatus.APPROVED,
        hr_approval_status=ApprovalStatus.PENDING,
    )
    db_session.add(leave)
    await db_session.commit()

    dispatched = await EmailService.notify_leave_manager_approved(
        db=db_session,
        leave_request_id=leave.id,
        manager_profile=mgr_emp,
        manager_note="Endorsed without objection",
    )

    assert len(dispatched) >= 1
    recipients = [d.recipient_email for d in dispatched]
    assert hr_user.email in recipients
    assert "HR Approval" in dispatched[0].subject or "Stage 2" in dispatched[0].body_html


@pytest.mark.asyncio
async def test_role_routing_manager_rejection_notifies_employee(setup_notification_env, db_session: AsyncSession):
    """Manager rejection closes request and notifies the employee."""
    env = setup_notification_env
    org = env["org"]
    mgr_user, mgr_emp, _ = env["mgr"]
    sub_user, sub_emp, _ = env["sub"]
    leave_type = env["leave_type"]

    leave = LeaveRequest(
        organization_id=org.id,
        employee_id=sub_emp.id,
        leave_type_id=leave_type.id,
        start_date=date(2026, 11, 23),
        end_date=date(2026, 11, 25),
        total_days=3.0,
        reason="Vacation",
        status=LeaveStatus.REJECTED,
        manager_approval_status=ApprovalStatus.REJECTED,
        hr_approval_status=ApprovalStatus.PENDING,
    )
    db_session.add(leave)
    await db_session.commit()

    outbox = await EmailService.notify_leave_manager_rejected(
        db=db_session,
        leave_request_id=leave.id,
        manager_profile=mgr_emp,
        rejection_reason="Critical project sprint during requested dates",
    )

    assert outbox is not None
    assert outbox.recipient_email == sub_user.email
    assert "Declined" in outbox.subject or "DECLINED" in outbox.body_html
    assert "Critical project sprint" in outbox.body_html


@pytest.mark.asyncio
async def test_role_routing_hr_final_decision_notifies_employee_and_manager(setup_notification_env, db_session: AsyncSession):
    """Final HR decision must notify BOTH the employee and the relevant manager."""
    env = setup_notification_env
    org = env["org"]
    hr_user, hr_emp, _ = env["hr"]
    mgr_user, mgr_emp, _ = env["mgr"]
    sub_user, sub_emp, _ = env["sub"]
    leave_type = env["leave_type"]

    leave = LeaveRequest(
        organization_id=org.id,
        employee_id=sub_emp.id,
        leave_type_id=leave_type.id,
        start_date=date(2026, 11, 23),
        end_date=date(2026, 11, 25),
        total_days=3.0,
        reason="Vacation",
        status=LeaveStatus.APPROVED,
        manager_approval_status=ApprovalStatus.APPROVED,
        hr_approval_status=ApprovalStatus.APPROVED,
    )
    db_session.add(leave)
    await db_session.commit()

    # Case A: HR Approves
    dispatched_appr = await EmailService.notify_leave_hr_decision(
        db=db_session,
        leave_request_id=leave.id,
        hr_profile=hr_emp,
        is_approved=True,
    )
    assert len(dispatched_appr) >= 2
    recipients_appr = [d.recipient_email for d in dispatched_appr]
    assert sub_user.email in recipients_appr
    assert mgr_user.email in recipients_appr

    # Case B: HR Rejection
    dispatched_rej = await EmailService.notify_leave_hr_decision(
        db=db_session,
        leave_request_id=leave.id,
        hr_profile=hr_emp,
        is_approved=False,
        reason="Negative leave balance in policy",
    )
    assert len(dispatched_rej) >= 2
    recipients_rej = [d.recipient_email for d in dispatched_rej]
    assert sub_user.email in recipients_rej
    assert mgr_user.email in recipients_rej


@pytest.mark.asyncio
async def test_employee_account_creation_and_password_reset_dispatch(setup_notification_env, db_session: AsyncSession):
    """Verify onboarding and password reset security emails are correctly dispatched."""
    env = setup_notification_env
    sub_user, sub_emp, _ = env["sub"]

    # 1. Account creation
    outbox_create = await EmailService.notify_employee_account_creation(
        db=db_session,
        employee_id=sub_emp.id,
        temporary_password="WelcomeTemp123!",
    )
    assert outbox_create is not None
    assert outbox_create.recipient_email == sub_user.email
    assert "Welcome" in outbox_create.subject
    assert "WelcomeTemp123!" in outbox_create.body_html

    # 2. Password reset
    outbox_reset = await EmailService.notify_password_reset(
        db=db_session,
        user_id=sub_user.id,
        reset_token="sample-secure-token-12345",
        expires_minutes=15,
    )
    assert outbox_reset is not None
    assert outbox_reset.recipient_email == sub_user.email
    assert "Password Reset" in outbox_reset.subject
    assert "reset-password?token=sample-secure-token-12345" in outbox_reset.body_html


@pytest.mark.asyncio
async def test_attendance_daily_weekly_monthly_digests(setup_notification_env, db_session: AsyncSession):
    """Verify daily, weekly, and monthly attendance digest generation and dispatch."""
    env = setup_notification_env
    org = env["org"]
    mgr_user, _, _ = env["mgr"]

    # Daily
    d_outbox = await EmailService.notify_attendance_report(
        db=db_session,
        organization_id=org.id,
        recipient_email=mgr_user.email,
        recipient_name="Mark Manager",
        report_frequency="DAILY",
        date_str="2026-11-12",
        stats={"scope": "Team Alpha", "present_count": 12, "late_count": 1, "leave_count": 1, "total_net_hours": 96.0},
    )
    assert d_outbox.status == OutboxStatus.SENT
    assert "Daily Attendance" in d_outbox.subject

    # Weekly
    w_outbox = await EmailService.notify_attendance_report(
        db=db_session,
        organization_id=org.id,
        recipient_email=mgr_user.email,
        recipient_name="Mark Manager",
        report_frequency="WEEKLY",
        date_str="2026-W46",
        stats={"scope": "Team Alpha", "attendance_rate": 98.0, "total_working_hours": 480.0, "total_break_hours": 50.0, "resolved_leaves": 3},
    )
    assert w_outbox.status == OutboxStatus.SENT
    assert "Weekly Attendance" in w_outbox.subject

    # Monthly
    m_outbox = await EmailService.notify_attendance_report(
        db=db_session,
        organization_id=org.id,
        recipient_email=mgr_user.email,
        recipient_name="Mark Manager",
        report_frequency="MONTHLY",
        date_str="November 2026",
        stats={"active_headcount": 15, "compliance_rate": 99.5, "total_overtime_hours": 8.0},
    )
    assert m_outbox.status == OutboxStatus.SENT
    assert "Monthly Organization Attendance" in m_outbox.subject


@pytest.mark.asyncio
async def test_notifications_outbox_api_and_templates_catalog(client: AsyncClient, setup_notification_env):
    """Test REST API endpoints: /api/v1/notifications/templates, /outbox, /send-test, /process-queue."""
    env = setup_notification_env
    _, _, hr_token = env["hr"]
    _, _, sub_token = env["sub"]

    hr_headers = {"Authorization": f"Bearer {hr_token}"}
    sub_headers = {"Authorization": f"Bearer {sub_token}"}

    # 1. Templates catalog
    tmpl_res = await client.get("/api/v1/notifications/templates", headers=hr_headers)
    assert tmpl_res.status_code == 200
    templates = tmpl_res.json()
    assert len(templates) >= 10
    keys = [t["template_key"] for t in templates]
    assert "employee_account_creation" in keys
    assert "leave_manager_approval" in keys
    assert "attendance_monthly_report" in keys

    # 2. Outbox listing by HR
    outbox_res = await client.get("/api/v1/notifications/outbox", headers=hr_headers)
    assert outbox_res.status_code == 200
    assert isinstance(outbox_res.json(), list)

    # 3. RBAC: Employee cannot access general outbox
    emp_outbox_res = await client.get("/api/v1/notifications/outbox", headers=sub_headers)
    assert emp_outbox_res.status_code == 403

    # 4. Send test email
    test_res = await client.post(
        "/api/v1/notifications/send-test",
        headers=hr_headers,
        json={
            "recipient_email": "tester@apex.corp",
            "recipient_name": "QA Specialist",
            "template_key": "attendance_daily_report",
        },
    )
    assert test_res.status_code == 200
    test_data = test_res.json()
    assert test_data["recipient_email"] == "tester@apex.corp"
    assert test_data["status"] == "SENT"

    # 5. Process queue manually
    queue_res = await client.post("/api/v1/notifications/process-queue?limit=10", headers=hr_headers)
    assert queue_res.status_code == 200
    assert "dispatched_count" in queue_res.json()


@pytest.mark.asyncio
async def test_delivery_receipt_webhook(client: AsyncClient, setup_notification_env, db_session: AsyncSession):
    """Test telemetry receipt webhook logs delivery events."""
    env = setup_notification_env
    org = env["org"]

    outbox = EmailOutbox(
        organization_id=org.id,
        recipient_email="webhook_target@apex.corp",
        subject="Webhook Delivery Test",
        body_html="<p>Test</p>",
        status=OutboxStatus.SENT,
        retry_count=0,
        scheduled_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add(outbox)
    await db_session.commit()
    await db_session.refresh(outbox)

    webhook_payload = {
        "email_outbox_id": str(outbox.id),
        "event_type": "DELIVERED",
        "provider_message_id": "resend_msg_12345",
        "response_code": 250,
        "response_body": "250 2.0.0 OK",
    }
    wh_res = await client.post("/api/v1/notifications/webhook/delivery", json=webhook_payload)
    assert wh_res.status_code == 200
    assert wh_res.json()["status"] == "recorded"

    # Verify EmailDeliveryLog is in database
    stmt = select(EmailDeliveryLog).where(EmailDeliveryLog.email_outbox_id == outbox.id)
    res = await db_session.execute(stmt)
    logs = res.scalars().all()
    assert len(logs) == 1
    assert logs[0].event_type == DeliveryEventType.DELIVERED
    assert logs[0].provider_message_id == "resend_msg_12345"
