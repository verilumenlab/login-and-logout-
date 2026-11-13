"""Desktop presence events: app login/logout and Wi-Fi connect/disconnect

Revision ID: 0009_presence_events
Revises: 0008_report_scheduling
Create Date: 2026-11-13 12:00:00.000000

"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0009_presence_events'
down_revision: str | None = '0008_report_scheduling'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'presence_events',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('employee_id', sa.UUID(), sa.ForeignKey('employee_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(length=30), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('client_event_id', sa.String(length=100), nullable=False),
        sa.Column('device_id', sa.String(length=255), nullable=True),
        sa.Column('ssid', sa.String(length=255), nullable=True),
        sa.Column('bssid', sa.String(length=64), nullable=True),
        sa.Column('attendance_action', sa.String(length=20), server_default='NONE', nullable=False),
        sa.UniqueConstraint('employee_id', 'client_event_id', name='uq_presence_employee_client_event'),
    )
    op.create_index('ix_presence_events_organization_id', 'presence_events', ['organization_id'], unique=False)
    op.create_index('ix_presence_events_employee_id', 'presence_events', ['employee_id'], unique=False)
    op.create_index('ix_presence_events_emp_occurred', 'presence_events', ['employee_id', 'occurred_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_presence_events_emp_occurred', table_name='presence_events')
    op.drop_index('ix_presence_events_employee_id', table_name='presence_events')
    op.drop_index('ix_presence_events_organization_id', table_name='presence_events')
    op.drop_table('presence_events')
