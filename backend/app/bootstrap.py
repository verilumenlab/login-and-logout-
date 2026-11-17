"""
First-run setup for a fresh database (used on Render before the API starts).

Idempotent: seeds system roles/permissions every time; syncs leave types for existing organizations;
creates the organization, its leave types and the first administrator only when the database has no organization yet.

    python -m app.bootstrap

Environment:
    BOOTSTRAP_ORG_NAME        Organization name (default "My Company")
    BOOTSTRAP_ADMIN_EMAIL     First administrator's sign-in email (required on first run)
    BOOTSTRAP_ADMIN_PASSWORD  First administrator's password, at least 12 characters (required on first run)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.core.seeds import (
    seed_organization_leave_types,
    seed_organization_office_wifi,
    seed_organization_work_schedule,
    seed_system_roles,
)
from app.models.auth import User
from app.models.employee import EmployeeProfile, EmploymentStatus
from app.models.organization import Organization

logging.basicConfig(level=logging.INFO, format="%(levelname)s bootstrap: %(message)s")
logger = logging.getLogger(__name__)


async def bootstrap() -> int:
    async with AsyncSessionLocal() as db:
        role_map = await seed_system_roles(db)
        await db.commit()

        org_count = await db.scalar(select(func.count(Organization.id)))
        if org_count:
            orgs = (await db.execute(select(Organization))).scalars().all()
            for org in orgs:
                await seed_organization_leave_types(db, org.id)
                await seed_organization_office_wifi(db, org.id)
                await seed_organization_work_schedule(db, org.id)
            await db.commit()
            logger.info(
                "Database already set up (%s organization(s)); roles, leave types, office Wi-Fi, and work schedule refreshed.",
                org_count,
            )
            return 0

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
        await seed_organization_office_wifi(db, org.id)
        office_schedule = await seed_organization_work_schedule(db, org.id)

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
                work_schedule_id=office_schedule.id,
            )
        )
        await db.commit()
        logger.info("Created organization %r and administrator %s.", org_name, email)
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(bootstrap()))
