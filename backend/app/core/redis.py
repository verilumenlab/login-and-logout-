"""
Redis Connection & Health Module
"""

import time
from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

_redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.get_redis_url(),
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
    return _redis_client


async def close_redis_client() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    client = get_redis_client()
    try:
        yield client
    finally:
        pass


async def check_redis_health() -> dict[str, Any]:
    """Health check helper executing a PING against Redis."""
    start_time = time.perf_counter()
    try:
        client = get_redis_client()
        pong = await client.ping()
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if pong:
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "message": "PONG",
            }
        return {
            "status": "degraded",
            "latency_ms": latency_ms,
            "message": "Unexpected ping response",
        }
    except Exception as e:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "error": str(e),
        }
