"""§13 Business recovery + §14 pause and closure.

Recovery plans have a finite budget and review period with success
and failure thresholds — an unprofitable business never consumes
resources indefinitely under the label of recovery (§13.3). Root
cause classification distinguishes temporary operational problems
from structural model failure (§13.2/§21.1).

Closure is a staged workflow (§14.3) whose obligation inventory —
liabilities, unpaid invoices, refund obligations, subscriptions,
assets, all as verbatim P-07/P-06 readings — must exist BEFORE a
recommendation is made. Permanent closure is autonomy Level 4:
owner-only, hash-bound approval, executed through the P-06 lifecycle
(→ ARCHIVED). Closure never deletes history (§14.4): financial
records, lifecycle events, experiments and learning records all
remain readable after closure.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.survival import ClosureReview, RecoveryPlan
from ..database.repositories.survival import (
    ClosureReviewRepository, RecoveryPlanRepository,
)
from ..permissions.models import PrincipalType
from . import constants as C


def recovery_dict(row: RecoveryPlan) -> dict:
    return {
        "id": row.id, "business_id": row.business_id,
        "status": row.status, "root_cause": row.root_cause,
        "failure_kind": row.failure_kind,
        "financial_impact": row.financial_impact,
        "corrective_actions": row.corrective_actions,
        "responsible_agents": row.responsible_agents,
        "budget_minor": row.budget_minor, "currency": row.currency,
        "timeline_days": row.timeline_days,
        "expected_outcome": row.expected_outcome,
        "success_thresholds": row.success_thresholds,
        "failure_thresholds": row.failure_thresholds,
        "escalation_rules": row.escalation_rules,
        "review_on": row.review_on, "outcome": row.outcome,
        "approval_id": row.approval_id, "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
    }


def closure_dict(row: ClosureReview) -> dict:
    return {
        "id": row.id, "business_id": row.business_id, "stage": row.stage,
        "reason": row.reason, "inventory": row.inventory,
        "risk_notes": row.risk_notes,
        "recommendation": row.recommendation,
        "approval_id": row.approval_id, "wind_down": row.wind_down,
        "decision_id": row.decision_id, "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
    }


class RecoveryService:
    def __init__(self, session_factory, financial, business, monitoring,
                 audit):
        self._session_factory = session_factory
        self._financial = financial
        self._business = business
        self._monitoring = monitoring
        self._audit = audit

    # ------------------------------------------------------------ recovery
    def create_plan(self, principal, business_id: str,
                    data: dict) -> dict:
        self._business.get_business(business_id)
        budget = int(data.get("budget_minor") or 0)
        timeline = int(data.get("timeline_days") or 0)
        if budget < 0:
            raise ValidationError("recovery budget cannot be negative")
        if timeline <= 0:
            raise ValidationError(
                "a recovery plan must have a finite review period "
                "(§13.3)")
        if not data.get("success_thresholds") or \
                not data.get("failure_thresholds"):
            raise ValidationError(
                "success and failure thresholds are required: "
                "recovery is judged against declared criteria, "
                "never open-ended (§13.3)")
        reading = self._monitoring.collect(business_id)
        indicators = reading.get("indicators") or {}
        session = self._session_factory()
        try:
            row = RecoveryPlanRepository(session).add(RecoveryPlan(
                business_id=business_id, status="PROPOSED",
                root_cause=data.get("root_cause") or "",
                failure_kind=data.get("failure_kind") or "unknown",
                financial_impact={
                    "indicators": indicators,
                    "note": "verbatim P-07 readings at assessment "
                            "time; P-08 computes no financial figure"},
                corrective_actions=data.get("corrective_actions") or [],
                responsible_agents=data.get("responsible_agents") or [],
                budget_minor=budget,
                currency=data.get("currency") or "INR",
                timeline_days=timeline,
                expected_outcome=data.get("expected_outcome") or "",
                success_thresholds=data["success_thresholds"],
                failure_thresholds=data["failure_thresholds"],
                escalation_rules=data.get("escalation_rules") or "",
                review_on=(date.today()
                           + timedelta(days=timeline)).isoformat(),
                created_by=_actor(principal)))
            result = recovery_dict(row)
        finally:
            session.close()
        self._audit(principal, "survival.recovery_plan_created",
                    "recovery_plan", result["id"], "allow",
                    f"budget={budget} timeline={timeline}d")
        return result

    def conclude_plan(self, principal, plan_id: str,
                      outcome: str) -> dict:
        if outcome not in C.RECOVERY_OUTCOMES:
            raise ValidationError(
                f"unknown recovery outcome {outcome!r}; supported: "
                f"{C.RECOVERY_OUTCOMES}")
        session = self._session_factory()
        try:
            repo = RecoveryPlanRepository(session)
            row = repo.get(plan_id)
            if row is None:
                raise NotFoundError(f"recovery plan {plan_id} not found")
            if row.outcome is not None:
                raise ValidationError(
                    "recovery plan already concluded; outcomes are "
                    "history and are not rewritten (§13.4)")
            row.outcome = outcome
            row.status = "CONCLUDED"
            repo.save(row)
            result = recovery_dict(row)
        finally:
            session.close()
        self._audit(principal, "survival.recovery_concluded",
                    "recovery_plan", plan_id, "allow", outcome)
        return result

    def list_plans(self, *, business_id: str | None = None,
                   limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = RecoveryPlanRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [recovery_dict(r) for r in rows], total
        finally:
            session.close()


class ClosureService:
    def __init__(self, session_factory, financial, business, approvals,
                 audit):
        self._session_factory = session_factory
        self._financial = financial
        self._business = business
        self._approvals = approvals
        self._audit = audit

    # ------------------------------------------------------------- staging
    def _inventory(self, business_id: str) -> dict:
        """§14.2 closure inventory: every figure is a verbatim P-07
        reading; assets and obligations from P-06 records."""
        profile = self._financial.get_profile(business_id)
        inventory: dict = {"business_id": business_id}
        business = self._business.get_business(business_id)
        inventory["p06_status"] = business["status"]
        inventory["is_fixture"] = business["is_fixture"]
        assets = self._business.list_assets(business_id)
        inventory["asset_count"] = len(assets[0]) if isinstance(
            assets, tuple) else len(assets)
        if profile is None:
            inventory["financial_profile_missing"] = True
            return inventory
        currency = profile["base_currency"]
        summary = self._financial.business_summary(business_id)
        metrics = summary["revenue"]
        available = summary["available_cash"]
        inventory.update({
            "currency": currency,
            "outstanding_receivables_minor":
                metrics["outstanding_receivables_minor"],
            "disputed_open_minor": metrics["disputed_open_minor"],
            "obligations_minor": available["obligations_minor"],
            "protected_reserves_minor":
                available["protected_reserves_minor"],
            "committed_minor": available["committed_minor"],
            "cash_balance_minor": available["cash_balance_minor"],
            "verified_collected_revenue_minor":
                metrics["net_collected_minor"],
            "mrr_minor": metrics["mrr_minor"],
            "financial_health": summary["health"]["status"],
            "source": "p07.business_summary (verbatim readings)",
        })
        return inventory

    def propose(self, principal, business_id: str, reason: str) -> dict:
        self._business.get_business(business_id)
        inventory = self._inventory(business_id)
        blockers = []
        if inventory.get("outstanding_receivables_minor"):
            blockers.append("unpaid invoices / outstanding receivables "
                            "remain")
        if inventory.get("disputed_open_minor"):
            blockers.append("open disputes remain")
        if inventory.get("obligations_minor"):
            blockers.append("outstanding obligations remain")
        if inventory.get("mrr_minor"):
            blockers.append("active subscription revenue exists (MRR "
                            "> 0): customers may hold obligations")
        recommendation = (
            "OBLIGATIONS_MUST_BE_RESOLVED_FIRST" if blockers else
            "READY_FOR_OWNER_DECISION")
        session = self._session_factory()
        try:
            row = ClosureReviewRepository(session).add(ClosureReview(
                business_id=business_id, stage="PROPOSED_CLOSURE",
                reason=reason, inventory=inventory,
                risk_notes="; ".join(blockers),
                recommendation=recommendation,
                created_by=_actor(principal)))
            result = closure_dict(row)
        finally:
            session.close()
        self._audit(principal, "survival.closure_proposed",
                    "closure_review", result["id"], "allow",
                    recommendation)
        return result

    def advance(self, principal, review_id: str) -> dict:
        session = self._session_factory()
        try:
            repo = ClosureReviewRepository(session)
            row = repo.get(review_id)
            if row is None:
                raise NotFoundError(f"closure review {review_id} not found")
            stage = row.stage
        finally:
            session.close()
        order = C.CLOSURE_STAGES
        if stage in ("CLOSED", "ARCHIVED"):
            raise ValidationError("closure review is complete")
        if stage == "OWNER_APPROVAL":
            raise ValidationError(
                "the OWNER_APPROVAL stage completes only through "
                "execute_closure with a verified owner approval "
                "(Level 4, §14.4)")
        next_stage = order[order.index(stage) + 1]
        if next_stage == "WIND_DOWN":
            raise ValidationError(
                "wind-down begins only after owner approval "
                "(execute_closure)")
        session = self._session_factory()
        try:
            repo = ClosureReviewRepository(session)
            row = repo.get(review_id)
            row.stage = next_stage
            if next_stage == "FINANCIAL_REVIEW":
                row.inventory = self._inventory(row.business_id)
            repo.save(row)
            result = closure_dict(row)
        finally:
            session.close()
        self._audit(principal, "survival.closure_advanced",
                    "closure_review", review_id, "allow",
                    f"{stage} -> {next_stage}")
        return result

    # ------------------------------------------------------- Level 4 close
    async def execute_closure(self, principal, review_id: str,
                              approval_id: str | None) -> dict:
        """Permanent closure. Level 4 (§20.2): owner principal +
        hash-bound approval decided by the owner. Wind-down preserves
        all history; the P-06 business is archived through its own
        validated transition path."""
        if principal.type != PrincipalType.OWNER:
            self._audit(principal, "survival.closure_execute",
                        "closure_review", review_id, "deny",
                        "permanent closure is Level 4 owner-only")
            raise PermissionDeniedError(
                "permanent closure is a Level 4 decision: only the "
                "owner may execute it (§3.3/§14.4)")
        session = self._session_factory()
        try:
            repo = ClosureReviewRepository(session)
            row = repo.get(review_id)
            if row is None:
                raise NotFoundError(f"closure review {review_id} not found")
            if row.stage in ("CLOSED", "ARCHIVED"):
                return closure_dict(row) | {"idempotent_replay": True}
            if row.stage != "OWNER_APPROVAL":
                raise ValidationError(
                    f"closure review is at {row.stage}; it must pass "
                    "RISK_REVIEW, FINANCIAL_REVIEW and "
                    "CUSTOMER_OBLIGATION_REVIEW before OWNER_APPROVAL")
            business_id = row.business_id
            inventory = row.inventory
        finally:
            session.close()
        if approval_id is None:
            approval = self._approvals.create(
                principal, action=C.APPROVAL_ACTION_CLOSE,
                resource=business_id, risk_classification="high",
                reason="P-08 permanent business closure (§14)",
                requested_permissions=["modify_business_data"],
                parameters={"closure_review_id": review_id,
                            "business_id": business_id})
            self._approvals.decide(approval.id, principal, True)
            approval_id = approval.id
        else:
            try:
                approval = self._approvals.get(approval_id)
            except Exception:
                approval = None
            ok = bool(approval) and self._approvals.verify_binding(
                approval, C.APPROVAL_ACTION_CLOSE, business_id,
                {"closure_review_id": review_id,
                 "business_id": business_id}) \
                and approval.status == "approved" \
                and (approval.approver_id or "").startswith("owner:")
            if not ok:
                self._audit(principal, "survival.closure_execute",
                            "closure_review", review_id, "deny",
                            "approval binding invalid or not owner-decided")
                raise PermissionDeniedError(
                    "closure requires a hash-bound approval decided "
                    "by the owner (Level 4)")
        wind_down = {
            "new_sales_disabled": True,
            "new_acquisition_stopped": True,
            "financial_history_preserved": True,
            "business_records_preserved": True,
            "inventory_at_closure": inventory,
            "note": "wind-down preserves financial history and "
                    "business records permanently; nothing is "
                    "deleted (§14.4)",
        }
        # Move the P-06 business to ARCHIVED via its validated paths.
        business = self._business.get_business(business_id)
        status = business["status"]
        if status != "ARCHIVED":
            if status == "OPERATIONAL":
                await self._business.transition_business(
                    principal, business_id, "ARCHIVED",
                    reason="P-08 closure wind-down (§14.4)")
            elif status in ("BLOCKED", "FAILED", "PAUSED"):
                if status == "PAUSED":
                    # PAUSED returns only to paused_from; archive via
                    # the recorded return state is not guaranteed —
                    # record the limit honestly instead of forcing it.
                    wind_down["p06_archive_note"] = (
                        "business is PAUSED in P-06; its machine "
                        "returns only to the pre-pause state, so the "
                        "P-06 row keeps its state and the closure is "
                        "recorded as the P-08 CLOSED overlay")
                else:
                    await self._business.transition_business(
                        principal, business_id, "ARCHIVED",
                        reason="P-08 closure wind-down (§14.4)")
            else:
                await self._business.transition_business(
                    principal, business_id, "BLOCKED",
                    reason="P-08 closure wind-down (§14.4)")
                await self._business.transition_business(
                    principal, business_id, "ARCHIVED",
                    reason="P-08 closure wind-down (§14.4)")
        session = self._session_factory()
        try:
            repo = ClosureReviewRepository(session)
            row = repo.get(review_id)
            row.stage = "CLOSED"
            row.approval_id = approval_id
            row.wind_down = wind_down
            repo.save(row)
            result = closure_dict(row)
        finally:
            session.close()
        self._audit(principal, "survival.closure_executed",
                    "closure_review", review_id, "allow",
                    "business closed (Level 4); history preserved")
        return result

    def get_review(self, review_id: str) -> dict:
        session = self._session_factory()
        try:
            row = ClosureReviewRepository(session).get(review_id)
            if row is None:
                raise NotFoundError(f"closure review {review_id} not found")
            return closure_dict(row)
        finally:
            session.close()

    def list_reviews(self, *, business_id: str | None = None,
                     limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = ClosureReviewRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [closure_dict(r) for r in rows], total
        finally:
            session.close()


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}" if principal else "system"
