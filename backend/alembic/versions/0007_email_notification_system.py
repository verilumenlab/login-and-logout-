"""Email Notification System Migration (Phase 12)

Revision ID: 0007_email_notification
Revises: 0006_excel_reporting
Create Date: 2026-11-12 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007_email_notification'
down_revision: Union[str, None] = '0006_excel_reporting'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('email_outbox') as batch_op:
        batch_op.add_column(sa.Column('idempotency_key', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('body_text', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('attachments', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('sender_email', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('sender_name', sa.String(length=150), nullable=True))
        batch_op.create_index('ix_email_outbox_idempotency_key', ['idempotency_key'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('email_outbox') as batch_op:
        batch_op.drop_index('ix_email_outbox_idempotency_key')
        batch_op.drop_column('sender_name')
        batch_op.drop_column('sender_email')
        batch_op.drop_column('attachments')
        batch_op.drop_column('body_text')
        batch_op.drop_column('idempotency_key')

