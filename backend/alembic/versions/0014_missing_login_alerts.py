"""Missing login alert approval queue.

Revision ID: 0014_missing_login_alerts
Revises: 0013_admin_visible_passwords
Create Date: 2026-11-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_missing_login_alerts"
down_revision = "0013_admin_visible_passwords"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "missing_login_alerts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("employee_name", sa.String(length=200), nullable=False),
        sa.Column("employee_email", sa.String(length=255), nullable=False),
        sa.Column("employee_code", sa.String(length=50), nullable=False),
        sa.Column("department_name", sa.String(length=150), nullable=True),
        sa.Column("scheduled_shift", sa.String(length=100), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "APPROVED", "REJECTED", "SENT", name="missingloginalertstatus"),
            nullable=False,
        ),
        sa.Column("reviewed_by_user_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("emails_sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employee_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "work_date", name="uq_missing_login_emp_date"),
    )
    op.create_index("ix_missing_login_alerts_employee_id", "missing_login_alerts", ["employee_id"])
    op.create_index("ix_missing_login_alerts_organization_id", "missing_login_alerts", ["organization_id"])
    op.create_index("ix_missing_login_alerts_status", "missing_login_alerts", ["status"])
    op.create_index("ix_missing_login_alerts_work_date", "missing_login_alerts", ["work_date"])


def downgrade() -> None:
    op.drop_index("ix_missing_login_alerts_work_date", table_name="missing_login_alerts")
    op.drop_index("ix_missing_login_alerts_status", table_name="missing_login_alerts")
    op.drop_index("ix_missing_login_alerts_organization_id", table_name="missing_login_alerts")
    op.drop_index("ix_missing_login_alerts_employee_id", table_name="missing_login_alerts")
    op.drop_table("missing_login_alerts")
    op.execute("DROP TYPE IF EXISTS missingloginalertstatus")
