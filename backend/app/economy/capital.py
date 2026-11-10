"""CapitalMixin — §9 capital allocation recommendations, §10
profit reinvestment plans, and the §15 Panel E capital view.

Recommendations only. Nothing in this module moves money, creates
a P-07 record, or commits capital: approval records the owner's
endorsement of a *recommendation* under a hash-bound P-01 approval,
and any execution remains P-07's own governed paths. Two mechanical
guards encode the prompt's non-negotiables:

* **No double commitment** (§3 principle 10): a new recommendation
  is refused when its amount plus the open/approved P-16 proposals
  against the same business would exceed that business's P-07
  available capital.
* **Growth follows profitability** (owner's priority): the growth
  scenario cannot be created or approved while the profitability
  gate is closed, and no capital recommendation can be approved
  while the owner has frozen capital commitments (§18).
"""
from __future__ import annotations

from sqlalchemy import select

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.base import utcnow
from ..database.models.economy import (
    AllocationRecommendation, ReinvestmentPlan,
)
from ..permissions.models import Principal
from . import constants as C


def _iso(value):
    from ..database.models.base import as_utc
    value = as_utc(value)
    return value.isoformat() if value else None


def allocation_dict(row: AllocationRecommendation) -> dict:
    return {"id": row.id, "scenario": row.scenario,
            "business_id": row.business_id, "currency": row.currency,
            "proposed": row.proposed or {},
            "proposed_label": "PROPOSED — a recommendation; approval "
                              "moves no money and execution, if the "
                              "owner chooses it, happens through "
                              "P-07's governed paths",
            "rationale": row.rationale,
            "expected_benefits": row.expected_benefits,
            "downside": row.downside,
            "liquidity_snapshot": row.liquidity_snapshot or {},
            "payback_assumptions": row.payback_assumptions,
            "status": row.status, "approval_id": row.approval_id,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def reinvestment_dict(row: ReinvestmentPlan) -> dict:
    return {"id": row.id, "business_id": row.business_id,
            "currency": row.currency,
            "figures_snapshot": row.figures_snapshot or {},
            "shares": row.shares or {},
            "shares_label": "configurable owner policy; the §10 "
                            "example percentages are a default, "
                            "labelled illustrative — never financial "
                            "advice (§10)",
            "amounts_minor": row.amounts_minor or {},
            "amounts_label": "PROPOSED — derived from the snapshot's "
                             "distributable cash figure",
            "status": row.status, "approval_id": row.approval_id,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


class CapitalMixin:
    # ------------------------------------------------- §9 allocations
    def _liquidity_snapshot(self, business_id: str | None) -> dict:
        """Per-business available capital from P-07. Combined cash
        is never summed (P-13 rule) — a portfolio-level
        recommendation snapshots each business separately."""
        snapshot: dict = {"businesses": {}, "combined_available_cash": None,
                          "combined_cash_note": "never summed (P-13 "
                                                "§11 rule)",
                          "snapshot_at": utcnow().isoformat(),
                          "source": "P-07 p08_indicators"}
        ids = [business_id] if business_id else [
            b["id"] for b in self._all_businesses()]
        for bid in ids:
            indicators = self._indicators(bid)
            snapshot["businesses"][bid] = (
                {"available_capital_minor":
                    indicators.get("available_capital_minor"),
                 "runway_months": indicators.get("runway_months")}
                if indicators else
                {"available_capital_minor": None,
                 "note": "no P-07 financial profile"})
        return snapshot

    def _open_commitments_minor(self, business_id: str,
                                exclude_id: str | None = None) -> int:
        session = self._session_factory()
        try:
            total = 0
            for row in session.execute(
                    select(AllocationRecommendation).where(
                        AllocationRecommendation.business_id
                        == business_id,
                        AllocationRecommendation.status.in_(
                            ("proposed", "approved")))).scalars():
                if exclude_id and row.id == exclude_id:
                    continue
                total += int((row.proposed or {}).get("amount_minor")
                             or 0)
            return total
        finally:
            session.close()

    def allocation_scenarios(self, principal: Principal, *,
                             business_id: str) -> dict:
        """§9's three scenarios as analysis over one business's
        P-07 position. Reserve floors are stated policy fractions of
        available capital (conservative 50%, balanced 30%, growth
        15% kept back); deployable = available − floor − existing
        P-16 open commitments. Growth is reported as refused while
        the profitability gate is closed."""
        self._require_reader(principal, "economy.capital.scenarios")
        self._business_or_404(business_id)
        indicators = self._indicators(business_id)
        if indicators is None:
            return {"business_id": business_id,
                    "status": "INSUFFICIENT_DATA",
                    "reason": "no P-07 financial profile; scenarios "
                              "would be fabricated"}
        available = int(indicators.get("available_capital_minor") or 0)
        committed = self._open_commitments_minor(business_id)
        gate = self._gate()
        floors = {"conservative": 0.50, "balanced": 0.30, "growth": 0.15}
        scenarios = {}
        for name, fraction in floors.items():
            reserve_floor = int(available * fraction)
            scenarios[name] = {
                "reserve_floor_minor": reserve_floor,
                "open_p16_commitments_minor": committed,
                "deployable_minor": max(
                    available - reserve_floor - committed, 0),
                "posture": {
                    "conservative": "capital preservation, reserves "
                                    "and validated businesses first",
                    "balanced": "established businesses plus "
                                "controlled experiments",
                    "growth": "validated expansion within approved "
                              "risk limits"}[name],
                "refused": bool(name == "growth"
                                and gate["state"] == "closed"),
                "refusal_reason": (
                    "owner's profitability gate is closed; growth "
                    "allocation waits for verified profitability"
                    if name == "growth" and gate["state"] == "closed"
                    else None)}
        return {"business_id": business_id,
                "available_capital_minor": available,
                "currency": (indicators.get("currency") or "INR"),
                "scenarios": scenarios, "profitability_gate": gate,
                "basis": "P-07 available capital at request time; "
                         "reserve floors are policy fractions, "
                         "labelled as such"}

    def create_allocation(self, principal: Principal,
                          data: dict) -> dict:
        self._require_owner(principal, "economy.allocation.create")
        if data.get("scenario") not in C.ALLOCATION_SCENARIOS:
            raise ValidationError(
                f"scenario must be one of {list(C.ALLOCATION_SCENARIOS)}")
        proposed = data.get("proposed") or {}
        amount = proposed.get("amount_minor")
        if amount is None or int(amount) <= 0:
            raise ValidationError(
                "a recommendation requires a positive proposed "
                "amount_minor (§9)")
        business_id = data.get("business_id")
        if business_id:
            self._business_or_404(business_id)
            indicators = self._indicators(business_id)
            if indicators is None:
                raise ValidationError(
                    "the business has no P-07 financial profile; "
                    "allocating against unmeasured capital is refused")
            available = int(indicators.get("available_capital_minor")
                            or 0)
            committed = self._open_commitments_minor(business_id)
            if int(amount) + committed > available:
                raise ValidationError(
                    "double commitment refused (§3 principle 10): "
                    f"proposed {int(amount)} + open P-16 commitments "
                    f"{committed} exceeds P-07 available capital "
                    f"{available} for this business")
        if data["scenario"] == "growth":
            gate = self._gate()
            if gate["state"] == "closed":
                raise PermissionDeniedError(
                    "growth allocation refused while the owner's "
                    f"profitability gate is closed: {gate['reason']}")
        session = self._session_factory()
        try:
            row = AllocationRecommendation(
                scenario=data["scenario"], business_id=business_id,
                currency=data.get("currency") or "INR",
                proposed={**proposed, "amount_minor": int(amount)},
                rationale=data.get("rationale") or "",
                expected_benefits=data.get("expected_benefits") or "",
                downside=data.get("downside") or "",
                liquidity_snapshot=self._liquidity_snapshot(business_id),
                payback_assumptions=data.get("payback_assumptions") or "",
                status="proposed",
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = allocation_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.allocation_created", "economy",
                    result["id"], "allow",
                    "capital allocation recommendation proposed "
                    "(§9); no money moved")
        return result

    def list_allocations(self, principal: Principal, *,
                         status: str | None = None,
                         limit: int = 100) -> dict:
        self._require_reader(principal, "economy.allocations")
        session = self._session_factory()
        try:
            stmt = select(AllocationRecommendation)
            if status:
                stmt = stmt.where(
                    AllocationRecommendation.status == status)
            rows = session.execute(
                stmt.order_by(AllocationRecommendation.created_at.desc())
                .limit(limit)).scalars().all()
            return {"items": [allocation_dict(r) for r in rows],
                    "total": len(rows)}
        finally:
            session.close()

    def decide_allocation(self, principal: Principal,
                          recommendation_id: str, *,
                          approve: bool,
                          approval_id: str | None = None) -> dict:
        self._require_owner(principal, "economy.allocation.decide")
        settings = self.get_settings()
        session = self._session_factory()
        try:
            row = session.get(AllocationRecommendation, recommendation_id)
            if row is None:
                raise NotFoundError(
                    f"allocation recommendation {recommendation_id} "
                    "not found")
            if row.status != "proposed":
                raise ValidationError(
                    f"recommendation is {row.status}; only a "
                    "proposed one can be decided")
            snapshot = allocation_dict(row)
        finally:
            session.close()
        bound = None
        if approve:
            if settings["capital_commitments_frozen"]:
                raise PermissionDeniedError(
                    "capital commitments are frozen by the owner "
                    "(§18); allocation approvals are refused until "
                    "unfrozen")
            params = {"recommendation_id": recommendation_id,
                      "amount_minor": (snapshot["proposed"] or {}).get(
                          "amount_minor"),
                      "business_id": snapshot["business_id"]}
            bound = self._owner_approval(
                principal, action=C.APPROVAL_ACTION_ALLOCATION,
                resource=recommendation_id, parameters=params,
                reason="P-16 capital allocation recommendation "
                       "(§9) — endorsement of a recommendation; "
                       "moves no money",
                approval_id=approval_id)
        session = self._session_factory()
        try:
            row = session.get(AllocationRecommendation, recommendation_id)
            row.status = "approved" if approve else "rejected"
            row.approval_id = bound
            session.commit()
            session.refresh(row)
            result = allocation_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.allocation_decided", "economy",
                    recommendation_id, "allow",
                    f"recommendation {'approved' if approve else 'rejected'}"
                    "; approval endorses advice only — P-07 remains "
                    "the sole path for any actual movement of money")
        return result

    # ----------------------------------------------- §10 reinvestment
    def create_reinvestment_plan(self, principal: Principal,
                                 data: dict) -> dict:
        self._require_owner(principal, "economy.reinvestment.create")
        business_id = data.get("business_id")
        if not business_id:
            raise ValidationError("a reinvestment plan requires a "
                                  "business_id (§10)")
        self._business_or_404(business_id)
        summary = None
        try:
            summary = self._financial.business_summary(business_id)
        except Exception:
            summary = None
        if summary is None:
            raise ValidationError(
                "the business has no P-07 financial profile; a "
                "reinvestment plan without books is refused")
        settings = self.get_settings()
        shares = data.get("shares") or settings["reinvestment_shares"]
        shares = {k: float(v) for k, v in dict(shares).items()}
        if abs(sum(shares.values()) - 100.0) > 0.001:
            raise ValidationError("reinvestment shares must sum to 100")
        revenue = summary["revenue"]
        expenses = summary.get("expenses") or {}
        profit = summary.get("profitability") or {}
        cash = summary.get("available_cash") or {}
        net_profit = int(profit.get("net_profit_minor") or 0)
        available_cash = int(cash.get("available_cash_minor") or 0)
        adjustments = int(data.get("adjustments_minor") or 0)
        # Distributable = the lesser of accounting profit and real
        # available cash, less owner-declared tax/liability
        # adjustments, floored at zero (§10's distinctions made
        # arithmetic: accounting profit is not cash).
        distributable = max(min(net_profit, available_cash)
                            - adjustments, 0)
        amounts = {k: int(distributable * v / 100.0)
                   for k, v in shares.items()}
        figures = {
            "verified_collected_revenue_minor":
                revenue.get("net_collected_minor"),
            "actual_expenses_minor": expenses.get(
                "pl_expense_paid_minor"),
            "accounting_net_profit_minor": net_profit,
            "available_cash_minor": available_cash,
            "owner_declared_adjustments_minor": adjustments,
            "adjustments_note": "taxes payable, liabilities and "
                                "contractual restrictions are "
                                "owner-declared adjustments here; "
                                "P-07 tax records remain the "
                                "authoritative detail",
            "distributable_cash_minor": distributable,
            "distributable_basis": "min(accounting net profit, "
                                   "available cash) − adjustments, "
                                   "floored at 0",
            "snapshot_at": utcnow().isoformat(),
            "source": "P-07 business_summary (live at creation)"}
        session = self._session_factory()
        try:
            row = ReinvestmentPlan(
                business_id=business_id,
                currency=revenue.get("currency") or "INR",
                figures_snapshot=figures, shares=shares,
                amounts_minor=amounts, status="proposed",
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = reinvestment_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.reinvestment_created",
                    "economy", result["id"], "allow",
                    "profit reinvestment plan proposed (§10); "
                    "distributable cash computed as min(profit, "
                    "cash) − adjustments")
        return result

    def list_reinvestment_plans(self, principal: Principal, *,
                                business_id: str | None = None,
                                limit: int = 100) -> dict:
        self._require_reader(principal, "economy.reinvestment")
        session = self._session_factory()
        try:
            stmt = select(ReinvestmentPlan)
            if business_id:
                stmt = stmt.where(
                    ReinvestmentPlan.business_id == business_id)
            rows = session.execute(
                stmt.order_by(ReinvestmentPlan.created_at.desc())
                .limit(limit)).scalars().all()
            return {"items": [reinvestment_dict(r) for r in rows],
                    "total": len(rows)}
        finally:
            session.close()

    def decide_reinvestment_plan(self, principal: Principal,
                                 plan_id: str, *, approve: bool,
                                 approval_id: str | None = None) -> dict:
        self._require_owner(principal, "economy.reinvestment.decide")
        settings = self.get_settings()
        session = self._session_factory()
        try:
            row = session.get(ReinvestmentPlan, plan_id)
            if row is None:
                raise NotFoundError(
                    f"reinvestment plan {plan_id} not found")
            if row.status != "proposed":
                raise ValidationError(
                    f"plan is {row.status}; only a proposed plan "
                    "can be decided")
            snapshot = reinvestment_dict(row)
        finally:
            session.close()
        bound = None
        if approve:
            if settings["capital_commitments_frozen"]:
                raise PermissionDeniedError(
                    "capital commitments are frozen by the owner "
                    "(§18); reinvestment approvals are refused until "
                    "unfrozen")
            params = {"plan_id": plan_id,
                      "business_id": snapshot["business_id"],
                      "distributable_cash_minor": (snapshot[
                          "figures_snapshot"] or {}).get(
                              "distributable_cash_minor")}
            bound = self._owner_approval(
                principal, action=C.APPROVAL_ACTION_REINVESTMENT,
                resource=plan_id, parameters=params,
                reason="P-16 profit reinvestment plan (§10) — "
                       "endorsement of a plan; moves no money",
                approval_id=approval_id)
        session = self._session_factory()
        try:
            row = session.get(ReinvestmentPlan, plan_id)
            row.status = "approved" if approve else "rejected"
            row.approval_id = bound
            session.commit()
            session.refresh(row)
            result = reinvestment_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.reinvestment_decided",
                    "economy", plan_id, "allow",
                    f"reinvestment plan "
                    f"{'approved' if approve else 'rejected'}; "
                    "approval endorses the plan only")
        return result

    # ------------------------------------------------ §15 Panel E view
    def capital_overview(self, principal: Principal) -> dict:
        self._require_reader(principal, "economy.capital")
        rows = []
        for prow in self._profitability_rows():
            bid = prow["business_id"]
            rows.append({
                "business_id": bid, "name": prow["name"],
                "is_fixture": prow["is_fixture"],
                "available_capital_minor": prow["available_capital_minor"],
                "open_p16_commitments_minor":
                    self._open_commitments_minor(bid)
                    if prow["has_profile"] else 0,
                "runway_months": prow["runway_months"]})
        settings = self.get_settings()
        return {"businesses": rows,
                "combined_available_cash": None,
                "combined_cash_note": "never summed (P-13 §11 rule)",
                "capital_commitments_frozen":
                    settings["capital_commitments_frozen"],
                "profitability_gate": self._gate(),
                "financial_authority": "P-07"}
