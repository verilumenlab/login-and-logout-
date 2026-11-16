"""Admin-visible encrypted password vault for employee accounts.

Revision ID: 0013_admin_visible_passwords
Revises: 0012_attendance_break_source
Create Date: 2026-11-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_admin_visible_passwords"
down_revision = "0012_attendance_break_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("admin_password_encrypted", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("admin_password_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "admin_password_updated_at")
    op.drop_column("users", "admin_password_encrypted")
