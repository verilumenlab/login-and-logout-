"""Attendance break source + client_event_id for auto break tracking.

Revision ID: 0012_attendance_break_source
Revises: 0011_application_releases
Create Date: 2026-11-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_attendance_break_source"
down_revision = "0011_application_releases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attendance_breaks",
        sa.Column("source", sa.String(length=30), nullable=False, server_default="MANUAL"),
    )
    op.add_column(
        "attendance_breaks",
        sa.Column("client_event_id", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_attendance_breaks_client_event_id",
        "attendance_breaks",
        ["client_event_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_attendance_breaks_client_event_id", table_name="attendance_breaks")
    op.drop_column("attendance_breaks", "client_event_id")
    op.drop_column("attendance_breaks", "source")
