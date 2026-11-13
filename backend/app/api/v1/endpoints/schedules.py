"""
Report Schedule Management Endpoints (Phase 13)

Provides:
- List schedules for organization (with auto-initialization)
- Retrieve schedule configuration and execution history
- Update schedule parameters, cron expression, timezone, and delivery toggles
- Manual rerun trigger with on-demand execution
- Missed execution recovery trigger
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import get_current_active_user, require_role
from app.models.auth import User
from app.models.reporting import ReportFile, ReportJob, ReportSchedule, ReportStatus, ReportType
from app.services.report_scheduler_service import ReportSchedulerService

router = APIRouter()


class ScheduleJobFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_name: str
    file_size_bytes: int
    mime_type: str
    created_at: datetime


class ScheduleJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    report_type: ReportType
    status: ReportStatus
    idempotency_key: str | None = None
    parameters_json: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    files: list[ScheduleJobFileResponse] = []


class ReportScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    schedule_type: ReportType
    cron_expression: str
    timezone: str
    is_active: bool
    send_email: bool
    recipient_emails: list[str] = Field(default_factory=list)
    include_individual_reports: bool
    include_manager_reports: bool
    include_consolidated_report: bool
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    last_status: str | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime
    recent_jobs: list[ScheduleJobResponse] = []


class ReportScheduleUpdate(BaseModel):
    cron_expression: str | None = None
    timezone: str | None = None
    is_active: bool | None = None
    send_email: bool | None = None
    recipient_emails: list[str] | None = None
    include_individual_reports: bool | None = None
    include_manager_reports: bool | None = None
    include_consolidated_report: bool | None = None


class ManualRunRequest(BaseModel):
    force: bool = True
    reference_date: date | None = None


def _serialize_schedule(sched: ReportSchedule, jobs: list[ReportJob] | None = None) -> ReportScheduleResponse:
    recipients = []
    if sched.recipient_emails:
        try:
            recipients = json.loads(sched.recipient_emails)
        except Exception:
            recipients = [e.strip() for e in sched.recipient_emails.split(",") if e.strip()]

    return ReportScheduleResponse(
        id=sched.id,
        organization_id=sched.organization_id,
        schedule_type=sched.schedule_type,
        cron_expression=sched.cron_expression,
        timezone=sched.timezone,
        is_active=sched.is_active,
        send_email=sched.send_email,
        recipient_emails=recipients,
        include_individual_reports=sched.include_individual_reports,
        include_manager_reports=sched.include_manager_reports,
        include_consolidated_report=sched.include_consolidated_report,
        last_run_at=sched.last_run_at,
        next_run_at=sched.next_run_at,
        last_status=sched.last_status,
        last_error=sched.last_error,
        created_at=sched.created_at,
        updated_at=sched.updated_at,
        recent_jobs=[
            ScheduleJobResponse(
                id=j.id,
                report_type=j.report_type,
                status=j.status,
                idempotency_key=j.idempotency_key,
                parameters_json=j.parameters_json,
                started_at=j.started_at,
                completed_at=j.completed_at,
                error_message=j.error_message,
                created_at=j.created_at,
                files=[
                    ScheduleJobFileResponse(
                        id=f.id,
                        file_name=f.file_name,
                        file_size_bytes=f.file_size_bytes,
                        mime_type=f.mime_type,
                        created_at=f.created_at,
                    )
                    for f in j.files
                ],
            )
            for j in (jobs or [])
        ],
    )


@router.get("/", response_model=list[ReportScheduleResponse])
async def list_report_schedules(
    current_user: User = Depends(require_role(["Admin", "Super Admin", "HR"])),
    db: AsyncSession = Depends(get_db),
) -> list[ReportScheduleResponse]:
    """Lists configured schedules for the organization, auto-provisioning defaults if empty."""
    schedules = await ReportSchedulerService.get_or_create_default_schedules(
        db=db,
        organization_id=current_user.organization_id,
    )

    results: list[ReportScheduleResponse] = []
    for s in schedules:
        job_stmt = (
            select(ReportJob)
            .options(selectinload(ReportJob.files))
            .where(ReportJob.schedule_id == s.id)
            .order_by(desc(ReportJob.created_at))
            .limit(5)
        )
        job_res = await db.execute(job_stmt)
        recent_jobs = list(job_res.scalars().all())
        results.append(_serialize_schedule(s, recent_jobs))

    return results


@router.get("/{schedule_id}", response_model=ReportScheduleResponse)
async def get_report_schedule(
    schedule_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin", "HR"])),
    db: AsyncSession = Depends(get_db),
) -> ReportScheduleResponse:
    """Retrieves full configuration and job history for a specific schedule."""
    stmt = select(ReportSchedule).where(
        ReportSchedule.id == schedule_id,
        ReportSchedule.organization_id == current_user.organization_id,
    )
    res = await db.execute(stmt)
    sched = res.scalars().first()
    if not sched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report schedule not found.")

    job_stmt = (
        select(ReportJob)
        .options(selectinload(ReportJob.files))
        .where(ReportJob.schedule_id == sched.id)
        .order_by(desc(ReportJob.created_at))
        .limit(10)
    )
    job_res = await db.execute(job_stmt)
    jobs = list(job_res.scalars().all())
    return _serialize_schedule(sched, jobs)


@router.put("/{schedule_id}", response_model=ReportScheduleResponse)
async def update_report_schedule(
    schedule_id: uuid.UUID,
    payload: ReportScheduleUpdate,
    current_user: User = Depends(require_role(["Admin", "Super Admin", "HR"])),
    db: AsyncSession = Depends(get_db),
) -> ReportScheduleResponse:
    """Updates schedule configuration (cron expression, timezone, active status, email toggles)."""
    stmt = select(ReportSchedule).where(
        ReportSchedule.id == schedule_id,
        ReportSchedule.organization_id == current_user.organization_id,
    )
    res = await db.execute(stmt)
    sched = res.scalars().first()
    if not sched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report schedule not found.")

    if payload.cron_expression is not None:
        sched.cron_expression = payload.cron_expression
    if payload.timezone is not None:
        sched.timezone = payload.timezone
    if payload.is_active is not None:
        sched.is_active = payload.is_active
    if payload.send_email is not None:
        sched.send_email = payload.send_email
    if payload.recipient_emails is not None:
        sched.recipient_emails = json.dumps(payload.recipient_emails)
    if payload.include_individual_reports is not None:
        sched.include_individual_reports = payload.include_individual_reports
    if payload.include_manager_reports is not None:
        sched.include_manager_reports = payload.include_manager_reports
    if payload.include_consolidated_report is not None:
        sched.include_consolidated_report = payload.include_consolidated_report

    sched.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(sched)
    return _serialize_schedule(sched)


@router.post("/{schedule_id}/run", response_model=ScheduleJobResponse)
async def manual_rerun_schedule(
    schedule_id: uuid.UUID,
    payload: ManualRunRequest | None = None,
    current_user: User = Depends(require_role(["Admin", "Super Admin", "HR"])),
    db: AsyncSession = Depends(get_db),
) -> ScheduleJobResponse:
    """
    On-demand or manual rerun of a scheduled report for a specific reference date.
    Generates all requested Excel workbooks and dispatches notification digests.
    """
    stmt = select(ReportSchedule).where(
        ReportSchedule.id == schedule_id,
        ReportSchedule.organization_id == current_user.organization_id,
    )
    res = await db.execute(stmt)
    sched = res.scalars().first()
    if not sched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report schedule not found.")

    force = payload.force if payload else True
    ref_date = payload.reference_date if payload else None

    success, msg, job = await ReportSchedulerService.execute_scheduled_reporting(
        db=db,
        organization_id=sched.organization_id,
        schedule_type=sched.schedule_type,
        target_reference_date=ref_date,
        force=force,
        system_requester_id=current_user.id,
    )

    if not job:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg)

    # Re-fetch with files
    j_stmt = (
        select(ReportJob)
        .options(selectinload(ReportJob.files))
        .where(ReportJob.id == job.id)
    )
    j_res = await db.execute(j_stmt)
    job_with_files = j_res.scalars().first()

    return ScheduleJobResponse(
        id=job_with_files.id,
        report_type=job_with_files.report_type,
        status=job_with_files.status,
        idempotency_key=job_with_files.idempotency_key,
        parameters_json=job_with_files.parameters_json,
        started_at=job_with_files.started_at,
        completed_at=job_with_files.completed_at,
        error_message=job_with_files.error_message,
        created_at=job_with_files.created_at,
        files=[
            ScheduleJobFileResponse(
                id=f.id,
                file_name=f.file_name,
                file_size_bytes=f.file_size_bytes,
                mime_type=f.mime_type,
                created_at=f.created_at,
            )
            for f in job_with_files.files
        ],
    )


@router.post("/check-missed")
async def check_missed_reporting_runs(
    current_user: User = Depends(require_role(["Admin", "Super Admin", "HR"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Manually inspects and catches up any missed scheduled runs following system restarts."""
    results = await ReportSchedulerService.check_and_run_missed_executions(db)
    return {
        "status": "success",
        "processed_at": datetime.now(UTC).isoformat(),
        "schedules_checked": len(results),
        "details": results,
    }

