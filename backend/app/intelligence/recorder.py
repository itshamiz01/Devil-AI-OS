"""Decision recorder (P-02): every CIO decision becomes a decision_records
row. Security-relevant decisions additionally write an append-only
audit_events row through the P-01 AuditRepository."""
from __future__ import annotations

from ..database.models.base import utcnow
from ..database.models.core import AuditEvent
from ..database.models.intelligence import DecisionRecord
from ..database.repositories.core import AuditRepository
from ..database.repositories.intelligence import DecisionRecordRepository

# Decision types that must also appear in the P-01 audit trail.
AUDITED_TYPES = {
    "injection_detected", "plan_rejected", "plan_tampered",
    "execution_blocked_mode", "execution_blocked_unapproved",
    "permission_denied_at_execution", "model_profile_updated",
    "model_profile_edit_denied",
}


class DecisionRecorder:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def record(self, decision_type: str, actor: str, reason: str,
               mission_id: str | None = None, plan_id: str | None = None,
               step_id: str | None = None, evidence: dict | None = None,
               correlation_id: str | None = None) -> DecisionRecord:
        session = self._session_factory()
        try:
            record = DecisionRecordRepository(session).add(DecisionRecord(
                mission_id=mission_id, plan_id=plan_id, step_id=step_id,
                decision_type=decision_type, actor=actor, reason=reason,
                evidence=evidence or {}, correlation_id=correlation_id))
            if decision_type in AUDITED_TYPES:
                AuditRepository(session).add(AuditEvent(
                    actor_type="system", actor_id="intelligence",
                    action=f"intelligence.{decision_type}",
                    target_type="mission" if mission_id else "plan",
                    target_id=mission_id or plan_id,
                    decision="deny" if "denied" in decision_type or "blocked" in decision_type
                    or decision_type in ("plan_rejected", "plan_tampered", "injection_detected")
                    else "recorded",
                    reason=reason, correlation_id=correlation_id,
                    details={"decision_record_id": record.id, "evidence": evidence or {}},
                    created_at=utcnow()))
            return record
        finally:
            session.close()

    def list(self, mission_id: str | None = None, plan_id: str | None = None,
             limit: int = 200, offset: int = 0):
        session = self._session_factory()
        try:
            return DecisionRecordRepository(session).list(mission_id, plan_id, limit, offset)
        finally:
            session.close()
