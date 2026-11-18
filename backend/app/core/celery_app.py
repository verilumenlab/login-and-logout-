"""
Celery Application Initialization & Health Check
"""

from typing import Any

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "enterprise_attendance_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
)

# Automated Report Scheduling with Celery Beat (Phase 13)
celery_app.conf.beat_schedule = {
    "daily-attendance-reporting": {
        "task": "tasks.reporting.run_daily_reports",
        "schedule": crontab(hour=6, minute=0),  # Daily at 06:00
    },
    "weekly-attendance-reporting": {
        "task": "tasks.reporting.run_weekly_reports",
        "schedule": crontab(day_of_week=5, hour=14, minute=0),  # Friday at 19:30 IST (14:00 UTC)
    },
    "monthly-attendance-reporting": {
        "task": "tasks.reporting.run_monthly_reports",
        "schedule": crontab(day_of_month=1, hour=6, minute=0),  # 1st of month at 06:00
    },
    "scheduler-missed-recovery": {
        "task": "tasks.reporting.check_missed_executions",
        "schedule": crontab(minute="*/30"),  # Every 30 mins recovery check
    },
    # 6:30 PM IST idle logout — task no-ops until local 18:30, then closes idle sessions.
    "eod-idle-logout": {
        "task": "tasks.attendance.eod_idle_logout",
        "schedule": crontab(minute="*/10"),
    },
    # 10:30 IST no-login alert — no-ops until local 10:30, then emails employee/HR/manager/admin.
    "missing-login-alert": {
        "task": "tasks.attendance.missing_login_alert",
        "schedule": crontab(minute="*/10"),
    },
}

# Autodiscover tasks
celery_app.autodiscover_tasks([
    "app.tasks.attendance_tasks",
    "app.tasks.activity_tasks",
    "app.tasks.reporting_tasks",
])


def check_celery_health() -> dict[str, Any]:
    """Inspects Celery broker and worker health."""
    try:
        # Check broker connection
        with celery_app.connection_or_acquire() as conn:
            conn.default_channel
            broker_healthy = True
    except Exception as e:
        return {
            "status": "unhealthy",
            "broker_status": "disconnected",
            "error": str(e),
        }

    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        active_workers = inspector.ping() if inspector else None
        worker_count = len(active_workers) if active_workers else 0
        return {
            "status": "healthy" if broker_healthy else "degraded",
            "broker_status": "connected",
            "active_workers": worker_count,
        }
    except Exception:
        # Broker connected, but no worker response within timeout
        return {
            "status": "idle",
            "broker_status": "connected",
            "active_workers": 0,
            "note": "Broker connected; workers may be idle or offline",
        }
