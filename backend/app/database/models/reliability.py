"""SQLAlchemy models for the P-15 Performance, Reliability &
Production Readiness Engine tables.

One additive migration creates these tables; no P-01..P-14 table is
altered. P-15 is reliability *infrastructure* over the existing
engines, so its tables hold only state no earlier phase owns:

* ``performance_samples`` — persisted metric samples. Before P-15 the
  P-01 monitor produced on-demand snapshots only; nothing was ever
  recorded, so trends, growth and long-duration stability were
  unobservable. The sampler (and the long-duration harness, §11.5)
  writes here.
* ``reliability_incidents`` — the operational incident register
  (§10): detection → response → recovery → resolution for
  reliability events. P-10's security alerts/incidents are a
  different register (security scope); this one never duplicates
  them — it records reliability scope only (thresholds, breakers,
  dead letters, backups, database, queue).
* ``readiness_snapshots`` — every computed Production Readiness
  Score (§13) with its full evidence, so a classification is always
  reproducible after the fact.
* ``benchmark_runs`` — repeatable benchmark results (§11) with the
  raw timings, replacing P-14's one-off audit script artefact.

Discipline carried from P-07/P-12/P-13:

* **No monetary columns.** Financial reliability is a read-model over
  P-07; nothing financial is stored here.
* **No second scheduler/queue/breaker state.** Samples and incidents
  *observe* the P-01 queue, P-12 breakers and P-10 backups; control
  stays with the owning engines.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid, utcnow


class PerformanceSample(Base, TimestampMixin):
    """One persisted performance sample (§4.1).

    ``metrics`` carries the full measured payload (resources, queue,
    database latency, provider cache state) so new consumers never
    need a schema change; the indexed scalar columns are the ones
    trend/stability queries filter on.
    """

    __tablename__ = "performance_samples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    sampled_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="sampler", index=True)
    # source: sampler|manual|benchmark|test
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    queue_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    queue_running: Mapped[int | None] = mapped_column(Integer, nullable=True)
    db_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    database_healthy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ReliabilityIncident(Base, TimestampMixin):
    """One operational incident (§10). Severity is the prompt's
    P0..P3 scale (stored as ``P0``..``P3`` strings). The lifecycle is
    open → acknowledged → resolved; detection is deduplicated on
    (component, kind) while an incident is open."""

    __tablename__ = "reliability_incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    severity: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    # severity: P0|P1|P2|P3
    component: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", index=True)
    # status: open|acknowledged|resolved
    detected_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False)
    acknowledged_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery_actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    preventive: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ReadinessSnapshot(Base, TimestampMixin):
    """One computed Production Readiness Score (§13) with evidence."""

    __tablename__ = "readiness_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    computed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    band: Mapped[str] = mapped_column(String(60), nullable=False)
    classification: Mapped[str] = mapped_column(String(120), nullable=False)
    critical_gate_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    categories: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failed_checks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    blockers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    recommendations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class BenchmarkRun(Base, TimestampMixin):
    """One benchmark execution (§11): baseline timings, an in-process
    load probe and failure-injection recovery probes, all against
    labelled fixture scope or read paths — never real financial
    transactions."""

    __tablename__ = "benchmark_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="baseline")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    # status: running|completed|failed
    results: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
