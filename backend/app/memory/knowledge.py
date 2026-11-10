"""Knowledge evolution (§12), graph (§8.3), consolidation and
maintenance (§13), and P-04 agent-memory reconciliation (§14).

Contradiction detection NEVER edits either record: it flags the pair
and leaves resolution to supersession or owner review (§12.3).
Maintenance flags and archives by policy; age alone never deletes
important knowledge (§13.3).
"""
from __future__ import annotations

from datetime import timezone

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.base import utcnow
from ..database.models.memory import (
    AgentHandoff, MemoryConsolidation, MemoryContradiction, MemoryEntity,
    MemoryRelationship, MemoryReviewTask,
)
from ..database.repositories.memory import (
    AgentHandoffRepository, MemoryConsolidationRepository,
    MemoryContradictionRepository, MemoryEntityRepository,
    MemoryRecordRepository, MemoryRelationshipRepository,
    MemoryReviewTaskRepository,
)
from ..permissions.models import Principal, PrincipalType
from .records import record_to_dict


class KnowledgeService:
    def __init__(self, session_factory, store, audit):
        self._session_factory = session_factory
        self._store = store
        self._audit = audit

    # ------------------------------------------------- contradictions
    def detect_contradictions(self, memory_id: str) -> list[dict]:
        """§12.2: same subject+predicate, different content, both
        currently live → an OPEN contradiction preserving both."""
        row = self._store.get_row(memory_id)
        created: list[dict] = []
        session = self._session_factory()
        try:
            repo = MemoryRecordRepository(session)
            contra_repo = MemoryContradictionRepository(session)
            for other in repo.same_subject_predicate(
                    row.subject, row.predicate, exclude_id=memory_id):
                if other.status in ("SUPERSEDED", "DELETED"):
                    continue
                if other.content_hash == row.content_hash:
                    continue
                if contra_repo.open_between(memory_id, other.id):
                    continue
                entry = contra_repo.add(MemoryContradiction(
                    memory_a_id=memory_id, memory_b_id=other.id,
                    field="content", status="OPEN",
                    created_by="system:memory-engine"))
                created.append({"id": entry.id, "memory_a_id": memory_id,
                                "memory_b_id": other.id, "status": "OPEN"})
        finally:
            session.close()
        return created

    def contradictions(self, *, status: str | None = "OPEN") -> list[dict]:
        session = self._session_factory()
        try:
            rows, _ = MemoryContradictionRepository(session).list(
                limit=200, filters={"status": status} if status else None)
            return [{"id": r.id, "memory_a_id": r.memory_a_id,
                     "memory_b_id": r.memory_b_id, "field": r.field,
                     "status": r.status, "resolution": r.resolution}
                    for r in rows]
        finally:
            session.close()

    def resolve_contradiction(self, principal: Principal,
                              contradiction_id: str, *, resolution: str,
                              supersede_id: str | None = None) -> dict:
        if principal.type is not PrincipalType.OWNER:
            from ..core.exceptions import PermissionDeniedError
            raise PermissionDeniedError(
                "contradiction resolution is an owner action (§12.3)")
        session = self._session_factory()
        try:
            repo = MemoryContradictionRepository(session)
            row = repo.get(contradiction_id)
            if row is None:
                raise NotFoundError("contradiction not found")
            row.status = "RESOLVED"
            row.resolution = resolution
            repo.save(row)
            result = {"id": row.id, "status": row.status,
                      "resolution": row.resolution}
        finally:
            session.close()
        if supersede_id:
            result["note"] = ("resolution recorded; supersede the outdated "
                              "record through the records API to complete "
                              "the §12.3 workflow — both originals remain "
                              "preserved either way")
        self._audit(principal, "memory.contradiction_resolved",
                    "memory_contradiction", contradiction_id, "allowed", resolution)
        return result

    # ------------------------------------------------------------ graph
    def upsert_entity(self, principal: Principal, data: dict) -> dict:
        session = self._session_factory()
        try:
            repo = MemoryEntityRepository(session)
            existing = repo.find(data["entity_type"], data["entity_ref"])
            if existing is not None:
                return self._entity_dict(existing)
            row = repo.add(MemoryEntity(
                entity_type=data["entity_type"], entity_ref=data["entity_ref"],
                name=data.get("name", ""), business_id=data.get("business_id"),
                created_by=f"{principal.type.value}:{principal.id}"))
            return self._entity_dict(row)
        finally:
            session.close()

    @staticmethod
    def _entity_dict(row) -> dict:
        return {"id": row.id, "entity_type": row.entity_type,
                "entity_ref": row.entity_ref, "name": row.name,
                "business_id": row.business_id}

    def relate(self, principal: Principal, data: dict) -> dict:
        session = self._session_factory()
        try:
            repo = MemoryRelationshipRepository(session)
            row = repo.add(MemoryRelationship(
                from_entity_id=data["from_entity_id"],
                to_entity_id=data["to_entity_id"],
                relation=data["relation"],
                business_id=data.get("business_id"),
                created_by=f"{principal.type.value}:{principal.id}"))
            return {"id": row.id, "from_entity_id": row.from_entity_id,
                    "to_entity_id": row.to_entity_id, "relation": row.relation}
        finally:
            session.close()

    def traverse(self, entity_id: str, *, depth: int = 2) -> dict:
        session = self._session_factory()
        try:
            rels = MemoryRelationshipRepository(session)
            entities = MemoryEntityRepository(session)
            seen: dict[str, dict] = {}
            edges: list[dict] = []
            edge_keys: set[tuple] = set()
            frontier = [entity_id]
            for _ in range(max(1, depth)):
                nxt = []
                for current in frontier:
                    for edge in rels.edges_from(current) + rels.edges_to(current):
                        key = (edge.from_entity_id, edge.to_entity_id,
                               edge.relation)
                        if key not in edge_keys:
                            edge_keys.add(key)
                            edges.append({"from": edge.from_entity_id,
                                          "to": edge.to_entity_id,
                                          "relation": edge.relation})
                        for other in (edge.from_entity_id, edge.to_entity_id):
                            if other not in seen:
                                row = entities.get(other)
                                if row is not None:
                                    seen[other] = self._entity_dict(row)
                                    nxt.append(other)
                frontier = nxt
            return {"root": entity_id, "entities": list(seen.values()),
                    "edges": edges}
        finally:
            session.close()

    # ----------------------------------------------------- consolidation
    def consolidate(self, principal: Principal, *, title: str,
                    memory_ids: list[str], business_id: str | None = None) -> dict:
        """§13.1: a NEW summary memory linked to its sources; sources
        are preserved untouched."""
        if len(memory_ids) < 2:
            raise ValidationError("consolidation needs at least two source memories")
        sources = [self._store.get_row(mid) for mid in memory_ids]
        summary_text = "\n".join(
            f"- {s.title}: {s.content[:200]}" for s in sources)
        summary = self._store.create(principal, {
            "layer": "semantic", "category": "BUSINESS_KNOWLEDGE",
            "title": title,
            "content": f"Consolidated summary of {len(sources)} memories:\n{summary_text}",
            "truth_class": "agent_conclusion", "source_type": "system_record",
            "source_ref": "consolidation",
            "business_id": business_id,
            "evidence_refs": [f"memory:{s.id}" for s in sources],
            "access_scope": "BUSINESS_SHARED"})
        session = self._session_factory()
        try:
            row = MemoryConsolidationRepository(session).add(MemoryConsolidation(
                title=title, summary_memory_id=summary["id"],
                source_memory_ids=memory_ids, business_id=business_id,
                created_by=f"{principal.type.value}:{principal.id}"))
            result = {"id": row.id, "summary_memory_id": summary["id"],
                      "source_memory_ids": memory_ids}
        finally:
            session.close()
        self._audit(principal, "memory.consolidated", "memory_record",
                    summary["id"], "allowed", f"{len(memory_ids)} sources")
        return result

    # ------------------------------------------------------- maintenance
    def maintenance_scan(self, principal: Principal) -> dict:
        """§13.3/§13.4: expire working memory past its TTL (to
        ARCHIVED, never deleted), flag stale time-sensitive records
        and long-unverified records for review. Decisions, outcomes
        and verified facts are never auto-archived."""
        now = utcnow()
        expired: list[str] = []
        review_created: list[str] = []
        session = self._session_factory()
        try:
            repo = MemoryRecordRepository(session)
            review_repo = MemoryReviewTaskRepository(session)
            rows = repo.all_active(limit=2000)
            for row in rows:
                if row.layer == "working" and row.expires_at:
                    try:
                        expires = row.expires_at
                        from datetime import datetime
                        parsed = datetime.fromisoformat(expires)
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        if parsed <= now:
                            row.status = "ARCHIVED"
                            repo.save(row)
                            expired.append(row.id)
                            continue
                    except ValueError:
                        pass
                reason = None
                if row.freshness_days is not None and row.created_at:
                    created = row.created_at
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    age = (now - created).days
                    if age > row.freshness_days:
                        reason = "STALE_FRESHNESS"
                if reason is None and row.status == "UNVERIFIED" and row.created_at:
                    created = row.created_at
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    if (now - created).days > 30:
                        reason = "LONG_UNVERIFIED"
                if reason and review_repo.open_for(row.id, reason) is None:
                    review_repo.add(MemoryReviewTask(
                        memory_id=row.id, reason=reason,
                        created_by="system:memory-engine"))
                    review_created.append(row.id)
            result = {"expired_working": expired,
                      "review_tasks_created_for": review_created,
                      "scanned": len(rows)}
        finally:
            session.close()
        self._audit(principal, "memory.maintenance_scan", "memory_engine",
                    None, "allowed",
                    f"expired={len(expired)} reviews={len(review_created)}")
        return result

    def review_tasks(self, *, status: str | None = "OPEN") -> list[dict]:
        session = self._session_factory()
        try:
            rows, _ = MemoryReviewTaskRepository(session).list(
                limit=200, filters={"status": status} if status else None)
            return [{"id": r.id, "memory_id": r.memory_id, "reason": r.reason,
                     "status": r.status} for r in rows]
        finally:
            session.close()

    # ------------------------------------------------------------ handoff
    def create_handoff(self, principal: Principal, data: dict) -> dict:
        session = self._session_factory()
        try:
            row = AgentHandoffRepository(session).add(AgentHandoff(
                from_agent_id=data["from_agent_id"],
                to_agent_id=data.get("to_agent_id", ""),
                task_ref=data.get("task_ref", ""),
                business_id=data.get("business_id"),
                objective=data["objective"],
                work_completed=data.get("work_completed", ""),
                current_status=data.get("current_status", "IN_PROGRESS"),
                decisions=data.get("decisions", []),
                evidence=data.get("evidence", []),
                files_modified=data.get("files_modified", []),
                outstanding=data.get("outstanding", []),
                known_problems=data.get("known_problems", []),
                required_permissions=data.get("required_permissions", []),
                next_actions=data.get("next_actions", []),
                created_by=f"{principal.type.value}:{principal.id}"))
            return self._handoff_dict(row)
        finally:
            session.close()

    @staticmethod
    def _handoff_dict(row) -> dict:
        return {"id": row.id, "from_agent_id": row.from_agent_id,
                "to_agent_id": row.to_agent_id, "task_ref": row.task_ref,
                "business_id": row.business_id, "objective": row.objective,
                "work_completed": row.work_completed,
                "current_status": row.current_status,
                "decisions": row.decisions or [], "evidence": row.evidence or [],
                "files_modified": row.files_modified or [],
                "outstanding": row.outstanding or [],
                "known_problems": row.known_problems or [],
                "required_permissions": row.required_permissions or [],
                "next_actions": row.next_actions or [],
                "created_by": row.created_by,
                "created_at": row.created_at.isoformat() if row.created_at else None}

    def handoffs_for(self, principal: Principal, agent_id: str) -> list[dict]:
        if principal.type is PrincipalType.AGENT and principal.id != agent_id:
            from ..core.exceptions import PermissionDeniedError
            raise PermissionDeniedError(
                "an agent may only read its own handoffs (§14.3)")
        session = self._session_factory()
        try:
            rows = AgentHandoffRepository(session).for_agent(agent_id)
            return [self._handoff_dict(r) for r in rows]
        finally:
            session.close()


class P09MemoryInterface:
    """The P-04 seam, completed (§14/Stage-1 note 4).

    Implements P-04's ``AgentMemoryInterface`` protocol: the two
    scopes P-04 serves stay served by P-04's implementation; the three
    scopes P-04 deferred to P-09 are now served by the memory engine —
    scoped to the requesting agent, with cross-agent access refused
    exactly as P-04 enforced for its own scopes.
    """

    def __init__(self, p04_interface, memory_service):
        self._p04 = p04_interface
        self._memory = memory_service

    def read(self, *, requester: Principal, agent_id: str, scope: str,
             limit: int = 20) -> dict:
        from ..agents.memory_interface import DEFERRED_SCOPES, SERVED_SCOPES
        if scope in SERVED_SCOPES:
            return self._p04.read(requester=requester, agent_id=agent_id,
                                  scope=scope, limit=limit)
        if scope not in DEFERRED_SCOPES:
            return {"scope": scope, "status": "unavailable", "items": [],
                    "note": f"unknown memory scope '{scope}'"}
        if requester.type is PrincipalType.AGENT and requester.id != agent_id:
            from ..core.exceptions import PermissionDeniedError
            raise PermissionDeniedError(
                "an agent may only read its OWN memory scopes",
                details={"error_category": "CAPABILITY_NOT_AUTHORIZED",
                         "scope": scope})
        svc = self._memory
        if scope == "approved_contextual_memory":
            found = svc.retrieval.search(
                requester, query="", agent_id=agent_id, limit=limit)
            items = found["results"]
        elif scope == "business_context":
            business_ref = policy_business_ref(svc, requester)
            found = svc.retrieval.search(
                requester, query="", business_id=business_ref, limit=limit) \
                if business_ref else {"results": []}
            items = found["results"]
        else:  # approved_lessons_or_evaluations
            rows, _ = svc.learning.list(requester, limit=limit)
            items = rows
        return {"scope": scope, "status": "ok", "items": items,
                "note": "served by P-09 memory engine; scoped to this agent"}


def policy_business_ref(memory_service, principal) -> str | None:
    from . import policy as _policy
    return _policy.agent_business_ref(memory_service._session_factory, principal)
