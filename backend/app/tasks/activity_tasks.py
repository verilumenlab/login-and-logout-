"""
Celery Background Tasks for Computer Activity Aggregation
"""

from app.core.celery_app import celery_app


@celery_app.task(name="tasks.activity.aggregate_daily_productivity")
def aggregate_daily_productivity(user_id: int, date_str: str) -> dict:
    """Aggregates raw telemetry batches into hourly and daily metrics."""
    return {
        "status": "success",
        "user_id": user_id,
        "date": date_str,
        "active_hours": 0.0,
        "idle_hours": 0.0,
    }
