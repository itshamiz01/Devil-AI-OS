"""§8 Business decision engine + §20 controlled autonomy.

A decision is a record: trigger, evidence, metrics (P-07 readings,
referenced not recomputed), risk, expected benefit/cost/downside,
confidence, reversibility, horizon, alternatives (§8.3), an
explanation answering §8.2's ten questions, and an autonomy level
(§20.2). The §8.4 score is decision support only — it never grants
permission. Authorisation flows through the P-01 hash-bound
ApprovalService; Level 4 types (CLOSE) require the Owner principal
AND an owner-decided approval whose binding verifies — an agent has
no path (structural, audit §6). Execution is idempotent: the
``execution_key`` is unique and a second execution returns the
recorded outcome unchanged (§26.3).
"""
from __future__ import annotations

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.base import utcnow
from ..database.models.survival import (
    BusinessDecision, BusinessDecisionAlternative,
)
from ..database.repositories.survival import (
    DecisionAlternativeRepository, DecisionRepository,
)
from ..permissions.models import PrincipalType
from . import constants as C

# Decision types an agent may originate (never CLOSE — Level 4 is
# owner-originated only; agents may *recommend* via REVIEW_FOR_CLOSURE).
AGENT_ORIGINATABLE = set(C.DECISION_TYPES) - {"CLOSE"}


def decision_dict(row: BusinessDecision, alternatives: list) -> dict:
    return {
        "id": row.id, "business_id": row.business_id,
        "decision_type": row.decision_type, "trigger": row.trigger,
        "status": row.status, "autonomy_level": row.autonomy_level,
        "evidence": row.evidence, "metrics": row.metrics,
        "risk_assessment": row.risk_assessment,
        "expected_benefit": row.expected_benefit,
        "estimated_cost_minor": row.estimated_cost_minor,
        "estimated_cost_currency": row.estimated_cost_currency,
        "expected_downside": row.expected_downside,
        "confidence": row.confidence, "reversibility": row.reversibility,
        "time_horizon_days": row.time_horizon_days,
        "score_bps": row.score_bps, "approval_id": row.approval_id,
        "expires_on": row.expires_on,
        "review_conditions": row.review_conditions,
        "explanation": row.explanation,
        "execution_key": row.execution_key,
        "executed_at": row.executed_at,
        "execution_outcome": row.execution_outcome,
        "intelligence_record_id": row.intelligence_record_id,
        "alternatives": [{
            "kind": a.kind, "summary": a.summary,
            "expected_cost_minor": a.expected_cost_minor,
            "expected_downside": a.expected_downside,
            "score_bps": a.score_bps, "recommended": a.recommended,
        } for a in alternatives],
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
    }


class DecisionService:
    def __init__(self, session_factory, approvals, recorder, audit,
                 pause_checker):
        self._session_factory = session_factory
        self._approvals = approvals
        self._recorder = recorder
        self._audit = audit
        self._pause_active = pause_checker  # callable(business_id) -> bool

    # ------------------------------------------------------------- create
    def create_decision(self, principal, business_id: str,
                        data: dict) -> dict:
        decision_type = str(data.get("decision_type") or "").upper()
        if decision_type not in C.DECISION_TYPES:
            raise ValidationError(
                f"unknown decision type {decision_type!r}; supported: "
                f"{sorted(C.DECISION_TYPES)}")
        if principal.type == PrincipalType.AGENT and \
                decision_type not in AGENT_ORIGINATABLE:
            self._audit(principal, "survival.decision_create", "business",
                        business_id, "deny",
                        f"agents cannot originate Level-4 decision "
                        f"{decision_type}")
            raise PermissionDeniedError(
                f"{decision_type} is a Level-4 owner-only decision; an "
                "agent may recommend REVIEW_FOR_CLOSURE instead")
        level = C.AUTONOMY_LEVELS[decision_type]
        explanation = self._explain(decision_type, data)
        session = self._session_factory()
        try:
            repo = DecisionRepository(session)
            row = repo.add(BusinessDecision(
                business_id=business_id, decision_type=decision_type,
                trigger=data.get("trigger") or "",
                status="PROPOSED", autonomy_level=level,
                evidence=data.get("evidence") or [],
                metrics=data.get("metrics") or {},
                risk_assessment=data.get("risk_assessment") or "",
                expected_benefit=data.get("expected_benefit") or "",
                estimated_cost_minor=data.get("estimated_cost_minor"),
                estimated_cost_currency=data.get("estimated_cost_currency"),
                expected_downside=data.get("expected_downside") or "",
                confidence=data.get("confidence") or "low",
                reversibility=data.get("reversibility") or "reversible",
                time_horizon_days=data.get("time_horizon_days"),
                score_bps=data.get("score_bps"),
                expires_on=data.get("expires_on"),
                review_conditions=data.get("review_conditions") or "",
                explanation=explanation,
                created_by=_actor(principal)))
            alt_repo = DecisionAlternativeRepository(session)
            for alt in self._alternatives(decision_type, data):
                alt_repo.add(BusinessDecisionAlternative(
                    decision_id=row.id, kind=alt["kind"],
                    summary=alt["summary"],
                    expected_cost_minor=alt.get("expected_cost_minor"),
                    expected_downside=alt.get("expected_downside") or "",
                    score_bps=alt.get("score_bps"),
                    recommended=bool(alt.get("recommended"))))
            decision_id = row.id
        finally:
            session.close()
        # P-02 decision record: a reference, not a copy (§21).
        if self._recorder is not None:
            record = self._recorder.record(
                "survival_decision", _actor(principal),
                f"{decision_type}: {data.get('trigger') or ''}"[:500],
                evidence={"survival_decision_id": decision_id,
                          "business_id": business_id,
                          "autonomy_level": level})
            session = self._session_factory()
            try:
                row = DecisionRepository(session).get(decision_id)
                row.intelligence_record_id = record.id
                DecisionRepository(session).save(row)
            finally:
                session.close()
        self._audit(principal, "survival.decision_created", "decision",
                    decision_id, "allow",
                    f"{decision_type} level={level}")
        return self.get_decision(decision_id)

    @staticmethod
    def _alternatives(decision_type: str, data: dict) -> list[dict]:
        provided = data.get("alternatives") or []
        if len(provided) >= 3:
            return provided
        # §8.3: compare at least three alternatives where safe. For
        # CLOSE, "invest in expansion" is unsafe/prohibited and is
        # never fabricated as an option.
        base = list(provided)
        kinds = {a.get("kind") for a in base}
        defaults = [
            ("maintain", "Maintain current operations unchanged."),
            ("improve", "Improve the existing business within current "
                        "budgets."),
        ]
        if decision_type != "CLOSE":
            defaults.append(
                ("expand", "Invest in expansion (requires its own "
                           "readiness assessment and approval)."))
        else:
            defaults.append(
                ("pause_and_review", "Pause operations and review "
                                     "again with fresh evidence."))
        for kind, summary in defaults:
            if kind not in kinds and len(base) < 3:
                base.append({"kind": kind, "summary": summary,
                             "recommended": kind == "improve"
                             and decision_type not in ("CLOSE",)})
        if base and not any(a.get("recommended") for a in base):
            base[0]["recommended"] = True
        return base

    @staticmethod
    def _explain(decision_type: str, data: dict) -> dict:
        """§8.2's ten questions, answered from the record itself."""
        return {
            "what_is_happening": data.get("trigger") or "",
            "why_it_matters": data.get("risk_assessment") or "",
            "evidence": data.get("evidence") or [],
            "options": [a.get("kind") for a in
                        (data.get("alternatives") or [])] or
                       ["maintain", "improve", "expand"],
            "recommended_action": decision_type,
            "what_could_go_wrong": data.get("expected_downside") or "",
            "cost": data.get("estimated_cost_minor"),
            "expected_result": data.get("expected_benefit") or "",
            "success_measure": data.get("review_conditions") or "",
            "review_when": data.get("expires_on") or "",
        }

    # -------------------------------------------------------------- reads
    def get_decision(self, decision_id: str) -> dict:
        session = self._session_factory()
        try:
            repo = DecisionRepository(session)
            row = repo.get(decision_id)
            if row is None:
                raise NotFoundError(f"decision {decision_id} not found")
            alts = DecisionAlternativeRepository(session).for_decision(
                decision_id)
            return decision_dict(row, alts)
        finally:
            session.close()

    def list_decisions(self, *, business_id: str | None = None,
                       status: str | None = None, limit: int = 50,
                       offset: int = 0):
        session = self._session_factory()
        try:
            repo = DecisionRepository(session)
            filters = {"status": status} if status else None
            rows, total = repo.list(limit=limit, offset=offset,
                                    business_id=business_id,
                                    filters=filters)
            alt_repo = DecisionAlternativeRepository(session)
            return [decision_dict(r, alt_repo.for_decision(r.id))
                    for r in rows], total
        finally:
            session.close()

    # ----------------------------------------------------------- approval
    def request_approval(self, principal, decision_id: str,
                         reason: str | None = None) -> dict:
        decision = self.get_decision(decision_id)
        action = (C.APPROVAL_ACTION_CLOSE
                  if decision["decision_type"] == "CLOSE"
                  else C.APPROVAL_ACTION_DECISION)
        approval = self._approvals.create(
            principal, action=action, resource=decision["business_id"],
            risk_classification="high"
            if decision["autonomy_level"] >= 3 else "medium",
            reason=reason or
            f"P-08 {decision['decision_type']} decision approval (§8/§20)",
            requested_permissions=["modify_business_data"],
            parameters={"decision_id": decision_id,
                        "decision_type": decision["decision_type"],
                        "business_id": decision["business_id"]})
        session = self._session_factory()
        try:
            repo = DecisionRepository(session)
            row = repo.get(decision_id)
            row.approval_id = approval.id
            row.status = "PENDING_APPROVAL"
            repo.save(row)
        finally:
            session.close()
        return {"approval_id": approval.id, "status": approval.status,
                "action": action, "decision_id": decision_id}

    def _verify_approval(self, decision: dict) -> bool:
        """Hash-bound binding + owner-decided check (P-06 pattern).
        For Level 4 the approver must be the owner; self-approval by
        the originating agent can never satisfy this."""
        approval_id = decision.get("approval_id")
        if not approval_id:
            return False
        try:
            approval = self._approvals.get(approval_id)
        except Exception:
            return False
        action = (C.APPROVAL_ACTION_CLOSE
                  if decision["decision_type"] == "CLOSE"
                  else C.APPROVAL_ACTION_DECISION)
        params = {"decision_id": decision["id"],
                  "decision_type": decision["decision_type"],
                  "business_id": decision["business_id"]}
        if not self._approvals.verify_binding(
                approval, action, decision["business_id"], params):
            return False
        if approval.status != "approved":
            return False
        approver = approval.approver_id or ""
        if decision["autonomy_level"] >= 3:
            return approver.startswith("owner:")
        return bool(approver)

    def review(self, principal, decision_id: str, data: dict) -> dict:
        """Record an approval review. Only an owner-decided, binding-
        verified P-01 approval moves a decision to APPROVED; an
        agent's own 'approval' is refused structurally."""
        decision = self.get_decision(decision_id)
        if data.get("approval_id"):
            session = self._session_factory()
            try:
                repo = DecisionRepository(session)
                row = repo.get(decision_id)
                row.approval_id = data["approval_id"]
                repo.save(row)
            finally:
                session.close()
            decision = self.get_decision(decision_id)
        if not self._verify_approval(decision):
            self._audit(principal, "survival.decision_review", "decision",
                        decision_id, "deny",
                        "approval missing, undecided, drifted, or not "
                        "owner-decided for this level")
            raise PermissionDeniedError(
                "decision approval could not be verified: a hash-bound "
                "P-01 approval, decided by the owner where the level "
                "requires it, is mandatory (§20.2)")
        session = self._session_factory()
        try:
            repo = DecisionRepository(session)
            row = repo.get(decision_id)
            row.status = "APPROVED"
            repo.save(row)
        finally:
            session.close()
        self._audit(principal, "survival.decision_approved", "decision",
                    decision_id, "allow", "approval binding verified")
        return self.get_decision(decision_id)

    def reject(self, principal, decision_id: str, reason: str = "") -> dict:
        session = self._session_factory()
        try:
            repo = DecisionRepository(session)
            row = repo.get(decision_id)
            if row is None:
                raise NotFoundError(f"decision {decision_id} not found")
            if row.status == "EXECUTED":
                raise ValidationError("an executed decision cannot be "
                                      "rejected; record an outcome instead")
            row.status = "REJECTED"
            repo.save(row)
        finally:
            session.close()
        self._audit(principal, "survival.decision_rejected", "decision",
                    decision_id, "allow", reason)
        return self.get_decision(decision_id)

    # ----------------------------------------------------------- execution
    def execute(self, principal, decision_id: str,
                execution_key: str) -> dict:
        """Idempotent execution (§20.1 steps 10–13 as far as P-08's own
        scope reaches: the outcome records what the decision *does*
        inside P-08 — overlay recommendations, plan activations are
        separate owner-gated flows; P-08 never moves money)."""
        if not execution_key:
            raise ValidationError("execution_key is required "
                                  "(idempotency, §25)")
        session = self._session_factory()
        try:
            repo = DecisionRepository(session)
            existing = repo.by_execution_key(execution_key)
            if existing is not None:
                if existing.id != decision_id:
                    raise ValidationError(
                        "execution_key already used for another decision")
                return self.get_decision(existing.id) | {
                    "idempotent_replay": True}
            row = repo.get(decision_id)
            if row is None:
                raise NotFoundError(f"decision {decision_id} not found")
            if row.executed_at is not None:
                return self.get_decision(decision_id) | {
                    "idempotent_replay": True}
            decision = decision_dict(
                row, DecisionAlternativeRepository(session)
                .for_decision(decision_id))
        finally:
            session.close()
        if self._pause_active(decision["business_id"]):
            self._audit(principal, "survival.decision_execute", "decision",
                        decision_id, "deny",
                        "emergency pause active for this business (§25.2)")
            raise PermissionDeniedError(
                "emergency pause is active for this business; new "
                "controlled execution is blocked (§25.2)")
        level = decision["autonomy_level"]
        if level >= 3 and decision["status"] != "APPROVED":
            self._audit(principal, "survival.decision_execute", "decision",
                        decision_id, "deny",
                        f"Level {level} decision executed without a "
                        "verified approval")
            raise PermissionDeniedError(
                f"Level {level} decisions require a verified owner "
                "approval before execution (§20.2)")
        if decision["status"] in ("REJECTED", "EXPIRED", "BLOCKED"):
            raise ValidationError(
                f"decision in status {decision['status']} cannot execute")
        outcome = {
            "executed_by": _actor(principal),
            "executed_at": utcnow().isoformat(),
            "decision_type": decision["decision_type"],
            "effect": "recorded_in_p08",
            "note": "P-08 execution records the authorised decision "
                    "and its P-08-side effects; financial movement is "
                    "outside P-08 (§16.4) and execution of digital "
                    "work runs through P-05 under its own approvals",
        }
        session = self._session_factory()
        try:
            repo = DecisionRepository(session)
            row = repo.get(decision_id)
            row.execution_key = execution_key
            row.executed_at = outcome["executed_at"]
            row.execution_outcome = outcome
            row.status = "EXECUTED"
            repo.save(row)
        finally:
            session.close()
        self._audit(principal, "survival.decision_executed", "decision",
                    decision_id, "allow",
                    f"executed with key {execution_key}")
        return self.get_decision(decision_id) | {"idempotent_replay": False}


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}" if principal else "system"
