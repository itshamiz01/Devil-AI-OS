"""P-04 Stage 4: creation-request idempotency and the decision vocabularies

Revision ID: d0db25c9da23
Revises: e4817dfb6c0c
Create Date: 2026-11-04 10:00:13.392934

Adds what the creation engine needs from the table Stage 2 created for it:

* ``idempotency_key`` with a **named** unique constraint. A retried creation
  request must not produce a second agent; the second call returns the first
  request's outcome. The constraint is named because an unnamed one
  autogenerates into ``drop_constraint(None, ...)``, which cannot run
  (ADR-0024, and the reason the first generated revision for this change was
  deleted rather than patched).
* ``ck_agent_creation_requests_decision`` over the six decisions the factory may
  return, allowing NULL for a request that has not been decided yet.
* ``ck_agent_creation_requests_approval_status`` over the five approval states,
  plus the ``not_required`` server default the model declares and Stage 2's
  revision did not emit.

**Autogenerate detected only the column and the unique constraint.** It renders
neither a CHECK addition nor a ``server_default`` change on an existing column
(L-56), so those three operations were written by hand. The vocabularies mirror
``CREATION_DECISIONS`` and ``CREATION_APPROVAL_STATUSES`` in
``app/agents/schemas.py``; they are inlined here rather than imported because a
migration is history and must not move when the module does.

**Legacy values are normalized before the CHECKs are added.** Stage 2 created
both columns without a vocabulary constraint, so a database that ran Stages 2-3
may hold values the new CHECKs would reject - an empty string written by a raw
insert, or a status from a caller that has since changed. Adding a constraint
that existing rows violate does not merely fail: on SQLite it fails *during* the
batch rebuild, partway through a non-transactional DDL sequence, which is how a
database ends up half-migrated. So the upgrade first maps every unrecognized
``approval_status`` to ``not_required`` and clears every unrecognized
``decision`` to NULL - the honest value for a request whose recorded decision is
not one this system can produce. This is a one-way normalization and the
downgrade does not attempt to undo it: the previous values were already outside
every vocabulary the application understands.

On SQLite this runs through batch mode, which rebuilds
``agent_creation_requests``. That table references ``agent_templates`` and
``approvals`` but nothing references it, so the rebuild has no inbound foreign
keys to preserve; it is still verified against a populated database holding a
request row with both foreign keys set, and against one holding a row whose
``approval_status`` the new CHECK would otherwise reject.
"""
from alembic import op
import sqlalchemy as sa

from app.database.migrations.portable import portable_alter_table


revision = 'd0db25c9da23'
down_revision = 'e4817dfb6c0c'
branch_labels = None
depends_on = None


_DECISIONS = (
    "'CREATE_AGENT', 'REUSE_EXISTING', 'ASSIGN_EXISTING', 'QUEUE', "
    "'REQUEST_OWNER_APPROVAL', 'REJECT'"
)
_APPROVAL_STATUSES = "'not_required', 'pending', 'granted', 'rejected', 'expired'"


def upgrade() -> None:
    # Normalize first: a CHECK that existing rows violate fails mid-rebuild.
    op.execute(
        "UPDATE agent_creation_requests SET decision = NULL "
        f"WHERE decision IS NOT NULL AND decision NOT IN ({_DECISIONS})"
    )
    op.execute(
        "UPDATE agent_creation_requests SET approval_status = 'not_required' "
        f"WHERE approval_status IS NULL OR approval_status NOT IN ({_APPROVAL_STATUSES})"
    )
    with portable_alter_table('agent_creation_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('idempotency_key', sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint(
            'uq_agent_creation_requests_idempotency_key', ['idempotency_key'])
        batch_op.alter_column(
            'approval_status',
            existing_type=sa.String(length=32),
            existing_nullable=False,
            server_default='not_required',
        )
        batch_op.create_check_constraint(
            'ck_agent_creation_requests_decision',
            condition=f"decision IS NULL OR decision IN ({_DECISIONS})",
        )
        batch_op.create_check_constraint(
            'ck_agent_creation_requests_approval_status',
            condition=f"approval_status IN ({_APPROVAL_STATUSES})",
        )


def downgrade() -> None:
    # The normalization in upgrade() is deliberately not reversed: the values it
    # replaced were outside every vocabulary this application understands, so
    # there is nothing faithful to restore them to.
    with portable_alter_table('agent_creation_requests', schema=None) as batch_op:
        batch_op.drop_constraint(
            'ck_agent_creation_requests_approval_status', type_='check')
        batch_op.drop_constraint('ck_agent_creation_requests_decision', type_='check')
        batch_op.alter_column(
            'approval_status',
            existing_type=sa.String(length=32),
            existing_nullable=False,
            server_default=None,
        )
        batch_op.drop_constraint(
            'uq_agent_creation_requests_idempotency_key', type_='unique')
        batch_op.drop_column('idempotency_key')
