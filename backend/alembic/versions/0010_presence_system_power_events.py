"""Document SYSTEM_* presence event types for laptop power login/logout.

Revision ID: 0010_presence_system_power
Revises: 0009_presence_events
Create Date: 2026-11-13

presence_events.event_type is already String(30); this revision widens it slightly
for safety and records the new allowed values in migration history.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_presence_system_power"
down_revision = "0009_presence_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("presence_events") as batch_op:
        batch_op.alter_column(
            "event_type",
            existing_type=sa.String(length=30),
            type_=sa.String(length=40),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("presence_events") as batch_op:
        batch_op.alter_column(
            "event_type",
            existing_type=sa.String(length=40),
            type_=sa.String(length=30),
            existing_nullable=False,
        )
