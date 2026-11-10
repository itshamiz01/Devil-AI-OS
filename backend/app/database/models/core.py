"""P-01 core entities ONLY (per P-01 §6.1). Business/financial entities of
later phases are intentionally absent."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, new_uuid, utcnow


class SystemConfig(Base, TimestampMixin):
    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON-encoded, non-secret or hashed
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Agent(Base, TimestampMixin):
    """Agent REGISTRATION metadata + lifecycle status only (P-01 §12).
    No autonomous creation happens in P-01."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    business_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_profile: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created", index=True, nullable=False)
    budget: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # --- P-04 Dynamic Agent Factory extension (additive; see
    # docs/audits/P04_PRE_IMPLEMENTATION_AUDIT.md §5/§6). Factory-managed
    # agents carry a template pin, a configuration version and a governed
    # §11 lifecycle status; P-01 registration rows leave these NULL.
    agent_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_templates.id"), index=True, nullable=True)
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    configuration_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    security_classification: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_activity_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), default="general", index=True, nullable=False)
    handler_name: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=5, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="created", index=True, nullable=False)
    creator_type: Mapped[str] = mapped_column(String(32), nullable=False)
    creator_id: Mapped[str] = mapped_column(String(200), nullable=False)
    assigned_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    progress: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    essential: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(300), unique=True, nullable=True)
    next_attempt_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    executions: Mapped[list["TaskExecution"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskExecution.attempt_number"
    )


class TaskExecution(Base):
    """One row per execution attempt (attempt history, P-01 §6.1)."""

    __tablename__ = "task_executions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # running/completed/failed/interrupted/cancelled
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    task: Mapped[Task] = relationship(back_populates="executions")


class Permission(Base, TimestampMixin):
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("principal_type", "principal_id", "permission", "resource",
                         name="uq_permission_principal_resource"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    principal_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    principal_id: Mapped[str | None] = mapped_column(String(200), nullable=True)  # NULL = role default
    permission: Mapped[str] = mapped_column(String(100), nullable=False)
    effect: Mapped[str] = mapped_column(String(10), default="allow", nullable=False)  # allow | deny
    resource: Mapped[str | None] = mapped_column(String(300), nullable=True)


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    requesting_principal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    requesting_principal_id: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(300), nullable=True)
    risk_classification: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_permissions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    parameters_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    approver_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decision_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    """Append-only audit record. No update/delete API exists (P-01 §11)."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)  # allow/deny/approved/rejected/...
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SystemEvent(Base):
    """Persisted copy of critical internal events (P-01 §8)."""

    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    severity: Mapped[str] = mapped_column(String(32), default="info", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # P-14 Stage B (DEF-I2): envelope fields persisted with the event.
    business_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(32), default="delivered", nullable=False)


class EventDeadLetter(Base):
    """A failed or dropped event-bus delivery, recorded durably
    (P-14 Stage B, DEF-I4). One row per (event, handler) failure and
    per dropped critical event, so a lost delivery is always
    discoverable after the fact."""

    __tablename__ = "event_dead_letters"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    handler: Mapped[str] = mapped_column(String(300), nullable=False)
    error: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AppSession(Base):
    __tablename__ = "app_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    principal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Expansion Feature 1 (Identity & Device Security): the device
    # this session is bound to, when the login presented a device
    # credential. NULL = unbound (legacy) session. A plain indexed
    # reference to ``security_devices.id`` (the P-18 cross-module
    # reference pattern — no FK, so model import order can never
    # break mapper resolution); the binding is enforced in code,
    # and a session whose device is not currently trusted is
    # refused at resolution.
    device_id: Mapped[str | None] = mapped_column(
        String(36), index=True, nullable=True)
