"""Allow DAILY / WEEKLY / MONTHLY (and other) report types on report_jobs

The original ``reporttype`` PostgreSQL enum only knew four values (ATTENDANCE_SUMMARY,
ACTIVITY_BREAKDOWN, LEAVE_BALANCES, AUDIT_TRAIL). Saving a WEEKLY/DAILY/MONTHLY job therefore
failed on PostgreSQL ("invalid input value for enum reporttype"), which broke the scheduled
Friday report and manual dispatch. ``report_schedules.schedule_type`` is already VARCHAR(50);
this makes ``report_jobs.report_type`` VARCHAR(50) as well.

Revision ID: 0015_report_type_varchar
Revises: 0014_missing_login_alerts
Create Date: 2026-11-25 17:45:00.000000
"""
from alembic import op

revision = "0015_report_type_varchar"
down_revision = "0014_missing_login_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE report_jobs ALTER COLUMN report_type TYPE VARCHAR(50) USING report_type::text")
    op.execute("DROP TYPE IF EXISTS reporttype")


def downgrade() -> None:
    # Not reversible: rows may already use report types the old enum cannot represent.
    pass
