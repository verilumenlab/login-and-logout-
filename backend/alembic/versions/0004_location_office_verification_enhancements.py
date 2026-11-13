"""Location and Office Verification Enhancements Migration (Phase 08)

Revision ID: 0004_location_office_enhancements
Revises: 0003_attendance_engine
Create Date: 2026-11-12 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0004_location_office_enhancements'
down_revision: Union[str, None] = '0003_attendance_engine'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. OfficeNetwork addition: ssid
    with op.batch_alter_table('office_networks') as batch_op:
        batch_op.add_column(sa.Column('ssid', sa.String(length=100), nullable=True))

    # 2. LocationEvent additions: source, permission_status, client_event_id
    with op.batch_alter_table('location_events') as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=50), nullable=False, server_default='DESKTOP'))
        batch_op.add_column(sa.Column('permission_status', sa.String(length=50), nullable=False, server_default='GRANTED'))
        batch_op.add_column(sa.Column('client_event_id', sa.String(length=100), nullable=True))
        batch_op.create_index('ix_location_events_client_event_id', ['client_event_id'])

    # 3. LocationVerification additions: verification_method, is_conclusive, confidence_score, notes
    with op.batch_alter_table('location_verifications') as batch_op:
        batch_op.add_column(sa.Column('verification_method', sa.String(length=50), nullable=False, server_default='GPS'))
        batch_op.add_column(sa.Column('is_conclusive', sa.Boolean(), nullable=False, server_default='false'))
        batch_op.add_column(sa.Column('confidence_score', sa.Float(), nullable=False, server_default='1.0'))
        batch_op.add_column(sa.Column('notes', sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('location_verifications') as batch_op:
        batch_op.drop_column('notes')
        batch_op.drop_column('confidence_score')
        batch_op.drop_column('is_conclusive')
        batch_op.drop_column('verification_method')

    with op.batch_alter_table('location_events') as batch_op:
        batch_op.drop_index('ix_location_events_client_event_id')
        batch_op.drop_column('client_event_id')
        batch_op.drop_column('permission_status')
        batch_op.drop_column('source')

    with op.batch_alter_table('office_networks') as batch_op:
        batch_op.drop_column('ssid')

