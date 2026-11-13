"""Excel Reporting Engine Migration (Phase 11)

Revision ID: 0006_excel_reporting
Revises: 0005_leave_workflow
Create Date: 2026-11-12 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006_excel_reporting'
down_revision: Union[str, None] = '0005_leave_workflow'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add employee_id to report_files
    with op.batch_alter_table('report_files') as batch_op:
        batch_op.add_column(sa.Column('employee_id', sa.UUID(), nullable=True))
        batch_op.create_foreign_key(
            'fk_report_files_employee_id',
            'employee_profiles',
            ['employee_id'],
            ['id'],
            ondelete='SET NULL'
        )


def downgrade() -> None:
    with op.batch_alter_table('report_files') as batch_op:
        batch_op.drop_constraint('fk_report_files_employee_id', type_='foreignkey')
        batch_op.drop_column('employee_id')

