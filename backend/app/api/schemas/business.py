"""Request schemas for the P-06 business creation API (§25)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class BusinessSettingsIn(BaseModel):
    values: dict = Field(default_factory=dict)


class TemplateVersionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    definition: dict


class CreationApprovalRequestIn(BaseModel):
    opportunity_id: str
    template_name: str
    reason: str | None = None


class EligibilityIn(BaseModel):
    opportunity_id: str
    template_name: str | None = None
    approval_id: str | None = None


class BusinessCreateIn(BaseModel):
    opportunity_id: str
    template_name: str
    approval_id: str | None = None


class TransitionIn(BaseModel):
    target: str = Field(min_length=1, max_length=40)
    reason: str = ""


class DeclarationIn(BaseModel):
    success_criteria: list[str] = Field(min_length=1)
    budget_cap_amount: float = Field(gt=0)
    budget_currency: str = "USD"
    duration_days: int = Field(gt=0)
    min_test_volume: int = Field(gt=0)


class EvidenceIn(BaseModel):
    evidence_type: str = Field(min_length=1, max_length=60)
    claim_supported: str = Field(min_length=1)
    source: str = ""
    source_type: str = ""
    reliability: str = "medium"
    retrieved_at: str | None = None
    freshness_status: str = "current"
    associated_decision: str = ""
    limitations: str = ""


class AssumptionIn(BaseModel):
    assumption: str = Field(min_length=1)
    category: str = "general"
    basis: str = ""
    status: str = "UNVERIFIED"
    impact_if_wrong: str = ""
    validation_method: str = ""
    owner: str = ""


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    objective: str = ""
    audience: str = ""
    channel: str = ""
    message: str = ""
    assets: list = Field(default_factory=list)
    budget: dict = Field(default_factory=dict)
    schedule: dict = Field(default_factory=dict)
    success_metrics: list = Field(default_factory=list)


class LaunchIn(BaseModel):
    approval_id: str


class WorkspaceProbeIn(BaseModel):
    agent_id: str = Field(min_length=1)
