"""Employee application release management tables (Electron / Windows).

Revision ID: 0011_application_releases
Revises: 0010_presence_system_power
Create Date: 2026-11-13
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0011_application_releases"
down_revision = "0010_presence_system_power"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_release_channels",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_application_release_channels_name", "application_release_channels", ["name"])

    op.create_table(
        "application_releases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("build_number", sa.String(length=50), nullable=True),
        sa.Column("release_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="uploaded"),
        sa.Column("os_name", sa.String(length=30), nullable=False, server_default="windows"),
        sa.Column("package_size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("sha512", sa.String(length=128), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("metadata_json", sa.JSON().with_variant(sa.JSON(), "sqlite"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["application_release_channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", "version", name="uq_release_channel_version"),
    )
    op.create_index("ix_application_releases_channel_id", "application_releases", ["channel_id"])
    op.create_index("ix_application_releases_version", "application_releases", ["version"])
    op.create_index("ix_application_releases_status", "application_releases", ["status"])
    op.create_index("ix_application_releases_channel_status", "application_releases", ["channel_id", "status"])

    op.create_table(
        "application_release_files",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("release_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=1000), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["release_id"], ["application_releases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_application_release_files_release_id", "application_release_files", ["release_id"])
    op.create_index("ix_application_release_files_kind", "application_release_files", ["kind"])

    op.create_table(
        "application_update_policies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("min_supported_version", sa.String(length=50), nullable=True),
        sa.Column("force_update", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("auto_download", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("check_interval_minutes", sa.Integer(), nullable=False, server_default="240"),
        sa.Column("allow_rollback_publish", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["application_release_channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", name="uq_update_policy_channel"),
    )

    op.create_table(
        "employee_app_installations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=True),
        sa.Column("channel_name", sa.String(length=50), nullable=False, server_default="production"),
        sa.Column("installed_version", sa.String(length=50), nullable=False),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_update_status", sa.String(length=50), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employee_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", name="uq_app_installation_device"),
    )
    op.create_index("ix_employee_app_installations_org", "employee_app_installations", ["organization_id"])
    op.create_index("ix_employee_app_installations_device", "employee_app_installations", ["device_id"])
    op.create_index("ix_employee_app_installations_employee", "employee_app_installations", ["employee_id"])

    op.create_table(
        "employee_update_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=True),
        sa.Column("release_id", sa.UUID(), nullable=True),
        sa.Column("from_version", sa.String(length=50), nullable=True),
        sa.Column("to_version", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employee_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["release_id"], ["application_releases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_employee_update_history_org", "employee_update_history", ["organization_id"])
    op.create_index("ix_employee_update_history_device", "employee_update_history", ["device_id"])
    op.create_index("ix_employee_update_history_status", "employee_update_history", ["status"])
    op.create_index("ix_employee_update_history_created", "employee_update_history", ["created_at"])

    op.create_table(
        "application_update_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("release_id", sa.UUID(), nullable=True),
        sa.Column("device_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("details_json", sa.JSON().with_variant(sa.JSON(), "sqlite"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["release_id"], ["application_releases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_application_update_events_type", "application_update_events", ["event_type"])
    op.create_index("ix_application_update_events_release", "application_update_events", ["release_id"])
    op.create_index("ix_application_update_events_created", "application_update_events", ["created_at"])

    # Seed staging + production channels and default policies
    now = datetime.now(UTC)
    staging_id = str(uuid.uuid4())
    production_id = str(uuid.uuid4())
    channels = sa.table(
        "application_release_channels",
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        channels,
        [
            {
                "id": staging_id,
                "name": "staging",
                "display_name": "Staging",
                "description": "Pre-release validation channel for IT pilot devices",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": production_id,
                "name": "production",
                "display_name": "Production",
                "description": "General availability channel for all employee devices",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    policies = sa.table(
        "application_update_policies",
        sa.column("id", sa.UUID()),
        sa.column("channel_id", sa.UUID()),
        sa.column("min_supported_version", sa.String()),
        sa.column("force_update", sa.Boolean()),
        sa.column("auto_download", sa.Boolean()),
        sa.column("check_interval_minutes", sa.Integer()),
        sa.column("allow_rollback_publish", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        policies,
        [
            {
                "id": str(uuid.uuid4()),
                "channel_id": staging_id,
                "min_supported_version": None,
                "force_update": False,
                "auto_download": True,
                "check_interval_minutes": 60,
                "allow_rollback_publish": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": str(uuid.uuid4()),
                "channel_id": production_id,
                "min_supported_version": None,
                "force_update": False,
                "auto_download": True,
                "check_interval_minutes": 240,
                "allow_rollback_publish": False,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("application_update_events")
    op.drop_table("employee_update_history")
    op.drop_table("employee_app_installations")
    op.drop_table("application_update_policies")
    op.drop_table("application_release_files")
    op.drop_table("application_releases")
    op.drop_table("application_release_channels")
