"""SQLAlchemy models for the P-09 Memory and Continuous Learning tables.

One additive migration creates these tables; no P-01..P-08 table is
altered. Approvals reuse the P-01 ``approvals`` table, the audit trail
reuses the append-only P-01 ``audit_events`` table, and owner-governed
settings live in ``system_config`` (key ``memory.settings``) — there is
deliberately no ``memory_approvals``, ``memory_audit`` or
``memory_settings`` table here.

Truth discipline (P-09 locks): a memory record is DATA, never
authority. Nothing in this module writes to P-01 governance tables,
P-06 business tables or the P-07 ledger. Financial content is stored
only as a *reference* to a P-07 record plus a clearly labelled derived
insight (§16.2) — never as a copied ledger figure: accordingly there
is no amount/money column anywhere in this module. Scores are stored
as integer basis points, never binary floats.

History discipline (§3.2/§12): ``memory_records`` rows are versioned
in place only through ``memory_versions`` snapshots, and supersession
creates a NEW record linked to the preserved original. Failed
experiments and their learning records are permanent: repositories
expose no delete for versions, contradictions or learning records,
and record deletion is an owner-governed, receipt-verified operation
(§17/Scenario 15), never a silent row removal.
"""
from __future__ import annotations

from sqlalchemy import (
    JSON, Boolean, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class MemoryRecord(TimestampMixin, Base):
    """One classified, provenance-carrying memory (§5/§6).

    ``layer`` is the §5 memory layer (working / episodic / semantic /
    procedural / preference / organizational); ``category`` is the
    §6.1 category; ``truth_class`` keeps facts, assumptions and
    predictions distinct (§3.1/Constitution §10). ``status`` follows
    §6.3. Content is the CURRENT version's text; every prior version
    is preserved in ``memory_versions``.
    """

    __tablename__ = "memory_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    layer: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False, default="", index=True)
    predicate: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    truth_class: Mapped[str] = mapped_column(
        String(28), nullable=False, default="agent_conclusion")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="UNVERIFIED", index=True)
    confidence: Mapped[str] = mapped_column(
        String(16), nullable=False, default="LOW")
    confidence_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=3000)
    importance_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_ref: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_actor: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    project_ref: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    agent_id: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    task_ref: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    decision_ref: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    access_scope: Mapped[str] = mapped_column(
        String(24), nullable=False, default="BUSINESS_SHARED", index=True)
    sensitivity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="internal")
    retention_policy: Mapped[str] = mapped_column(
        String(24), nullable=False, default="standard")
    freshness_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[str | None] = mapped_column(
        ForeignKey("memory_records.id"), nullable=True)
    superseded_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    verified_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class MemoryVersion(TimestampMixin, Base):
    """Append-only snapshot of a record's prior version (§12.4)."""

    __tablename__ = "memory_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_records.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    changed_by: Mapped[str] = mapped_column(String(120), nullable=False)


class MemoryEntity(TimestampMixin, Base):
    """A node in the §8.3 relationship graph (relational representation,
    deliberately no separate graph database). ``entity_ref`` points at
    the authoritative record elsewhere (business id, agent id, task id,
    decision id…); entities are references, never copies."""

    __tablename__ = "memory_entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_ref: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class MemoryRelationship(TimestampMixin, Base):
    __tablename__ = "memory_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    from_entity_id: Mapped[str] = mapped_column(
        ForeignKey("memory_entities.id"), nullable=False, index=True)
    to_entity_id: Mapped[str] = mapped_column(
        ForeignKey("memory_entities.id"), nullable=False, index=True)
    relation: Mapped[str] = mapped_column(String(80), nullable=False)
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class MemoryEmbedding(TimestampMixin, Base):
    """The local vector store (§8.2): one row per indexed memory, the
    replaceable-adapter backing table. Vectors are JSON float lists
    produced by the deterministic local embedder — there is no numpy
    or ChromaDB in this environment (Stage-1 evidence), so similarity
    is computed in pure Python over these rows. Deletion of a record
    deletes its embedding row, and the deletion receipt verifies it."""

    __tablename__ = "memory_embeddings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_records.id"), nullable=False, unique=True, index=True)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class MemoryIngestionJob(TimestampMixin, Base):
    """One ingestion decision (§7.2): stored, or rejected with the
    reason recorded — duplicates, secrets and low-value candidates
    are visible here, never silently dropped."""

    __tablename__ = "memory_ingestion_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_ref: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    candidate_title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    memory_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class MemoryContradiction(TimestampMixin, Base):
    """A §12 conflict between two preserved records. Neither record is
    edited by detection; resolution is a supersede or an owner review."""

    __tablename__ = "memory_contradictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    memory_a_id: Mapped[str] = mapped_column(
        ForeignKey("memory_records.id"), nullable=False, index=True)
    memory_b_id: Mapped[str] = mapped_column(
        ForeignKey("memory_records.id"), nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(120), nullable=False, default="content")
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="OPEN", index=True)
    resolution: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class MemoryRetrievalLog(TimestampMixin, Base):
    """§18.4/§22 retrieval audit: who searched, what was returned, and
    whether any store was degraded. The query text is stored only as a
    digest plus length — restricted query text is not retained."""

    __tablename__ = "memory_retrieval_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    requester: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    query_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    query_len: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    degraded: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class LearningRecord(TimestampMixin, Base):
    """One §11.3 learning record: expected vs actual, with evidence and
    an enforced confidence ceiling (§11.4 — a single observation, or
    an LLM-generated claim, can never be VERIFIED)."""

    __tablename__ = "learning_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_ref: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    project_ref: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actual_outcome: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    causes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    alternative_explanations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    lesson: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(
        String(16), nullable=False, default="LOW")
    applicability_scope: Mapped[str] = mapped_column(Text, nullable=False, default="")
    limitations: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    observations: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="UNREVIEWED", index=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class AgentHandoff(TimestampMixin, Base):
    """A §14.3 structured handoff package. Append-only: a handoff is a
    historical record of a transfer, never edited after creation."""

    __tablename__ = "agent_handoffs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    from_agent_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    to_agent_id: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    task_ref: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    work_completed: Mapped[str] = mapped_column(Text, nullable=False, default="")
    current_status: Mapped[str] = mapped_column(String(40), nullable=False, default="IN_PROGRESS")
    decisions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    files_modified: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    outstanding: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    known_problems: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    required_permissions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    next_actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class MemoryConsolidation(TimestampMixin, Base):
    """A §13.1 consolidation: a new summary memory plus the preserved
    links to every source record it was built from."""

    __tablename__ = "memory_consolidations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary_memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_records.id"), nullable=False, index=True)
    source_memory_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class OwnerMemoryPreference(TimestampMixin, Base):
    """§17 owner context entries. ``kind`` distinguishes explicit
    owner instruction from inference — an inferred row can never
    override an explicit one, and agent principals cannot write
    ``EXPLICIT_OWNER_INSTRUCTION`` rows at all (enforced in service)."""

    __tablename__ = "owner_memory_preferences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="CONFIRMED_OWNER_PREFERENCE")
    updated_by: Mapped[str] = mapped_column(String(120), nullable=False)


class MemoryReviewTask(TimestampMixin, Base):
    """A §13.4 revalidation task: the record stays readable (flagged),
    the task tracks the review — age alone never deletes knowledge."""

    __tablename__ = "memory_review_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_records.id"), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="OPEN", index=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class MemoryDeletionReceipt(TimestampMixin, Base):
    """Scenario-15 proof: a deletion is reported complete only with
    ``index_sync_verified`` true, checked AFTER the embedding row and
    derived copies were removed (§17/§20/§30 rule 18)."""

    __tablename__ = "memory_deletion_receipts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    memory_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    index_sync_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")


class MemoryExport(TimestampMixin, Base):
    """An §17 owner export event: the exported record ids are kept so
    an export is itself auditable (§18.4)."""

    __tablename__ = "memory_exports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False)
    business_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    record_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
