"""P-05 Stage 2: the execution core's nine tables

Revision ID: 229ca08ee712
Revises: d577d056a63b
Create Date: 2026-11-05

The execution engine's persistence, created before any adapter exists so that
the policy engine, the tool registry and the request manager have somewhere
real to write. Nine tables from the brief's §19:

``execution_tools``, ``execution_requests``, ``execution_runs``,
``execution_evidence``, ``execution_workspaces``, ``browser_sessions``,
``workflow_definitions``, ``workflow_runs``, ``workflow_step_runs``.

Two of §19's logical entities are **not** created, by the brief's own
instruction to prefer what exists: ``execution_approvals`` (the central
``approvals`` table carries execution approvals; ``execution_requests``
references it) and ``execution_audit_events`` (``audit_events`` and
``system_events`` already record execution decisions). A second approval queue
and a second audit log would be two systems to reconcile, which is what §17
forbids.

Every CHECK is named (`ck_*`) and every unique constraint is named (`uq_*`),
per ADR-0024. Autogenerate rendered **none** of the column-level CHECKs for
these tables - it silently omits them from ``create_table``, the exact failure
ADR-0024 records from P-04 - so the constraint bodies below were written from
the model definitions by hand and are proven by the schema tests, which insert
values the CHECKs must refuse. Foreign keys in ``create_table`` bodies follow
the P-04 convention and are unnamed: the downgrade drops whole tables, so no
later revision needs to address an FK here by name. No existing table is
touched and no existing row needs normalizing, so unlike Stages 4-6 there is
no data step: the database gains 43 + 9 = 52 tables.

``server_default`` is declared alongside the Python-side default on every
column that has one, so a raw insert that omits the column receives a value
inside the constrained vocabulary rather than an empty string the CHECK then
rejects - the half-migrated state Stage 6's revision exists to prevent.
"""
from alembic import op
import sqlalchemy as sa

from app.database.migrations.portable import portable_alter_table

revision = '229ca08ee712'
down_revision = 'd577d056a63b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('execution_tools',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=64), nullable=False),
    sa.Column('adapter_type', sa.String(length=32), nullable=False),
    sa.Column('version', sa.String(length=32), nullable=False),
    sa.Column('supported_actions', sa.JSON(), nullable=False),
    sa.Column('input_schema', sa.JSON(), nullable=False),
    sa.Column('output_schema', sa.JSON(), nullable=False),
    sa.Column('capability_requirements', sa.JSON(), nullable=False),
    sa.Column('risk_level', sa.Integer(), server_default='1', nullable=False),
    sa.Column('required_approval_level', sa.Integer(), server_default='0', nullable=False),
    sa.Column('supported_platforms', sa.JSON(), nullable=False),
    sa.Column('resource_requirements', sa.JSON(), nullable=False),
    sa.Column('timeout_default_seconds', sa.Integer(), server_default='60', nullable=False),
    sa.Column('retry_eligible', sa.Boolean(), nullable=False),
    sa.Column('idempotent', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=32), server_default='REGISTERED', nullable=False),
    sa.Column('health_status', sa.String(length=32), server_default='unknown', nullable=False),
    sa.Column('health_detail', sa.Text(), nullable=True),
    sa.Column('configuration_reference', sa.String(length=256), nullable=True),
    sa.Column('isolation_strength', sa.String(length=128), nullable=True),
    sa.Column('disabled_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("adapter_type IN ('filesystem', 'code', 'browser', 'desktop', 'api', 'document', 'data')", name='ck_execution_tools_adapter_type'),
    sa.CheckConstraint('risk_level >= 0 AND risk_level <= 3', name='ck_execution_tools_risk_level'),
    sa.CheckConstraint('required_approval_level >= 0 AND required_approval_level <= 3', name='ck_execution_tools_required_approval_level'),
    sa.CheckConstraint('timeout_default_seconds > 0', name='ck_execution_tools_timeout_default'),
    sa.CheckConstraint("status IN ('REGISTERED', 'VALIDATING', 'AVAILABLE', 'DEGRADED', 'DISABLED', 'DEPRECATED', 'REMOVED')", name='ck_execution_tools_status'),
    sa.UniqueConstraint('name', 'version', name='uq_execution_tools_name_version'),
    sa.PrimaryKeyConstraint('id')
    )
    with portable_alter_table('execution_tools', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_execution_tools_status'), ['status'], unique=False)

    op.create_table('execution_workspaces',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('workspace_name', sa.String(length=128), nullable=False),
    sa.Column('owner_type', sa.String(length=32), nullable=False),
    sa.Column('owner_id', sa.String(length=64), nullable=False),
    sa.Column('root_path', sa.String(length=1024), nullable=False),
    sa.Column('permission_scope', sa.String(length=512), nullable=False),
    sa.Column('status', sa.String(length=32), server_default='active', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('active', 'disabled', 'removed')", name='ck_execution_workspaces_status'),
    sa.UniqueConstraint('owner_type', 'owner_id', 'workspace_name', name='uq_execution_workspaces_owner_name'),
    sa.PrimaryKeyConstraint('id')
    )
    with portable_alter_table('execution_workspaces', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_execution_workspaces_owner_id'), ['owner_id'], unique=False)

    op.create_table('workflow_definitions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('definition_json', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=32), server_default='draft', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('version >= 1', name='ck_workflow_definitions_version'),
    sa.CheckConstraint("status IN ('draft', 'validating', 'approved', 'disabled')", name='ck_workflow_definitions_status'),
    sa.UniqueConstraint('name', 'version', name='uq_workflow_definitions_name_version'),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('browser_sessions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('agent_id', sa.String(length=36), sa.ForeignKey('agents.id'), nullable=False),
    sa.Column('browser_type', sa.String(length=64), nullable=False),
    sa.Column('allowed_domains', sa.JSON(), nullable=False),
    sa.Column('permission_scope', sa.String(length=512), nullable=False),
    sa.Column('status', sa.String(length=32), server_default='created', nullable=False),
    sa.Column('last_activity', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('created', 'active', 'paused', 'closed', 'expired')", name='ck_browser_sessions_status'),
    sa.PrimaryKeyConstraint('id')
    )
    with portable_alter_table('browser_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_browser_sessions_agent_id'), ['agent_id'], unique=False)

    op.create_table('execution_requests',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('task_id', sa.String(length=36), sa.ForeignKey('tasks.id'), nullable=False),
    sa.Column('agent_id', sa.String(length=36), sa.ForeignKey('agents.id'), nullable=False),
    sa.Column('tool_id', sa.String(length=36), sa.ForeignKey('execution_tools.id'), nullable=False),
    sa.Column('adapter_type', sa.String(length=32), nullable=False),
    sa.Column('action_name', sa.String(length=128), nullable=False),
    sa.Column('request_payload', sa.JSON(), nullable=False),
    sa.Column('input_references', sa.JSON(), nullable=False),
    sa.Column('requested_scope', sa.String(length=512), nullable=False),
    sa.Column('required_capabilities', sa.JSON(), nullable=False),
    sa.Column('risk_level', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=32), server_default='ACCEPTED', nullable=False),
    sa.Column('priority', sa.Integer(), server_default='5', nullable=False),
    sa.Column('timeout_seconds', sa.Integer(), server_default='60', nullable=False),
    sa.Column('retry_policy', sa.JSON(), nullable=False),
    sa.Column('expected_output_schema', sa.JSON(), nullable=False),
    sa.Column('approval_reference', sa.String(length=36), sa.ForeignKey('approvals.id'), nullable=True),
    sa.Column('standing_authorization_id', sa.String(length=64), nullable=True),
    sa.Column('idempotency_key', sa.String(length=128), nullable=True),
    sa.Column('business_id', sa.String(length=64), nullable=True),
    sa.Column('refusal_reason', sa.Text(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("adapter_type IN ('filesystem', 'code', 'browser', 'desktop', 'api', 'document', 'data')", name='ck_execution_requests_adapter_type'),
    sa.CheckConstraint('risk_level >= 0 AND risk_level <= 3', name='ck_execution_requests_risk_level'),
    sa.CheckConstraint("status IN ('ACCEPTED', 'VALIDATING', 'AWAITING_APPROVAL', 'QUEUED', 'RUNNING', 'COMPLETED', 'COMPLETED_WITH_WARNINGS', 'FAILED', 'REJECTED', 'CANCELLED', 'TIMED_OUT', 'INTERRUPTED', 'REQUIRES_HUMAN_ACTION', 'REQUIRES_RECONCILIATION')", name='ck_execution_requests_status'),
    sa.CheckConstraint('priority >= 1 AND priority <= 10', name='ck_execution_requests_priority'),
    sa.UniqueConstraint('idempotency_key', name='uq_execution_requests_idempotency_key'),
    sa.PrimaryKeyConstraint('id')
    )
    with portable_alter_table('execution_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_execution_requests_task_id'), ['task_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_execution_requests_agent_id'), ['agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_execution_requests_tool_id'), ['tool_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_execution_requests_status'), ['status'], unique=False)

    op.create_table('execution_runs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('execution_request_id', sa.String(length=36), sa.ForeignKey('execution_requests.id'), nullable=False),
    sa.Column('worker_id', sa.String(length=64), server_default='unassigned', nullable=False),
    sa.Column('status', sa.String(length=32), server_default='QUEUED', nullable=False),
    sa.Column('attempt', sa.Integer(), server_default='1', nullable=False),
    sa.Column('executed_action', sa.String(length=128), nullable=True),
    sa.Column('exit_code', sa.Integer(), nullable=True),
    sa.Column('result_summary', sa.Text(), nullable=True),
    sa.Column('error_category', sa.String(length=64), nullable=True),
    sa.Column('verification_status', sa.String(length=32), nullable=True),
    sa.Column('resource_usage', sa.JSON(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('ACCEPTED', 'VALIDATING', 'AWAITING_APPROVAL', 'QUEUED', 'RUNNING', 'COMPLETED', 'COMPLETED_WITH_WARNINGS', 'FAILED', 'REJECTED', 'CANCELLED', 'TIMED_OUT', 'INTERRUPTED', 'REQUIRES_HUMAN_ACTION', 'REQUIRES_RECONCILIATION')", name='ck_execution_runs_status'),
    sa.CheckConstraint('attempt >= 1', name='ck_execution_runs_attempt'),
    sa.PrimaryKeyConstraint('id')
    )
    with portable_alter_table('execution_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_execution_runs_execution_request_id'), ['execution_request_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_execution_runs_status'), ['status'], unique=False)

    op.create_table('execution_evidence',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('execution_run_id', sa.String(length=36), sa.ForeignKey('execution_runs.id'), nullable=False),
    sa.Column('evidence_type', sa.String(length=64), nullable=False),
    sa.Column('evidence_reference', sa.String(length=512), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('verification_status', sa.String(length=32), server_default='unverified', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("verification_status IN ('unverified', 'verified', 'failed')", name='ck_execution_evidence_verification_status'),
    sa.PrimaryKeyConstraint('id')
    )
    with portable_alter_table('execution_evidence', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_execution_evidence_execution_run_id'), ['execution_run_id'], unique=False)

    op.create_table('workflow_runs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('workflow_id', sa.String(length=36), sa.ForeignKey('workflow_definitions.id'), nullable=False),
    sa.Column('workflow_version', sa.Integer(), nullable=False),
    sa.Column('requesting_agent_id', sa.String(length=36), sa.ForeignKey('agents.id'), nullable=False),
    sa.Column('task_id', sa.String(length=36), sa.ForeignKey('tasks.id'), nullable=True),
    sa.Column('status', sa.String(length=32), server_default='QUEUED', nullable=False),
    sa.Column('current_step', sa.String(length=128), nullable=True),
    sa.Column('checkpoint_data', sa.JSON(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('DRAFT', 'VALIDATING', 'APPROVED', 'QUEUED', 'RUNNING', 'PAUSED', 'AWAITING_APPROVAL', 'AWAITING_HUMAN', 'COMPLETED', 'FAILED', 'CANCELLED', 'RECOVERY_REQUIRED')", name='ck_workflow_runs_status'),
    sa.PrimaryKeyConstraint('id')
    )
    with portable_alter_table('workflow_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workflow_runs_workflow_id'), ['workflow_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_runs_requesting_agent_id'), ['requesting_agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_runs_task_id'), ['task_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workflow_runs_status'), ['status'], unique=False)

    op.create_table('workflow_step_runs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('workflow_run_id', sa.String(length=36), sa.ForeignKey('workflow_runs.id'), nullable=False),
    sa.Column('step_id', sa.String(length=128), nullable=False),
    sa.Column('execution_run_id', sa.String(length=36), sa.ForeignKey('execution_runs.id'), nullable=True),
    sa.Column('status', sa.String(length=32), server_default='pending', nullable=False),
    sa.Column('input_reference', sa.String(length=512), nullable=True),
    sa.Column('output_reference', sa.String(length=512), nullable=True),
    sa.Column('error_details', sa.JSON(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('pending', 'queued', 'running', 'completed', 'failed', 'cancelled', 'skipped')", name='ck_workflow_step_runs_status'),
    sa.UniqueConstraint('workflow_run_id', 'step_id', name='uq_workflow_step_runs_run_step'),
    sa.PrimaryKeyConstraint('id')
    )
    with portable_alter_table('workflow_step_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workflow_step_runs_workflow_run_id'), ['workflow_run_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('workflow_step_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_workflow_step_runs_workflow_run_id'))

    op.drop_table('workflow_step_runs')
    with op.batch_alter_table('workflow_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_workflow_runs_workflow_id'))
        batch_op.drop_index(batch_op.f('ix_workflow_runs_requesting_agent_id'))
        batch_op.drop_index(batch_op.f('ix_workflow_runs_task_id'))
        batch_op.drop_index(batch_op.f('ix_workflow_runs_status'))

    op.drop_table('workflow_runs')
    with op.batch_alter_table('execution_evidence', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_execution_evidence_execution_run_id'))

    op.drop_table('execution_evidence')
    with op.batch_alter_table('execution_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_execution_runs_execution_request_id'))
        batch_op.drop_index(batch_op.f('ix_execution_runs_status'))

    op.drop_table('execution_runs')
    with op.batch_alter_table('execution_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_execution_requests_task_id'))
        batch_op.drop_index(batch_op.f('ix_execution_requests_agent_id'))
        batch_op.drop_index(batch_op.f('ix_execution_requests_tool_id'))
        batch_op.drop_index(batch_op.f('ix_execution_requests_status'))

    op.drop_table('execution_requests')
    with op.batch_alter_table('browser_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_browser_sessions_agent_id'))

    op.drop_table('browser_sessions')
    op.drop_table('workflow_definitions')
    with op.batch_alter_table('execution_workspaces', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_execution_workspaces_owner_id'))

    op.drop_table('execution_workspaces')
    with op.batch_alter_table('execution_tools', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_execution_tools_status'))

    op.drop_table('execution_tools')
