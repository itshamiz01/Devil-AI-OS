from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Principal(TimestampMixin, Base):
    __tablename__ = "principals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class OwnerCredential(TimestampMixin, Base):
    __tablename__ = "owner_credentials"
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)


class AuthSession(TimestampMixin, Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 token hash
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SystemConfiguration(TimestampMixin, Base):
    __tablename__ = "system_configurations"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class Agent(TimestampMixin, Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    principal_id: Mapped[str | None] = mapped_column(ForeignKey("principals.id"), unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="registered", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Permission(TimestampMixin, Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(128), primary_key=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class PermissionAssignment(TimestampMixin, Base):
    __tablename__ = "permission_assignments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), nullable=False, index=True)
    permission_code: Mapped[str] = mapped_column(ForeignKey("permissions.code"), nullable=False)
    resource_scope: Mapped[str] = mapped_column(String(256), default="*", nullable=False)
    effect: Mapped[str] = mapped_column(String(8), default="allow", nullable=False)
    __table_args__ = (UniqueConstraint("principal_id", "permission_code", "resource_scope", "effect", name="uq_assignment"),)


class Approval(TimestampMixin, Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requester_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[str] = mapped_column(String(256), nullable=False)
    risk: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    approver_id: Mapped[str | None] = mapped_column(ForeignKey("principals.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    handler: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="CREATED", nullable=False, index=True)
    creator_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), nullable=False)
    assigned_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    progress: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    essential: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskExecution(TimestampMixin, Base):
    __tablename__ = "task_executions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    worker_id: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    principal_id: Mapped[str | None] = mapped_column(ForeignKey("principals.id"))
    resource: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    action: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(36), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SystemEvent(Base):
    __tablename__ = "system_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(36), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# --------------------------------------------------------------------------- #
# P-02 Master Intelligence Engine (see ADR-0015)
#
# These tables extend the P-01 schema; nothing above is altered. Model usage is
# kept separate from any business revenue or expense record, as P-02 section 17
# requires: this is operational accounting, not a financial ledger.
# --------------------------------------------------------------------------- #


class Mission(TimestampMixin, Base):
    __tablename__ = "missions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    original_request: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)
    intended_outcome: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(48), default="general_conversation", nullable=False)
    classification: Mapped[str] = mapped_column(String(48), default="simple_request", nullable=False)
    risk: Mapped[str] = mapped_column(String(16), default="LOW", nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True when a model contributed to the interpretation; keeps model output
    # attributable rather than indistinguishable from owner-stated fact.
    model_interpreted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    financial_limit: Mapped[float | None] = mapped_column(Float)
    financial_limit_currency: Mapped[str | None] = mapped_column(String(8))
    time_constraint: Mapped[str | None] = mapped_column(String(128))
    constraints: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    success_criteria: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    assumptions: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    required_capabilities: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    expected_deliverables: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    missing_information: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    # Present on the pydantic Mission contract, so they must have columns: without
    # them a persist/reload round trip would silently drop owner-stated resources
    # and declared dependencies.
    available_resources: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    dependencies: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)


class MissionHistory(Base):
    """Every mission state transition, with the reason and the actor."""
    __tablename__ = "mission_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False, index=True)
    from_state: Mapped[str | None] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Plan(TimestampMixin, Base):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    strategy: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False, index=True)
    risk: Mapped[str] = mapped_column(String(16), default="LOW", nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revision_reason: Mapped[str | None] = mapped_column(Text)
    supersedes_plan_id: Mapped[str | None] = mapped_column(String(36))
    validation_errors: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    estimated_resource_requirements: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    completion_criteria: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    alternative_strategies: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    __table_args__ = (UniqueConstraint("mission_id", "version", name="uq_plans_mission_version"),)


class PlanStep(TimestampMixin, Base):
    __tablename__ = "plan_steps"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), nullable=False, index=True)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    depends_on: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    capability_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    expected_output: Mapped[str | None] = mapped_column(Text)
    completion_criteria: Mapped[str | None] = mapped_column(Text)
    parallel_group: Mapped[str | None] = mapped_column(String(32))
    estimated_duration_seconds: Mapped[float | None] = mapped_column(Float)
    risk: Mapped[str] = mapped_column(String(16), default="LOW", nullable=False)
    __table_args__ = (UniqueConstraint("plan_id", "step_key", name="uq_plan_steps_plan_key"),)


class IntelligenceDecision(TimestampMixin, Base):
    __tablename__ = "intelligence_decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.id"), index=True)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    evidence_refs: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    assumptions: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    constraints: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    scores: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    selected_option_id: Mapped[str | None] = mapped_column(String(64))
    reasoning_summary: Mapped[str | None] = mapped_column(Text)
    risk: Mapped[str] = mapped_column(String(16), default="LOW", nullable=False)
    uncertainty: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="RECOMMENDATION", nullable=False, index=True)
    refusal_reason: Mapped[str | None] = mapped_column(Text)
    # Set only by an owner authorization recorded through the permission engine.
    authorized_by_principal_id: Mapped[str | None] = mapped_column(String(36))


class EvidenceRecord(TimestampMixin, Base):
    __tablename__ = "evidence_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.id"), index=True)
    source: Mapped[str] = mapped_column(String(256), nullable=False)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    reliability: Mapped[str] = mapped_column(String(32), default="untrusted", nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False, index=True)
    stance: Mapped[str] = mapped_column(String(16), default="neutral", nullable=False)
    trust_domain: Mapped[str] = mapped_column(String(16), default="external", nullable=False)
    # A reference, never the artefact itself: evidence rows must not become a
    # side channel for secrets.
    content_reference: Mapped[str | None] = mapped_column(String(256))


class HypothesisRecord(TimestampMixin, Base):
    __tablename__ = "hypotheses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.id"), index=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_evidence: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    contradicting_evidence: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Always "unvalidated_estimate" in P-02: no calibration process exists, and
    # section 8.3 forbids presenting confidence as objective truth.
    confidence_basis: Mapped[str] = mapped_column(String(32), default="unvalidated_estimate", nullable=False)
    validation_requirement: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="PROPOSED", nullable=False, index=True)


class RegisteredModel(TimestampMixin, Base):
    __tablename__ = "registered_models"
    model_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    local: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    context_window: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    supports_structured_output: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_tool_calling: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_reasoning: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_ram_gb: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cost_per_1k_tokens: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    limitations: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    healthy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    health_detail: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    health_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelUsage(Base):
    """One inference attempt. Operational accounting, not a financial ledger."""
    __tablename__ = "model_usage"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    local: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(String(64), default="unspecified", nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class IntelligenceExecution(TimestampMixin, Base):
    """Reasoning and orchestration operation history."""
    __tablename__ = "intelligence_executions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    operation: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(String(36))
    principal_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(32), default="ok", nullable=False, index=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)


# --------------------------------------------------------------------------- #
# P-03 Opportunity Discovery Engine (§21)
#
# Twelve tables in ten entity groups:
#   G1 opportunity lifecycle   opportunity_candidates, opportunities,
#                              opportunity_history
#   G2 research sources        research_sources
#   G3 research execution      research_sweeps (acquisition refusals included)
#   G4 evidence                source_evidence
#   G5 market analysis         market_analyses
#   G6 competitor intelligence competitor_records
#   G7 commercial feasibility  commercial_analyses
#   G8 risk and compliance     risk_findings
#   G9 scoring and validation  opportunity_scores
#   G10 reporting              opportunity_reports
#
# MONETARY AND DECIMAL VALUES ARE STORED AS TEXT, NOT FLOAT.
# SQLite has no decimal type: a Numeric column degrades to REAL, and a float
# cannot represent 0.1 exactly. Section 13's contribution margin, break-even and
# payback arithmetic is deterministic and hand-verified, so persisting it through
# a float would silently change the numbers between a write and a read. Exact
# decimal text round-trips losslessly and is compared as Decimal on the way out.
# --------------------------------------------------------------------------- #


class OpportunityCandidate(TimestampMixin, Base):
    """A discovered candidate, before it is opened as an opportunity (§7)."""

    __tablename__ = "opportunity_candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    discovery_method: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    derived_from: Mapped[str | None] = mapped_column(String(256))
    target_customer: Mapped[str | None] = mapped_column(Text)
    problem_addressed: Mapped[str | None] = mapped_column(Text)
    proposed_offering: Mapped[str | None] = mapped_column(Text)
    budget_band: Mapped[str | None] = mapped_column(String(32))
    generated_by: Mapped[str] = mapped_column(String(32), default="deterministic_rule", nullable=False)
    duplicate_of: Mapped[str | None] = mapped_column(String(64))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Opportunity(TimestampMixin, Base):
    """The opportunity aggregate root (§17)."""

    __tablename__ = "opportunities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    discovery_method: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="discovered", nullable=False, index=True)
    final_classification: Mapped[str | None] = mapped_column(String(48), index=True)
    # Money and quantities as exact decimal text - see the note above.
    budget_available_capital: Mapped[str | None] = mapped_column(String(32))
    budget_currency: Mapped[str | None] = mapped_column(String(3))
    budget_band: Mapped[str | None] = mapped_column(String(32))
    budget_owner_stated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    attractiveness: Mapped[str | None] = mapped_column(String(32))
    evidence_quality: Mapped[str | None] = mapped_column(String(32))
    evidence_coverage_pct: Mapped[str | None] = mapped_column(String(32))
    validation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    evidence_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    rejection_reasons: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    assumptions: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    owner_notes: Mapped[str | None] = mapped_column(Text)
    # Fields of the Opportunity aggregate that have no analysis table of their own.
    # business_model and distribution are NOT fields of CommercialAssessment, so
    # storing them there would have left them unwritten and silently lost.
    business_model: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    distribution: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    # Assessment-level summaries.  The child rows (competitor_records, risk_findings)
    # are normalised in their own tables, but the verdict, saturation, price range
    # and gaps belong to the assessment as a whole.  A competitor assessment with no
    # competitors and a risk assessment with no findings are real results - "the
    # market is unknown", "nothing was blocked" - not an absence of a result, so
    # storing only the children would have lost exactly the cases that matter most.
    competitor_assessment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    risk_assessment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # Derived from final_classification rather than stored independently: two
    # columns that can disagree about whether to recommend is worse than one.
    recommendable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    principal_id: Mapped[str | None] = mapped_column(ForeignKey("principals.id"), index=True)


class OpportunityHistory(Base):
    """Append-only lifecycle audit trail (§17). Never updated, never deleted."""

    __tablename__ = "opportunity_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    from_state: Mapped[str | None] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(120), default="system", nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)


class ResearchSource(TimestampMixin, Base):
    """A registered research source descriptor (§8).

    Credentials are never stored here.  ``auth_mechanism`` records that
    authentication is required and how; the secret itself stays out of the
    database entirely (§27).
    """

    __tablename__ = "research_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    access_method: Mapped[str] = mapped_column(String(32), nullable=False)
    requires_auth: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auth_mechanism: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer)
    returned_fields: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    refresh_frequency: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    licensing: Mapped[str] = mapped_column(String(400), nullable=False)
    reliability: Mapped[str] = mapped_column(String(32), default="untrusted", nullable=False)
    supported_operations: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="not_configured", nullable=False, index=True)
    endpoint_template: Mapped[str | None] = mapped_column(String(512))
    notes: Mapped[str | None] = mapped_column(Text)


class ResearchSweep(TimestampMixin, Base):
    """One acquisition sweep (§20), including every refusal it produced."""

    __tablename__ = "research_sweeps"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), default="search", nullable=False)
    query: Mapped[str | None] = mapped_column(String(512))
    source_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    responses_obtained: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evidence_extracted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Refusals are stored, not discarded: an absence of evidence is only
    # interpretable when the reason for the absence is recorded.
    refusals: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceEvidenceRecord(TimestampMixin, Base):
    """One observation tied to one source (§9)."""

    __tablename__ = "source_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evidence_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    opportunity_id: Mapped[str | None] = mapped_column(String(64), index=True)
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    classification: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    observed_value: Mapped[str | None] = mapped_column(Text)
    numeric_value: Mapped[str | None] = mapped_column(String(32))
    unit: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(64), index=True)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    publication_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reliability: Mapped[str] = mapped_column(String(32), default="untrusted", nullable=False)
    trust_domain: Mapped[str] = mapped_column(String(16), default="external", nullable=False)
    independence_group: Mapped[str | None] = mapped_column(String(128), index=True)
    supersedes: Mapped[str | None] = mapped_column(String(64))
    contradicts: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    stale_after_days: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)


class MarketAnalysis(TimestampMixin, Base):
    """The §10 market and customer assessment for one opportunity."""

    __tablename__ = "market_analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    demand_evidence_level: Mapped[str] = mapped_column(String(32), nullable=False)
    problem_importance: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    problem_importance_basis: Mapped[str | None] = mapped_column(Text)
    customer_description: Mapped[str | None] = mapped_column(Text)
    # TAM/SAM/SOM stored as a whole structure: each level carries its own value,
    # provenance, basis and citations, and most deployments will have none of them.
    sizing: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    signals: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    willingness_indicators: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    data_gaps: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    reasons: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)


class CompetitorRecord(TimestampMixin, Base):
    """One observed competitor (§11)."""

    __tablename__ = "competitor_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    competitor_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048))
    offering: Mapped[str | None] = mapped_column(Text)
    positioning: Mapped[str | None] = mapped_column(Text)
    price_points: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    price_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    pricing_provenance: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    rating: Mapped[str | None] = mapped_column(String(32))
    review_count: Mapped[int | None] = mapped_column(Integer)
    rating_provenance: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    strengths: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    weaknesses: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    complaint_themes: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    identified_gaps: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    evidence_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Distinguishes a competitor actually inspected from one merely named.
    inspected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CommercialAnalysis(TimestampMixin, Base):
    """The §13 commercial feasibility result."""

    __tablename__ = "commercial_analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    viable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    affordable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    costs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    scenarios: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    break_even: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    budget_compatibility: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    unpriced_cost_items: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    # Recorded explicitly so an audit can confirm the ceiling was never raised.
    budget_was_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reasons: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    assumptions: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)


class RiskFindingRecord(TimestampMixin, Base):
    """One legal / platform / ethical finding (§15)."""

    __tablename__ = "risk_findings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    finding_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String(64))
    platform: Mapped[str | None] = mapped_column(String(120))
    mitigation: Mapped[str | None] = mapped_column(Text)
    evidence_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    blocks_recommendation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    risk_verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    prohibited_category_matched: Mapped[str | None] = mapped_column(Text)
    # Assessment-level fields, denormalised onto each finding row so the whole
    # RiskAssessment can be rebuilt. They are identical across the findings of one
    # opportunity, which is cheaper than a twelfth table and loses nothing.
    highest_severity: Mapped[str | None] = mapped_column(String(16))
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    jurisdictions_considered: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    data_gaps: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    reasons: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)


class OpportunityScoreRecord(TimestampMixin, Base):
    """The §16 scoring result and the §18 validation assessment."""

    __tablename__ = "opportunity_scores"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dimensions: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    weights_sum: Mapped[str] = mapped_column(String(32), nullable=False)
    attractiveness: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    evidence_quality: Mapped[str] = mapped_column(String(32), nullable=False)
    scorable_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unscored_dimensions: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    coverage_pct: Mapped[str] = mapped_column(String(32), nullable=False)
    ranking_key: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    # Recorded so two rankings can be compared only if they used the same weights.
    weights_fingerprint: Mapped[str] = mapped_column(String(32), nullable=False)
    hard_rejections: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    rejected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    recommendable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    final_classification: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    validation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    validation_satisfied: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    validation_rejected: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    validation_blocking: Mapped[str | None] = mapped_column(Text)
    validation_next_level: Mapped[int | None] = mapped_column(Integer)
    validation_next_requirement: Mapped[str | None] = mapped_column(Text)
    reasons: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)


class OpportunityReportRecord(TimestampMixin, Base):
    """The §23 generated report."""

    __tablename__ = "opportunity_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    final_classification: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    sections: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    headline_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_index: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    refusals: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    assumptions: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    # Mandatory, and defaults to True: a report built from fixtures must announce
    # itself rather than being mistaken for acquired market research.
    score_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    validation_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_test_data: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    test_data_notice: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
