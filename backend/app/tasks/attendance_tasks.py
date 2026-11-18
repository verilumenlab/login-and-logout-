"""
Celery Background Tasks for Attendance Processing
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.tasks.reporting_tasks import run_async

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.attendance.auto_clockout")
def auto_clockout_inactive_sessions() -> dict:
    """Legacy alias — prefer tasks.attendance.eod_idle_logout."""
    return eod_idle_logout()


@celery_app.task(name="tasks.attendance.eod_idle_logout")
def eod_idle_logout() -> dict[str, Any]:
    """
    Every ~10 minutes: after 6:30 PM IST, auto-logout employees whose laptop
    is idle (open AUTO_IDLE / LOCK / SLEEP break). Active users stay logged in.
    """
    from app.services.end_of_day import run_end_of_day_idle_logout

    async def _execute():
        async with AsyncSessionLocal() as db:
            return await run_end_of_day_idle_logout(db)

    try:
        result = run_async(_execute())
        logger.info(
            "EOD idle logout: status=%s closed=%s still_active=%s",
            result.get("status"),
            result.get("closed_count", 0),
            result.get("still_active_count", 0),
        )
        return result
    except Exception:
        logger.exception("EOD idle logout failed")
        raise


@celery_app.task(name="tasks.attendance.daily_summary")
def generate_daily_attendance_summary(date_str: str) -> dict:
    """Calculates daily attendance stats for managers."""
    return {"status": "success", "date": date_str, "processed_employees": 0}


@celery_app.task(name="tasks.attendance.missing_login_alert")
def missing_login_alert() -> dict[str, Any]:
    """
    Every ~10 minutes: after 10:30 IST, queue PENDING missing-login alerts
    for Admin/HR approval. Emails are not sent until approved.
    """
    from app.services.missing_login_alert import run_missing_login_alerts

    async def _execute():
        async with AsyncSessionLocal() as db:
            return await run_missing_login_alerts(db)

    try:
        result = run_async(_execute())
        logger.info(
            "Missing login queue: status=%s queued=%s",
            result.get("status"),
            result.get("queued_count", 0),
        )
        return result
    except Exception:
        logger.exception("Missing login queue failed")
        raise
