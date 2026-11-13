"""Automated Report Scheduling Migration (Phase 13)

Revision ID: 0008_report_scheduling
Revises: 0007_email_notification
Create Date: 2026-11-12 23:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008_report_scheduling'
down_revision: Union[str, None] = '0007_email_notification'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create report_schedules table
    op.create_table(
        'report_schedules',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('schedule_type', sa.String(length=50), nullable=False),
        sa.Column('cron_expression', sa.String(length=100), server_default='0 6 * * *', nullable=False),
        sa.Column('timezone', sa.String(length=50), server_default='UTC', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('send_email', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('recipient_emails', sa.Text(), nullable=True),
        sa.Column('include_individual_reports', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('include_manager_reports', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('include_consolidated_report', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_status', sa.String(length=50), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'schedule_type', name='uq_report_schedule_org_type'),
    )
    op.create_index('ix_report_schedules_org_id', 'report_schedules', ['organization_id'], unique=False)
    op.create_index('ix_report_schedules_active', 'report_schedules', ['is_active'], unique=False)

    # 2. Add schedule_id and idempotency_key to report_jobs
    with op.batch_alter_table('report_jobs') as batch_op:
        batch_op.add_column(sa.Column('schedule_id', sa.UUID(), nullable=True))
        batch_op.add_column(sa.Column('idempotency_key', sa.String(length=255), nullable=True))
        batch_op.create_index('ix_report_jobs_idempotency_key', ['idempotency_key'], unique=False)
        batch_op.create_foreign_key(
            'fk_report_jobs_schedule_id',
            'report_schedules',
            ['schedule_id'],
            ['id'],
            ondelete='SET NULL'
        )


def downgrade() -> None:
    with op.batch_alter_table('report_jobs') as batch_op:
        batch_op.drop_constraint('fk_report_jobs_schedule_id', type_='foreignkey')
        batch_op.drop_index('ix_report_jobs_idempotency_key')
        batch_op.drop_column('idempotency_key')
        batch_op.drop_column('schedule_id')

    op.drop_index('ix_report_schedules_active', table_name='report_schedules')
    op.drop_index('ix_report_schedules_org_id', table_name='report_schedules')
    op.drop_table('report_schedules')

