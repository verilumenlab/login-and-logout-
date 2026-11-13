"""Leave Management Workflow Enhancements Migration (Phase 09)

Revision ID: 0005_leave_workflow
Revises: 0004_location_office_enhancements
Create Date: 2026-11-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0005_leave_workflow'
down_revision: Union[str, None] = '0004_location_office_enhancements'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. LeaveType: include_weekends
    with op.batch_alter_table('leave_types') as batch_op:
        batch_op.add_column(sa.Column('include_weekends', sa.Boolean(), nullable=False, server_default='false'))

    # 2. LeaveRequest: is_half_day, half_day_period, manager_approval_status, hr_approval_status, withdrawn_at
    with op.batch_alter_table('leave_requests') as batch_op:
        batch_op.add_column(sa.Column('is_half_day', sa.Boolean(), nullable=False, server_default='false'))
        batch_op.add_column(sa.Column('half_day_period', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('manager_approval_status', sa.String(length=20), nullable=False, server_default='PENDING'))
        batch_op.add_column(sa.Column('hr_approval_status', sa.String(length=20), nullable=False, server_default='PENDING'))
        batch_op.add_column(sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True))

    # 3. LeaveApproval: stage
    with op.batch_alter_table('leave_approvals') as batch_op:
        batch_op.add_column(sa.Column('stage', sa.String(length=20), nullable=False, server_default='MANAGER'))


def downgrade() -> None:
    with op.batch_alter_table('leave_approvals') as batch_op:
        batch_op.drop_column('stage')

    with op.batch_alter_table('leave_requests') as batch_op:
        batch_op.drop_column('withdrawn_at')
        batch_op.drop_column('hr_approval_status')
        batch_op.drop_column('manager_approval_status')
        batch_op.drop_column('half_day_period')
        batch_op.drop_column('is_half_day')

    with op.batch_alter_table('leave_types') as batch_op:
        batch_op.drop_column('include_weekends')

