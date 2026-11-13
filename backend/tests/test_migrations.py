"""
Alembic Migration Upgrade & Downgrade Automated Verification
"""

import os
import pathlib

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from alembic import command


def test_revision_ids_fit_alembic_version_column():
    """alembic_version.version_num is VARCHAR(32); PostgreSQL rejects longer IDs (SQLite does not)."""
    base_dir = pathlib.Path(__file__).parent.parent
    alembic_cfg = Config(str(base_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(base_dir / "alembic"))

    too_long = [
        rev.revision for rev in ScriptDirectory.from_config(alembic_cfg).walk_revisions() if len(rev.revision) > 32
    ]
    assert too_long == []


def test_alembic_upgrade_and_downgrade():
    """Verifies that all migrations apply cleanly to head, rollback to base, and re-apply."""
    base_dir = pathlib.Path(__file__).parent.parent
    ini_path = str(base_dir / "alembic.ini")
    temp_db_path = str(base_dir / "test_migration_run.db")

    # Remove temporary database if it exists
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)

    sync_db_url = f"sqlite:///{temp_db_path}"

    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option("script_location", str(base_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", sync_db_url)

    engine = create_engine(sync_db_url)

    try:
        # Step 1: Upgrade to head
        command.upgrade(alembic_cfg, "head")

        inspector = inspect(engine)
        tables_after_upgrade = inspector.get_table_names()
        assert "organizations" in tables_after_upgrade
        assert "employee_profiles" in tables_after_upgrade
        assert "attendance_days" in tables_after_upgrade
        assert "leave_requests" in tables_after_upgrade
        assert "devices" in tables_after_upgrade
        assert len(tables_after_upgrade) >= 30

        # Step 2: Downgrade to base
        command.downgrade(alembic_cfg, "base")

        inspector = inspect(engine)
        tables_after_downgrade = inspector.get_table_names()
        # Should only have alembic_version (or empty)
        non_alembic_tables = [t for t in tables_after_downgrade if t != "alembic_version"]
        assert len(non_alembic_tables) == 0

        # Step 3: Re-upgrade to head (verifies migration idempotency and clean re-application)
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(engine)
        tables_after_reupgrade = inspector.get_table_names()
        assert "organizations" in tables_after_reupgrade
        assert "attendance_days" in tables_after_reupgrade
        assert len(tables_after_reupgrade) >= 30

    finally:
        engine.dispose()
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except Exception:
                pass
