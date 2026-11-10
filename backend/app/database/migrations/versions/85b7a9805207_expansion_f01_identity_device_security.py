"""expansion feature 1: identity & device security

Revision ID: 85b7a9805207
Revises: 218ddd92a0aa

Expansion Feature 1 (Identity & Device Security) extends P-10 in
place. It adds two new tables and one additive nullable column —
no existing table is otherwise altered, and no money column is
added anywhere:

- ``security_devices``: the device registry. Device identity is a
  server-issued credential: only the SHA-256 hash of the device
  secret is stored (the P-01 session-token pattern); label /
  platform / device_name are owner-supplied descriptive metadata,
  self-declared, never identity evidence. Trust lifecycle:
  untrusted -> trusted -> revoked (terminal).
- ``security_recovery_codes``: MFA recovery codes, closing the
  standing P-10 limitation "recovery codes NOT IMPLEMENTED".
  Codes are stored ONLY as scrypt hashes (P-01's hash_password);
  single-use; regeneration invalidates earlier unused codes.
- ``app_sessions.device_id``: nullable indexed reference to
  ``security_devices.id`` (plain column, the P-18 cross-module
  reference pattern). NULL = unbound (legacy) session. Sessions
  bound to a device are revoked when the device is untrusted,
  revoked or rotated, and refused at resolution while the device
  is not trusted.

P-01 remains the identity/session authority and P-10 the security
authority; this migration creates no second auth, session,
permission or audit store (all device/recovery events are written
to the existing ``audit_events`` table).

Create Date: 2026-11-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '85b7a9805207'
down_revision: Union[str, None] = '218ddd92a0aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('security_devices',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('principal_type', sa.String(length=32), nullable=False),
    sa.Column('principal_id', sa.String(length=200), nullable=False),
    sa.Column('label', sa.String(length=200), nullable=False),
    sa.Column('platform', sa.String(length=100), nullable=True),
    sa.Column('device_name', sa.String(length=200), nullable=True),
    sa.Column('secret_hash', sa.String(length=64), nullable=False),
    sa.Column('trust_status', sa.String(length=24), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_by', sa.String(length=232), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('security_devices', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_security_devices_principal_type'), ['principal_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_devices_principal_id'), ['principal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_devices_trust_status'), ['trust_status'], unique=False)

    op.create_table('security_recovery_codes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('principal_type', sa.String(length=32), nullable=False),
    sa.Column('principal_id', sa.String(length=200), nullable=False),
    sa.Column('batch_id', sa.String(length=36), nullable=False),
    sa.Column('code_hash', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('security_recovery_codes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_security_recovery_codes_principal_type'), ['principal_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_recovery_codes_principal_id'), ['principal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_recovery_codes_batch_id'), ['batch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_recovery_codes_status'), ['status'], unique=False)

    with op.batch_alter_table('app_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('device_id', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_app_sessions_device_id'), ['device_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('app_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_app_sessions_device_id'))
        batch_op.drop_column('device_id')

    op.drop_table('security_recovery_codes')
    op.drop_table('security_devices')
