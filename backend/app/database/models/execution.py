"""P-05 Universal Digital Execution Engine entities (additive).

Reuse posture (docs/audits/P05_PRE_IMPLEMENTATION_AUDIT.md §7): approvals
are the P-01 ``approvals`` rows (hash-bound) — there is deliberately NO
``execution_approvals`` table; execution audit is the P-01 ``audit_events``
trail — there is deliberately NO ``execution_audit_events`` table. The ten
tables here are the §19 concepts with no existing home, plus the §17
standing-authorization entity.

Secrecy rule (§19/§30.23): NO column in this module can hold a raw
password, API key, private key, cookie or session token. Credential
*references* (e.g. ``env:AUTONOMUS_X_API_KEY``) are the only credential
material ever stored, and request parameters are schema-validated to
reject secret-looking values before they can reach these tables.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid, utcnow


class ExecutionTool(Base, TimestampMixin):
    """One row of the §7 tool registry. ``actions`` is the governed action
    catalogue: each entry carries its own risk level, required capabilities
    and approval level. A tool may be AVAILABLE only after its adapter
    health check passes at startup."""

    __tablename__ = "execution_tools"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    actions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    input_schema: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_schema: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    required_capabilities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    risk_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # max action risk 0..3
    approval_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    supported_os: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    resource_requirements: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    timeout_default: Mapped[float] = mapped_column(Float, default=60.0, nullable=False)
    retry_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    idempotency_supported: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # registered | validating | available | degraded | disabled | deprecated | removed
    status: Mapped[str] = mapped_column(String(32), default="registered", index=True, nullable=False)
    # healthy | degraded | unavailable | disabled | unknown
    health_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    health_details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    config_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)


class ExecutionWorkspace(Base, TimestampMixin):
    """A managed workspace root (§9.1). Agents may touch files ONLY inside
    a workspace they are authorized for; the path validator resolves every
    operation against these roots."""

    __tablename__ = "execution_workspaces"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    # system | agent | project | business
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # shared | projects | businesses | agent | temporary | quarantine
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    root_path: Mapped[str] = mapped_column(Text, nullable=False)
    permission_scope: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # active | disabled
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)


class ExecutionRequest(Base, TimestampMixin):
    """One governed execution request (§6). The four §6 facts are separate
    columns and are never conflated: ``requested_action`` (what was asked),
    ``approved_action`` (what an approval actually covered, if any),
    ``executed_action`` (what the adapter actually ran), and
    ``verified_outcome`` (what the result validator confirmed)."""

    __tablename__ = "execution_requests"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_execution_request_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True, nullable=False)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), index=True, nullable=True)
    business_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tool_id: Mapped[str] = mapped_column(ForeignKey("execution_tools.id"), index=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action_name: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    input_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    required_capabilities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    requested_scope: Mapped[str | None] = mapped_column(String(500), nullable=True)
    risk_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0..3 (§8)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=60.0, nullable=False)
    retry_policy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    expected_outcome: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"), nullable=True)
    standing_authorization_id: Mapped[str | None] = mapped_column(
        ForeignKey("execution_standing_authorizations.id"), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # §6.1 outcomes: ACCEPTED VALIDATING AWAITING_APPROVAL QUEUED RUNNING
    # COMPLETED COMPLETED_WITH_WARNINGS FAILED REJECTED CANCELLED
    # TIMED_OUT INTERRUPTED REQUIRES_HUMAN_ACTION REQUIRES_RECONCILIATION
    status: Mapped[str] = mapped_column(String(40), default="ACCEPTED", index=True, nullable=False)
    requested_action: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    approved_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    executed_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verified_outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # unverified | verified | failed
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified", nullable=False)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    submitted_by_type: Mapped[str] = mapped_column(String(32), nullable=False)
    submitted_by_id: Mapped[str] = mapped_column(String(200), nullable=False)
    workflow_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("execution_workflow_runs.id"), index=True, nullable=True)
    workflow_step_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionRun(Base):
    """One execution attempt of a request (§19 execution_runs). Retries
    append rows; history is never rewritten."""

    __tablename__ = "execution_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    request_id: Mapped[str] = mapped_column(ForeignKey("execution_requests.id"), index=True, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="RUNNING", nullable=False)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_usage: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ExecutionEvidence(Base):
    """Verifiable evidence captured for a run (§5.1 J): file hashes, fetch
    provenance, exit codes, screenshots-as-references. Content itself is
    referenced, never bulk-copied; hashes make tampering detectable."""

    __tablename__ = "execution_evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("execution_runs.id"), index=True, nullable=False)
    request_id: Mapped[str] = mapped_column(ForeignKey("execution_requests.id"), index=True, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(100), nullable=False)
    reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # unverified | verified | failed
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified", nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class BrowserSession(Base, TimestampMixin):
    """A governed browser session record (§11.2). Holds scope and state
    only — NEVER cookies, tokens or storage state (§11.2/§19)."""

    __tablename__ = "execution_browser_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True, nullable=False)
    browser_type: Mapped[str] = mapped_column(String(50), default="fetch", nullable=False)
    allowed_domains: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    permission_profile: Mapped[str] = mapped_column(String(100), default="read_only", nullable=False)
    # active | paused | requires_human_authentication | closed | expired
    status: Mapped[str] = mapped_column(String(40), default="active", index=True, nullable=False)
    current_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_activity: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowDefinition(Base, TimestampMixin):
    """A workflow definition: validated DATA (§15.1), never code. The
    definition is re-validated on every run; a definition that no longer
    validates (e.g. a tool was disabled) cannot run."""

    __tablename__ = "execution_workflow_definitions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_workflow_definition_name_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    definition: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    required_capabilities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # draft | validated | approved | deprecated
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_by_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(200), nullable=True)


class WorkflowRun(Base, TimestampMixin):
    """A persistent workflow run (§15.3 states). ``checkpoint`` is rewritten
    after every step (§16.1): completed steps, current step, outputs,
    evidence references, recovery status."""

    __tablename__ = "execution_workflow_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    definition_id: Mapped[str] = mapped_column(
        ForeignKey("execution_workflow_definitions.id"), index=True, nullable=False)
    workflow_name: Mapped[str] = mapped_column(String(200), nullable=False)
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False)
    requesting_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True, nullable=False)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    # DRAFT VALIDATING APPROVED QUEUED RUNNING PAUSED AWAITING_APPROVAL
    # AWAITING_HUMAN COMPLETED FAILED CANCELLED RECOVERY_REQUIRED
    status: Mapped[str] = mapped_column(String(40), default="QUEUED", index=True, nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    submitted_by_type: Mapped[str] = mapped_column(String(32), nullable=False)
    submitted_by_id: Mapped[str] = mapped_column(String(200), nullable=False)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowStepRun(Base):
    """One step of a workflow run, linked to the execution request that
    performed it (§19 workflow_step_runs)."""

    __tablename__ = "execution_workflow_step_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    workflow_run_id: Mapped[str] = mapped_column(
        ForeignKey("execution_workflow_runs.id"), index=True, nullable=False)
    step_id: Mapped[str] = mapped_column(String(100), nullable=False)
    execution_request_id: Mapped[str | None] = mapped_column(
        ForeignKey("execution_requests.id"), nullable=True)
    # pending | running | completed | failed | skipped | compensated | awaiting_approval
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    input_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StandingAuthorization(Base, TimestampMixin):
    """Owner-configured, narrowly scoped standing authorization (§17).

    Structural honesty rule: ``max_uses`` and ``expires_at`` are NOT
    NULL — an unlimited standing authorization cannot be expressed in
    this schema, by design."""

    __tablename__ = "execution_standing_authorizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    tool_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    action_name: Mapped[str] = mapped_column(String(100), nullable=False)
    scope_pattern: Mapped[str] = mapped_column(String(500), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    role: Mapped[str | None] = mapped_column(String(200), nullable=True)
    limits: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False)
    uses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # active | revoked | expired | exhausted
    status: Mapped[str] = mapped_column(String(32), default="active", index=True, nullable=False)
    created_by_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
