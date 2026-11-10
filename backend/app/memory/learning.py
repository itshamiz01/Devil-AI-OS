"""Continuous learning (§11) and business/financial learning (§16).

Learning is extracted from OUTCOMES — P-05 execution results, P-06
business outcomes, P-07 financial references, P-08 decisions and
experiments — by comparing expected vs actual. The confidence rules
are mechanical (§11.4): a record starts LOW/VERY_LOW, grows with
independent observations, and reaches VERIFIED only with >= the
configured minimum observations AND an owner review. An LLM is never
involved in assigning confidence.
"""
from __future__ import annotations

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.memory import LearningRecord
from ..database.repositories.memory import LearningRecordRepository
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from . import policy


def learning_to_dict(row: LearningRecord) -> dict:
    return {
        "id": row.id, "source_type": row.source_type,
        "source_ref": row.source_ref, "business_id": row.business_id,
        "project_ref": row.project_ref, "hypothesis": row.hypothesis,
        "expected_outcome": row.expected_outcome,
        "actual_outcome": row.actual_outcome, "metrics": row.metrics or {},
        "causes": row.causes or [],
        "alternative_explanations": row.alternative_explanations or [],
        "lesson": row.lesson, "confidence": row.confidence,
        "applicability_scope": row.applicability_scope,
        "limitations": row.limitations, "evidence_refs": row.evidence_refs or [],
        "observations": row.observations, "review_status": row.review_status,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class LearningService:
    def __init__(self, session_factory, audit):
        self._session_factory = session_factory
        self._audit = audit

    def analyze(self, principal: Principal, data: dict) -> dict:
        """§11.2 workflow: build a learning record from an outcome.
        Callers supply the source's original objective/expectation and
        the observed actual result; the engine compares and stores —
        it does not invent either side."""
        lesson = (data.get("lesson") or "").strip()
        if not lesson:
            raise ValidationError("a learning record requires a lesson")
        expected = (data.get("expected_outcome") or "").strip()
        actual = (data.get("actual_outcome") or "").strip()
        if not expected or not actual:
            raise ValidationError(
                "learning requires BOTH the expected and the actual "
                "outcome (§11.2 steps 4–6): activity alone teaches nothing")
        observations = int(data.get("observations", 1))
        requested = data.get("confidence") or "LOW"
        confidence = self._cap_confidence(requested, observations,
                                          reviewed=False)
        session = self._session_factory()
        try:
            row = LearningRecordRepository(session).add(LearningRecord(
                source_type=data.get("source_type", "task"),
                source_ref=data.get("source_ref", ""),
                business_id=data.get("business_id"),
                project_ref=data.get("project_ref", ""),
                hypothesis=data.get("hypothesis", ""),
                expected_outcome=expected, actual_outcome=actual,
                metrics=data.get("metrics", {}),
                causes=data.get("causes", []),
                alternative_explanations=data.get("alternative_explanations", []),
                lesson=lesson, confidence=confidence,
                applicability_scope=data.get("applicability_scope", ""),
                limitations=data.get("limitations", ""),
                evidence_refs=data.get("evidence_refs", []),
                observations=observations,
                created_by=f"{principal.type.value}:{principal.id}"))
            result = learning_to_dict(row)
        finally:
            session.close()
        self._audit(principal, "memory.learning_recorded", "learning_record",
                    result["id"], "allowed",
                    f"{result['source_type']}:{result['source_ref']} "
                    f"confidence={confidence}")
        return result

    @staticmethod
    def _cap_confidence(requested: str, observations: int,
                        reviewed: bool) -> str:
        """§11.4 mechanical ceiling: observations bound confidence;
        VERIFIED additionally requires owner review."""
        if requested not in C.CONFIDENCE_BPS:
            raise ValidationError(f"unknown confidence '{requested}'")
        if observations <= 1:
            ceiling = "LOW"
        elif observations == 2:
            ceiling = "MODERATE"
        elif observations < C.VERIFIED_MIN_OBSERVATIONS:
            ceiling = "HIGH"
        else:
            ceiling = "VERIFIED" if reviewed else "HIGH"
        order = C.CONFIDENCE_ORDER
        return requested if order.index(requested) <= order.index(ceiling) \
            else ceiling

    def add_observation(self, principal: Principal, learning_id: str) -> dict:
        session = self._session_factory()
        try:
            repo = LearningRecordRepository(session)
            row = repo.get(learning_id)
            if row is None:
                raise NotFoundError(f"learning record '{learning_id}' not found")
            row.observations += 1
            row.confidence = self._cap_confidence(
                row.confidence, row.observations,
                reviewed=row.review_status == "REVIEWED")
            repo.save(row)
            return learning_to_dict(row)
        finally:
            session.close()

    def review(self, principal: Principal, learning_id: str) -> dict:
        """Owner review (§11.4): with enough observations this is the
        final step to VERIFIED; it never upgrades on its own."""
        if principal.type is not PrincipalType.OWNER:
            raise PermissionDeniedError(
                "learning review is an owner action (§11.4/§17)")
        session = self._session_factory()
        try:
            repo = LearningRecordRepository(session)
            row = repo.get(learning_id)
            if row is None:
                raise NotFoundError(f"learning record '{learning_id}' not found")
            row.review_status = "REVIEWED"
            if row.observations >= C.VERIFIED_MIN_OBSERVATIONS:
                row.confidence = "VERIFIED"
            repo.save(row)
            result = learning_to_dict(row)
        finally:
            session.close()
        self._audit(principal, "memory.learning_reviewed", "learning_record",
                    learning_id, "allowed", f"confidence={result['confidence']}")
        return result

    def get(self, principal: Principal, learning_id: str) -> dict:
        session = self._session_factory()
        try:
            row = LearningRecordRepository(session).get(learning_id)
            if row is None:
                raise NotFoundError(f"learning record '{learning_id}' not found")
            scoped = policy.ScopedPrincipal(
                principal, policy.agent_business_ref(self._session_factory, principal))
            if not policy.can_read_learning(scoped, row):
                raise PermissionDeniedError(
                    "this learning record belongs to another business (§16/§18.1)")
            return learning_to_dict(row)
        finally:
            session.close()

    def list(self, principal: Principal, *, limit: int = 50, offset: int = 0,
             business_id: str | None = None) -> tuple[list, int]:
        session = self._session_factory()
        try:
            rows, _ = LearningRecordRepository(session).list(
                limit=1000, offset=0,
                filters={"business_id": business_id} if business_id else None)
            scoped = policy.ScopedPrincipal(
                principal, policy.agent_business_ref(self._session_factory, principal))
            visible = [r for r in rows if policy.can_read_learning(scoped, r)]
            return [learning_to_dict(r) for r in visible[offset:offset + limit]], len(visible)
        finally:
            session.close()

    # ------------------------------------------------- §16 integrations
    def from_experiment(self, principal: Principal, experiment_id: str,
                        data: dict) -> dict:
        """Learn from a P-08 experiment outcome, referencing — never
        copying — the experiment and its P-07-backed evaluation."""
        session = self._session_factory()
        try:
            from ..database.models.survival import BusinessExperiment
            experiment = session.get(BusinessExperiment, experiment_id)
            if experiment is None:
                raise NotFoundError(f"P-08 experiment '{experiment_id}' not found")
            business_id = experiment.business_id
            hypothesis = experiment.hypothesis
            expected = experiment.expected_outcome
        finally:
            session.close()
        return self.analyze(principal, {
            **data, "source_type": "experiment", "source_ref": experiment_id,
            "business_id": data.get("business_id", business_id),
            "hypothesis": data.get("hypothesis", hypothesis),
            "expected_outcome": data.get("expected_outcome", expected)})

    def from_decision(self, principal: Principal, decision_id: str,
                      data: dict) -> dict:
        """§16.3 decision learning: original recommendation, evidence
        and approval are referenced from P-08; quality is judged with
        the outcome, not by the outcome alone (alternatives kept)."""
        session = self._session_factory()
        try:
            from ..database.models.survival import BusinessDecision
            decision = session.get(BusinessDecision, decision_id)
            if decision is None:
                raise NotFoundError(f"P-08 decision '{decision_id}' not found")
            business_id = decision.business_id
            expected = decision.expected_benefit
        finally:
            session.close()
        return self.analyze(principal, {
            **data, "source_type": "decision", "source_ref": decision_id,
            "business_id": data.get("business_id", business_id),
            "expected_outcome": data.get("expected_outcome", expected)})

    def financial_reference(self, principal: Principal, ref: str) -> dict:
        """§16.2: resolve a P-07 reference WITHOUT copying it. Returns
        existence + table only; figures stay in P-07, which remains
        the authoritative financial source."""
        from sqlalchemy import text as sa_text
        session = self._session_factory()
        try:
            for table in ("revenue_records", "expense_records",
                          "journal_entries", "financial_forecasts"):
                found = session.execute(
                    sa_text(f"SELECT 1 FROM {table} WHERE id = :ref LIMIT 1"),
                    {"ref": ref}).first()
                if found:
                    return {"reference": ref, "found": True, "source": f"p07.{table}",
                            "authoritative_source": "p07",
                            "note": "P-09 stores the reference only; the "
                                    "financial record itself remains in P-07 (§16.2)"}
            return {"reference": ref, "found": False, "source": None,
                    "authoritative_source": "p07",
                    "note": "no P-07 record with this id — the reference is "
                            "reported unresolved, never fabricated"}
        finally:
            session.close()
