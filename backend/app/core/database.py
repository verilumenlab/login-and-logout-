"""
Database Configuration & Async Session Management
Provides SQLAlchemy 2.0 AsyncEngine, SessionLocal, declarative base and health check utilities.
"""

import time
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


# Build database URL with fallback handling for local offline development/testing
async_database_url = settings.get_async_database_url()

# Connection pooling settings (sqlite in-memory doesn't use pool_size/max_overflow)
connect_args: dict[str, Any] = {}
is_sqlite = "sqlite" in async_database_url

if is_sqlite:
    connect_args["check_same_thread"] = False
    engine = create_async_engine(
        async_database_url,
        echo=settings.DEBUG,
        connect_args=connect_args,
        future=True,
    )
else:
    engine = create_async_engine(
        async_database_url,
        echo=settings.DEBUG,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_pre_ping=True,
        future=True,
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_health(session: AsyncSession | None = None) -> dict[str, Any]:
    """Health check helper executing a ping query against the database."""
    start_time = time.perf_counter()
    try:
        if session is not None:
            await session.execute(text("SELECT 1"))
        else:
            async with AsyncSessionLocal() as s:
                await s.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "database": "sqlite" if is_sqlite else "postgresql",
        }
    except Exception as e:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "error": str(e),
        }
