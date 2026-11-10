"""API schemas for the Master Intelligence endpoints (P-02)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MissionCreate(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class MissionOut(BaseModel):
    id: str
    text: str
    creator_type: str
    creator_id: str
    status: str
    mode: str
    matched_template: str | None = None
    correlation_id: str | None = None

    @classmethod
    def from_model(cls, m) -> "MissionOut":
        return cls(id=m.id, text=m.text, creator_type=m.creator_type,
                   creator_id=m.creator_id, status=m.status, mode=m.mode,
                   matched_template=m.matched_template,
                   correlation_id=m.correlation_id)


class PlanStepOut(BaseModel):
    id: str
    order: int
    name: str
    tool_name: str
    payload: dict
    expectation: dict
    task_class: str
    status: str
    task_id: str | None = None
    verification_status: str
    verification_detail: str | None = None

    @classmethod
    def from_model(cls, s) -> "PlanStepOut":
        return cls(id=s.id, order=s.order_index, name=s.name, tool_name=s.tool_name,
                   payload=s.payload, expectation=s.expectation,
                   task_class=s.task_class, status=s.status, task_id=s.task_id,
                   verification_status=s.verification_status,
                   verification_detail=s.verification_detail)


class PlanOut(BaseModel):
    id: str
    mission_id: str
    version: int
    planner: str
    model_profile: str | None = None
    status: str
    plan_hash: str | None = None
    approval_id: str | None = None
    rationale: str | None = None
    steps: list[PlanStepOut] = Field(default_factory=list)

    @classmethod
    def from_model(cls, p) -> "PlanOut":
        return cls(id=p.id, mission_id=p.mission_id, version=p.version,
                   planner=p.planner, model_profile=p.model_profile, status=p.status,
                   plan_hash=p.plan_hash, approval_id=p.approval_id,
                   rationale=p.rationale,
                   steps=[PlanStepOut.from_model(s)
                          for s in sorted(p.steps, key=lambda s: s.order_index)])


class DecisionOut(BaseModel):
    id: str
    mission_id: str | None = None
    plan_id: str | None = None
    step_id: str | None = None
    decision_type: str
    actor: str
    reason: str
    evidence: dict = Field(default_factory=dict)
    correlation_id: str | None = None

    @classmethod
    def from_model(cls, d) -> "DecisionOut":
        return cls(id=d.id, mission_id=d.mission_id, plan_id=d.plan_id,
                   step_id=d.step_id, decision_type=d.decision_type, actor=d.actor,
                   reason=d.reason, evidence=d.evidence or {},
                   correlation_id=d.correlation_id)


class ModelProfileOut(BaseModel):
    name: str
    task_classes: list
    provider: str
    model_id: str
    enabled: bool
    limits: dict

    @classmethod
    def from_model(cls, p) -> "ModelProfileOut":
        return cls(name=p.name, task_classes=p.task_classes or [], provider=p.provider,
                   model_id=p.model_id, enabled=p.enabled, limits=p.limits or {})


class ModelProfileUpsert(BaseModel):
    task_classes: list[str] | None = None
    provider: str | None = None
    model_id: str | None = None
    enabled: bool | None = None
    limits: dict | None = None
