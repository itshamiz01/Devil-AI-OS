"""P-04 Stage 5: capability governance vocabularies

Revision ID: e8b2ced758fc
Revises: d0db25c9da23
Create Date: 2026-11-05

Stage 2 created ``agent_capabilities`` and ``agent_permissions`` with an
``approval_level`` CHECK and nothing else: ``risk_level``, ``access_class`` and
the grant ``status`` were free text, and four columns had Python-side defaults
only. Stage 5 governs those columns, so it closes them:

* named CHECKs over ``risk_level`` (the same four values ``approvals.risk``
  uses), ``access_class`` (read / write / execute) and
  ``agent_permissions.status`` (pending / active / revoked / expired);
* the server defaults the models declare, so a raw insert that omits them gets
  a valid value instead of failing or storing an empty string;
* two new catalog columns — ``requires_scope`` (a conditional capability that
  must be granted with a non-empty scope) and ``prohibited_reason`` (why a
  level-3 capability is refused). The reason is informational: the prohibition
  itself is enforced from the code-level list in ``app/agents/capabilities.py``,
  so editing a row cannot lift it.

**Autogenerate detected only the two added columns.** It renders neither a CHECK
addition nor a ``server_default`` change on an existing column (L-56), so all
seven of those operations were written by hand.

**Legacy values are normalized before the CHECKs are added**, for the reason
Stage 4 established: a constraint existing rows violate does not merely fail, it
fails *during* SQLite's batch rebuild, partway through a non-transactional DDL
sequence, which is how a database ends up half-migrated. Unrecognized values are
mapped to the safest member of each vocabulary — ``medium`` risk, ``read``
access, ``active`` status — rather than dropped, because both tables can already
hold rows in a deployment that ran Stages 2 to 4. The normalization is one-way
and the downgrade does not attempt to undo it.

Both tables are referenced by foreign keys (``agent_permissions`` points at
``agents``, ``agent_capabilities`` and ``approvals``) but neither is referenced
by anything else, so the SQLite batch rebuild has no inbound references to
preserve. It is still verified against a populated database holding grants and
capabilities, and against one holding values the new CHECKs would reject.
"""
from alembic import op
import sqlalchemy as sa

from app.database.migrations.portable import portable_alter_table


revision = 'e8b2ced758fc'
down_revision = 'd0db25c9da23'
branch_labels = None
depends_on = None

_RISK_LEVELS = "'low', 'medium', 'high', 'critical'"
_ACCESS_CLASSES = "'read', 'write', 'execute'"
_GRANT_STATUSES = "'pending', 'active', 'revoked', 'expired'"


def upgrade() -> None:
    # Normalize first: a CHECK that existing rows violate fails mid-rebuild.
    op.execute(
        "UPDATE agent_capabilities SET risk_level = 'medium' "
        f"WHERE risk_level IS NULL OR risk_level NOT IN ({_RISK_LEVELS})"
    )
    op.execute(
        "UPDATE agent_capabilities SET access_class = 'read' "
        f"WHERE access_class IS NULL OR access_class NOT IN ({_ACCESS_CLASSES})"
    )
    op.execute(
        "UPDATE agent_permissions SET status = 'active' "
        f"WHERE status IS NULL OR status NOT IN ({_GRANT_STATUSES})"
    )

    with portable_alter_table('agent_capabilities', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'requires_scope', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column(
            'prohibited_reason', sa.Text(), nullable=False, server_default=''))
        batch_op.create_check_constraint(
            'ck_agent_capabilities_risk_level',
            condition=f"risk_level IN ({_RISK_LEVELS})")
        batch_op.create_check_constraint(
            'ck_agent_capabilities_access_class',
            condition=f"access_class IN ({_ACCESS_CLASSES})")
        batch_op.alter_column(
            'access_class', existing_type=sa.String(length=16),
            existing_nullable=False, server_default='read')
        batch_op.alter_column(
            'description', existing_type=sa.Text(),
            existing_nullable=False, server_default='')
        batch_op.alter_column(
            'enabled', existing_type=sa.Boolean(),
            existing_nullable=False, server_default='1')

    with portable_alter_table('agent_permissions', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_agent_permissions_status',
            condition=f"status IN ({_GRANT_STATUSES})")
        batch_op.alter_column(
            'status', existing_type=sa.String(length=32),
            existing_nullable=False, server_default='active')
        batch_op.alter_column(
            'scope', existing_type=sa.String(length=256),
            existing_nullable=False, server_default='')


def downgrade() -> None:
    # The normalization in upgrade() is deliberately not reversed: the values it
    # replaced were outside every vocabulary this application understands.
    with portable_alter_table('agent_permissions', schema=None) as batch_op:
        batch_op.alter_column(
            'scope', existing_type=sa.String(length=256),
            existing_nullable=False, server_default=None)
        batch_op.alter_column(
            'status', existing_type=sa.String(length=32),
            existing_nullable=False, server_default=None)
        batch_op.drop_constraint('ck_agent_permissions_status', type_='check')

    with portable_alter_table('agent_capabilities', schema=None) as batch_op:
        batch_op.alter_column(
            'enabled', existing_type=sa.Boolean(),
            existing_nullable=False, server_default=None)
        batch_op.alter_column(
            'description', existing_type=sa.Text(),
            existing_nullable=False, server_default=None)
        batch_op.alter_column(
            'access_class', existing_type=sa.String(length=16),
            existing_nullable=False, server_default=None)
        batch_op.drop_constraint('ck_agent_capabilities_access_class', type_='check')
        batch_op.drop_constraint('ck_agent_capabilities_risk_level', type_='check')
        batch_op.drop_column('prohibited_reason')
        batch_op.drop_column('requires_scope')
