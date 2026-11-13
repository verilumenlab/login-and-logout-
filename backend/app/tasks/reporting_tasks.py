"""
Celery Background Tasks for Automated Report Scheduling (Phase 13)

Features:
- Daily, Weekly, and Monthly automated report generation
- Retry on failure with exponential backoff
- Idempotent execution preventing duplicate report generation and email dispatch
- Missed execution recovery across server restarts
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from celery import Task
from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.organization import Organization
from app.models.reporting import ReportSchedule, ReportType
from app.services.report_scheduler_service import ReportSchedulerService

logger = logging.getLogger(__name__)


def run_async(coro):
    """Utility to run asynchronous coroutines inside synchronous Celery worker threads."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return loop.run_until_complete(coro)


@celery_app.task(
    name="tasks.reporting.run_daily_reports",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run_daily_reports(self: Task) -> dict[str, Any]:
    """Triggers previous-day attendance digests for all active organizations."""
    async def _execute():
        async with AsyncSessionLocal() as db:
            stmt = select(Organization.id).where(Organization.is_active.is_(True))
            res = await db.execute(stmt)
            org_ids = res.scalars().all()

            results = []
            for org_id in org_ids:
                success, msg, job = await ReportSchedulerService.execute_scheduled_reporting(
                    db=db,
                    organization_id=org_id,
                    schedule_type=ReportType.DAILY,
                )
                results.append({
                    "organization_id": str(org_id),
                    "success": success,
                    "message": msg,
                    "job_id": str(job.id) if job else None,
                })
            return {"status": "success", "processed_orgs": len(results), "details": results}

    try:
        return run_async(_execute())
    except Exception as exc:
        logger.exception("Daily report task failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    name="tasks.reporting.run_weekly_reports",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def run_weekly_reports(self: Task) -> dict[str, Any]:
    """Friday digest: this week's (Mon-Fri) attendance, Wi-Fi/login and leave Excel for all active organizations."""
    async def _execute():
        async with AsyncSessionLocal() as db:
            stmt = select(Organization.id).where(Organization.is_active.is_(True))
            res = await db.execute(stmt)
            org_ids = res.scalars().all()

            results = []
            for org_id in org_ids:
                success, msg, job = await ReportSchedulerService.execute_scheduled_reporting(
                    db=db,
                    organization_id=org_id,
                    schedule_type=ReportType.WEEKLY,
                )
                results.append({
                    "organization_id": str(org_id),
                    "success": success,
                    "message": msg,
                    "job_id": str(job.id) if job else None,
                })
            return {"status": "success", "processed_orgs": len(results), "details": results}

    try:
        return run_async(_execute())
    except Exception as exc:
        logger.exception("Weekly report task failed: %s", exc)
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))


@celery_app.task(
    name="tasks.reporting.run_monthly_reports",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def run_monthly_reports(self: Task) -> dict[str, Any]:
    """Triggers previous-month organization executive digests for all active organizations."""
    async def _execute():
        async with AsyncSessionLocal() as db:
            stmt = select(Organization.id).where(Organization.is_active.is_(True))
            res = await db.execute(stmt)
            org_ids = res.scalars().all()

            results = []
            for org_id in org_ids:
                success, msg, job = await ReportSchedulerService.execute_scheduled_reporting(
                    db=db,
                    organization_id=org_id,
                    schedule_type=ReportType.MONTHLY,
                )
                results.append({
                    "organization_id": str(org_id),
                    "success": success,
                    "message": msg,
                    "job_id": str(job.id) if job else None,
                })
            return {"status": "success", "processed_orgs": len(results), "details": results}

    try:
        return run_async(_execute())
    except Exception as exc:
        logger.exception("Monthly report task failed: %s", exc)
        raise self.retry(exc=exc, countdown=300 * (2 ** self.request.retries))


@celery_app.task(name="tasks.reporting.check_missed_executions")
def check_missed_executions() -> dict[str, Any]:
    """Recovers any missed scheduled runs following system restarts or offline periods."""
    async def _execute():
        async with AsyncSessionLocal() as db:
            results = await ReportSchedulerService.check_and_run_missed_executions(db)
            return {"status": "success", "checked_schedules": len(results), "details": results}

    return run_async(_execute())


@celery_app.task(
    name="tasks.reporting.run_single_schedule",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def run_single_schedule(
    self: Task,
    schedule_id_str: str,
    force: bool = False,
    reference_date_str: str | None = None,
) -> dict[str, Any]:
    """Runs a single schedule on-demand or manually."""
    async def _execute():
        async with AsyncSessionLocal() as db:
            sched_uuid = uuid.UUID(schedule_id_str)
            stmt = select(ReportSchedule).where(ReportSchedule.id == sched_uuid)
            res = await db.execute(stmt)
            sched = res.scalars().first()
            if not sched:
                return {"status": "error", "message": "Schedule not found"}

            ref_date = None
            if reference_date_str:
                from datetime import date
                ref_date = date.fromisoformat(reference_date_str)

            success, msg, job = await ReportSchedulerService.execute_scheduled_reporting(
                db=db,
                organization_id=sched.organization_id,
                schedule_type=sched.schedule_type,
                target_reference_date=ref_date,
                force=force,
            )
            return {
                "status": "success" if success else "failed",
                "message": msg,
                "job_id": str(job.id) if job else None,
            }

    try:
        return run_async(_execute())
    except Exception as exc:
        logger.exception("Single schedule task failed: %s", exc)
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))

