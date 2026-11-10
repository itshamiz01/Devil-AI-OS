"""Ingestion pipeline (§7): candidate → validate source → classify
→ entity extraction → sensitive-data screen → duplicate detection →
usefulness filter → policy assignment → store or reject, with the
decision recorded either way (§7.2 steps 1–14).

Deterministic extraction (§7.3): no LLM is required anywhere in this
pipeline; classification is keyword/subject based and labelled as
such. The LLM-unavailable scenario (Scenario 10) therefore holds by
construction.
"""
from __future__ import annotations

import re

from ..database.models.memory import MemoryIngestionJob
from ..database.repositories.memory import (
    MemoryIngestionJobRepository, MemoryRecordRepository,
)
from ..permissions.models import Principal
from . import constants as C
from . import policy
from .records import content_hash

FILLER = {
    "ok", "okay", "thanks", "thank you", "got it", "noted", "yes", "no",
    "hello", "hi", "done", "status update", "update", "fyi",
}

KEYWORD_CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("EXPERIMENT_OUTCOME", ("experiment", "a/b test", "trial run")),
    ("DECISION_HISTORY", ("decision", "decided", "approved", "rejected")),
    ("FINANCIAL_INSIGHT", ("revenue", "margin", "cash flow", "payout",
                           "acquisition cost", "cac", "refund")),
    ("MARKET_EVIDENCE", ("market", "demand", "competitor", "trend")),
    ("CUSTOMER_INSIGHT", ("customer", "user feedback", "churn")),
    ("PROCEDURE", ("procedure", "how to", "runbook", "workflow", "deploy")),
    ("LESSON_LEARNED", ("lesson", "learned", "mistake", "root cause")),
    ("SECURITY_EVENT", ("security", "breach", "credential", "injection")),
    ("TECHNICAL_KNOWLEDGE", ("api", "database", "schema", "architecture",
                             "bug", "configuration")),
    ("BUSINESS_KNOWLEDGE", ("business model", "pricing", "offer", "product")),
]


def classify(text: str, hint: str | None = None) -> str:
    if hint and hint in C.CATEGORIES:
        return hint
    lowered = f" {text.lower()} "
    for category, keywords in KEYWORD_CATEGORIES:
        if any(k in lowered for k in keywords):
            return category
    return "TECHNICAL_KNOWLEDGE"


def usefulness(text: str) -> tuple[bool, str]:
    """§7.4 candidate filtering: filler and near-empty content have no
    retrieval value and are rejected with the reason recorded."""
    stripped = " ".join(text.lower().split())
    if len(stripped) < 12:
        return False, "candidate too short to carry retrievable knowledge"
    if stripped.strip(" .!") in FILLER:
        return False, "trivial conversational filler (§7.4)"
    return True, ""


_ENTITY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)\b")


def extract_entities(text: str) -> list[str]:
    """Deterministic, deliberately conservative entity extraction:
    capitalised multi-word names only. Labelled as heuristic."""
    return sorted(set(_ENTITY_RE.findall(text or "")))[:10]


class IngestionService:
    def __init__(self, session_factory, store, audit):
        self._session_factory = session_factory
        self._store = store
        self._audit = audit

    def ingest(self, principal: Principal, candidate: dict) -> dict:
        title = (candidate.get("title") or "").strip()
        content = (candidate.get("content") or "").strip()
        source_type = candidate.get("source_type", "agent_output")
        source_ref = candidate.get("source_ref", "")

        def record_job(status: str, reason: str, memory_id=None) -> dict:
            session = self._session_factory()
            try:
                job = MemoryIngestionJobRepository(session).add(
                    MemoryIngestionJob(
                        source_type=source_type, source_ref=source_ref,
                        candidate_title=title[:300], status=status,
                        reason=reason, memory_id=memory_id,
                        created_by=f"{principal.type.value}:{principal.id}"))
                return {"job_id": job.id, "status": status, "reason": reason,
                        "memory_id": memory_id}
            finally:
                session.close()

        # Steps 6/§18.2: secret screen BEFORE anything is stored.
        found = policy.detect_secrets(title, content)
        if found:
            self._store._record_security_event(principal, found, source_ref)
            return record_job(
                "REJECTED_SENSITIVE",
                f"credential-shaped material detected ({', '.join(found)}); "
                "value not stored, embedded or logged (§18.2)")
        # Step 10/§7.4: usefulness filter.
        useful, why = usefulness(f"{title} {content}")
        if not useful:
            return record_job("REJECTED_LOW_VALUE", why)
        # Steps 8–9: duplicate detection on content hash (§13.2 exact).
        digest = content_hash(title, content)
        session = self._session_factory()
        try:
            existing = MemoryRecordRepository(session).by_content_hash(digest)
        finally:
            session.close()
        if existing is not None and existing.status != "DELETED":
            return record_job(
                "REJECTED_DUPLICATE",
                f"exact duplicate of memory {existing.id}; original "
                "provenance preserved (§13.2, Scenario 9)",
                memory_id=existing.id)
        # Steps 4–5: classify + extract.
        category = classify(f"{title} {content}", candidate.get("category"))
        entities = extract_entities(f"{title} {content}")
        data = {
            "layer": candidate.get("layer", "semantic"),
            "category": category,
            "title": title, "content": content,
            "subject": candidate.get("subject", ""),
            "predicate": candidate.get("predicate", ""),
            "truth_class": candidate.get("truth_class", "agent_conclusion"),
            "source_type": source_type, "source_ref": source_ref,
            "business_id": candidate.get("business_id"),
            "project_ref": candidate.get("project_ref", ""),
            "agent_id": candidate.get("agent_id", ""),
            "task_ref": candidate.get("task_ref", ""),
            "decision_ref": candidate.get("decision_ref", ""),
            "evidence_refs": candidate.get("evidence_refs", []),
            "access_scope": candidate.get("access_scope", "BUSINESS_SHARED"),
            "sensitivity": candidate.get("sensitivity", "internal"),
            "retention_policy": candidate.get("retention_policy", "standard"),
            "freshness_days": candidate.get("freshness_days"),
            "importance_bps": candidate.get("importance_bps", 5000),
        }
        # Step 12–14: store through the single policy-gated path.
        record = self._store.create(principal, data)
        self._audit(principal, "memory.ingested", "memory_record",
                    record["id"], "allowed",
                    f"entities={entities}; category={category}")
        return record_job("STORED", "candidate stored and indexed",
                          memory_id=record["id"]) | {"record": record}

    def jobs(self, *, limit: int = 50, offset: int = 0,
             status: str | None = None) -> tuple[list, int]:
        session = self._session_factory()
        try:
            rows, total = MemoryIngestionJobRepository(session).list(
                limit=limit, offset=offset,
                filters={"status": status} if status else None)
            return [{"id": r.id, "source_type": r.source_type,
                     "source_ref": r.source_ref, "status": r.status,
                     "reason": r.reason, "memory_id": r.memory_id,
                     "candidate_title": r.candidate_title,
                     "created_by": r.created_by,
                     "created_at": r.created_at.isoformat() if r.created_at else None}
                    for r in rows], total
        finally:
            session.close()
