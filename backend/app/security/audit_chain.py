"""Audit hash chain (§19.3): tamper-EVIDENCE for the P-01 audit
trail.

Each seal appends one row per unsealed ``audit_events`` record:
``entry_hash = sha256(previous_hash + canonical_json(event))`` in
the canonical order (created_at, id) — the same order verification
recomputes. Verification walks the whole chain and the live audit
table together and reports the first divergence: a modified row
(hash mismatch), a deleted row (chain entry with no audit row), or
an unsealed tail (reported separately, not as tampering).

Honest limits, per the prompt's own §19.3 caveat: a hash chain
detects tampering; it does not prevent it. An attacker with raw
database write access could rewrite audit rows AND the chain.
Protected storage and backups remain owner concerns; this layer
guarantees that silent, single-sided edits are caught.
"""
from __future__ import annotations

import hashlib
import json

from ..database.models.base import utcnow
from ..database.models.core import AuditEvent
from ..database.models.security import SecurityAuditChain
from ..database.repositories.security import AuditChainRepository, SecurityAuditQuery

GENESIS_HASH = "0" * 64


def canonical_event(event: AuditEvent) -> str:
    """The canonical serialization an audit row is sealed with.
    Field selection is deliberate: everything that gives the record
    its meaning, in a fixed key order, with JSON-safe values."""
    payload = {
        "id": event.id,
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "action": event.action,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "decision": event.decision,
        "reason": event.reason,
        "correlation_id": event.correlation_id,
        "details": event.details or {},
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def entry_hash(previous_hash: str, event: AuditEvent) -> str:
    return hashlib.sha256(
        (previous_hash + canonical_event(event)).encode("utf-8")).hexdigest()


class AuditChainService:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def seal_new_events(self) -> dict:
        """Seal every audit event not yet in the chain. Idempotent:
        sealing twice seals nothing the second time."""
        session = self._session_factory()
        try:
            chain_repo = AuditChainRepository(session)
            last = chain_repo.last()
            previous_hash = last.entry_hash if last else GENESIS_HASH
            seq = last.seq if last else 0
            sealed_ids = chain_repo.sealed_event_ids()
            new_events = [e for e in SecurityAuditQuery(session).all_ordered()
                          if e.id not in sealed_ids]
            sealed = 0
            for event in new_events:
                digest = entry_hash(previous_hash, event)
                seq += 1
                session.add(SecurityAuditChain(
                    seq=seq, audit_event_id=event.id,
                    previous_hash=previous_hash, entry_hash=digest,
                    created_at=utcnow(), updated_at=utcnow()))
                session.commit()
                previous_hash = digest
                sealed += 1
            return {"sealed": sealed, "chain_length": seq,
                    "head_hash": previous_hash}
        finally:
            session.close()

    def verify(self) -> dict:
        """Recompute the chain against the live audit table.

        Returns ok=True only when every sealed entry still matches
        its audit row exactly and the linkage is intact. An audit
        tail that simply hasn't been sealed yet is reported as
        ``unsealed_events`` and does not fail verification."""
        session = self._session_factory()
        try:
            chain = AuditChainRepository(session).all_ordered()
            events = {e.id: e for e in SecurityAuditQuery(session).all_ordered()}
            previous_hash = GENESIS_HASH
            checked = 0
            for entry in chain:
                event = events.get(entry.audit_event_id)
                if event is None:
                    return {"ok": False, "checked": checked,
                            "chain_length": len(chain),
                            "first_mismatch": {
                                "seq": entry.seq,
                                "audit_event_id": entry.audit_event_id,
                                "problem": "audit event missing (deleted)"},
                            "unsealed_events": 0}
                if entry.previous_hash != previous_hash:
                    return {"ok": False, "checked": checked,
                            "chain_length": len(chain),
                            "first_mismatch": {
                                "seq": entry.seq,
                                "audit_event_id": entry.audit_event_id,
                                "problem": "chain linkage broken"},
                            "unsealed_events": 0}
                if entry_hash(previous_hash, event) != entry.entry_hash:
                    return {"ok": False, "checked": checked,
                            "chain_length": len(chain),
                            "first_mismatch": {
                                "seq": entry.seq,
                                "audit_event_id": entry.audit_event_id,
                                "problem": "audit event content changed since sealing"},
                            "unsealed_events": 0}
                previous_hash = entry.entry_hash
                checked += 1
            unsealed = len([e for e in events.values()
                             if e.id not in {c.audit_event_id for c in chain}])
            return {"ok": True, "checked": checked,
                    "chain_length": len(chain), "first_mismatch": None,
                    "unsealed_events": unsealed, "head_hash": previous_hash}
        finally:
            session.close()
