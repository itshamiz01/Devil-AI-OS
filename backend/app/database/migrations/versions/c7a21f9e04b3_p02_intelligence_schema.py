"""p02 intelligence schema (missions, plans, plan_steps, decision_records,
model_profiles) — additive on top of the P-01 core schema.

Revision ID: c7a21f9e04b3
Revises: b36fd80092d2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7a21f9e04b3'
down_revision: Union[str, None] = 'b36fd80092d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('missions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('creator_type', sa.String(length=32), nullable=False),
    sa.Column('creator_id', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('mode', sa.String(length=32), nullable=False),
    sa.Column('matched_template', sa.String(length=100), nullable=True),
    sa.Column('correlation_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('missions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_missions_status'), ['status'], unique=False)

    op.create_table('model_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('task_classes', sa.JSON(), nullable=False),
    sa.Column('provider', sa.String(length=100), nullable=False),
    sa.Column('model_id', sa.String(length=300), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('limits', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('model_profiles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_model_profiles_name'), ['name'], unique=True)

    op.create_table('plans',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('mission_id', sa.String(length=64), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('planner', sa.String(length=200), nullable=False),
    sa.Column('model_profile', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('plan_hash', sa.String(length=64), nullable=True),
    sa.Column('approval_id', sa.String(length=64), nullable=True),
    sa.Column('rationale', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['approval_id'], ['approvals.id'], ),
    sa.ForeignKeyConstraint(['mission_id'], ['missions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_plans_mission_id'), ['mission_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_plans_status'), ['status'], unique=False)

    op.create_table('plan_steps',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('plan_id', sa.String(length=64), nullable=False),
    sa.Column('order_index', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('tool_name', sa.String(length=200), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('expectation', sa.JSON(), nullable=False),
    sa.Column('task_class', sa.String(length=100), nullable=False),
    sa.Column('essential', sa.Boolean(), nullable=False),
    sa.Column('timeout_seconds', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('task_id', sa.String(length=64), nullable=True),
    sa.Column('verification_status', sa.String(length=32), nullable=False),
    sa.Column('verification_detail', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('plan_steps', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_plan_steps_plan_id'), ['plan_id'], unique=False)

    op.create_table('decision_records',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('mission_id', sa.String(length=64), nullable=True),
    sa.Column('plan_id', sa.String(length=64), nullable=True),
    sa.Column('step_id', sa.String(length=64), nullable=True),
    sa.Column('decision_type', sa.String(length=100), nullable=False),
    sa.Column('actor', sa.String(length=200), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('evidence', sa.JSON(), nullable=False),
    sa.Column('correlation_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['mission_id'], ['missions.id'], ),
    sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ),
    sa.ForeignKeyConstraint(['step_id'], ['plan_steps.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('decision_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_decision_records_decision_type'), ['decision_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_decision_records_mission_id'), ['mission_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_decision_records_plan_id'), ['plan_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('decision_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_decision_records_plan_id'))
        batch_op.drop_index(batch_op.f('ix_decision_records_mission_id'))
        batch_op.drop_index(batch_op.f('ix_decision_records_decision_type'))
    op.drop_table('decision_records')
    with op.batch_alter_table('plan_steps', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_plan_steps_plan_id'))
    op.drop_table('plan_steps')
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_plans_status'))
        batch_op.drop_index(batch_op.f('ix_plans_mission_id'))
    op.drop_table('plans')
    with op.batch_alter_table('model_profiles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_model_profiles_name'))
    op.drop_table('model_profiles')
    with op.batch_alter_table('missions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_missions_status'))
    op.drop_table('missions')
