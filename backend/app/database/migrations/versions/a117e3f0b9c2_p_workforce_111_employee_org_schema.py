"""P-WORKFORCE: the 111-employee virtual organization schema

Revision ID: a117e3f0b9c2
Revises: 229ca08ee712
Create Date: 2026-11-15

Eight tables for the workforce transformation (§3, §6, §7, §10, §14):

``workforce_departments``, ``workforce_employees``, ``workforce_objectives``,
``workforce_work_orders``, ``workforce_handoffs``, ``workforce_messages``,
``workforce_employee_performance``, ``workforce_status_history``.

The workforce does **not** create a second agent registry, task scheduler or
financial ledger. ``workforce_employees.employee_id`` is the stable employee
identity (``DEV-CEO-001``, ``DEV-MGR-001``, ``DEV-STR-001``, ...) and doubles
as the key into the existing ``agents`` registry: the workforce layer writes
agent rows through the existing ``AgentRepo`` at seed time, and the employee
profile here is the organizational overlay (responsibilities, skills,
instructions, work orders, handoffs, performance) the registry deliberately
does not carry.

Every CHECK is named (``ck_*``) and every unique constraint is named
(``uq_*``), per ADR-0024, and every column that has a Python-side default
also gets a ``server_default`` inside the constrained vocabulary, so a raw
insert that omits the column lands in a valid state rather than one the CHECK
then refuses. The CHECK bodies are written from the model definitions by
hand because autogenerate renders none of the column-level CHECKs (ADR-0024).
The vocabularies are kept as literals here because a migration must not
import the vocabulary it is in the middle of constraining.

No existing table is touched and no existing row needs normalizing, so there
is no data step: the database gains 52 + 8 = 60 tables.
"""
from alembic import op
import sqlalchemy as sa

revision = 'a117e3f0b9c2'
down_revision = '229ca08ee712'
branch_labels = None
depends_on = None

_EMPLOYEE_STATUSES = (
    'ACTIVE', 'AVAILABLE', 'BUSY', 'WAITING', 'BLOCKED',
    'ON_LEAVE', 'SUSPENDED', 'DISABLED',
)
_WORK_ORDER_STATES = (
    'TASK_ASSIGNED', 'TASK_ACCEPTED', 'WORKING', 'REVIEW_PENDING',
    'COMPLETED', 'BLOCKED', 'WAITING_FOR_INPUT', 'WAITING_FOR_APPROVAL',
    'FAILED', 'REASSIGNED', 'CANCELLED',
)
_HANDOFF_STATES = ('pending', 'accepted', 'in_progress', 'completed', 'rejected')
_OBJECTIVE_STATES = ('OPEN', 'DELEGATED', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'CANCELLED')


def upgrade() -> None:
    op.create_table(
        'workforce_employees',
        sa.Column('employee_id', sa.String(length=64), nullable=False),
        sa.Column('display_name', sa.String(length=128), nullable=False),
        sa.Column('department_code', sa.String(length=32), nullable=False),
        sa.Column('department_name', sa.String(length=128), nullable=False),
        sa.Column('job_title', sa.String(length=128), nullable=False),
        sa.Column('role_description', sa.Text(), nullable=False),
        sa.Column('primary_responsibilities', sa.JSON(), nullable=False),
        sa.Column('secondary_responsibilities', sa.JSON(), nullable=False),
        sa.Column('manager_employee_id', sa.String(length=64), nullable=True),
        sa.Column('seniority', sa.Integer(), server_default='1', nullable=False),
        sa.Column('skills', sa.JSON(), nullable=False),
        sa.Column('tool_access', sa.JSON(), nullable=False),
        sa.Column('memory_scope', sa.String(length=512), nullable=False),
        sa.Column('system_instructions', sa.Text(), nullable=False),
        sa.Column('communication_style', sa.String(length=128), server_default='professional', nullable=False),
        sa.Column('autonomy_level', sa.String(length=64), server_default='supervised', nullable=False),
        sa.Column('permission_scope', sa.String(length=512), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='ACTIVE', nullable=False),
        sa.Column('is_baseline', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('is_expansion', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('current_assignments', sa.JSON(), nullable=False),
        sa.Column('last_activity', sa.DateTime(timezone=True), nullable=True),
        sa.Column('configuration_version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('seniority >= 0', name='ck_workforce_employees_seniority'),
        sa.CheckConstraint('status IN (%s)' % ", ".join("'%s'" % s for s in _EMPLOYEE_STATUSES),
                           name='ck_workforce_employees_status'),
        sa.CheckConstraint('configuration_version >= 1', name='ck_workforce_employees_config_version'),
        sa.PrimaryKeyConstraint('employee_id'),
        sa.UniqueConstraint('display_name', name='uq_workforce_employees_display_name'),
        sa.ForeignKeyConstraint(['manager_employee_id'], ['workforce_employees.employee_id']),
    )
    op.create_index('ix_workforce_employees_department', 'workforce_employees', ['department_code'])
    op.create_index('ix_workforce_employees_status', 'workforce_employees', ['status'])
    op.create_index('ix_workforce_employees_manager', 'workforce_employees', ['manager_employee_id'])

    op.create_table(
        'workforce_departments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('manager_employee_id', sa.String(length=64), nullable=False),
        sa.Column('mission', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_workforce_departments_code'),
        sa.ForeignKeyConstraint(['manager_employee_id'], ['workforce_employees.employee_id']),
    )
    op.create_index('ix_workforce_departments_manager', 'workforce_departments', ['manager_employee_id'])

    op.create_table(
        'workforce_objectives',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('objective', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=32), server_default='owner', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='OPEN', nullable=False),
        sa.Column('departments', sa.JSON(), nullable=False),
        sa.Column('expected_outcome', sa.Text(), nullable=False),
        sa.Column('created_by', sa.String(length=64), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('status IN (%s)' % ", ".join("'%s'" % s for s in _OBJECTIVE_STATES),
                           name='ck_workforce_objectives_status'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_workforce_objectives_status', 'workforce_objectives', ['status'])

    op.create_table(
        'workforce_work_orders',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('employee_id', sa.String(length=64), nullable=False),
        sa.Column('manager_employee_id', sa.String(length=64), nullable=False),
        sa.Column('objective_id', sa.String(length=36), nullable=True),
        sa.Column('task_id', sa.String(length=36), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('instructions', sa.Text(), nullable=False),
        sa.Column('required_inputs', sa.JSON(), nullable=False),
        sa.Column('expected_deliverable', sa.JSON(), nullable=False),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('priority', sa.Integer(), server_default='5', nullable=False),
        sa.Column('dependencies', sa.JSON(), nullable=False),
        sa.Column('available_tools', sa.JSON(), nullable=False),
        sa.Column('permission_scope', sa.String(length=512), nullable=False),
        sa.Column('budget_constraints', sa.JSON(), nullable=False),
        sa.Column('verification_requirements', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='TASK_ASSIGNED', nullable=False),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('priority >= 1 AND priority <= 10', name='ck_workforce_work_orders_priority'),
        sa.CheckConstraint('status IN (%s)' % ", ".join("'%s'" % s for s in _WORK_ORDER_STATES),
                           name='ck_workforce_work_orders_status'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['employee_id'], ['workforce_employees.employee_id']),
        sa.ForeignKeyConstraint(['objective_id'], ['workforce_objectives.id']),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
    )
    op.create_index('ix_workforce_work_orders_employee', 'workforce_work_orders', ['employee_id'])
    op.create_index('ix_workforce_work_orders_status', 'workforce_work_orders', ['status'])
    op.create_index('ix_workforce_work_orders_objective', 'workforce_work_orders', ['objective_id'])
    op.create_index('ix_workforce_work_orders_task', 'workforce_work_orders', ['task_id'])

    op.create_table(
        'workforce_handoffs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('from_department', sa.String(length=32), nullable=False),
        sa.Column('to_department', sa.String(length=32), nullable=False),
        sa.Column('from_employee_id', sa.String(length=64), nullable=False),
        sa.Column('to_employee_id', sa.String(length=64), nullable=False),
        sa.Column('source_work_order_id', sa.String(length=36), nullable=True),
        sa.Column('objective', sa.Text(), nullable=False),
        sa.Column('deliverable', sa.Text(), nullable=False),
        sa.Column('context', sa.JSON(), nullable=False),
        sa.Column('references', sa.JSON(), nullable=False),
        sa.Column('required_action', sa.Text(), nullable=False),
        sa.Column('access_scope', sa.String(length=512), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='pending', nullable=False),
        sa.Column('completion_criteria', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('status IN (%s)' % ", ".join("'%s'" % s for s in _HANDOFF_STATES),
                           name='ck_workforce_handoffs_status'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['to_employee_id'], ['workforce_employees.employee_id']),
        sa.ForeignKeyConstraint(['source_work_order_id'], ['workforce_work_orders.id']),
    )
    op.create_index('ix_workforce_handoffs_from_employee', 'workforce_handoffs', ['from_employee_id'])
    op.create_index('ix_workforce_handoffs_to_employee', 'workforce_handoffs', ['to_employee_id'])
    op.create_index('ix_workforce_handoffs_status', 'workforce_handoffs', ['status'])

    op.create_table(
        'workforce_messages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('from_employee_id', sa.String(length=64), nullable=False),
        sa.Column('to_employee_id', sa.String(length=64), nullable=False),
        sa.Column('channel_type', sa.String(length=32), server_default='direct', nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=True),
        sa.Column('handoff_id', sa.String(length=36), nullable=True),
        sa.Column('kind', sa.String(length=64), server_default='message', nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['to_employee_id'], ['workforce_employees.employee_id']),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
        sa.ForeignKeyConstraint(['handoff_id'], ['workforce_handoffs.id']),
    )
    op.create_index('ix_workforce_messages_from', 'workforce_messages', ['from_employee_id'])
    op.create_index('ix_workforce_messages_to', 'workforce_messages', ['to_employee_id'])
    op.create_index('ix_workforce_messages_task', 'workforce_messages', ['task_id'])
    op.create_index('ix_workforce_messages_handoff', 'workforce_messages', ['handoff_id'])

    op.create_table(
        'workforce_employee_performance',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('employee_id', sa.String(length=64), nullable=False),
        sa.Column('period', sa.String(length=32), nullable=False),
        sa.Column('task_completion_rate', sa.Float(), server_default='0', nullable=False),
        sa.Column('quality_score', sa.Float(), server_default='0', nullable=False),
        sa.Column('deadline_adherence', sa.Float(), server_default='0', nullable=False),
        sa.Column('rework_rate', sa.Float(), server_default='0', nullable=False),
        sa.Column('verified_success_rate', sa.Float(), server_default='0', nullable=False),
        sa.Column('resource_efficiency', sa.Float(), server_default='0', nullable=False),
        sa.Column('error_rate', sa.Float(), server_default='0', nullable=False),
        sa.Column('collaboration_quality', sa.Float(), server_default='0', nullable=False),
        sa.Column('policy_compliance', sa.Float(), server_default='100', nullable=False),
        sa.Column('composite_score', sa.Float(), server_default='0', nullable=False),
        sa.Column('weights', sa.JSON(), nullable=False),
        sa.Column('source', sa.String(length=64), server_default='system', nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', 'period', name='uq_workforce_performance_employee_period'),
        sa.ForeignKeyConstraint(['employee_id'], ['workforce_employees.employee_id']),
    )
    op.create_index('ix_workforce_performance_employee', 'workforce_employee_performance', ['employee_id'])

    op.create_table(
        'workforce_status_history',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('employee_id', sa.String(length=64), nullable=False),
        sa.Column('from_status', sa.String(length=32), nullable=True),
        sa.Column('to_status', sa.String(length=32), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('actor', sa.String(length=64), server_default='system', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['employee_id'], ['workforce_employees.employee_id']),
    )
    op.create_index('ix_workforce_status_history_employee', 'workforce_status_history', ['employee_id'])

    op.create_table(
        'workforce_memory',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('employee_id', sa.String(length=64), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('scope', sa.String(length=512), nullable=False),
        sa.Column('source', sa.String(length=64), server_default='employee', nullable=False),
        sa.Column('shared_with', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['employee_id'], ['workforce_employees.employee_id']),
    )
    op.create_index('ix_workforce_memory_employee', 'workforce_memory', ['employee_id'])


def downgrade() -> None:
    op.drop_table('workforce_memory')
    op.drop_table('workforce_status_history')
    op.drop_table('workforce_employee_performance')
    op.drop_table('workforce_messages')
    op.drop_table('workforce_handoffs')
    op.drop_table('workforce_work_orders')
    op.drop_table('workforce_objectives')
    op.drop_table('workforce_employees')
    op.drop_table('workforce_departments')
