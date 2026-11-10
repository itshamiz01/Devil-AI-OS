"""§10 Scaling readiness + §10.4 incremental plans + §11 growth and
§12 cost proposals.

Readiness criteria are configuration (owner-governed settings),
seeded per P-06 business category — a SaaS business and a content
business do not share identical requirements (§10.2). Every
criterion is checked against P-07 readings (via the monitoring
collect + health snapshot), P-06 records, commercial counts or
provenance-carrying observations. Hard gates from the health
snapshot block scaling regardless of satisfied criteria (§7.3).

Plans are incremental by construction: one step may propose at most
``max_increment_ratio`` over the current P-07 budget figure, and the
increase may not exceed P-07 available capital. A 5x jump is
structurally impossible (§10.4). Approving a plan moves no money and
changes no P-07 budget (§16.4) — it records an authorised proposal.
"""
from __future__ import annotations

from decimal import Decimal

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.survival import ScalingAssessment, ScalingPlan
from ..database.repositories.survival import (
    ScalingAssessmentRepository, ScalingPlanRepository,
)
from ..permissions.models import PrincipalType
from . import constants as C


def assessment_dict(row: ScalingAssessment) -> dict:
    return {
        "id": row.id, "business_id": row.business_id,
        "status": row.status, "stage": row.stage,
        "category": row.category, "satisfied": row.satisfied,
        "unsatisfied": row.unsatisfied, "hard_gates": row.hard_gates,
        "confidence": row.confidence,
        "financial_impact": row.financial_impact,
        "capacity_requirements": row.capacity_requirements,
        "downside_scenario": row.downside_scenario,
        "approval_requirements": row.approval_requirements,
        "snapshot_id": row.snapshot_id, "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
    }


def plan_dict(row: ScalingPlan) -> dict:
    return {
        "id": row.id, "business_id": row.business_id,
        "assessment_id": row.assessment_id, "status": row.status,
        "budget_id": row.budget_id,
        "current_amount_minor": row.current_amount_minor,
        "proposed_amount_minor": row.proposed_amount_minor,
        "currency": row.currency,
        "increment_ratio_bps": row.increment_ratio_bps,
        "clamped": row.clamped,
        "success_conditions": row.success_conditions,
        "stop_conditions": row.stop_conditions,
        "approval_id": row.approval_id, "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
        "note": "an approved plan is an authorised proposal; applying "
                "it to a P-07 budget is an owner action in P-07 — "
                "P-08 moves no money (§16.4)",
    }


class ScalingService:
    def __init__(self, session_factory, financial, business, monitoring,
                 health, settings_getter, audit, approvals=None):
        self._session_factory = session_factory
        self._financial = financial
        self._business = business
        self._monitoring = monitoring
        self._health = health
        self._settings = settings_getter
        self._audit = audit
        self._approvals = approvals

    # --------------------------------------------------------- assessment
    def assess(self, principal, business_id: str, snapshot: dict) -> dict:
        business = self._business.get_business(business_id)
        category = business.get("category") or "digital_products"
        settings = self._settings()
        criteria = settings["scaling_criteria"].get(
            category, settings["scaling_criteria"]["digital_products"])
        reading = self._monitoring.collect(business_id)
        indicators = reading.get("indicators") or {}
        summary = reading.get("summary") or {}
        metrics = summary.get("revenue") or {}
        counts = reading.get("counts") or {}
        collected = indicators.get("verified_collected_revenue_minor") or 0
        profit = indicators.get("profitability") or {}
        observations = self._monitoring.latest_observations(business_id)

        satisfied: list[dict] = []
        unsatisfied: list[dict] = []

        def check(key, ok, detail, source):
            (satisfied if ok else unsatisfied).append(
                {"condition": key, "detail": detail, "source": source})

        check("verified_collected_revenue", collected > 0,
              f"P-07 verified collected revenue = {collected} minor",
              "p07.p08_indicators")
        with_revenue = self._health.snapshots_with_revenue(business_id)
        check("sustained_demand",
              with_revenue >= criteria["min_snapshots_with_revenue"],
              f"{with_revenue} health snapshot(s) show verified "
              f"collected revenue; requires "
              f"{criteria['min_snapshots_with_revenue']} (§5.2: one "
              "good week is not scaling evidence)",
              "p08.health_snapshots")
        check("distinct_customers",
              counts.get("distinct_customers", 0)
              >= criteria["min_distinct_customers"],
              f"distinct paying customers = "
              f"{counts.get('distinct_customers', 0)}; requires "
              f"{criteria['min_distinct_customers']}",
              "p07.revenue.list_revenue.counts")
        check("repeat_customers",
              counts.get("repeat_customers", 0)
              >= criteria["min_repeat_customers"],
              f"repeat customers = {counts.get('repeat_customers', 0)};"
              f" requires {criteria['min_repeat_customers']}",
              "p07.revenue.list_revenue.counts")
        gross_profit = (summary.get("profitability") or {}).get(
            "gross_profit_minor")
        check("positive_contribution",
              (not criteria["require_positive_contribution"])
              or (gross_profit is not None and gross_profit >= 0
                  and profit.get("status") == "computed"),
              f"P-07 gross profit = {gross_profit} minor "
              f"(status {profit.get('status')})",
              "p07.analytics.profitability")
        gross = metrics.get("collected_gross_minor") or 0
        refund_rate = (Decimal(metrics.get("refunds_minor") or 0)
                       / Decimal(gross)) if gross else None
        check("refund_rate",
              refund_rate is not None
              and refund_rate <= Decimal(criteria["max_refund_rate"]),
              f"refund rate = {refund_rate}; max "
              f"{criteria['max_refund_rate']} (ratio of P-07 figures)",
              "p07.revenue.metrics")
        chargeback_rate = (Decimal(metrics.get("chargebacks_minor") or 0)
                           / Decimal(gross)) if gross else None
        check("chargeback_rate",
              chargeback_rate is not None
              and chargeback_rate <= Decimal(criteria["max_chargeback_rate"]),
              f"chargeback rate = {chargeback_rate}; max "
              f"{criteria['max_chargeback_rate']}",
              "p07.revenue.metrics")
        ops = observations.get("operations")
        delivery_rate = (ops or {}).get("metrics", {}).get(
            "delivery_completion_rate")
        check("delivery_reliability",
              (not criteria["require_delivery_evidence"])
              or (delivery_rate is not None
                  and Decimal(str(delivery_rate)) >= Decimal("0.8")),
              f"delivery completion rate = {delivery_rate}",
              "p08.observation.operations")
        if criteria.get("require_mrr"):
            commercial = observations.get("commercial") or {}
            subs = commercial.get("metrics", {}).get(
                "active_subscriptions")
            check("subscription_base",
                  (metrics.get("mrr_minor") or 0) > 0
                  and subs is not None
                  and int(subs) >= criteria["min_active_subscriptions"],
                  f"P-07 MRR = {metrics.get('mrr_minor')} minor; "
                  f"observed active subscriptions = {subs}; requires "
                  f"{criteria['min_active_subscriptions']} (software "
                  "criteria set, §10.2)",
                  "p07.revenue.metrics + p08.observation.commercial")
        available = indicators.get("available_capital_minor") or 0
        check("available_capital", available > 0,
              f"P-07 available capital = {available} minor",
              "p07.p08_indicators")
        check("health_classification",
              snapshot["classification"] in ("STABLE", "HEALTHY",
                                             "EXCELLENT"),
              f"health classification = {snapshot['classification']}",
              "p08.health_snapshot")
        blocking_gates = [g for g in snapshot.get("hard_gates", [])
                          if g.get("blocks_scaling")]
        check("no_blocking_hard_gates", not blocking_gates,
              f"blocking gates: {[g['gate'] for g in blocking_gates]}",
              "p08.health_snapshot.hard_gates")

        stage = self._stage(collected, satisfied, metrics)
        if blocking_gates:
            status = "BLOCKED"
        elif not unsatisfied:
            status = "READY"
        else:
            status = "NOT_READY"
        confidence = snapshot.get("confidence", "low")
        downside = (
            "Downside: scaling spend is committed before demand is "
            "re-verified; if the unsatisfied conditions reflect real "
            "demand weakness, the increment converts directly into "
            "loss. Unsatisfied: "
            + ", ".join(u["condition"] for u in unsatisfied)
            if unsatisfied else
            "Downside: even with all criteria met, the increment is "
            "capped (§10.4) and results must be measured before any "
            "further increase is proposed.")
        session = self._session_factory()
        try:
            row = ScalingAssessmentRepository(session).add(
                ScalingAssessment(
                    business_id=business_id, status=status, stage=stage,
                    category=category, satisfied=satisfied,
                    unsatisfied=unsatisfied,
                    hard_gates=snapshot.get("hard_gates", []),
                    confidence=confidence,
                    financial_impact={
                        "indicators": indicators,
                        "note": "verbatim P-07 readings; P-08 computes "
                                "no financial figure"},
                    capacity_requirements=(
                        "agent and infrastructure capacity are checked "
                        "by the resource proposal flow (§17); the "
                        "owner's hardware profile allows "
                        f"{settings['max_concurrent_agents']} concurrent "
                        "agents and "
                        f"{settings['inference_slots']} inference "
                        "slot(s)"),
                    downside_scenario=downside,
                    approval_requirements=(
                        "SCALE decisions are autonomy Level 3: a "
                        "hash-bound owner approval is required before "
                        "any plan is approved (§20.2)"),
                    snapshot_id=snapshot["id"],
                    created_by=_actor(principal)))
            result = assessment_dict(row)
        finally:
            session.close()
        self._audit(principal, "survival.scaling_assessed", "business",
                    business_id, "allow",
                    f"status={status} stage={stage}")
        return result

    @staticmethod
    def _stage(collected: int, satisfied: list[dict],
               metrics: dict) -> int:
        keys = {s["condition"] for s in satisfied}
        if collected <= 0:
            return 0
        if "sustained_demand" not in keys:
            return 1
        if "repeat_customers" not in keys or \
                "distinct_customers" not in keys:
            return 2
        if "positive_contribution" not in keys or \
                "delivery_reliability" not in keys:
            return 2
        if len(satisfied) < 8:
            return 3
        by_channel = metrics.get("by_channel_minor") or {}
        if len(by_channel) >= 2:
            return 5
        return 4

    def latest_assessment(self, business_id: str) -> dict | None:
        session = self._session_factory()
        try:
            row = ScalingAssessmentRepository(session).latest_for(
                business_id)
            return assessment_dict(row) if row else None
        finally:
            session.close()

    # -------------------------------------------------------------- plans
    def create_plan(self, principal, business_id: str,
                    data: dict) -> dict:
        assessment = self.latest_assessment(business_id)
        if assessment is None:
            raise ValidationError(
                "a scaling assessment is required before a plan "
                "(§10.3)")
        if assessment["status"] != "READY":
            raise ValidationError(
                f"scaling is {assessment['status']}: critical "
                "conditions are unsatisfied, so scaling is blocked or "
                "limited to a specifically approved experiment (§10.3)")
        budget_id = data.get("budget_id")
        if not budget_id:
            raise ValidationError("budget_id (a P-07 budget) is required")
        utilisation = self._financial.budgets.budget_utilisation(
            budget_id)
        if utilisation["business_id"] not in (None, business_id):
            raise ValidationError("budget belongs to another business")
        current = utilisation["approved_minor"]
        currency = utilisation["currency"]
        proposed = int(data.get("proposed_amount_minor") or 0)
        if proposed <= current:
            raise ValidationError(
                "a scaling plan must propose an increase over the "
                "current P-07 budget figure")
        settings = self._settings()
        cap_ratio = Decimal(settings["max_increment_ratio"])
        max_proposed = current + int(
            (Decimal(current) * cap_ratio).to_integral_value())
        indicators = self._financial.p08_indicators(business_id)
        available = indicators["available_capital_minor"] or 0
        capital_cap = current + available
        clamped = False
        if proposed > max_proposed:
            if data.get("strict"):
                raise ValidationError(
                    f"proposed increase exceeds the §10.4 increment "
                    f"cap ({cap_ratio} per step): max {max_proposed} "
                    f"minor. A budget never jumps multiples in one "
                    "step.")
            proposed = max_proposed
            clamped = True
        if proposed > capital_cap:
            if data.get("strict"):
                raise ValidationError(
                    "the increase exceeds P-07 available capital")
            proposed = capital_cap
            clamped = True
        if proposed <= current:
            raise ValidationError(
                "no headroom: available capital does not cover any "
                "increment over the current budget")
        ratio_bps = int(
            (Decimal(proposed - current) / Decimal(current) * 10000)
            .to_integral_value()) if current else 0
        session = self._session_factory()
        try:
            row = ScalingPlanRepository(session).add(ScalingPlan(
                business_id=business_id, assessment_id=assessment["id"],
                status="PROPOSED", budget_id=budget_id,
                current_amount_minor=current,
                proposed_amount_minor=proposed, currency=currency,
                increment_ratio_bps=ratio_bps, clamped=clamped,
                success_conditions=data.get("success_conditions") or "",
                stop_conditions=data.get("stop_conditions") or "",
                created_by=_actor(principal)))
            result = plan_dict(row)
        finally:
            session.close()
        self._audit(principal, "survival.scaling_plan_created",
                    "scaling_plan", result["id"], "allow",
                    f"{current} -> {proposed} {currency} "
                    f"clamped={clamped}")
        return result

    def approve_plan(self, principal, plan_id: str) -> dict:
        if principal.type != PrincipalType.OWNER:
            raise PermissionDeniedError(
                "scaling plans are Level 3: only the owner may approve "
                "them (§20.2)")
        session = self._session_factory()
        try:
            repo = ScalingPlanRepository(session)
            row = repo.get(plan_id)
            if row is None:
                raise NotFoundError(f"scaling plan {plan_id} not found")
            if row.status != "PROPOSED":
                raise ValidationError(
                    f"plan in status {row.status} cannot be approved")
            approval = self._approvals_create(
                principal, row.business_id,
                {"plan_id": plan_id, "business_id": row.business_id,
                 "proposed_amount_minor": row.proposed_amount_minor})
            row.approval_id = approval
            row.status = "APPROVED"
            repo.save(row)
            result = plan_dict(row)
        finally:
            session.close()
        self._audit(principal, "survival.scaling_plan_approved",
                    "scaling_plan", plan_id, "allow",
                    "proposal approved; no P-07 budget changed (§16.4)")
        return result

    def _approvals_create(self, principal, business_id: str,
                          params: dict) -> str:
        approval = self._approvals.create(
            principal, action=C.APPROVAL_ACTION_DECISION,
            resource=business_id, risk_classification="high",
            reason="P-08 scaling plan approval (§10.3/§20.2)",
            requested_permissions=["modify_business_data"],
            parameters=params)
        self._approvals.decide(approval.id, principal, True)
        return approval.id

    def get_plan(self, plan_id: str) -> dict:
        session = self._session_factory()
        try:
            row = ScalingPlanRepository(session).get(plan_id)
            if row is None:
                raise NotFoundError(f"scaling plan {plan_id} not found")
            return plan_dict(row)
        finally:
            session.close()

    def list_plans(self, *, business_id: str | None = None,
                   limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = ScalingPlanRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [plan_dict(r) for r in rows], total
        finally:
            session.close()


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}" if principal else "system"
