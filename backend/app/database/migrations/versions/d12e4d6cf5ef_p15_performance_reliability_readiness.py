"""p15 performance reliability and production readiness engine

Revision ID: d12e4d6cf5ef
Revises: 4d41d6a6a605

P-15 adds four tables, all new — no P-01..P-14 table is altered:

- ``performance_samples``: persisted metric samples (before P-15 the
  P-01 monitor produced on-demand snapshots only; nothing was
  recorded, so trends and long-duration stability were unobservable).
- ``reliability_incidents``: the operational incident register
  (P0..P3) for reliability scope. P-10's security register is a
  different scope and is untouched.
- ``readiness_snapshots``: computed Production Readiness Scores
  (§13) with their full evidence.
- ``benchmark_runs``: repeatable benchmark results (§11).

No monetary columns exist in any P-15 table; financial reliability
is a read-model over P-07.

Create Date: 2026-11-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd12e4d6cf5ef'
down_revision: Union[str, None] = '4d41d6a6a605'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'performance_samples',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('sampled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('cpu_percent', sa.Float(), nullable=True),
        sa.Column('memory_percent', sa.Float(), nullable=True),
        sa.Column('disk_percent', sa.Float(), nullable=True),
        sa.Column('queue_depth', sa.Integer(), nullable=True),
        sa.Column('queue_running', sa.Integer(), nullable=True),
        sa.Column('db_latency_ms', sa.Float(), nullable=True),
        sa.Column('database_healthy', sa.Boolean(), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_performance_samples_sampled_at'),
                    'performance_samples', ['sampled_at'], unique=False)
    op.create_index(op.f('ix_performance_samples_source'),
                    'performance_samples', ['source'], unique=False)

    op.create_table(
        'reliability_incidents',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('severity', sa.String(length=4), nullable=False),
        sa.Column('component', sa.String(length=80), nullable=False),
        sa.Column('kind', sa.String(length=80), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('detail', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('response', sa.Text(), nullable=True),
        sa.Column('recovery_actions', sa.JSON(), nullable=False),
        sa.Column('preventive', sa.Text(), nullable=True),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_reliability_incidents_severity'),
                    'reliability_incidents', ['severity'], unique=False)
    op.create_index(op.f('ix_reliability_incidents_component'),
                    'reliability_incidents', ['component'], unique=False)
    op.create_index(op.f('ix_reliability_incidents_kind'),
                    'reliability_incidents', ['kind'], unique=False)
    op.create_index(op.f('ix_reliability_incidents_status'),
                    'reliability_incidents', ['status'], unique=False)

    op.create_table(
        'readiness_snapshots',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('overall_score', sa.Float(), nullable=False),
        sa.Column('band', sa.String(length=60), nullable=False),
        sa.Column('classification', sa.String(length=120), nullable=False),
        sa.Column('critical_gate_ok', sa.Boolean(), nullable=False),
        sa.Column('categories', sa.JSON(), nullable=False),
        sa.Column('failed_checks', sa.JSON(), nullable=False),
        sa.Column('blockers', sa.JSON(), nullable=False),
        sa.Column('recommendations', sa.JSON(), nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_readiness_snapshots_computed_at'),
                    'readiness_snapshots', ['computed_at'], unique=False)

    op.create_table(
        'benchmark_runs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('results', sa.JSON(), nullable=False),
        sa.Column('notes', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_benchmark_runs_started_at'),
                    'benchmark_runs', ['started_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_benchmark_runs_started_at'),
                  table_name='benchmark_runs')
    op.drop_table('benchmark_runs')
    op.drop_index(op.f('ix_readiness_snapshots_computed_at'),
                  table_name='readiness_snapshots')
    op.drop_table('readiness_snapshots')
    op.drop_index(op.f('ix_reliability_incidents_status'),
                  table_name='reliability_incidents')
    op.drop_index(op.f('ix_reliability_incidents_kind'),
                  table_name='reliability_incidents')
    op.drop_index(op.f('ix_reliability_incidents_component'),
                  table_name='reliability_incidents')
    op.drop_index(op.f('ix_reliability_incidents_severity'),
                  table_name='reliability_incidents')
    op.drop_table('reliability_incidents')
    op.drop_index(op.f('ix_performance_samples_source'),
                  table_name='performance_samples')
    op.drop_index(op.f('ix_performance_samples_sampled_at'),
                  table_name='performance_samples')
    op.drop_table('performance_samples')
