"""expansion feature 2: universal integration framework

Revision ID: 3f7a1c9e52b4
Revises: 85b7a9805207

Expansion Feature 2 (Universal Integration Framework) adds two new
tables and alters nothing else:

- ``integration_connectors``: the connector registry — identity,
  provider, the declared capability contract (descriptor JSON),
  lifecycle, reported state in the framework's one vocabulary,
  health/sync/error history. ``adapter_key`` names the in-code
  adapter implementing the connector; NULL means no
  implementation exists. ``credential_secret_name`` stores only
  the NAME of a P-10 secrets-registry entry — a metadata
  reference, never a value.
- ``integration_invocations``: the append-only invocation ledger
  (every attempt: success, error, denied, refused, rate-limited,
  duplicate) with its P-10 broker decision reference.

No money column is added anywhere (the framework is plumbing and
moves no money; P-07 is untouched) and no secret value is stored
(P-10 remains the credential authority; values resolve through
its brokered use at invocation time only).

Create Date: 2026-11-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3f7a1c9e52b4'
down_revision: Union[str, None] = '85b7a9805207'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('integration_connectors',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('provider', sa.String(length=200), nullable=False),
    sa.Column('version', sa.String(length=30), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=30), nullable=False),
    sa.Column('descriptor', sa.JSON(), nullable=False),
    sa.Column('adapter_key', sa.String(length=100), nullable=True),
    sa.Column('requires_credential', sa.Boolean(), nullable=False),
    sa.Column('credential_secret_name', sa.String(length=200), nullable=True),
    sa.Column('settings', sa.JSON(), nullable=False),
    sa.Column('lifecycle_status', sa.String(length=24), nullable=False),
    sa.Column('health_state', sa.String(length=40), nullable=False),
    sa.Column('health_detail', sa.Text(), nullable=True),
    sa.Column('last_health_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_invoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('error_count', sa.Integer(), nullable=False),
    sa.Column('registered_by', sa.String(length=232), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('integration_connectors', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_integration_connectors_key'), ['key'], unique=True)
        batch_op.create_index(batch_op.f('ix_integration_connectors_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_integration_connectors_lifecycle_status'), ['lifecycle_status'], unique=False)
        batch_op.create_index(batch_op.f('ix_integration_connectors_health_state'), ['health_state'], unique=False)

    op.create_table('integration_invocations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('connector_key', sa.String(length=100), nullable=False),
    sa.Column('capability', sa.String(length=100), nullable=False),
    sa.Column('principal_type', sa.String(length=32), nullable=False),
    sa.Column('principal_id', sa.String(length=200), nullable=False),
    sa.Column('idempotency_key', sa.String(length=200), nullable=True),
    sa.Column('broker_decision_id', sa.String(length=36), nullable=True),
    sa.Column('outcome', sa.String(length=40), nullable=False),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('error_detail', sa.Text(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('correlation_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('integration_invocations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_integration_invocations_connector_key'), ['connector_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_integration_invocations_principal_type'), ['principal_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_integration_invocations_principal_id'), ['principal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_integration_invocations_idempotency_key'), ['idempotency_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_integration_invocations_outcome'), ['outcome'], unique=False)


def downgrade() -> None:
    op.drop_table('integration_invocations')
    op.drop_table('integration_connectors')
