"""agentic workforce transformation: departments, profiles, objectives, deliverables

Revision ID: cb34dbb7a7c9
Revises: af39baad9c40

Additive only (see docs/agentic-workforce/WORKFORCE_PRE_IMPLEMENTATION_AUDIT.md
§3). Four new tables; no existing table is altered:

- ``workforce_departments`` — the ten §5 departments.
- ``workforce_profiles`` — 1:1 extension of the P-01 ``agents`` registry
  holding the stable employee code (unique — this is what makes the
  111-employee seed idempotent) and the §6 profile data.
- ``workforce_objectives`` — CEO executive objectives, plan, report.
- ``workforce_deliverables`` — §10 deliverable submissions + reviews.

Employees remain rows in ``agents``; work orders remain P-01 ``tasks`` +
P-04 ``agent_assignments``; performance remains ``agent_metrics``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'cb34dbb7a7c9'
down_revision: Union[str, None] = 'af39baad9c40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'workforce_departments',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('mission', sa.Text(), nullable=False),
        sa.Column('manager_agent_id', sa.String(length=64), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['manager_agent_id'], ['agents.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workforce_departments_code'),
                    'workforce_departments', ['code'], unique=True)
    op.create_table(
        'workforce_profiles',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('agent_id', sa.String(length=64), nullable=False),
        sa.Column('employee_code', sa.String(length=32), nullable=False),
        sa.Column('level', sa.String(length=16), nullable=False),
        sa.Column('department_id', sa.String(length=64), nullable=True),
        sa.Column('display_name', sa.String(length=200), nullable=False),
        sa.Column('job_title', sa.String(length=200), nullable=False),
        sa.Column('role_description', sa.Text(), nullable=False),
        sa.Column('primary_responsibilities', sa.JSON(), nullable=False),
        sa.Column('secondary_responsibilities', sa.JSON(), nullable=False),
        sa.Column('seniority', sa.String(length=32), nullable=False),
        sa.Column('skills', sa.JSON(), nullable=False),
        sa.Column('tool_access', sa.JSON(), nullable=False),
        sa.Column('memory_scope', sa.JSON(), nullable=False),
        sa.Column('system_instructions', sa.Text(), nullable=False),
        sa.Column('communication_style', sa.String(length=200), nullable=False),
        sa.Column('autonomy_level', sa.String(length=32), nullable=False),
        sa.Column('permission_scope', sa.JSON(), nullable=False),
        sa.Column('workforce_status', sa.String(length=32), nullable=False),
        sa.Column('kpi_weights', sa.JSON(), nullable=False),
        sa.Column('config_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id']),
        sa.ForeignKeyConstraint(['department_id'], ['workforce_departments.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agent_id', name='uq_workforce_profile_agent'),
        sa.UniqueConstraint('employee_code', name='uq_workforce_employee_code'),
    )
    op.create_index(op.f('ix_workforce_profiles_agent_id'),
                    'workforce_profiles', ['agent_id'], unique=False)
    op.create_index(op.f('ix_workforce_profiles_employee_code'),
                    'workforce_profiles', ['employee_code'], unique=False)
    op.create_index(op.f('ix_workforce_profiles_level'),
                    'workforce_profiles', ['level'], unique=False)
    op.create_index(op.f('ix_workforce_profiles_department_id'),
                    'workforce_profiles', ['department_id'], unique=False)
    op.create_index(op.f('ix_workforce_profiles_workforce_status'),
                    'workforce_profiles', ['workforce_status'], unique=False)
    op.create_table(
        'workforce_objectives',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('submitted_by_type', sa.String(length=32), nullable=False),
        sa.Column('submitted_by_id', sa.String(length=200), nullable=False),
        sa.Column('ceo_agent_id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('plan', sa.JSON(), nullable=False),
        sa.Column('restricted_actions', sa.JSON(), nullable=False),
        sa.Column('consolidated_report', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['ceo_agent_id'], ['agents.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workforce_objectives_status'),
                    'workforce_objectives', ['status'], unique=False)
    op.create_table(
        'workforce_deliverables',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('assignment_id', sa.String(length=64), nullable=False),
        sa.Column('task_id', sa.String(length=64), nullable=True),
        sa.Column('employee_agent_id', sa.String(length=64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('objective', sa.Text(), nullable=False),
        sa.Column('work_performed', sa.Text(), nullable=False),
        sa.Column('result', sa.Text(), nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('limitations', sa.Text(), nullable=False),
        sa.Column('outstanding_issues', sa.Text(), nullable=False),
        sa.Column('verification_status', sa.String(length=32), nullable=False),
        sa.Column('review_status', sa.String(length=32), nullable=False),
        sa.Column('reviewed_by_agent_id', sa.String(length=64), nullable=True),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('quality_score', sa.Float(), nullable=True),
        sa.Column('on_time', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['assignment_id'], ['agent_assignments.id']),
        sa.ForeignKeyConstraint(['employee_agent_id'], ['agents.id']),
        sa.ForeignKeyConstraint(['reviewed_by_agent_id'], ['agents.id']),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workforce_deliverables_assignment_id'),
                    'workforce_deliverables', ['assignment_id'], unique=False)
    op.create_index(op.f('ix_workforce_deliverables_employee_agent_id'),
                    'workforce_deliverables', ['employee_agent_id'], unique=False)
    op.create_index(op.f('ix_workforce_deliverables_review_status'),
                    'workforce_deliverables', ['review_status'], unique=False)


def downgrade() -> None:
    op.drop_table('workforce_deliverables')
    op.drop_table('workforce_objectives')
    op.drop_table('workforce_profiles')
    op.drop_table('workforce_departments')
