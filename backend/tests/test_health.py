"""
Unit & Integration tests for health check endpoints
"""

from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "Enterprise Attendance" in data["name"]
    assert data["health_url"] == "/api/v1/health"


@pytest.mark.asyncio
async def test_liveness_health_check(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_detailed_health_check(client: AsyncClient):
    with (
        patch("app.api.v1.endpoints.health.check_redis_health") as mock_redis,
        patch("app.api.v1.endpoints.health.check_celery_health") as mock_celery,
    ):
        mock_redis.return_value = {"status": "healthy", "latency_ms": 1.2, "message": "PONG"}
        mock_celery.return_value = {"status": "healthy", "broker_status": "connected", "active_workers": 2}

        response = await client.get("/api/v1/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "database" in data
        assert "redis" in data
        assert "celery" in data
        assert data["redis"]["status"] == "healthy"
        assert data["celery"]["status"] == "healthy"
