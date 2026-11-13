"""
Enterprise Redis Rate Limiting & Brute Force Defense Module (Phase 14)
Implements sliding-window counter rate limiting to protect authentication,
device registration, and sensitive API endpoints against automated attacks.
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request, status

from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

# Fallback in-memory tracking if Redis is unreachable
_in_memory_rate_cache: dict[str, list[float]] = {}


class RateLimitExceeded(HTTPException):
    def __init__(self, retry_after: int, detail: str = "Rate limit exceeded. Too many requests."):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(retry_after)},
        )


async def check_rate_limit(
    key: str,
    max_requests: int,
    window_seconds: int,
) -> tuple[bool, int]:
    """
    Check if a key has exceeded max_requests in window_seconds.
    Returns (is_allowed: bool, retry_after_seconds: int).
    """
    now = time.time()
    redis_key = f"rl:{key}"

    try:
        redis = get_redis_client()
        pipe = redis.pipeline()
        # Remove requests older than the current window
        pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
        # Add unique member with current timestamp score
        member = f"{now}:{time.perf_counter()}"
        pipe.zadd(redis_key, {member: now})
        # Count elements in window
        pipe.zcard(redis_key)
        # Set TTL on key
        pipe.expire(redis_key, window_seconds + 5)
        _, _, count, _ = await pipe.execute()

        if count > max_requests:
            # Over limit
            return False, window_seconds
        return True, 0
    except Exception as exc:
        logger.warning(f"Redis rate limiter unavailable, falling back to memory: {exc}")
        # In-memory sliding window fallback
        timestamps = _in_memory_rate_cache.get(key, [])
        cutoff = now - window_seconds
        valid_timestamps = [t for t in timestamps if t > cutoff]
        valid_timestamps.append(now)
        _in_memory_rate_cache[key] = valid_timestamps

        if len(valid_timestamps) > max_requests:
            return False, window_seconds
        return True, 0


def rate_limit(
    max_requests: int = 60,
    window_seconds: int = 60,
    key_prefix: str = "general",
) -> Callable:
    """
    FastAPI dependency factory enforcing rate limits by client IP and path.
    """

    async def _rate_limit_dependency(request: Request) -> None:
        # In automated test suites (pytest), bypass endpoint rate limiting unless explicitly tested
        if "pytest" in sys.modules and request.headers.get("x-enforce-rate-limit") != "true":
            return

        client_ip = request.client.host if request.client else "unknown"

        # Forwarded IP check if behind reverse proxy
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        key = f"{key_prefix}:{client_ip}:{request.url.path}"
        is_allowed, retry_after = await check_rate_limit(
            key=key,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )

        if not is_allowed:
            raise RateLimitExceeded(
                retry_after=retry_after,
                detail=f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds}s allowed.",
            )

    return _rate_limit_dependency
