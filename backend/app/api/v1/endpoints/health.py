"""
Health Check Endpoints
Provides liveness and deep readiness probes for container orchestrators, load balancers, and monitoring.
"""

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import check_celery_health
from app.core.config import settings
from app.core.database import check_database_health, get_db
from app.core.redis import check_redis_health
from app.schemas.health import DetailedHealthResponse, HealthResponse

router = APIRouter()

START_TIME = time.time()


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
    description="Fast lightweight health check verifying process is alive.",
)
async def liveness_probe() -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.ENVIRONMENT,
        version=settings.VERSION,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get(
    "/health/detailed",
    response_model=DetailedHealthResponse,
    summary="Readiness Probe",
    description="Deep health check verifying connectivity to PostgreSQL, Redis, and Celery broker.",
)
async def readiness_probe(
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> DetailedHealthResponse:
    db_health = await check_database_health(session=db)
    redis_health = await check_redis_health()
    celery_health = check_celery_health()

    # Overall system health computation
    is_healthy = (
        db_health.get("status") == "healthy"
        and redis_health.get("status") in ["healthy", "degraded"]
        and celery_health.get("status") in ["healthy", "idle"]
    )

    if not is_healthy:
        # Service degraded or unhealthy; still return structured report
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall_status = "degraded" if db_health.get("status") == "healthy" else "unhealthy"
    else:
        overall_status = "healthy"

    uptime_seconds = round(time.time() - START_TIME, 2)

    provider = (settings.EMAIL_PROVIDER or "console").strip().lower()
    email_health = {
        "status": "healthy" if provider in ("smtp", "resend") else "degraded",
        "provider": provider,
        "from_email": settings.DEFAULT_FROM_EMAIL,
        "delivers_to_inbox": provider in ("smtp", "resend"),
        "note": None
        if provider in ("smtp", "resend")
        else "EMAIL_PROVIDER=console only logs mail. Outbox may show SENT but nothing reaches an inbox.",
    }

    return DetailedHealthResponse(
        status=overall_status,
        environment=settings.ENVIRONMENT,
        version=settings.VERSION,
        timestamp=datetime.now(UTC).isoformat(),
        uptime_seconds=uptime_seconds,
        database=db_health,
        redis=redis_health,
        celery=celery_health,
        email=email_health,
    )
