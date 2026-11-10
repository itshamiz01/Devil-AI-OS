"""p11 premium command center (dashboard-owned tables only)

Revision ID: 193731df4c37
Revises: e37d00443d20
Create Date: 2026-11-09

P-11 adds exactly two tables, both dashboard-OWNED presentation state
(§25): per-principal UI preferences and per-principal notification
read/dismiss markers. No authoritative record of P-01–P-10 is duplicated.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '193731df4c37'
down_revision: Union[str, None] = 'e37d00443d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('dashboard_preferences',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('principal_key', sa.String(length=232), nullable=False),
    sa.Column('preferences', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('dashboard_preferences', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dashboard_preferences_principal_key'), ['principal_key'], unique=True)

    op.create_table('dashboard_notification_states',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('principal_key', sa.String(length=232), nullable=False),
    sa.Column('notification_id', sa.String(length=300), nullable=False),
    sa.Column('is_read', sa.Boolean(), nullable=False),
    sa.Column('is_dismissed', sa.Boolean(), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('principal_key', 'notification_id', name='uq_dashboard_notification_state')
    )
    with op.batch_alter_table('dashboard_notification_states', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dashboard_notification_states_principal_key'), ['principal_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_dashboard_notification_states_notification_id'), ['notification_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('dashboard_notification_states', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dashboard_notification_states_notification_id'))
        batch_op.drop_index(batch_op.f('ix_dashboard_notification_states_principal_key'))

    op.drop_table('dashboard_notification_states')
    with op.batch_alter_table('dashboard_preferences', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dashboard_preferences_principal_key'))

    op.drop_table('dashboard_preferences')
