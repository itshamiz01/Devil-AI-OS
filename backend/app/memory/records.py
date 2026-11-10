"""Memory record store: creation, versioning, supersession,
verification, archival and governed deletion (§3/§6/§12/§17).

Every write passes the single policy gate (Article 0 + secret
filter). History is preserved: updates snapshot the prior version,
supersession creates a new record and marks — never edits away —
the original, and deletion is verified against the derived vector
index before it is reported complete (Scenario 15).
"""
from __future__ import annotations

import hashlib

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.base import utcnow
from ..database.models.memory import (
    MemoryDeletionReceipt, MemoryRecord, MemoryVersion,
)
from ..database.repositories.memory import (
    MemoryDeletionReceiptRepository, MemoryEmbeddingRepository,
    MemoryRecordRepository, MemoryVersionRepository,
)
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from . import policy


def content_hash(title: str, content: str) -> str:
    return hashlib.sha256(f"{title}\n{content}".encode("utf-8")).hexdigest()


def record_to_dict(row: MemoryRecord) -> dict:
    return {
        "id": row.id, "layer": row.layer, "category": row.category,
        "title": row.title, "content": row.content,
        "subject": row.subject, "predicate": row.predicate,
        "truth_class": row.truth_class, "status": row.status,
        "confidence": row.confidence, "confidence_bps": row.confidence_bps,
        "importance_bps": row.importance_bps,
        "source_type": row.source_type, "source_ref": row.source_ref,
        "source_actor": row.source_actor, "business_id": row.business_id,
        "project_ref": row.project_ref, "agent_id": row.agent_id,
        "task_ref": row.task_ref, "decision_ref": row.decision_ref,
        "evidence_refs": row.evidence_refs or [],
        "access_scope": row.access_scope, "sensitivity": row.sensitivity,
        "retention_policy": row.retention_policy,
        "freshness_days": row.freshness_days, "expires_at": row.expires_at,
        "version": row.version, "supersedes_id": row.supersedes_id,
        "superseded_by_id": row.superseded_by_id,
        "verified_at": row.verified_at,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class MemoryStore:
    def __init__(self, session_factory, vector_store, audit, get_settings):
        self._session_factory = session_factory
        self._vectors = vector_store
        self._audit = audit
        self._get_settings = get_settings

    # ------------------------------------------------------------ create
    def create(self, principal: Principal, data: dict, *,
               _skip_secret_check: bool = False) -> dict:
        layer = data.get("layer", "semantic")
        category = data.get("category", "TECHNICAL_KNOWLEDGE")
        truth_class = data.get("truth_class", "agent_conclusion")
        access_scope = data.get("access_scope", "BUSINESS_SHARED")
        if layer not in C.LAYERS:
            raise ValidationError(f"unknown memory layer '{layer}'")
        if category not in C.CATEGORIES:
            raise ValidationError(f"unknown memory category '{category}'")
        if truth_class not in C.TRUTH_CLASSES:
            raise ValidationError(f"unknown truth class '{truth_class}'")
        if access_scope not in C.ACCESS_SCOPES:
            raise ValidationError(f"unknown access scope '{access_scope}'")
        title = (data.get("title") or "").strip()
        content = (data.get("content") or "").strip()
        if not title or not content:
            raise ValidationError("a memory requires a title and content")
        policy.assert_write_allowed(
            principal, category=category, access_scope=access_scope,
            truth_class=truth_class, title=title, content=content)
        if not _skip_secret_check:
            found = policy.detect_secrets(title, content)
            if found:
                self._record_security_event(
                    principal, found, data.get("source_ref", ""))
                raise ValidationError(
                    "content contains credential-shaped material and was "
                    "blocked from memory storage (§18.2); a safe security "
                    "event was recorded without the value",
                    details={"patterns": found})
        if layer == "working" and not data.get("expires_at"):
            hours = int(self._get_settings()["working_ttl_hours"])
            expires = utcnow().timestamp() + hours * 3600
            from datetime import datetime, timezone
            data = {**data, "expires_at": datetime.fromtimestamp(
                expires, tz=timezone.utc).isoformat()}
        confidence = data.get("confidence") or (
            "MODERATE" if truth_class in ("user_provided", "corroborated")
            else "LOW")
        if confidence not in C.CONFIDENCE_BPS:
            raise ValidationError(f"unknown confidence '{confidence}'")
        if truth_class == "verified_fact" and confidence != "VERIFIED":
            confidence = "VERIFIED"
        status = data.get("status") or (
            "ACTIVE" if truth_class in ("verified_fact", "user_provided",
                                         "corroborated")
            else "UNVERIFIED")
        session = self._session_factory()
        try:
            repo = MemoryRecordRepository(session)
            row = repo.add(MemoryRecord(
                layer=layer, category=category, title=title, content=content,
                subject=data.get("subject", ""), predicate=data.get("predicate", ""),
                truth_class=truth_class, status=status, confidence=confidence,
                confidence_bps=C.CONFIDENCE_BPS[confidence],
                importance_bps=int(data.get("importance_bps", 5000)),
                source_type=data.get("source_type", "agent_output"),
                source_ref=data.get("source_ref", ""),
                source_actor=f"{principal.type.value}:{principal.id}",
                business_id=data.get("business_id"),
                project_ref=data.get("project_ref", ""),
                agent_id=data.get("agent_id", ""),
                task_ref=data.get("task_ref", ""),
                decision_ref=data.get("decision_ref", ""),
                evidence_refs=data.get("evidence_refs", []),
                access_scope=access_scope,
                sensitivity=data.get("sensitivity", "internal"),
                retention_policy=data.get("retention_policy", "standard"),
                freshness_days=data.get("freshness_days"),
                expires_at=data.get("expires_at"),
                content_hash=content_hash(title, content),
                created_by=f"{principal.type.value}:{principal.id}"))
            result = record_to_dict(row)
        finally:
            session.close()
        self._index(result["id"], f"{title}\n{content}")
        self._audit(principal, "memory.record_created", "memory_record",
                    result["id"], "allowed", f"{layer}/{category}/{truth_class}")
        return result

    def _index(self, memory_id: str, text: str) -> None:
        try:
            self._vectors.upsert(memory_id, text)
        except Exception:
            pass  # degraded indexing is reported via status, never fatal

    def _record_security_event(self, principal, patterns: list[str],
                               source_ref: str) -> None:
        """A safe §18.2 event: pattern names only, never values."""
        try:
            session = self._session_factory()
            try:
                MemoryRecordRepository(session).add(MemoryRecord(
                    layer="episodic", category="SECURITY_EVENT",
                    title="Credential-shaped content blocked from memory",
                    content=("Ingestion blocked: credential-shaped material "
                             f"detected (patterns: {', '.join(patterns)}). "
                             "The value was not stored, embedded or logged."),
                    truth_class="historical_observation", status="ACTIVE",
                    confidence="HIGH", confidence_bps=C.CONFIDENCE_BPS["HIGH"],
                    source_type="system_record", source_ref=source_ref,
                    source_actor="memory-engine",
                    access_scope="OWNER_ONLY",
                    content_hash=content_hash(
                        "secret-block", ",".join(patterns) + source_ref),
                    created_by="system:memory-engine"))
            finally:
                session.close()
        except Exception:
            pass

    # -------------------------------------------------------------- read
    def get_row(self, memory_id: str) -> MemoryRecord:
        session = self._session_factory()
        try:
            row = MemoryRecordRepository(session).get(memory_id)
            if row is None or row.status == "DELETED":
                raise NotFoundError(f"memory record '{memory_id}' not found")
            session.expunge(row)
            return row
        finally:
            session.close()

    def get(self, principal: Principal, memory_id: str) -> dict:
        row = self.get_row(memory_id)
        scoped = policy.ScopedPrincipal(
            principal, policy.agent_business_ref(self._session_factory, principal))
        if not policy.can_read(scoped, row):
            raise PermissionDeniedError(
                "this memory is not accessible to this principal (§18.1)")
        return record_to_dict(row)

    def list(self, principal: Principal, *, limit: int = 50, offset: int = 0,
             filters: dict | None = None) -> tuple[list, int]:
        session = self._session_factory()
        try:
            rows, _ = MemoryRecordRepository(session).list(
                limit=1000, offset=0, filters=filters)
            scoped = policy.ScopedPrincipal(
                principal, policy.agent_business_ref(self._session_factory, principal))
            visible = [r for r in rows
                       if r.status != "DELETED" and policy.can_read(scoped, r)]
            total = len(visible)
            return [record_to_dict(r) for r in visible[offset:offset + limit]], total
        finally:
            session.close()

    # ------------------------------------------------------------ update
    def update(self, principal: Principal, memory_id: str, patch: dict,
               *, reason: str = "") -> dict:
        """Versioned update (§12.4): the prior version is snapshotted
        before any field changes; history is never silently rewritten."""
        row = self.get_row(memory_id)
        self._assert_can_modify(principal, row)
        if principal.type is PrincipalType.AGENT and \
                patch.get("truth_class") == "verified_fact":
            raise PermissionDeniedError(
                "agents cannot escalate a memory to verified_fact (§3.1)")
        new_title = patch.get("title", row.title)
        new_content = patch.get("content", row.content)
        found = policy.detect_secrets(new_title, new_content)
        if found:
            self._record_security_event(principal, found, row.source_ref)
            raise ValidationError(
                "updated content contains credential-shaped material (§18.2)",
                details={"patterns": found})
        session = self._session_factory()
        try:
            repo = MemoryRecordRepository(session)
            live = repo.get(memory_id)
            MemoryVersionRepository(session).add(MemoryVersion(
                memory_id=memory_id, version=live.version, title=live.title,
                content=live.content, change_reason=reason,
                changed_by=f"{principal.type.value}:{principal.id}"))
            for field in ("title", "content", "subject", "predicate",
                          "status", "importance_bps", "freshness_days",
                          "access_scope", "sensitivity"):
                if field in patch and patch[field] is not None:
                    setattr(live, field, patch[field])
            if "truth_class" in patch and patch["truth_class"]:
                if principal.type is PrincipalType.AGENT and \
                        patch["truth_class"] == "verified_fact":
                    raise PermissionDeniedError(
                        "agents cannot escalate a memory to verified_fact (§3.1)")
                live.truth_class = patch["truth_class"]
            live.version += 1
            live.content_hash = content_hash(live.title, live.content)
            repo.save(live)
            result = record_to_dict(live)
        finally:
            session.close()
        self._index(memory_id, f"{result['title']}\n{result['content']}")
        self._audit(principal, "memory.record_updated", "memory_record",
                    memory_id, "allowed", reason or "versioned update")
        return result

    def supersede(self, principal: Principal, memory_id: str,
                  new_data: dict, *, reason: str = "") -> dict:
        """§12.3/Scenario 6: the original is preserved and marked
        SUPERSEDED; the replacement is a new record linked to it, so
        current and historical knowledge stay distinguishable."""
        old = self.get_row(memory_id)
        self._assert_can_modify(principal, old)
        created = self.create(principal, dict(new_data))
        session = self._session_factory()
        try:
            repo = MemoryRecordRepository(session)
            live_old = repo.get(memory_id)
            live_old.status = "SUPERSEDED"
            live_old.superseded_by_id = created["id"]
            repo.save(live_old)
            live_new = repo.get(created["id"])
            live_new.supersedes_id = memory_id
            repo.save(live_new)
            created["supersedes_id"] = memory_id
        finally:
            session.close()
        self._audit(principal, "memory.record_superseded", "memory_record",
                    memory_id, "allowed", reason or f"superseded by {created['id']}")
        return created

    def verify(self, principal: Principal, memory_id: str, *,
               evidence_refs: list | None = None) -> dict:
        """Owner verification: the only path to verified_fact (§3.1)."""
        if principal.type is not PrincipalType.OWNER:
            raise PermissionDeniedError(
                "only the owner can verify a memory (§3.1/§17)")
        row = self.get_row(memory_id)
        session = self._session_factory()
        try:
            repo = MemoryRecordRepository(session)
            live = repo.get(memory_id)
            live.truth_class = "verified_fact"
            live.confidence = "VERIFIED"
            live.confidence_bps = C.CONFIDENCE_BPS["VERIFIED"]
            live.status = "ACTIVE"
            live.verified_at = utcnow().isoformat()
            if evidence_refs:
                live.evidence_refs = list({*(live.evidence_refs or []),
                                           *evidence_refs})
            repo.save(live)
            result = record_to_dict(live)
        finally:
            session.close()
        self._audit(principal, "memory.record_verified", "memory_record",
                    memory_id, "allowed", "owner verification")
        return result

    def history(self, memory_id: str) -> list[dict]:
        session = self._session_factory()
        try:
            rows = MemoryVersionRepository(session).for_memory(memory_id)
            return [{"version": r.version, "title": r.title,
                     "content": r.content, "change_reason": r.change_reason,
                     "changed_by": r.changed_by,
                     "created_at": r.created_at.isoformat() if r.created_at else None}
                    for r in rows]
        finally:
            session.close()

    def sources(self, memory_id: str) -> dict:
        row = self.get_row(memory_id)
        return {"memory_id": memory_id, "source_type": row.source_type,
                "source_ref": row.source_ref, "source_actor": row.source_actor,
                "evidence_refs": row.evidence_refs or [],
                "created_by": row.created_by, "verified_at": row.verified_at}

    # ------------------------------------------------------------ delete
    def delete(self, principal: Principal, memory_id: str) -> dict:
        """Governed deletion (Scenario 15): owner only; retention
        ``permanent`` blocks deletion; the embedding row is removed
        and its absence VERIFIED before the receipt says complete."""
        if principal.type is not PrincipalType.OWNER:
            raise PermissionDeniedError(
                "memory deletion is an owner action (§17)")
        row = self.get_row(memory_id)
        session = self._session_factory()
        try:
            receipt_repo = MemoryDeletionReceiptRepository(session)
            if row.retention_policy == "permanent":
                receipt = receipt_repo.add(MemoryDeletionReceipt(
                    memory_id=memory_id,
                    requested_by=f"{principal.type.value}:{principal.id}",
                    status="BLOCKED_RETENTION", index_sync_verified=False,
                    detail="retention policy 'permanent' forbids deletion (§13.3)"))
                return {"memory_id": memory_id, "status": receipt.status,
                        "index_sync_verified": False,
                        "detail": receipt.detail}
        finally:
            session.close()
        # Remove the derived index entry first, then verify absence.
        removed = False
        try:
            removed = self._vectors.remove(memory_id)
        except Exception:
            removed = False
        index_gone = True
        try:
            index_gone = not self._vectors.contains(memory_id)
        except Exception:
            # Fall back to the authoritative table check.
            s2 = self._session_factory()
            try:
                index_gone = MemoryEmbeddingRepository(s2).for_memory(memory_id) is None
            finally:
                s2.close()
        verified = bool(index_gone)
        session = self._session_factory()
        try:
            repo = MemoryRecordRepository(session)
            live = repo.get(memory_id)
            live.status = "DELETED"
            live.content = "[deleted by owner; content removed]"
            live.title = "[deleted]"
            live.content_hash = content_hash("deleted", memory_id)
            repo.save(live)
            receipt = MemoryDeletionReceiptRepository(session).add(
                MemoryDeletionReceipt(
                    memory_id=memory_id,
                    requested_by=f"{principal.type.value}:{principal.id}",
                    status="COMPLETED" if verified else "COMPLETED_UNVERIFIED_INDEX",
                    index_sync_verified=verified,
                    detail=("embedding row removed and absence verified"
                            if verified else
                            "record removed; index absence could not be verified")))
            result = {"memory_id": memory_id, "status": receipt.status,
                      "index_sync_verified": verified, "detail": receipt.detail,
                      "embedding_removed": removed}
        finally:
            session.close()
        self._audit(principal, "memory.record_deleted", "memory_record",
                    memory_id, "allowed", "owner deletion (receipt-verified)")
        return result

    def _assert_can_modify(self, principal: Principal, row: MemoryRecord) -> None:
        if principal.type in (PrincipalType.OWNER, PrincipalType.SYSTEM):
            return
        scoped = policy.ScopedPrincipal(
            principal, policy.agent_business_ref(self._session_factory, principal))
        if principal.type is PrincipalType.AGENT and policy.can_read(scoped, row) \
                and row.agent_id == principal.id:
            return
        raise PermissionDeniedError(
            "this principal cannot modify this memory record (§18.1)")
