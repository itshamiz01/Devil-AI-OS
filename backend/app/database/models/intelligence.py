"""P-02 Master Intelligence entities (additive — P-01 tables untouched).

Missions are owner/system intents; plans are TYPED DATA (step lists that
reference registered task handlers by name), never code; decision_records
are the first-class audit trail every CIO decision is explained from;
model_profiles are governance configuration that only the Owner principal
may edit (Article 0).
"""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, new_uuid


class Mission(Base, TimestampMixin):
    __tablename__ = "missions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    creator_type: Mapped[str] = mapped_column(String(32), nullable=False)
    creator_id: Mapped[str] = mapped_column(String(200), nullable=False)
    # received -> planned -> approved -> executing -> completed | failed;
    # planning_failed when no planner could produce a valid plan.
    status: Mapped[str] = mapped_column(String(32), default="received", index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)  # operating mode at intake
    matched_template: Mapped[str | None] = mapped_column(String(100), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    plans: Mapped[list["Plan"]] = relationship(back_populates="mission")


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # planner identity: "rule-engine" or "llm:<provider>:<model_id>"
    planner: Mapped[str] = mapped_column(String(200), nullable=False)
    model_profile: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # draft -> approved -> executing -> completed | failed; rejected when
    # validation refused the proposal (nothing was executed).
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True, nullable=False)
    plan_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    mission: Mapped[Mission] = relationship(back_populates="plans")
    steps: Mapped[list["PlanStep"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="PlanStep.order_index")


class PlanStep(Base):
    __tablename__ = "plan_steps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), index=True, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    tool_name: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    expectation: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    task_class: Mapped[str] = mapped_column(String(100), default="standard", nullable=False)
    essential: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timeout_seconds: Mapped[float] = mapped_column(default=30.0, nullable=False)
    # pending -> submitted -> completed | failed
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    # pending | verified | failed | unverified (first-class honest outcome)
    verification_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    verification_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped[Plan] = relationship(back_populates="steps")


class DecisionRecord(Base, TimestampMixin):
    """One row per CIO decision (plan created/rejected, router choice,
    approval, execution block, verification outcome, injection flag...).
    Explanations are assembled from these rows, never invented."""

    __tablename__ = "decision_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.id"), index=True, nullable=True)
    plan_id: Mapped[str | None] = mapped_column(ForeignKey("plans.id"), index=True, nullable=True)
    step_id: Mapped[str | None] = mapped_column(ForeignKey("plan_steps.id"), nullable=True)
    decision_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)  # rule-engine | llm:<provider>:<model> | owner | system
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ModelProfile(Base, TimestampMixin):
    """Owner/governance-editable ONLY (Article 0). Rows are seeded with
    empty model_id and enabled=False: no default model is invented while
    the owner's hardware is unknown."""

    __tablename__ = "model_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    task_classes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)  # ollama | cloud | fake
    model_id: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    limits: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
