"""P-09 API schemas (§20, adapted to /api/v1/memory conventions)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryCreateIn(BaseModel):
    layer: str = "semantic"
    category: str = "TECHNICAL_KNOWLEDGE"
    title: str
    content: str
    subject: str = ""
    predicate: str = ""
    truth_class: str = "agent_conclusion"
    confidence: str | None = None
    importance_bps: int = 5000
    source_type: str = "agent_output"
    source_ref: str = ""
    business_id: str | None = None
    project_ref: str = ""
    agent_id: str = ""
    task_ref: str = ""
    decision_ref: str = ""
    evidence_refs: list = Field(default_factory=list)
    access_scope: str = "BUSINESS_SHARED"
    sensitivity: str = "internal"
    retention_policy: str = "standard"
    freshness_days: int | None = None
    expires_at: str | None = None


class MemoryUpdateIn(BaseModel):
    title: str | None = None
    content: str | None = None
    subject: str | None = None
    predicate: str | None = None
    status: str | None = None
    truth_class: str | None = None
    importance_bps: int | None = None
    freshness_days: int | None = None
    access_scope: str | None = None
    sensitivity: str | None = None
    reason: str = ""


class SupersedeIn(BaseModel):
    record: MemoryCreateIn
    reason: str = ""


class VerifyIn(BaseModel):
    evidence_refs: list = Field(default_factory=list)


class IngestIn(BaseModel):
    title: str
    content: str
    category: str | None = None
    layer: str = "semantic"
    subject: str = ""
    predicate: str = ""
    truth_class: str = "agent_conclusion"
    source_type: str = "agent_output"
    source_ref: str = ""
    business_id: str | None = None
    project_ref: str = ""
    agent_id: str = ""
    task_ref: str = ""
    decision_ref: str = ""
    evidence_refs: list = Field(default_factory=list)
    access_scope: str = "BUSINESS_SHARED"
    sensitivity: str = "internal"
    retention_policy: str = "standard"
    freshness_days: int | None = None
    importance_bps: int = 5000


class SearchIn(BaseModel):
    query: str = ""
    categories: list[str] | None = None
    business_id: str | None = None
    project_ref: str | None = None
    agent_id: str | None = None
    since: str | None = None
    until: str | None = None
    include_history: bool = False
    limit: int | None = None


class ContextIn(BaseModel):
    task: str = ""
    business_id: str | None = None
    project_ref: str | None = None
    agent_id: str | None = None
    categories: list[str] | None = None


class LearningIn(BaseModel):
    source_type: str = "task"
    source_ref: str = ""
    business_id: str | None = None
    project_ref: str = ""
    hypothesis: str = ""
    expected_outcome: str = ""
    actual_outcome: str = ""
    metrics: dict = Field(default_factory=dict)
    causes: list = Field(default_factory=list)
    alternative_explanations: list = Field(default_factory=list)
    lesson: str
    confidence: str | None = None
    applicability_scope: str = ""
    limitations: str = ""
    evidence_refs: list = Field(default_factory=list)
    observations: int = 1


class LearningFromIn(BaseModel):
    actual_outcome: str = ""
    lesson: str
    causes: list = Field(default_factory=list)
    alternative_explanations: list = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    evidence_refs: list = Field(default_factory=list)
    applicability_scope: str = ""
    limitations: str = ""
    observations: int = 1
    confidence: str | None = None
    expected_outcome: str | None = None
    hypothesis: str | None = None
    business_id: str | None = None


class EntityIn(BaseModel):
    entity_type: str
    entity_ref: str
    name: str = ""
    business_id: str | None = None


class RelateIn(BaseModel):
    from_entity_id: str
    to_entity_id: str
    relation: str
    business_id: str | None = None


class ConsolidateIn(BaseModel):
    title: str
    memory_ids: list[str]
    business_id: str | None = None


class ResolveContradictionIn(BaseModel):
    resolution: str
    supersede_id: str | None = None


class HandoffIn(BaseModel):
    from_agent_id: str = ""  # set from the path by the route
    to_agent_id: str = ""
    task_ref: str = ""
    business_id: str | None = None
    objective: str
    work_completed: str = ""
    current_status: str = "IN_PROGRESS"
    decisions: list = Field(default_factory=list)
    evidence: list = Field(default_factory=list)
    files_modified: list = Field(default_factory=list)
    outstanding: list = Field(default_factory=list)
    known_problems: list = Field(default_factory=list)
    required_permissions: list = Field(default_factory=list)
    next_actions: list = Field(default_factory=list)


class PreferenceIn(BaseModel):
    value: dict = Field(default_factory=dict)
    kind: str = "CONFIRMED_OWNER_PREFERENCE"


class SettingsUpdateIn(BaseModel):
    working_ttl_hours: int | None = None
    market_freshness_days: int | None = None
    procedure_revalidation_days: int | None = None
    context_max_items: int | None = None
    retrieval_default_limit: int | None = None
    vector_enabled: bool | None = None
    embedding_model: str | None = None
    weights: dict | None = None
