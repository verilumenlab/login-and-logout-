"""First-run setup used by the Render deployment."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.bootstrap as bootstrap_module
from app.core.config import _with_driver
from app.core.database import Base
from app.core.security import verify_password
from app.models.auth import User
from app.models.employee import EmployeeProfile
from app.models.leave import LeaveType
from app.models.organization import Organization


@pytest.fixture
async def fresh_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(bootstrap_module, "AsyncSessionLocal", session_factory)
    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_bootstrap_requires_admin_credentials_on_empty_database(fresh_db, monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_ADMIN_EMAIL", raising=False)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "short")
    assert await bootstrap_module.bootstrap() == 1
    async with fresh_db() as db:
        assert await db.scalar(select(func.count(Organization.id))) == 0


@pytest.mark.asyncio
async def test_bootstrap_creates_org_and_admin_once(fresh_db, monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ORG_NAME", "Acme Labs")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "Owner@Acme.com")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "Very-Strong-Pass-42")

    assert await bootstrap_module.bootstrap() == 0
    assert await bootstrap_module.bootstrap() == 0  # second deploy is a no-op

    async with fresh_db() as db:
        assert await db.scalar(select(func.count(Organization.id))) == 1
        admin = (await db.execute(select(User).where(User.email == "owner@acme.com"))).scalars().one()
        assert admin.is_superuser and verify_password("Very-Strong-Pass-42", admin.hashed_password)
        assert await db.scalar(select(func.count(EmployeeProfile.id))) == 1
        assert await db.scalar(select(func.count(LeaveType.id))) > 0


def test_render_database_urls_get_explicit_drivers():
    assert _with_driver("postgresql://u:p@host/db", "asyncpg") == "postgresql+asyncpg://u:p@host/db"
    assert _with_driver("postgres://u:p@host/db", "psycopg2") == "postgresql+psycopg2://u:p@host/db"
    assert _with_driver("postgresql+asyncpg://u:p@host/db", "psycopg2") == "postgresql+psycopg2://u:p@host/db"
    assert _with_driver("sqlite+aiosqlite:///x.db", "asyncpg") == "sqlite+aiosqlite:///x.db"
