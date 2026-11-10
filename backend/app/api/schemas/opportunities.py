"""API schemas for the Opportunity Discovery endpoints (P-03)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from ...opportunities.constants import (
    CATEGORIES, COST_CLASSIFICATIONS, DISCOVERY_METHODS, EVIDENCE_CATEGORIES,
    EVIDENCE_CLASSIFICATIONS,
)
from ...opportunities.lifecycle import STATES


class BriefCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1, max_length=4000)
    budget_amount: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", max_length=10)
    geography: str = Field(default="global", max_length=100)
    categories: list[str] = Field(default_factory=list)
    constraints: dict = Field(default_factory=dict)
    mission_id: str | None = None

    @field_validator("categories")
    @classmethod
    def _known_categories(cls, v: list[str]) -> list[str]:
        unknown = [c for c in v if c not in CATEGORIES]
        if unknown:
            raise ValueError(f"unknown business categories: {unknown}")
        return v


class BriefOut(BaseModel):
    id: str
    title: str
    objective: str
    budget_amount: float | None = None
    currency: str
    geography: str
    categories: list
    constraints: dict
    status: str
    mission_id: str | None = None

    @classmethod
    def from_model(cls, b) -> "BriefOut":
        return cls(id=b.id, title=b.title, objective=b.objective,
                   budget_amount=b.budget_amount, currency=b.currency,
                   geography=b.geography, categories=b.categories or [],
                   constraints=b.constraints or {}, status=b.status,
                   mission_id=b.mission_id)


class DiscoverRequest(BaseModel):
    brief_id: str = Field(min_length=1, max_length=64)


class OpportunityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    category: str
    description: str = ""
    target_customer: str = ""
    geography: str = "global"
    problem_statement: str = ""
    proposed_solution: str = ""
    revenue_model: str = ""
    required_capabilities: list[str] = Field(default_factory=list)
    source_keys: list[str] = Field(default_factory=list)
    brief_id: str | None = None
    mission_id: str | None = None

    @field_validator("category")
    @classmethod
    def _known_category(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError(f"unknown business category: {v}")
        return v


class OpportunityOut(BaseModel):
    id: str
    name: str
    slug: str
    description: str
    category: str
    target_customer: str
    geography: str
    problem_statement: str
    proposed_solution: str
    revenue_model: str
    discovery_method: str
    status: str
    validation_level: int
    brief_id: str | None = None
    mission_id: str | None = None
    duplicate_of_id: str | None = None
    capability_fit: dict
    compliance: dict

    @classmethod
    def from_model(cls, o) -> "OpportunityOut":
        return cls(id=o.id, name=o.name, slug=o.slug, description=o.description,
                   category=o.category, target_customer=o.target_customer,
                   geography=o.geography, problem_statement=o.problem_statement,
                   proposed_solution=o.proposed_solution, revenue_model=o.revenue_model,
                   discovery_method=o.discovery_method, status=o.status,
                   validation_level=o.validation_level, brief_id=o.brief_id,
                   mission_id=o.mission_id, duplicate_of_id=o.duplicate_of_id,
                   capability_fit=o.capability_fit or {}, compliance=o.compliance or {})


class TransitionRequest(BaseModel):
    target: str
    reason: str = ""

    @field_validator("target")
    @classmethod
    def _known_state(cls, v: str) -> str:
        if v not in STATES:
            raise ValueError(f"unknown lifecycle state: {v}")
        return v


class ResearchStartRequest(BaseModel):
    source_keys: list[str] | None = None
    objective: str = ""


class ResearchSessionOut(BaseModel):
    id: str
    opportunity_id: str
    objective: str
    stage: str
    status: str
    task_id: str | None = None
    sources_examined: list
    findings_summary: str
    failure_reason: str | None = None

    @classmethod
    def from_model(cls, s) -> "ResearchSessionOut":
        return cls(id=s.id, opportunity_id=s.opportunity_id, objective=s.objective,
                   stage=s.stage, status=s.status, task_id=s.task_id,
                   sources_examined=s.sources_examined or [],
                   findings_summary=s.findings_summary or "",
                   failure_reason=s.failure_reason)


class EvidenceCreate(BaseModel):
    claim: str = Field(min_length=1, max_length=4000)
    category: str = "demand"
    classification: str = "UNVERIFIED"
    evidence_kind: str = "source_claim"
    supporting_content: str = ""
    topic_key: str = ""
    source_id: str | None = None
    source_url: str | None = None
    publication_date: str | None = None
    independence_group: str = ""

    @field_validator("category")
    @classmethod
    def _known_category(cls, v: str) -> str:
        if v not in EVIDENCE_CATEGORIES:
            raise ValueError(f"unknown evidence category: {v}")
        return v

    @field_validator("classification")
    @classmethod
    def _known_classification(cls, v: str) -> str:
        if v not in EVIDENCE_CLASSIFICATIONS:
            raise ValueError(f"unknown evidence classification: {v}")
        return v

    @field_validator("evidence_kind")
    @classmethod
    def _known_kind(cls, v: str) -> str:
        if v not in ("source_claim", "owner_real_world", "owner_payment"):
            raise ValueError(f"unknown evidence kind: {v}")
        return v


class EvidenceOut(BaseModel):
    id: str
    opportunity_id: str
    source_id: str | None = None
    claim: str
    supporting_content: str
    category: str
    classification: str
    evidence_kind: str
    topic_key: str
    independence_group: str
    source_url: str | None = None
    retrieval_timestamp: str | None = None
    publication_date: str | None = None
    extraction_method: str
    freshness_status: str
    recorded_by: str

    @classmethod
    def from_model(cls, e) -> "EvidenceOut":
        return cls(id=e.id, opportunity_id=e.opportunity_id, source_id=e.source_id,
                   claim=e.claim, supporting_content=e.supporting_content,
                   category=e.category, classification=e.classification,
                   evidence_kind=e.evidence_kind, topic_key=e.topic_key,
                   independence_group=e.independence_group, source_url=e.source_url,
                   retrieval_timestamp=e.retrieval_timestamp.isoformat() if e.retrieval_timestamp else None,
                   publication_date=e.publication_date,
                   extraction_method=e.extraction_method,
                   freshness_status=e.freshness_status, recorded_by=e.recorded_by)


class CompetitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    website: str | None = None
    product: str = ""
    competitor_type: str = "direct"
    pricing_claim: str | None = None
    pricing_evidence_id: str | None = None
    features: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    positioning: str = ""


class CompetitorOut(BaseModel):
    id: str
    opportunity_id: str
    name: str
    website: str | None = None
    product: str
    competitor_type: str
    pricing_claim: str | None = None
    pricing_evidence_id: str | None = None
    features: list
    strengths: list
    weaknesses: list
    positioning: str

    @classmethod
    def from_model(cls, c) -> "CompetitorOut":
        return cls(id=c.id, opportunity_id=c.opportunity_id, name=c.name,
                   website=c.website, product=c.product, competitor_type=c.competitor_type,
                   pricing_claim=c.pricing_claim, pricing_evidence_id=c.pricing_evidence_id,
                   features=c.features or [], strengths=c.strengths or [],
                   weaknesses=c.weaknesses or [], positioning=c.positioning)


class CostLine(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    amount: float | None = None
    classification: str = "unknown"
    source_note: str = ""

    @field_validator("classification")
    @classmethod
    def _known_classification(cls, v: str) -> str:
        if v not in COST_CLASSIFICATIONS:
            raise ValueError(f"unknown cost classification: {v}")
        return v


class PriceInput(BaseModel):
    amount: float | None = None
    classification: str = "unknown"
    basis: str = ""

    @field_validator("classification")
    @classmethod
    def _known_classification(cls, v: str) -> str:
        if v not in COST_CLASSIFICATIONS:
            raise ValueError(f"unknown price classification: {v}")
        return v


class ScenarioInput(BaseModel):
    sales_per_month: float = Field(ge=0)
    assumptions: list[str] = Field(default_factory=list)


class CommercialAnalysisRequest(BaseModel):
    startup_costs: list[CostLine] = Field(default_factory=list)
    recurring_costs_monthly: list[CostLine] = Field(default_factory=list)
    variable_costs_per_sale: list[CostLine] = Field(default_factory=list)
    price: PriceInput | None = None
    platform_fee_pct: float = Field(default=0, ge=0, le=100)
    payment_fee_pct: float = Field(default=0, ge=0, le=100)
    scenario_sales: dict[str, ScenarioInput] | None = None
    budget_amount: float | None = Field(default=None, ge=0)
    currency: str | None = None
    proposed_channels: list[str] | None = None


class CommercialAnalysisOut(BaseModel):
    id: str
    opportunity_id: str
    revenue_model: str
    currency: str
    startup_costs: list
    recurring_costs_monthly: list
    variable_costs_per_sale: list
    price_assumption: dict
    scenarios: dict
    break_even: dict
    budget: dict
    distribution: dict

    @classmethod
    def from_model(cls, a) -> "CommercialAnalysisOut":
        return cls(id=a.id, opportunity_id=a.opportunity_id, revenue_model=a.revenue_model,
                   currency=a.currency, startup_costs=a.startup_costs or [],
                   recurring_costs_monthly=a.recurring_costs_monthly or [],
                   variable_costs_per_sale=a.variable_costs_per_sale or [],
                   price_assumption=a.price_assumption or {}, scenarios=a.scenarios or {},
                   break_even=a.break_even or {}, budget=a.budget or {},
                   distribution=a.distribution or {})


class MarketAnalysisOut(BaseModel):
    id: str
    opportunity_id: str
    customer_segment: str
    geographic_market: str
    problem_analysis: dict
    demand_indicators: dict
    market_size: dict
    saturation: dict
    gaps: list

    @classmethod
    def from_model(cls, a) -> "MarketAnalysisOut":
        return cls(id=a.id, opportunity_id=a.opportunity_id,
                   customer_segment=a.customer_segment,
                   geographic_market=a.geographic_market,
                   problem_analysis=a.problem_analysis or {},
                   demand_indicators=a.demand_indicators or {},
                   market_size=a.market_size or {}, saturation=a.saturation or {},
                   gaps=a.gaps or [])


class ScoreOut(BaseModel):
    id: str
    opportunity_id: str
    scoring_version: str
    dimensions: dict
    dimension_reasons: dict
    weights: dict
    weighted_score: float
    evidence_quality: float
    risk_classification: str
    hard_rejection: dict | None = None
    recommendation: str

    @classmethod
    def from_model(cls, s) -> "ScoreOut":
        return cls(id=s.id, opportunity_id=s.opportunity_id,
                   scoring_version=s.scoring_version, dimensions=s.dimensions or {},
                   dimension_reasons=s.dimension_reasons or {}, weights=s.weights or {},
                   weighted_score=s.weighted_score, evidence_quality=s.evidence_quality,
                   risk_classification=s.risk_classification,
                   hard_rejection=s.hard_rejection, recommendation=s.recommendation)


class ValidateRequest(BaseModel):
    claimed_level: int | None = Field(default=None, ge=0, le=5)


class ValidationOut(BaseModel):
    id: str
    opportunity_id: str
    level: int
    criteria_met: list
    criteria_missing: list
    reviewer: str
    decision: str
    notes: str

    @classmethod
    def from_model(cls, v) -> "ValidationOut":
        return cls(id=v.id, opportunity_id=v.opportunity_id, level=v.level,
                   criteria_met=v.criteria_met or [], criteria_missing=v.criteria_missing or [],
                   reviewer=v.reviewer, decision=v.decision, notes=v.notes)


class SourceCreate(BaseModel):
    source_key: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=300)
    url: str | None = None
    source_type: str = "public_website"
    access_method: str = "web_page"
    auth_required: bool = False
    rate_limit: dict = Field(default_factory=dict)
    reliability_classification: str = "unverified_claim"
    usage_restrictions: str = ""
    independence_group: str = ""


class SourceOut(BaseModel):
    id: str
    source_key: str
    name: str
    url: str | None = None
    source_type: str
    access_method: str
    auth_required: bool
    reliability_classification: str
    usage_restrictions: str
    independence_group: str
    origin: str
    enabled: bool

    @classmethod
    def from_model(cls, s) -> "SourceOut":
        return cls(id=s.id, source_key=s.source_key, name=s.name, url=s.url,
                   source_type=s.source_type, access_method=s.access_method,
                   auth_required=s.auth_required,
                   reliability_classification=s.reliability_classification,
                   usage_restrictions=s.usage_restrictions,
                   independence_group=s.independence_group, origin=s.origin,
                   enabled=s.enabled)


class ScoringConfigUpdate(BaseModel):
    weights: dict[str, float]


class RecheckRequest(BaseModel):
    note: str = ""
