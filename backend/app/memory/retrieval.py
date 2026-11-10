"""Hybrid retrieval (§9) and context assembly (§10).

Retrieval combines exact, keyword, semantic (local vector adapter),
relationship and temporal signals under the §9.3 weights — with the
access filter applied BEFORE ranking, so a high score can never
widen access (§9.3/§18.1). Every result carries its score breakdown,
provenance, freshness and contradiction flags (§9.5): if nothing
reliable exists, the answer says ``no_reliable_memory`` instead of
inventing one.

No LLM is used anywhere in retrieval: the engine works identically
with the local model offline (Scenario 10), and with the vector
store down it degrades to keyword/exact and reports it (Scenario 11).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from ..database.models.base import utcnow
from ..database.models.memory import MemoryRetrievalLog
from ..database.repositories.memory import (
    MemoryContradictionRepository, MemoryEmbeddingRepository,
    MemoryEntityRepository, MemoryRecordRepository,
    MemoryRelationshipRepository, MemoryRetrievalLogRepository,
)
from ..permissions.models import Principal
from . import constants as C
from . import policy
from .embeddings import tokenize
from .records import record_to_dict


def _age_days(row) -> float:
    created = row.created_at
    if created is None:
        return 0.0
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0.0, (utcnow() - created).total_seconds() / 86400.0)


def _is_stale(row) -> bool:
    if row.freshness_days is None:
        return False
    return _age_days(row) > row.freshness_days


class RetrievalService:
    def __init__(self, session_factory, vector_store, get_settings, audit):
        self._session_factory = session_factory
        self._vectors = vector_store
        self._get_settings = get_settings
        self._audit = audit

    # ------------------------------------------------------------- search
    def search(self, principal: Principal, *, query: str = "",
               categories: list[str] | None = None,
               business_id: str | None = None,
               project_ref: str | None = None,
               agent_id: str | None = None,
               since: str | None = None, until: str | None = None,
               include_history: bool = False,
               limit: int | None = None) -> dict:
        settings = self._get_settings()
        weights = settings.get("weights") or C.DEFAULT_WEIGHTS
        limit = limit or int(settings["retrieval_default_limit"])
        scoped = policy.ScopedPrincipal(
            principal, policy.agent_business_ref(self._session_factory, principal))
        session = self._session_factory()
        try:
            repo = MemoryRecordRepository(session)
            candidates = repo.all_active(limit=2000)
            # Relationship signal: entities tied to the query's business.
            related_ids = self._related_memory_ids(session, business_id)
            open_contradictions = self._contradiction_index(session)
        finally:
            session.close()

        # Semantic candidates (degradable).
        degraded = {"semantic": False, "llm": "not_required"}
        semantic_scores: dict[str, float] = {}
        if query and settings.get("vector_enabled", True):
            try:
                for hit in self._vectors.search(query, limit=50):
                    semantic_scores[hit["memory_id"]] = hit["similarity"]
            except Exception:
                degraded["semantic"] = True

        query_tokens = set(tokenize(query))
        results: list[dict] = []
        for row in candidates:
            # ---- hard filters BEFORE ranking (§9.3) ----
            if not policy.can_read(scoped, row):
                continue
            if row.status in ("SUPERSEDED", "ARCHIVED") and not include_history:
                continue
            if categories and row.category not in categories:
                continue
            if business_id and row.business_id != business_id:
                continue
            if project_ref and row.project_ref != project_ref:
                continue
            if agent_id and row.agent_id != agent_id:
                continue
            if since and row.created_at and row.created_at.isoformat() < since:
                continue
            if until and row.created_at and row.created_at.isoformat() > until:
                continue
            # ---- component scores ----
            text_tokens = set(tokenize(f"{row.title} {row.content} {row.subject}"))
            keyword = (len(query_tokens & text_tokens) / len(query_tokens)
                       if query_tokens else 0.0)
            exact = 1.0 if query and (query.lower() in row.title.lower()
                                      or query.lower() in row.content.lower()) else 0.0
            task_rel = max(keyword, exact)
            if categories and row.category in categories:
                task_rel = max(task_rel, 0.6)
            semantic = semantic_scores.get(row.id, 0.0)
            confidence = row.confidence_bps / 10000.0
            reliability = C.SOURCE_RELIABILITY_BPS.get(row.source_type, 4000) / 10000.0
            importance = row.importance_bps / 10000.0
            recency = 1.0 / (1.0 + _age_days(row) / 30.0)
            relationship = 1.0 if row.id in related_ids else 0.0
            score = (
                weights["task_relevance"] * task_rel
                + weights["semantic_similarity"] * semantic
                + weights["evidence_confidence"] * confidence
                + weights["source_reliability"] * reliability
                + weights["importance"] * importance
                + weights["recency"] * recency
                + weights["relationship_relevance"] * relationship)
            if query and task_rel == 0.0 and semantic == 0.0 \
                    and row.id not in related_ids:
                continue  # no signal at all for a text query
            entry = record_to_dict(row)
            entry["score"] = round(score, 4)
            entry["score_breakdown"] = {
                "task_relevance": round(task_rel, 4),
                "semantic_similarity": round(semantic, 4),
                "evidence_confidence": round(confidence, 4),
                "source_reliability": round(reliability, 4),
                "importance": round(importance, 4),
                "recency": round(recency, 4),
                "relationship_relevance": relationship,
            }
            entry["freshness"] = ("stale" if _is_stale(row) else "current")
            entry["contradictions"] = open_contradictions.get(row.id, [])
            entry["why"] = self._why(entry["score_breakdown"])
            results.append(entry)
        results.sort(key=lambda e: e["score"], reverse=True)
        results = results[:limit]

        self._log_retrieval(principal, query, [r["id"] for r in results], degraded)
        reliable = [r for r in results
                    if (r["score_breakdown"]["task_relevance"] > 0
                        or r["score_breakdown"]["semantic_similarity"] >= 0.35)
                    and r["truth_class"] in ("verified_fact", "corroborated",
                                             "user_provided")
                    and r["freshness"] == "current"]
        return {
            "query": query, "results": results, "count": len(results),
            "degraded": degraded,
            "no_reliable_memory": len(reliable) == 0,
            "note": ("no reliable (verified/corroborated/user-provided, "
                     "current) memory matched — absence is reported, "
                     "never filled by invention (§9.5)"
                     if not reliable else ""),
        }

    @staticmethod
    def _why(breakdown: dict) -> str:
        top = sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)[:2]
        return "retrieved mainly for: " + ", ".join(
            f"{name} ({value})" for name, value in top if value > 0) or \
            "retrieved on scope match"

    def _related_memory_ids(self, session, business_id: str | None) -> set[str]:
        if not business_id:
            return set()
        entities = MemoryEntityRepository(session)
        rels = MemoryRelationshipRepository(session)
        ids: set[str] = set()
        business_entity = entities.find("business", business_id)
        if business_entity is None:
            return ids
        seen = {business_entity.id}
        frontier = [business_entity.id]
        for _ in range(2):  # two-hop traversal (§8.3)
            nxt = []
            for entity_id in frontier:
                for edge in rels.edges_from(entity_id) + rels.edges_to(entity_id):
                    for other in (edge.from_entity_id, edge.to_entity_id):
                        if other not in seen:
                            seen.add(other)
                            nxt.append(other)
            frontier = nxt
        for entity_id in seen:
            entity = session.get(type(business_entity), entity_id)
            if entity is not None and entity.entity_type == "memory":
                ids.add(entity.entity_ref)
        return ids

    def _contradiction_index(self, session) -> dict[str, list[str]]:
        from sqlalchemy import select
        from ..database.models.memory import MemoryContradiction
        rows = session.scalars(select(MemoryContradiction).where(
            MemoryContradiction.status == "OPEN")).all()
        index: dict[str, list[str]] = {}
        for row in rows:
            index.setdefault(row.memory_a_id, []).append(row.id)
            index.setdefault(row.memory_b_id, []).append(row.id)
        return index

    def _log_retrieval(self, principal, query, result_ids, degraded) -> None:
        session = self._session_factory()
        try:
            MemoryRetrievalLogRepository(session).add(MemoryRetrievalLog(
                requester=f"{principal.type.value}:{principal.id}",
                query_digest=hashlib.sha256((query or "").encode()).hexdigest(),
                query_len=len(query or ""), result_ids=result_ids,
                degraded=degraded, result_count=len(result_ids)))
        finally:
            session.close()

    # ------------------------------------------------- context assembly
    def build_context(self, principal: Principal, *, task: str = "",
                      business_id: str | None = None,
                      project_ref: str | None = None,
                      agent_id: str | None = None,
                      categories: list[str] | None = None) -> dict:
        """§10: priority-ordered, access-filtered, size-limited context
        package with provenance and per-item explanations."""
        settings = self._get_settings()
        max_items = int(settings["context_max_items"])
        query = task or ""
        found = self.search(
            principal, query=query, business_id=business_id,
            project_ref=project_ref, limit=100)
        all_results = found["results"]
        priority = {
            "OWNER_INSTRUCTION": 0, "USER_PREFERENCE": 1,
            "SYSTEM_CONFIGURATION": 2, "PROCEDURE": 3,
            "DECISION_HISTORY": 4, "LESSON_LEARNED": 5,
            "EXPERIMENT_OUTCOME": 6,
        }
        all_results.sort(key=lambda e: (
            priority.get(e["category"], 7), -e["score"]))
        package_items = all_results[:max_items]
        contradictions = sorted({cid for e in package_items
                                 for cid in e["contradictions"]})
        return {
            "task": task, "business_id": business_id,
            "project_ref": project_ref, "agent_id": agent_id,
            "items": package_items, "item_count": len(package_items),
            "contradiction_ids": contradictions,
            "degraded": found["degraded"],
            "no_reliable_memory": found["no_reliable_memory"],
            "ordering": "owner instructions → preferences → constraints → "
                        "procedures → decisions → lessons → supporting (§10.3)",
        }

    def vector_health(self) -> dict:
        try:
            return self._vectors.health()
        except Exception as exc:  # degraded, reported truthfully
            return {"store": getattr(self._vectors, "name", "unknown"),
                    "status": "unavailable", "indexed": 0,
                    "embedder": None, "note": f"health check failed: {exc}"}
