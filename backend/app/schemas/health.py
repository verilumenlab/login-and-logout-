"""
Health Check Pydantic Schemas
"""

from typing import Any

from pydantic import BaseModel, Field


class ComponentHealth(BaseModel):
    status: str = Field(..., description="healthy, degraded, unhealthy, or idle")
    latency_ms: float | None = Field(None, description="Response time in milliseconds")
    error: str | None = Field(None, description="Error message if unhealthy")
    details: dict[str, Any] | None = Field(None, description="Additional component metadata")


class HealthResponse(BaseModel):
    status: str = "ok"
    environment: str
    version: str
    timestamp: str


class DetailedHealthResponse(BaseModel):
    status: str = Field(..., description="Overall platform status (healthy, degraded, unhealthy)")
    environment: str
    version: str
    timestamp: str
    uptime_seconds: float
    database: dict[str, Any]
    redis: dict[str, Any]
    celery: dict[str, Any]
    email: dict[str, Any] | None = None
