"""P-04 Dynamic Agent Factory entities (additive).

Reuse posture (docs/audits/P04_PRE_IMPLEMENTATION_AUDIT.md §5): the agent
REGISTRY is the P-01 ``agents`` table (extended additively in models/core.py);
agent EVENTS are the P-01 ``audit_events``/``system_events`` trail; factory
SETTINGS live in ``system_config``. The nine tables here are the concepts
with no existing home: templates + versions, the capability catalogue, the
per-agent grant ledger, assignments, health snapshots, metrics, config
history and creation-request decision records.

Agents are LOGICAL configurations: a row here plus JSON configuration.
No table in this module represents a process, a model instance or a
session — all inference is shared through the P-02 model router.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid, utcnow


class AgentTemplate(Base, TimestampMixin):
    """A reusable agent template (P-04 §6). The mutable head row points at
    the current DRAFT and current PUBLISHED versions; the actual
    configuration lives in immutable ``agent_template_versions`` rows.
    Agents pin a published version number — publishing a new version never
    rewrites a running agent."""

    __tablename__ = "agent_templates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # draft | published | deprecated (describes the template as a whole)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    published_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(200), nullable=True)


class AgentTemplateVersion(Base):
    """One immutable version of a template's configuration (§6)."""

    __tablename__ = "agent_template_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_template_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    template_id: Mapped[str] = mapped_column(ForeignKey("agent_templates.id"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # unknown | valid | invalid (set by the validation service)
    validation_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_by_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(200), nullable=True)


class AgentCapability(Base, TimestampMixin):
    """Capability catalogue entry (§8.1). A catalogue row is a DECLARATION:
    it says what the capability is, its risk and required approval level,
    and whether any existing module actually backs it (``supported``).
    Unsupported capabilities can be requested for the record but can never
    be granted in this build — the factory does not simulate them."""

    __tablename__ = "agent_capabilities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="low", nullable=False)  # low|medium|high|critical
    approval_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0..3 (§8.3); 3 = prohibited
    scope: Mapped[str | None] = mapped_column(String(300), nullable=True)
    action_class: Mapped[str] = mapped_column(String(32), default="read", nullable=False)  # read|write|execute
    # P-01 Permission name this capability maps to at task/tool-use time, if any.
    mapped_permission: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_requirements: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    expiry_rule: Mapped[str | None] = mapped_column(String(200), nullable=True)
    supported: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AgentPermission(Base, TimestampMixin):
    """Per-agent capability grant LEDGER (§17 agent_permissions).

    The enforcement artefact is a mirrored rule in the P-01 ``permissions``
    table (allow on grant, explicit deny on revoke) so the single
    deny-by-default PermissionEngine governs capability checks. This ledger
    carries what ``permissions`` cannot: approval reference, expiry,
    revocation and grant status."""

    __tablename__ = "agent_permissions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True, nullable=False)
    capability_id: Mapped[str] = mapped_column(ForeignKey("agent_capabilities.id"), index=True, nullable=False)
    scope: Mapped[str | None] = mapped_column(String(300), nullable=True)
    approval_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    approval_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)  # approvals.id when L1/L2
    granted_by_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    granted_by_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    granted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # granted | revoked | expired | denied
    status: Mapped[str] = mapped_column(String(32), default="granted", index=True, nullable=False)


class AgentCreationRequest(Base, TimestampMixin):
    """The deterministic §7.3 creation-decision record. EVERY evaluation —
    including REUSE, QUEUE and REJECT outcomes that create nothing — is a
    row here, so the factory's decisions are fully auditable."""

    __tablename__ = "agent_creation_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    requester_type: Mapped[str] = mapped_column(String(32), nullable=False)
    requester_id: Mapped[str] = mapped_column(String(200), nullable=False)
    requested_role: Mapped[str] = mapped_column(String(200), nullable=False)
    requested_template_id: Mapped[str | None] = mapped_column(ForeignKey("agent_templates.id"), nullable=True)
    business_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_capabilities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    resource_estimate: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    requirement: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # CREATE_AGENT | REUSE_EXISTING_AGENT | ASSIGN_TO_EXISTING_AGENT |
    # QUEUE_FOR_LATER | REQUEST_OWNER_APPROVAL | REJECT_CREATION
    decision: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    decision_reasons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # not_required | pending | approved | rejected
    approval_status: Mapped[str] = mapped_column(String(32), default="not_required", nullable=False)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"), nullable=True)
    created_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    reused_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    proposed_template_id: Mapped[str | None] = mapped_column(ForeignKey("agent_templates.id"), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(300), unique=True, nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentAssignment(Base, TimestampMixin):
    """Factory-level record linking an agent to a REAL P-01 task (§9.1).
    The task engine remains the only executor; this row carries the
    assignment contract: required capabilities, expected output schema,
    quality requirements, delegation chain and the contract verdict."""

    __tablename__ = "agent_assignments"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_assignment_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True, nullable=False)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), index=True, nullable=True)
    business_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    input_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    required_capabilities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    deadline: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    expected_output: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # {required_fields: [...]}
    quality_requirements: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    retry_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parent_assignment_id: Mapped[str | None] = mapped_column(ForeignKey("agent_assignments.id"), nullable=True)
    delegation_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assigned_by_type: Mapped[str] = mapped_column(String(32), nullable=False)
    assigned_by_id: Mapped[str] = mapped_column(String(200), nullable=False)
    # assigned | running | completed | failed | cancelled | rejected | output_invalid
    status: Mapped[str] = mapped_column(String(32), default="assigned", index=True, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_validation: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentHealth(Base):
    """Point-in-time health snapshot (§12.3)."""

    __tablename__ = "agent_health"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True, nullable=False)
    # HEALTHY | WARNING | DEGRADED | UNRESPONSIVE | FAILED
    health_status: Mapped[str] = mapped_column(String(32), nullable=False)
    last_check: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AgentMetric(Base):
    """One metric observation (§12). ``measurement_type`` is mandatory:
    measured | estimated | unavailable — estimates are never presented as
    measurements."""

    __tablename__ = "agent_metrics"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True, nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    measurement_type: Mapped[str] = mapped_column(String(32), default="measured", nullable=False)
    recorded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AgentConfigurationHistory(Base):
    """Immutable per-agent configuration snapshot (§13): every creation and
    every controlled update appends a row; rollback restores an earlier
    snapshot AS a new version — history is never rewritten."""

    __tablename__ = "agent_configuration_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True, nullable=False)
    configuration_version: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    changed_by_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    approval_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
