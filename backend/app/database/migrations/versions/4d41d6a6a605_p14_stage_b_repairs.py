"""p14 stage b integration and data repairs

Revision ID: 4d41d6a6a605
Revises: d02b4208d228

P-14 Stage B controlled repairs (additive only; no column is
dropped, renamed or re-typed):

- DEF-I2: ``system_events`` gains the persisted envelope fields
  ``business_id``, ``workflow_id`` and ``processing_status``.
- DEF-I4: new ``event_dead_letters`` table records failed/dropped
  event-bus deliveries durably.
- DEF-D1: ``research_briefs.budget_minor`` and
  ``business_declarations.budget_cap_minor`` add integer minor-unit
  money columns alongside the deprecated Float columns; existing
  rows are backfilled with round(amount * 100). The Float columns
  stay (deprecated) — readers prefer the ``*_minor`` values.
- DEF-D3: canonical foreign keys on the width-matching subset —
  ``journal_entries.counterpart_business_id`` → ``businesses.id``
  (String(36) both sides), ``journal_entries.approval_id``,
  ``expense_records.approval_id`` and
  ``spending_requests.approval_id`` → ``approvals.id`` (String(64)
  both sides). The remaining FK-less references are documented
  intentional soft references (polymorphic principals, correlation
  and external IDs) in the P-14 data architecture report.

Create Date: 2026-11-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4d41d6a6a605'
down_revision: Union[str, None] = 'd02b4208d228'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # DEF-I4: durable dead-letter table for failed event deliveries.
    op.create_table(
        'event_dead_letters',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('handler', sa.String(length=300), nullable=False),
        sa.Column('error', sa.Text(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_event_dead_letters_event_id'),
                    'event_dead_letters', ['event_id'], unique=False)
    op.create_index(op.f('ix_event_dead_letters_event_type'),
                    'event_dead_letters', ['event_type'], unique=False)

    # DEF-I2: persisted event envelope fields.
    with op.batch_alter_table('system_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('business_id', sa.String(length=64),
                                      nullable=True))
        batch_op.add_column(sa.Column('workflow_id', sa.String(length=64),
                                      nullable=True))
        batch_op.add_column(sa.Column('processing_status', sa.String(length=32),
                                      server_default='delivered',
                                      nullable=False))
        batch_op.create_index(op.f('ix_system_events_business_id'),
                              ['business_id'], unique=False)

    # DEF-D1: integer minor-unit money columns + backfill.
    with op.batch_alter_table('research_briefs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('budget_minor', sa.BigInteger(),
                                      nullable=True))
    op.execute(
        'UPDATE research_briefs SET budget_minor = '
        'CAST(ROUND(budget_amount * 100) AS BIGINT) '
        'WHERE budget_amount IS NOT NULL')
    with op.batch_alter_table('business_declarations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('budget_cap_minor', sa.BigInteger(),
                                      nullable=True))
    op.execute(
        'UPDATE business_declarations SET budget_cap_minor = '
        'CAST(ROUND(budget_cap_amount * 100) AS BIGINT)')

    # DEF-D3: canonical foreign keys on the width-matching subset.
    with op.batch_alter_table('journal_entries', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_journal_entries_counterpart_business',
            'businesses', ['counterpart_business_id'], ['id'])
        batch_op.create_foreign_key(
            'fk_journal_entries_approval',
            'approvals', ['approval_id'], ['id'])
    with op.batch_alter_table('expense_records', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_expense_records_approval',
            'approvals', ['approval_id'], ['id'])
    with op.batch_alter_table('spending_requests', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_spending_requests_approval',
            'approvals', ['approval_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('spending_requests', schema=None) as batch_op:
        batch_op.drop_constraint('fk_spending_requests_approval',
                                 type_='foreignkey')
    with op.batch_alter_table('expense_records', schema=None) as batch_op:
        batch_op.drop_constraint('fk_expense_records_approval',
                                 type_='foreignkey')
    with op.batch_alter_table('journal_entries', schema=None) as batch_op:
        batch_op.drop_constraint('fk_journal_entries_approval',
                                 type_='foreignkey')
        batch_op.drop_constraint('fk_journal_entries_counterpart_business',
                                 type_='foreignkey')
    with op.batch_alter_table('business_declarations', schema=None) as batch_op:
        batch_op.drop_column('budget_cap_minor')
    with op.batch_alter_table('research_briefs', schema=None) as batch_op:
        batch_op.drop_column('budget_minor')
    with op.batch_alter_table('system_events', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_system_events_business_id'))
        batch_op.drop_column('processing_status')
        batch_op.drop_column('workflow_id')
        batch_op.drop_column('business_id')
    op.drop_index(op.f('ix_event_dead_letters_event_type'),
                  table_name='event_dead_letters')
    op.drop_index(op.f('ix_event_dead_letters_event_id'),
                  table_name='event_dead_letters')
    op.drop_table('event_dead_letters')
