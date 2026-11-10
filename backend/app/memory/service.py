"""MemoryService — the P-09 facade.

Owns the owner-governed settings lifecycle (system_config pattern),
engine status (with truthful degraded flags), owner controls (§17:
preferences, correction via the versioned store, export), analytics
(§22) and the P-04 capability reconciliation (the ``memory_write``
flip + the completed agent-memory interface).

Article 0 boundary, stated structurally: this facade holds NO
reference to the permission engine's rule store, the approvals
service's decision path, or system_config keys other than its own
``memory.settings``. Memory can be read INTO a decision by P-02 —
it can never change who may decide, what may be spent, or what the
owner instructed. A structural test greps this package for writes to
those surfaces.
"""
from __future__ import annotations

import json

from ..core.exceptions import PermissionDeniedError, ValidationError
from ..database.models.core import AuditEvent
from ..database.repositories.core import AuditRepository, ConfigRepository
from ..database.repositories.memory import (
    LearningRecordRepository, MemoryContradictionRepository,
    MemoryRecordRepository, MemoryRetrievalLogRepository,
    MemoryReviewTaskRepository, OwnerMemoryPreferenceRepository,
)
from ..database.models.base import utcnow
from ..database.models.memory import MemoryExport, OwnerMemoryPreference
from ..database.repositories.memory import MemoryExportRepository
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from .embeddings import SqliteVectorStore
from .ingestion import IngestionService
from .knowledge import KnowledgeService
from .learning import LearningService
from .records import MemoryStore
from .retrieval import RetrievalService


class MemoryService:
    def __init__(self, session_factory, *, bus=None, vector_store=None,
                 agents=None):
        self._session_factory = session_factory
        self._bus = bus
        self._agents = agents
        self.vectors = vector_store or SqliteVectorStore(session_factory)
        self.store = MemoryStore(session_factory, self.vectors,
                                 self._audit, self.get_settings)
        self.ingestion = IngestionService(session_factory, self.store, self._audit)
        self.retrieval = RetrievalService(session_factory, self.vectors,
                                          self.get_settings, self._audit)
        self.learning = LearningService(session_factory, self._audit)
        self.knowledge = KnowledgeService(session_factory, self.store, self._audit)

    # ------------------------------------------------------------ settings
    def seed_settings(self) -> None:
        session = self._session_factory()
        try:
            repo = ConfigRepository(session)
            if repo.get(C.SETTINGS_KEY) is None:
                repo.set(C.SETTINGS_KEY, json.dumps(C.DEFAULT_SETTINGS),
                         "memory settings (owner-governed; weights, TTLs, "
                         "freshness windows, context limits)")
        finally:
            session.close()

    def get_settings(self) -> dict:
        session = self._session_factory()
        try:
            row = ConfigRepository(session).get(C.SETTINGS_KEY)
            stored = json.loads(row.value) if row and row.value else {}
        finally:
            session.close()
        return {**C.DEFAULT_SETTINGS, **stored}

    def update_settings(self, principal: Principal, patch: dict) -> dict:
        if principal.type is not PrincipalType.OWNER:
            raise PermissionDeniedError(
                "memory settings are owner-governed (Article 0)")
        current = self.get_settings()
        allowed = set(C.DEFAULT_SETTINGS) | {"weights"}
        for key, value in patch.items():
            if key not in allowed:
                raise ValidationError(f"unknown memory setting '{key}'")
            current[key] = value
        session = self._session_factory()
        try:
            ConfigRepository(session).set(
                C.SETTINGS_KEY, json.dumps(current),
                f"updated by {principal.type.value}:{principal.id}")
        finally:
            session.close()
        self._audit(principal, "memory.settings_updated", "system_config",
                    C.SETTINGS_KEY, "allowed", f"keys={sorted(patch)}")
        return current

    # --------------------------------------------------------- P-04 recon
    def seed_capability_flip(self) -> list[str]:
        """Mirror of P-05's flip: ``memory_write`` becomes grantable
        because P-09 genuinely backs it. The P-04 catalogue constant
        is not edited; the seeded DB row is flipped with the new
        truthful description."""
        from ..database.repositories.agents import CapabilityRepository
        session = self._session_factory()
        try:
            repo = CapabilityRepository(session)
            flipped = []
            for name, description in C.P09_SUPPORTED_CAPABILITIES.items():
                row = repo.get_by_name(name)
                if row is not None and not row.supported:
                    row.supported = True
                    row.description = description
                    repo.save(row)
                    flipped.append(name)
            return flipped
        finally:
            session.close()

    def wire_agent_memory(self) -> None:
        """Complete the P-04 seam: the factory's memory interface now
        serves the three deferred scopes through this engine."""
        if self._agents is None:
            return
        from ..agents.memory_interface import P04MemoryInterface
        from .knowledge import P09MemoryInterface
        p04 = P04MemoryInterface(self._session_factory)
        self._agents.memory = P09MemoryInterface(p04, self)

    # -------------------------------------------------------------- status
    def status(self) -> dict:
        session = self._session_factory()
        try:
            repo = MemoryRecordRepository(session)
            by_layer = repo.count_grouped(MemoryRecordRepository.model.layer) \
                if hasattr(repo, "model") else {}
            rows, total = repo.list(limit=1)
            learning_total = LearningRecordRepository(session).list(limit=1)[1]
        finally:
            session.close()
        vector_health = self.retrieval.vector_health()
        return {
            "engine": "P-09 Memory and Continuous Learning Engine",
            "total_memories": total,
            "by_layer": by_layer,
            "learning_records": learning_total,
            "vector_store": vector_health,
            "financial_source": "p07 by reference only (§16.2) — memory "
                                "stores no ledger figures",
            "authority_boundary": "memory is data, never authority "
                                  "(Article 0): no memory write can change "
                                  "permissions, approvals, owner instructions "
                                  "or spending limits",
            "llm_dependency": "none — ingestion, retrieval and learning are "
                              "deterministic; the engine is fully functional "
                              "with the local model offline (Scenario 10)",
        }

    # -------------------------------------------------------- owner (§17)
    def set_preference(self, principal: Principal, key: str, value: dict,
                       *, kind: str = "CONFIRMED_OWNER_PREFERENCE") -> dict:
        if kind == "EXPLICIT_OWNER_INSTRUCTION" and \
                principal.type is not PrincipalType.OWNER:
            raise PermissionDeniedError(
                "only the owner can record an explicit owner instruction "
                "(§17.2) — an inference can never become one")
        if principal.type is PrincipalType.AGENT and kind != "INFERRED_PREFERENCE":
            raise PermissionDeniedError(
                "agents may only record INFERRED_PREFERENCE entries, "
                "labelled as such (§17.2)")
        session = self._session_factory()
        try:
            repo = OwnerMemoryPreferenceRepository(session)
            row = repo.by_key(key)
            actor = f"{principal.type.value}:{principal.id}"
            if row is None:
                row = repo.add(OwnerMemoryPreference(
                    key=key, value=value, kind=kind, updated_by=actor))
            else:
                # Explicit beats inferred, permanently (§17.2).
                if row.kind == "EXPLICIT_OWNER_INSTRUCTION" and \
                        kind == "INFERRED_PREFERENCE":
                    return {"key": key, "value": row.value, "kind": row.kind,
                            "note": "existing explicit owner instruction "
                                    "not overridden by an inference (§17.2)"}
                row.value = value
                row.kind = kind
                row.updated_by = actor
                repo.save(row)
            result = {"key": row.key, "value": row.value, "kind": row.kind,
                      "updated_by": row.updated_by}
        finally:
            session.close()
        self._audit(principal, "memory.owner_preference_set",
                    "owner_memory_preference", key, "allowed", kind)
        return result

    def preferences(self) -> list[dict]:
        session = self._session_factory()
        try:
            rows, _ = OwnerMemoryPreferenceRepository(session).list(limit=200)
            return [{"key": r.key, "value": r.value, "kind": r.kind,
                     "updated_by": r.updated_by} for r in rows]
        finally:
            session.close()

    def export(self, principal: Principal, *,
               business_id: str | None = None) -> dict:
        """§17 owner export: only records the requester can read, and
        the export itself is recorded (§18.4)."""
        if principal.type is not PrincipalType.OWNER:
            raise PermissionDeniedError("memory export is an owner action (§17)")
        records, _ = self.store.list(
            principal, limit=1000,
            filters={"business_id": business_id} if business_id else None)
        session = self._session_factory()
        try:
            MemoryExportRepository(session).add(MemoryExport(
                requested_by=f"{principal.type.value}:{principal.id}",
                business_id=business_id,
                record_ids=[r["id"] for r in records]))
        finally:
            session.close()
        self._audit(principal, "memory.exported", "memory_export", None,
                    "allowed", f"{len(records)} records")
        return {"count": len(records), "records": records}

    def owner_audit(self, *, limit: int = 50) -> list[dict]:
        session = self._session_factory()
        try:
            from sqlalchemy import select
            rows = session.scalars(
                select(AuditEvent).where(
                    AuditEvent.action.like("memory.%"))
                .order_by(AuditEvent.created_at.desc()).limit(limit)).all()
            return [{"action": r.action, "actor": f"{r.actor_type}:{r.actor_id}",
                     "target_type": r.target_type, "target_id": r.target_id,
                     "decision": r.decision, "reason": r.reason,
                     "created_at": r.created_at.isoformat() if r.created_at else None}
                    for r in rows]
        finally:
            session.close()

    # ----------------------------------------------------------- analytics
    def analytics(self) -> dict:
        """§22 measured from the actual tables — storage volume alone
        is never claimed as improvement."""
        session = self._session_factory()
        try:
            repo = MemoryRecordRepository(session)
            rows = repo.all_active(limit=5000)
            total = len(rows)
            by_category = repo.count_grouped(repo.model.category)
            by_status = repo.count_grouped(repo.model.status)
            missing_provenance = sum(
                1 for r in rows if not r.source_type or not r.source_ref)
            contradictions, contra_total = MemoryContradictionRepository(
                session).list(limit=1, filters={"status": "OPEN"})
            reviews, review_total = MemoryReviewTaskRepository(session).list(
                limit=1, filters={"status": "OPEN"})
            learning_rows, learning_total = LearningRecordRepository(
                session).list(limit=1000)
            retrieval_rows, retrieval_total = MemoryRetrievalLogRepository(
                session).list(limit=200)
            verified = sum(1 for r in learning_rows
                           if r.confidence == "VERIFIED")
            repeated = {}
            for r in learning_rows:
                if r.source_type == "task" and "fail" in r.actual_outcome.lower():
                    key = r.lesson[:60]
                    repeated[key] = repeated.get(key, 0) + 1
        finally:
            session.close()
        return {
            "total_active_memories": total,
            "by_category": by_category, "by_status": by_status,
            "duplication_rate": round(
                (by_status.get("SUPERSEDED", 0) / total) if total else 0.0, 4),
            "verification_rate": round(
                (by_status.get("ACTIVE", 0) / total) if total else 0.0, 4),
            "missing_provenance_count": missing_provenance,
            "open_contradictions": contra_total,
            "pending_review": review_total,
            "learning_records": learning_total,
            "learning_verified": verified,
            "retrieval_queries_logged": retrieval_total,
            "repeated_failure_patterns": {k: v for k, v in repeated.items()
                                          if v > 1},
            "note": "metrics describe memory health only; no claim of "
                    "improved intelligence is made from storage volume (§22)",
        }

    # --------------------------------------------------------------- audit
    def _audit(self, principal, action: str, resource_type: str,
               resource_id, decision: str, reason: str) -> None:
        session = self._session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value if principal else "system",
                actor_id=principal.id if principal else "memory-engine",
                action=action, target_type=resource_type,
                target_id=resource_id, decision=decision,
                reason=reason, details={}, created_at=utcnow()))
        finally:
            session.close()
