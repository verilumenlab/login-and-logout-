"""Attendance Engine Enhancements Migration (Phase 07)

Revision ID: 0003_attendance_engine
Revises: 0002_os_session_events
Create Date: 2026-11-12 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0003_attendance_engine'
down_revision: Union[str, None] = '0002_os_session_events'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

jsonb_type = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite')


def upgrade() -> None:
    # AttendanceDay additions
    op.add_column('attendance_days', sa.Column('late_minutes', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('attendance_days', sa.Column('early_departure_minutes', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('attendance_days', sa.Column('is_wfh', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('attendance_days', sa.Column('is_missing_checkout', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('attendance_days', sa.Column('metadata_json', jsonb_type, nullable=True))

    # AttendanceEvent additions
    op.add_column('attendance_events', sa.Column('client_event_id', sa.String(length=100), nullable=True))
    op.add_column('attendance_events', sa.Column('is_wfh', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('attendance_events', sa.Column('sync_delay_seconds', sa.Float(), nullable=False, server_default='0.0'))
    op.create_index('ix_attendance_events_client_event_id', 'attendance_events', ['client_event_id'])


def downgrade() -> None:
    op.drop_index('ix_attendance_events_client_event_id', table_name='attendance_events')
    op.drop_column('attendance_events', 'sync_delay_seconds')
    op.drop_column('attendance_events', 'is_wfh')
    op.drop_column('attendance_events', 'client_event_id')

    op.drop_column('attendance_days', 'metadata_json')
    op.drop_column('attendance_days', 'is_missing_checkout')
    op.drop_column('attendance_days', 'is_wfh')
    op.drop_column('attendance_days', 'early_departure_minutes')
    op.drop_column('attendance_days', 'late_minutes')

