"""
First-run setup for a fresh database (used on Render before the API starts).

Idempotent: seeds system roles/permissions every time; creates the organization, its leave types and the
first administrator only when the database has no organization yet.

    python -m app.bootstrap

Environment:
    BOOTSTRAP_ORG_NAME        Organization name (default "My Company")
    BOOTSTRAP_ADMIN_EMAIL     First administrator's sign-in email (required on first run)
    BOOTSTRAP_ADMIN_PASSWORD  First administrator's password, at least 12 characters (required on first run)
    BOOTSTRAP_RESET_PASSWORD  Set to "true" to update/create admin from BOOTSTRAP_ADMIN_* (then turn off)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import traceback
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.core.seeds import seed_organization_leave_types, seed_system_roles
from app.models.auth import Role, User
from app.models.employee import EmployeeProfile, EmploymentStatus
from app.models.organization import Organization

logging.basicConfig(level=logging.INFO, format="%(levelname)s bootstrap: %(message)s")
logger = logging.getLogger(__name__)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


async def _create_admin_on_org(db, org: Organization, role_map: dict[str, Role], email: str, password: str) -> User:
    admin = User(
        organization_id=org.id,
        email=email,
        hashed_password=get_password_hash(password),
        role_id=role_map["Administrator"].id,
        is_active=True,
        is_superuser=True,
    )
    db.add(admin)
    await db.flush()
    db.add(
        EmployeeProfile(
            organization_id=org.id,
            user_id=admin.id,
            employee_code="ADMIN-001",
            first_name="System",
            last_name="Administrator",
            hire_date=datetime.now(UTC).date(),
            employment_status=EmploymentStatus.ACTIVE,
        )
    )
    await db.commit()
    return admin


async def _maybe_reset_admin_password(db, role_map: dict[str, Role]) -> int:
    """One-shot admin password (and email) recovery when BOOTSTRAP_RESET_PASSWORD=true."""
    if not _env_flag("BOOTSTRAP_RESET_PASSWORD"):
        return 0

    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    if "@" not in email or len(password) < 12:
        logger.error(
            "BOOTSTRAP_RESET_PASSWORD is set, but BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD "
            "(12+ characters) are missing or invalid."
        )
        return 1

    try:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()

        if not user:
            admin_role_ids = (
                await db.execute(
                    select(Role.id).where(Role.name.in_(["Administrator", "Super Administrator"]))
                )
            ).scalars().all()
            candidates: list[User] = []
            if admin_role_ids:
                candidates = (
                    await db.execute(
                        select(User).where(User.role_id.in_(admin_role_ids)).order_by(User.created_at.asc())
                    )
                ).scalars().all()
            if not candidates:
                candidates = (
                    await db.execute(
                        select(User).where(User.is_superuser.is_(True)).order_by(User.created_at.asc())
                    )
                ).scalars().all()
            if not candidates:
                candidates = (await db.execute(select(User).order_by(User.created_at.asc()))).scalars().all()

            if candidates:
                profile = (
                    await db.execute(
                        select(EmployeeProfile).where(EmployeeProfile.employee_code == "ADMIN-001")
                    )
                ).scalars().first()
                if profile:
                    user = next((u for u in candidates if u.id == profile.user_id), None)
                if not user:
                    user = candidates[0]
                logger.info(
                    "Found existing account %s to reset (requested %s).",
                    user.email,
                    email,
                )
            else:
                org = (await db.execute(select(Organization).order_by(Organization.created_at.asc()))).scalars().first()
                if not org:
                    logger.error("BOOTSTRAP_RESET_PASSWORD set but no organization exists.")
                    return 1
                user = await _create_admin_on_org(db, org, role_map, email, password)
                logger.info(
                    "No users existed; created administrator %s. Turn OFF BOOTSTRAP_RESET_PASSWORD now.",
                    email,
                )
                return 0

            if user.email != email:
                logger.info("Updating admin email from %s to %s.", user.email, email)
                user.email = email

        user.hashed_password = get_password_hash(password)
        user.is_active = True
        user.is_superuser = True
        if "Administrator" in role_map:
            user.role_id = role_map["Administrator"].id
        await db.commit()
        logger.info(
            "Reset password for %s. Turn OFF BOOTSTRAP_RESET_PASSWORD in Render Environment now.",
            email,
        )
        return 0
    except Exception:
        logger.error("Admin password reset failed:\n%s", traceback.format_exc())
        return 1


async def bootstrap() -> int:
    async with AsyncSessionLocal() as db:
        role_map = await seed_system_roles(db)
        await db.commit()

        org_count = await db.scalar(select(func.count(Organization.id)))
        if org_count:
            logger.info("Database already set up (%s organization(s)); roles refreshed.", org_count)
            return await _maybe_reset_admin_password(db, role_map)

        email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
        if "@" not in email or len(password) < 12:
            logger.error(
                "No organization exists yet. Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD "
                "(12+ characters) to create the first administrator."
            )
            return 1

        org_name = os.environ.get("BOOTSTRAP_ORG_NAME", "").strip() or "My Company"
        slug = re.sub(r"[^a-z0-9]+", "-", org_name.lower()).strip("-")[:90] or "company"
        org = Organization(
            name=org_name,
            slug=slug,
            code=slug.replace("-", "_").upper()[:16],
            settings_json={"timezone": "Asia/Kolkata"},
        )
        db.add(org)
        await db.flush()
        await seed_organization_leave_types(db, org.id)
        await _create_admin_on_org(db, org, role_map, email, password)
        logger.info("Created organization %r and administrator %s.", org_name, email)
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(bootstrap()))
