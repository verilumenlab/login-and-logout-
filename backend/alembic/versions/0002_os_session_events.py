"""Native OS Session Monitoring Events Migration (Phase 06)

Revision ID: 0002_os_session_events
Revises: 0001_complete_architecture
Create Date: 2026-11-12 15:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002_os_session_events'
down_revision: Union[str, None] = '0001_complete_architecture'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

jsonb_type = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite')


def upgrade() -> None:
    op.create_table(
        'os_session_events',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('event_id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('device_id', sa.String(length=255), nullable=False),
        sa.Column('operating_system', sa.String(length=50), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sequence_number', sa.BigInteger(), nullable=False),
        sa.Column('sync_delay_seconds', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('agent_version', sa.String(length=50), nullable=False, server_default='1.0.0'),
        sa.Column('metadata_json', jsonb_type, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employee_profiles.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('event_id', name='uq_os_session_event_id'),
        sa.UniqueConstraint('device_id', 'sequence_number', name='uq_device_sequence_number'),
    )
    op.create_index('ix_os_session_events_event_id', 'os_session_events', ['event_id'], unique=True)
    op.create_index('ix_os_session_events_employee_id', 'os_session_events', ['employee_id'])
    op.create_index('ix_os_session_events_device_id', 'os_session_events', ['device_id'])
    op.create_index('ix_os_session_events_type', 'os_session_events', ['event_type'])
    op.create_index('ix_os_session_events_occurred', 'os_session_events', ['occurred_at'])
    op.create_index('ix_os_session_events_dev_occurred', 'os_session_events', ['device_id', 'occurred_at'])
    op.create_index('ix_os_session_events_emp_occurred', 'os_session_events', ['employee_id', 'occurred_at'])


def downgrade() -> None:
    op.drop_table('os_session_events')

