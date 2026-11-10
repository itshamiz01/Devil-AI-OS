"""P-13 API schemas (request bodies). Response shapes are the
service dicts themselves, wrapped in the standard envelope."""
from __future__ import annotations

from pydantic import BaseModel, Field


class PortfolioCreate(BaseModel):
    name: str
    description: str = ""
    mission: str = ""


class SettingsUpdate(BaseModel):
    concentration_threshold_bps: int | None = None
    business_share_cap_bps: int | None = None
    capacities: dict | None = None


class MembershipCreate(BaseModel):
    business_id: str
    strategic_priority: int = 50
    group_labels: list[str] = Field(default_factory=list)
    notes: str = ""


class MembershipUpdate(BaseModel):
    strategic_priority: int | None = None
    group_labels: list[str] | None = None
    notes: str | None = None


class MembershipStatus(BaseModel):
    status: str


class ObjectiveCreate(BaseModel):
    title: str
    description: str = ""
    horizon: str = "90_DAY"
    targets: dict = Field(default_factory=dict)


class RelationshipCreate(BaseModel):
    portfolio_id: str
    source_business_id: str
    target_business_id: str
    relationship_type: str
    sharing_policy: str = "NONE"
    notes: str = ""
    expires_at: str | None = None


class RelationshipTransition(BaseModel):
    status: str


class OpportunitySubmit(BaseModel):
    category: str
    involved_business_ids: list[str]
    title: str = ""
    description: str = ""
    evidence: list[dict] = Field(default_factory=list)
    expected_benefits: list[str] = Field(default_factory=list)
    estimated_costs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    resource_requirements: dict = Field(default_factory=dict)
    confidence: str = "low"


class DecisionBody(BaseModel):
    decision: str
    rationale: str = ""


class ServiceCreate(BaseModel):
    name: str
    kind: str
    description: str = ""
    provider: str = ""
    supported_categories: list[str] = Field(default_factory=list)
    capacity_units: int = 0
    cost_model: dict = Field(default_factory=dict)
    security_classification: str = "internal"
    access_policy: str = "owner_approval"
    sla: str = ""


class ServiceStatusBody(BaseModel):
    status: str


class AccessRequest(BaseModel):
    business_id: str
    scope: dict = Field(default_factory=dict)
    units_reserved: int = 0


class ApproveBody(BaseModel):
    approve: bool = True


class UsageRecord(BaseModel):
    business_id: str
    units: int
    note: str = ""


class AllocationCreate(BaseModel):
    service_id: str
    portfolio_id: str
    method: str
    period_label: str = ""
    currency: str = "INR"
    total_cost_minor: int
    business_ids: list[str]
    allocations: list[dict] = Field(default_factory=list)


class QuotaSet(BaseModel):
    business_id: str
    resource_kind: str
    max_units: int
    priority: int = 50


class ResourcePropose(BaseModel):
    business_id: str
    resource_kind: str
    units: int
    purpose: str = ""
    essential: bool = False
    priority: int = 50


class GrantCreate(BaseModel):
    portfolio_id: str
    grantee_agent_id: str
    business_id: str
    target_business_id: str | None = None
    categories: list[str]
    purpose: str = ""
    rationale: str
    permitted_actions: list[str] = Field(default_factory=lambda: ["read"])
    expires_at: str


class AssignmentCreate(BaseModel):
    portfolio_id: str
    agent_id: str
    scope_type: str
    business_id: str | None = None
    categories: list[str]
    allowed_tools: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    budget_ref: str | None = None
    expires_at: str


class AccessCheck(BaseModel):
    business_id: str
    category: str


class ServiceAccessCheck(BaseModel):
    service_id: str


class WorkflowCreate(BaseModel):
    name: str
    objective: str = ""
    participations: list[dict]


class ParticipationAuthorize(BaseModel):
    business_id: str


class VentureCreate(BaseModel):
    name: str
    category: str
    rationale: str = ""
    evidence: list[dict] = Field(default_factory=list)
    expected_synergy: dict = Field(default_factory=dict)
    estimated_requirements: dict = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)


class ReportGenerate(BaseModel):
    report_type: str = "SNAPSHOT"
    title: str | None = None
    currency: str = "INR"
    business_ids: list[str] | None = None


class SurvivalModeBody(BaseModel):
    enabled: bool
