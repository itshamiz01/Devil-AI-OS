"""SQLAlchemy models for the P-12 Autonomous Operations Engine tables.

One additive migration creates these tables; no P-01..P-11 table is
altered. P-12 is a coordination layer, so its tables hold only
operational state that no earlier phase owns:

* workflows and their task graphs (P-05's ``WorkflowRun`` is a
  tool-step chain inside one execution request — a different level;
  P-01 ``Task`` rows remain the queue substrate a workflow task
  dispatches into),
* trigger definitions (no scheduler existed before P-12 — see
  ``docs/autonomous-operations/P12_PRE_IMPLEMENTATION_AUDIT.md`` §2.1),
* autonomy policy rows (§4 framework — new in P-12),
* operational decision records (§12/§18 audit trail),
* recovery records and the dead-letter store (§13),
* report snapshots (§19 — every live metric is computed, never
  stored; only generated reports are persisted).

Discipline carried from P-07/P-08/P-10:

* **No monetary columns.** A workflow references a P-07 ``budget_id``;
  limits, utilisation and spend decisions live in P-07's tables and
  are read or decided through ``BudgetService`` at runtime. Amounts
  appear only inside decision/evidence JSON payloads as labelled
  P-07-sourced snapshots.
* **No approval store.** Approvals are P-01 ``approvals`` rows;
  ``operations_approval_links`` holds references (approval id +
  parameters hash) only.
* **No ledger, no second scheduler state for tasks**: execution
  happens only through the P-01 TaskManager and P-05
  ExecutionService; substrate references are stored, never substrate
  state copies beyond status mirrors used for display.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON, Boolean, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class AutonomousWorkflow(TimestampMixin, Base):
    """One §5 business workflow: an objective decomposed into a DAG of
    tasks, governed by autonomy policy, P-10 authorization and P-07
    budget checks. The state machine lives in
    ``app.operations.state_machine`` and is enforced by the service —
    this row is never written outside it."""

    __tablename__ = "autonomous_workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str] = mapped_column(
        String(32), nullable=False, default="owner", index=True)
    # origin: owner|intelligence|agent|business|schedule|event|threshold|recovery
    trigger_id: Mapped[str | None] = mapped_column(
        ForeignKey("operations_triggers.id"), nullable=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    priority_class: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    autonomy_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    execution_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Reference only — the authoritative budget is the P-07 row.
    budget_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    deadline: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    success_conditions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failure_conditions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    verification_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="DRAFT", index=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_id: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(300), nullable=True, unique=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    verified_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    learning_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class WorkflowVersion(TimestampMixin, Base):
    """Immutable snapshot of a workflow definition at each version."""

    __tablename__ = "operations_workflow_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("autonomous_workflows.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(232), nullable=False)


class WorkflowTask(TimestampMixin, Base):
    """One §6 task inside a workflow's dependency DAG. ``depends_on``
    holds predecessor step keys (validated acyclic at plan time).
    Monetary need is expressed as ``budget_ref`` ({budget_id,
    category}) — a reference into P-07, never an amount column."""

    __tablename__ = "operations_workflow_tasks"
    __table_args__ = (
        UniqueConstraint("workflow_id", "step_key",
                         name="uq_operations_task_step"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("autonomous_workflows.id"), nullable=False, index=True)
    step_key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="task_handler")
    # kind: task_handler (P-01 queue) | execution (P-05) | internal (P-12 runner)
    action_class: Mapped[str] = mapped_column(
        String(100), nullable=False, default="business.read")
    substrate: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    depends_on: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    assigned_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id"), nullable=True, index=True)
    required_capabilities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    deadline: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    estimated_effort: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    budget_ref: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    permission_requirements: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    input_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    expected_output: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    acceptance_criteria: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    verification_method: Mapped[str] = mapped_column(
        String(64), nullable=False, default="acceptance_criteria")
    retry_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(300), nullable=True, unique=True)
    substrate_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unverified")
    verification_detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)


class WorkflowExecution(TimestampMixin, Base):
    """One drive attempt of a workflow (start / resume / recovery)."""

    __tablename__ = "operations_workflow_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("autonomous_workflows.id"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    trigger_source: Mapped[str] = mapped_column(String(64), nullable=False, default="owner")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="running", index=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class WorkflowCheckpoint(TimestampMixin, Base):
    """Resume point written whenever a workflow's progress settles.
    Holds the set of completed step keys (with their idempotency
    keys) so a resumed workflow skips finished work instead of
    re-executing it (§13 checkpointing)."""

    __tablename__ = "operations_workflow_checkpoints"
    __table_args__ = (
        UniqueConstraint("workflow_id", name="uq_operations_checkpoint_workflow"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("autonomous_workflows.id"), nullable=False, index=True)
    execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    completed_steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class WorkflowEvent(TimestampMixin, Base):
    """Append-only workflow history (§5 execution history). The same
    events are published on the P-01 bus; this table is the durable
    per-workflow trail."""

    __tablename__ = "operations_workflow_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("autonomous_workflows.id"), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(232), nullable=False, default="system")
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class OperationsTrigger(TimestampMixin, Base):
    """One §8 trigger. Time triggers carry a timezone-aware schedule;
    event triggers name a bus event type; threshold triggers carry a
    deterministic predicate over P-07/P-08 read models. Firing is
    deduplicated by (trigger, scheduled instant) in the service."""

    __tablename__ = "operations_triggers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # trigger_type: time|event|threshold|owner|agent
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    workflow_template: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    schedule: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    event_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    threshold: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", index=True)
    next_fire_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True)
    last_fire_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    last_fire_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fire_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_id: Mapped[str] = mapped_column(String(200), nullable=False)


class OperationsAssignment(TimestampMixin, Base):
    """A P-12 task→agent assignment decision (§7), with the recorded
    selection reason and evidence. P-04's own business assignments
    are a different record and are not duplicated here."""

    __tablename__ = "operations_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("autonomous_workflows.id"), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("operations_workflow_tasks.id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id"), nullable=False, index=True)
    previous_agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selection_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    selection_evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="assigned", index=True)
    handoff: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class OperationsApprovalLink(TimestampMixin, Base):
    """Reference-only link from a workflow/task to a P-01 approval
    (the single approval store). Holds the parameters hash the
    approval was bound to so drift is detectable at a glance;
    verification always re-reads the P-01 row."""

    __tablename__ = "operations_approval_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("autonomous_workflows.id"), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    approval_id: Mapped[str] = mapped_column(
        ForeignKey("approvals.id"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="task_step")
    # purpose: workflow_start|task_step|spend
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    parameters_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True)


class OperationsRecoveryRecord(TimestampMixin, Base):
    """One §13 recovery action taken for a workflow/task."""

    __tablename__ = "operations_recovery_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("autonomous_workflows.id"), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    failure_category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    # action: retry|reassign|resume|compensate|dead_letter|escalate|pause
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class OperationsDeadLetter(TimestampMixin, Base):
    """Permanently failed / unprocessable workflow tasks (§13
    dead-letter queue), kept with full context for investigation."""

    __tablename__ = "operations_dead_letter"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("autonomous_workflows.id"), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("operations_workflow_tasks.id"), nullable=False, index=True)
    failure_category: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="open", index=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)


class OperationsAutonomyPolicy(TimestampMixin, Base):
    """One §4 autonomy policy row. Scopes: global, business, agent
    (an agent's ceiling everywhere), agent_business (an agent's
    ceiling inside one business — the row that makes "Level 3 in
    Business A" meaningless in Business B), workflow. Written by the
    owner only; read by the autonomy resolver."""

    __tablename__ = "operations_autonomy_policies"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_ref", "agent_ref",
                         name="uq_operations_autonomy_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scope_ref: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    agent_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    action_caps: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    set_by: Mapped[str] = mapped_column(String(232), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class OperationsDecision(TimestampMixin, Base):
    """One §12/§18 operational decision with its evidence, policy
    checks and authorization result — the decision audit trail."""

    __tablename__ = "operations_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_id: Mapped[str | None] = mapped_column(
        ForeignKey("autonomous_workflows.id"), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    business_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # category: EXECUTE|EXECUTE_WITH_LIMITS|REQUEST_APPROVAL|DEFER|
    #           RESEARCH_MORE|PAUSE|ESCALATE|REJECT
    subject: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    policy_checks: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    authorization_result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decided_by: Mapped[str] = mapped_column(String(232), nullable=False)


class OperationsReport(TimestampMixin, Base):
    """A generated §19 operational report snapshot. The payload is
    computed from authoritative rows at generation time; the
    snapshot preserves what was reported, labelled with its period
    and sources."""

    __tablename__ = "operations_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # kind: daily|weekly|business|failure|resource|agent
    business_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    period_start: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    period_end: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    generated_by: Mapped[str] = mapped_column(String(232), nullable=False)
