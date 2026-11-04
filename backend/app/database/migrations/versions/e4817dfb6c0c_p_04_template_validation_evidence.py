"""P-04 Stage 3: template validation evidence and the template status vocabulary

Revision ID: e4817dfb6c0c
Revises: 3013ebdd2699
Create Date: 2026-11-04 07:20:03.491859

Adds the one column Stage 3 needs that Stage 2 did not have, and puts two
vocabularies that were previously implicit under named CHECK constraints:

* ``agent_template_versions.validation_details_json`` - why a version was
  judged valid or invalid, persisted next to the verdict. The configuration
  document itself is never edited: a version row is immutable, so the evidence
  of a refusal lives beside it rather than inside it.
* ``agent_templates.status`` in ('draft', 'published', 'deprecated').
* ``agent_template_versions.validation_status`` in
  ('unvalidated', 'valid', 'invalid').

Both status columns also receive the server defaults their models declare,
which Stage 2's revision did not emit.

**Autogenerate detected only the new column.** It renders neither a CHECK
addition nor a ``server_default`` change on an existing column (recorded as
L-56), so the four constraint/default operations below were written by hand
and are proven two ways: ``tests/test_agents_schema_stage3.py`` inserts
invalid values against a migrated SQLite database, and
``tests/test_migration_portability.py`` renders the whole chain for Postgres.

On SQLite these run through Alembic's batch mode, which rebuilds the table.
``agent_templates`` is referenced by ``agent_template_versions``, ``agents``
and ``agent_creation_requests``, so the rebuild is verified against a database
holding rows in all of those tables, not an empty one.
"""
from alembic import op
import sqlalchemy as sa

from app.database.migrations.portable import portable_alter_table


revision = 'e4817dfb6c0c'
down_revision = '3013ebdd2699'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with portable_alter_table('agent_template_versions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('validation_details_json', sa.JSON(), nullable=True))
        batch_op.alter_column(
            'validation_status',
            existing_type=sa.String(length=32),
            existing_nullable=False,
            server_default='unvalidated',
        )
        batch_op.create_check_constraint(
            'ck_agent_template_versions_validation_status',
            condition="validation_status IN ('unvalidated', 'valid', 'invalid')",
        )
    with portable_alter_table('agent_templates', schema=None) as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=sa.String(length=32),
            existing_nullable=False,
            server_default='draft',
        )
        batch_op.create_check_constraint(
            'ck_agent_templates_status',
            condition="status IN ('draft', 'published', 'deprecated')",
        )


def downgrade() -> None:
    with portable_alter_table('agent_templates', schema=None) as batch_op:
        batch_op.drop_constraint('ck_agent_templates_status', type_='check')
        batch_op.alter_column(
            'status',
            existing_type=sa.String(length=32),
            existing_nullable=False,
            server_default=None,
        )
    with portable_alter_table('agent_template_versions', schema=None) as batch_op:
        batch_op.drop_constraint(
            'ck_agent_template_versions_validation_status', type_='check')
        batch_op.alter_column(
            'validation_status',
            existing_type=sa.String(length=32),
            existing_nullable=False,
            server_default=None,
        )
        batch_op.drop_column('validation_details_json')
