"""P-04 Stage 6: the assignment ledger's status vocabulary, and the work a decision is about

Revision ID: d577d056a63b
Revises: e8b2ced758fc
Create Date: 2026-11-05

Stage 2 created ``agent_assignments`` with a free-text ``status`` and a
Python-side default of ``assigned``. Nothing wrote to the table until Stage 6, so
in practice it is empty — but "in practice" is not a guarantee about somebody
else's deployment, and a governed ledger needs its vocabulary closed in the
database rather than only in the code that happens to be running.

Two changes:

* ``ck_agent_assignments_status`` over the five-value vocabulary
  (``assigned``, ``in_progress``, ``completed``, ``failed``, ``cancelled``), plus
  the server default the model already declared, so a raw insert that omits the
  column gets a valid value instead of an empty string.
* ``agent_creation_requests.task_id``, a nullable reference to ``tasks.id``.
  ``ASSIGN_EXISTING`` was declared in the decision vocabulary at Stage 4 and never
  emitted, because nothing could name the work an existing agent should be given.
  This column is what makes that decision recordable.

Legacy ``status`` values are normalized **before** the CHECK is added, for the
reason Stage 4 established and Stage 5 repeated: a constraint existing rows
violate does not merely fail, it fails during SQLite's batch rebuild, partway
through non-transactional DDL, which is how a database ends up half-migrated.

An unrecognized status becomes ``cancelled`` rather than ``assigned``. ``assigned``
would tell a scheduler that work is waiting to be handed out, which is a claim
this revision has no evidence for; ``cancelled`` is terminal, so nothing acts on
it. Because that loses information, ``failure_reason`` is filled where it was
empty to say the value was normalized and that the original is not recoverable —
a row that explains itself is better than a row that looks deliberate.

Autogenerate is not used: it renders neither a CHECK addition nor a
``server_default`` change on an existing column (L-56).
"""
from alembic import op
import sqlalchemy as sa

from app.database.migrations.portable import portable_alter_table

revision = 'd577d056a63b'
down_revision = 'e8b2ced758fc'
branch_labels = None
depends_on = None

#: Shared with the CHECK bodies and with ``app.agents.schemas.ASSIGNMENT_STATUSES``.
#: Kept as a literal here because a migration must not import the vocabulary it is
#: in the middle of constraining: if the code changes later, the revision has to
#: keep meaning what it meant when it ran.
_STATUSES = ('assigned', 'in_progress', 'completed', 'failed', 'cancelled',)
_STATUS_LIST = ", ".join("'%s'" % s for s in _STATUSES)
_NOTE = ("status was not in the assignment vocabulary before revision d577d056a63b; "
         "normalized to cancelled on upgrade and the original value is not "
         "recoverable")


def upgrade() -> None:
    # Normalize first, and say so on the row.
    op.execute(
        "UPDATE agent_assignments SET failure_reason = '" + _NOTE + "' "
        "WHERE (failure_reason IS NULL OR failure_reason = '') "
        f"AND (status IS NULL OR status NOT IN ({_STATUS_LIST}))"
    )
    op.execute(
        "UPDATE agent_assignments SET status = 'cancelled' "
        f"WHERE status IS NULL OR status NOT IN ({_STATUS_LIST})"
    )

    with portable_alter_table('agent_assignments', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_agent_assignments_status',
            condition=f"status IN ({_STATUS_LIST})")
        batch_op.alter_column(
            'status', existing_type=sa.String(length=32),
            existing_nullable=False, server_default='assigned')

    with portable_alter_table('agent_creation_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('task_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_agent_creation_requests_task_id', 'tasks', ['task_id'], ['id'])
        batch_op.create_index('ix_agent_creation_requests_task_id', ['task_id'])


def downgrade() -> None:
    """Schema only. The normalization is not undone: the original values are gone,
    and inventing a value to restore would be a worse lie than leaving the
    ``failure_reason`` that says what happened."""
    with portable_alter_table('agent_creation_requests', schema=None) as batch_op:
        batch_op.drop_index('ix_agent_creation_requests_task_id')
        batch_op.drop_constraint('fk_agent_creation_requests_task_id', type_='foreignkey')
        batch_op.drop_column('task_id')

    with portable_alter_table('agent_assignments', schema=None) as batch_op:
        batch_op.drop_constraint('ck_agent_assignments_status', type_='check')
        batch_op.alter_column(
            'status', existing_type=sa.String(length=32),
            existing_nullable=False, server_default=None)
