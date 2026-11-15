"""Agentic Workforce Transformation entities (additive).

Justification (docs/agentic-workforce/WORKFORCE_PRE_IMPLEMENTATION_AUDIT.md
§3): the workforce layer needs exactly four concepts with no existing home.
Everything else reuses existing tables — employees ARE rows in the P-01
``agents`` registry, work orders ARE P-01 ``tasks`` + P-04
``agent_assignments``, permissions ARE the P-04 grant ledger + P-01
permission engine, performance IS P-04 ``agent_metrics``, handoffs ARE
P-09 ``agent_handoffs``.

- ``workforce_departments``: the ten §5 departments.
- ``workforce_profiles``: 1:1 extension of ``agents`` holding the stable
  employee code and the §6 profile. The unique ``employee_code`` is what
  makes seeding idempotent across restarts.
- ``workforce_objectives``: a CEO executive objective, its departmental
  plan and its consolidated report (P-02 plans are model-router plans,
  not organizational plans — no existing home).
- ``workforce_deliverables``: one §10-standard deliverable submission per
  work order version, with the manager's review verdict.
"""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class WorkforceDepartment(Base, TimestampMixin):
    __tablename__ = "workforce_departments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    mission: Mapped[str] = mapped_column(Text, nullable=False)
    manager_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id"), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WorkforceProfile(Base, TimestampMixin):
    """1:1 workforce extension of a P-01 ``agents`` registry row (§6)."""

    __tablename__ = "workforce_profiles"
    __table_args__ = (
        UniqueConstraint("employee_code", name="uq_workforce_employee_code"),
        UniqueConstraint("agent_id", name="uq_workforce_profile_agent"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True, nullable=False)
    employee_code: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # ceo | manager | employee
    level: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("workforce_departments.id"), index=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    job_title: Mapped[str] = mapped_column(String(200), nullable=False)
    role_description: Mapped[str] = mapped_column(Text, nullable=False)
    primary_responsibilities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    secondary_responsibilities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    seniority: Mapped[str] = mapped_column(String(32), default="specialist", nullable=False)
    skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Capability names from the P-04 catalogue ONLY (declaration of the
    # role's tool scope; an actual grant still requires the factory path).
    tool_access: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    memory_scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    system_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    communication_style: Mapped[str] = mapped_column(String(200), nullable=False)
    autonomy_level: Mapped[str] = mapped_column(String(32), nullable=False)
    permission_scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # §6 status set: ACTIVE | AVAILABLE | BUSY | WAITING | BLOCKED |
    # ON_LEAVE | SUSPENDED | DISABLED
    workforce_status: Mapped[str] = mapped_column(
        String(32), default="AVAILABLE", index=True, nullable=False)
    kpi_weights: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class WorkforceObjective(Base, TimestampMixin):
    """A CEO executive objective + its plan + consolidated report (§4/§8)."""

    __tablename__ = "workforce_objectives"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by_type: Mapped[str] = mapped_column(String(32), nullable=False)
    submitted_by_id: Mapped[str] = mapped_column(String(200), nullable=False)
    ceo_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False)
    # submitted | plan_ready | dispatched | in_progress | completed | blocked
    status: Mapped[str] = mapped_column(String(32), default="submitted", index=True, nullable=False)
    # [{department_code, manager_code, goal, requires_approval, rationale}]
    plan: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    restricted_actions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    consolidated_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class WorkforceDeliverable(Base, TimestampMixin):
    """One §10-standard deliverable submission for a work order."""

    __tablename__ = "workforce_deliverables"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    assignment_id: Mapped[str] = mapped_column(
        ForeignKey("agent_assignments.id"), index=True, nullable=False)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    employee_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # §10 output standard fields
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    work_performed: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    limitations: Mapped[str] = mapped_column(Text, default="", nullable=False)
    outstanding_issues: Mapped[str] = mapped_column(Text, default="", nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(32), default="self_reported", nullable=False)
    # submitted | accepted | rework_requested
    review_status: Mapped[str] = mapped_column(
        String(32), default="submitted", index=True, nullable=False)
    reviewed_by_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id"), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(nullable=True)
    on_time: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
