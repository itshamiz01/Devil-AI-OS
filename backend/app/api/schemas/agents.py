from __future__ import annotations

from pydantic import BaseModel


class AgentOut(BaseModel):
    id: str
    name: str
    role: str
    parent_agent_id: str | None
    business_ref: str | None
    objective: str | None
    model_profile: str | None
    status: str
    budget: dict | None
    created_at: str
    # P-04 additive fields (factory-managed agents; NULL for P-01 rows).
    agent_type: str | None = None
    description: str | None = None
    template_id: str | None = None
    template_version: int | None = None
    configuration_version: int | None = None
    security_classification: str | None = None
    last_activity_at: str | None = None
    retired_at: str | None = None

    @classmethod
    def from_model(cls, a) -> "AgentOut":
        return cls(id=a.id, name=a.name, role=a.role, parent_agent_id=a.parent_agent_id,
                   business_ref=a.business_ref, objective=a.objective,
                   model_profile=a.model_profile, status=a.status, budget=a.budget,
                   created_at=a.created_at.isoformat() if a.created_at else "",
                   agent_type=getattr(a, "agent_type", None),
                   description=getattr(a, "description", None),
                   template_id=getattr(a, "template_id", None),
                   template_version=getattr(a, "template_version", None),
                   configuration_version=getattr(a, "configuration_version", None),
                   security_classification=getattr(a, "security_classification", None),
                   last_activity_at=a.last_activity_at.isoformat()
                   if getattr(a, "last_activity_at", None) else None,
                   retired_at=a.retired_at.isoformat()
                   if getattr(a, "retired_at", None) else None)
