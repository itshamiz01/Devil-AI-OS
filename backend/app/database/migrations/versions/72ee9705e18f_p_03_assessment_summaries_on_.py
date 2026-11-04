"""P-03 assessment summaries on opportunities

Revision ID: 72ee9705e18f
Revises: 5953caf8f23e
Create Date: 2026-11-03 21:02:24.415590

Adds the two assessment-level summary columns that let a competitor assessment with
no competitors and a risk assessment with no findings survive a round trip.  Those
are real results - "the market is unknown", "nothing was blocked" - not an absence
of a result, and storing only the normalised child rows would have lost them.

A SERVER DEFAULT IS REQUIRED HERE, AND AUTOGENERATE DID NOT EMIT ONE.  The columns
are NOT NULL, and the model's ``default=dict`` is a Python-side default that never
reaches the DDL.  SQLite therefore refuses the statement outright:

    OperationalError: Cannot add a NOT NULL column with default value NULL
    [SQL: ALTER TABLE opportunities ADD COLUMN competitor_assessment JSON NOT NULL]

An upgrade/downgrade round trip over an EMPTY database passes regardless, because
there is no row for the constraint to apply to - so this was found by running the
migration against a database that already held an opportunity row, which is the
state any real deployment would be in.  ``server_default`` is set to the JSON text
``{}`` so existing rows receive a valid empty summary rather than failing.
"""
from alembic import op
import sqlalchemy as sa

# The migrations directory is not importable by name under every runner,
# so the shared helper is loaded by explicit path.
import pathlib as _pathlib
import sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent.parent))
from portable import portable_alter_table  # noqa: E402


revision = '72ee9705e18f'
down_revision = '5953caf8f23e'
branch_labels = None
depends_on = None

# SQLite stores JSON as TEXT, so the server default is the literal text '{}'.
EMPTY_JSON = sa.text("'{}'")


def upgrade() -> None:
    with portable_alter_table('opportunities') as batch_op:
        batch_op.add_column(
            sa.Column('competitor_assessment', sa.JSON(), nullable=False, server_default=EMPTY_JSON)
        )
        batch_op.add_column(
            sa.Column('risk_assessment', sa.JSON(), nullable=False, server_default=EMPTY_JSON)
        )


def downgrade() -> None:
    with portable_alter_table('opportunities') as batch_op:
        batch_op.drop_column('risk_assessment')
        batch_op.drop_column('competitor_assessment')
