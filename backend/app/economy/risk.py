"""RiskMixin — §6 revenue diversification intelligence and §12
portfolio economic risk monitoring with the ten stress scenarios.

Everything is computed live from P-07 figures at request time;
risk assessments are stored as snapshots *of that arithmetic with
its inputs*, labelled SIMULATION, so a later reader can see exactly
what was computed from what. Risk monitoring never conceals
distress: loss-making, concentration and negative-flow findings are
reported as found, and an INSUFFICIENT_DATA business is listed as
unmeasurable rather than passed over in silence.
"""
from __future__ import annotations

from sqlalchemy import select

from ..core.exceptions import NotFoundError
from ..database.models.base import utcnow
from ..database.models.economy import RiskAssessment
from ..permissions.models import Principal
from . import constants as C
from . import scoring


def _iso(value):
    from ..database.models.base import as_utc
    value = as_utc(value)
    return value.isoformat() if value else None


def risk_dict(row: RiskAssessment) -> dict:
    return {"id": row.id, "computed_at": _iso(row.computed_at),
            "scope": row.scope, "detectors": row.detectors or [],
            "scenarios": row.scenarios or [],
            "scenarios_label": "SIMULATION — arithmetic on current "
                               "P-07 figures, never predictions",
            "inputs_snapshot": row.inputs_snapshot or {},
            "recommendations": row.recommendations or [],
            "created_by": row.created_by}


class RiskMixin:
    # ------------------------------------------- §6 diversification
    def business_diversification(self, principal: Principal,
                                 business_id: str) -> dict:
        self._require_reader(principal, "economy.diversification")
        self._business_or_404(business_id)
        try:
            summary = self._financial.business_summary(business_id)
        except Exception:
            return {"business_id": business_id,
                    "status": "INSUFFICIENT_DATA",
                    "reason": "no P-07 financial profile"}
        metrics = summary["revenue"]
        result = scoring.diversification_score(metrics)
        settings = self.get_settings()
        threshold = settings["concentration_threshold_bps"] / 10000
        warnings = []
        if result["status"] == "computed":
            if (result["top_channel_share"] or 0) > threshold:
                warnings.append({
                    "kind": "single_channel_dependency",
                    "detail": f"channel '{result['top_channel']}' "
                              f"supplies {result['top_channel_share']} "
                              "of verified collected revenue (§6: "
                              "excessive dependence on one platform/"
                              "channel)"})
            if (result["top_product_share"] or 0) > threshold:
                warnings.append({
                    "kind": "single_product_dependency",
                    "detail": f"product '{result['top_product']}' "
                              f"supplies {result['top_product_share']} "
                              "of verified collected revenue"})
            if (metrics.get("mrr_minor") or 0) == 0:
                warnings.append({
                    "kind": "no_recurring_revenue",
                    "detail": "no active subscription contracts; "
                              "revenue is entirely one-time (§6)"})
            profit = summary.get("profitability") or {}
            if profit.get("is_loss"):
                warnings.append({
                    "kind": "revenue_without_profit",
                    "detail": "the business collects revenue but is "
                              "loss-making — revenue is not "
                              "profitability (§3 principle 8)"})
        return {"business_id": business_id,
                "diversification": result,
                "by_category_minor": metrics.get("by_category_minor"),
                "collected_vs_projected": {
                    "net_collected_minor": metrics.get(
                        "net_collected_minor"),
                    "projected_minor": metrics.get("projected_minor"),
                    "note": "kept separate, never blended"},
                "warnings": warnings,
                "source": "P-07 revenue metrics (live)"}

    def portfolio_diversification(self, principal: Principal) -> dict:
        """§15 Panel D: revenue by business / channel / category,
        recurring vs one-time, and concentration — all live from
        P-07. Cross-business channel/category sums are flow sums in
        each business's profile currency; the staging portfolio is
        single-currency (INR) and any other-currency business is
        listed separately rather than summed."""
        self._require_reader(principal, "economy.diversification")
        per_business = []
        by_channel: dict[str, int] = {}
        by_category: dict[str, int] = {}
        total_collected = 0
        total_projected = 0
        total_arr = 0
        currencies = set()
        for business in self._all_businesses():
            try:
                summary = self._financial.business_summary(business["id"])
            except Exception:
                continue
            metrics = summary["revenue"]
            currencies.add(metrics.get("currency"))
            div = scoring.diversification_score(metrics)
            per_business.append({
                "business_id": business["id"], "name": business["name"],
                "is_fixture": business.get("is_fixture", False),
                "currency": metrics.get("currency"),
                "net_collected_minor": metrics.get("net_collected_minor"),
                "projected_minor": metrics.get("projected_minor"),
                "diversification_score": div["score"],
                "diversification_status": div["status"]})
            total_collected += int(metrics.get("net_collected_minor") or 0)
            total_projected += int(metrics.get("projected_minor") or 0)
            total_arr += int(metrics.get("arr_minor") or 0)
            for key, value in (metrics.get("by_channel_minor")
                               or {}).items():
                by_channel[key] = by_channel.get(key, 0) + int(value or 0)
            for key, value in (metrics.get("by_category_minor")
                               or {}).items():
                by_category[key] = by_category.get(key, 0) + int(value or 0)
        return {"per_business": per_business,
                "by_channel_minor": by_channel,
                "by_category_minor": by_category,
                "totals": {
                    "net_collected_minor": total_collected,
                    "projected_minor": total_projected,
                    "recurring_arr_minor": total_arr,
                    "currencies_present": sorted(
                        c for c in currencies if c),
                    "note": "flow sums over profiled businesses; "
                            "collected and projected are separate "
                            "fields, never blended; cash is never "
                            "summed (Panel A/E carry it per "
                            "business)"},
                "concentration": self._revenue_concentration(
                    self._profitability_rows()),
                "generated_at": utcnow().isoformat()}

    # ------------------------------------------------- §12 risk
    def compute_risk_assessment(self, principal: Principal) -> dict:
        self._require_owner(principal, "economy.risk.compute")
        settings = self.get_settings()
        threshold = settings["concentration_threshold_bps"] / 10000
        rows = []
        detectors = []
        for prow in self._profitability_rows():
            bid = prow["business_id"]
            if not prow["has_profile"]:
                detectors.append({
                    "kind": "unmeasurable_business",
                    "business_id": bid,
                    "detail": "no P-07 financial profile; this "
                              "business's risk cannot be measured "
                              "and is reported, not skipped (§12)"})
                continue
            summary = self._financial.business_summary(bid)
            metrics = summary["revenue"]
            expenses = summary.get("expenses") or {}
            rows.append({
                "business_id": bid, "name": prow["name"],
                "currency": metrics.get("currency"),
                "net_collected_minor":
                    metrics.get("net_collected_minor") or 0,
                "expenses_minor":
                    expenses.get("pl_expense_paid_minor") or 0,
                "net_profit_minor": prow["net_profit_minor"] or 0,
                "by_channel_minor": metrics.get("by_channel_minor")
                or {}})
            if prow["net_profit_minor"] is not None and \
                    prow["net_profit_minor"] < 0:
                detectors.append({
                    "kind": "loss_making_business",
                    "business_id": bid,
                    "detail": "verified net profit is negative"})
            top_channel, share = scoring.largest_share(
                metrics.get("by_channel_minor") or {})
            if share is not None and share > threshold:
                detectors.append({
                    "kind": "platform_dependency",
                    "business_id": bid,
                    "detail": f"channel '{top_channel}' supplies "
                              f"{share} of collected revenue"})
            if (metrics.get("net_collected_minor") or 0) > 0 and \
                    (metrics.get("mrr_minor") or 0) == 0:
                detectors.append({
                    "kind": "no_recurring_revenue",
                    "business_id": bid,
                    "detail": "collected revenue with zero "
                              "recurring revenue"})
        concentration = self._revenue_concentration(
            self._profitability_rows())
        if concentration["overconcentrated"]:
            detectors.append({
                "kind": "revenue_concentration",
                "business_id": concentration["top_business_id"],
                "detail": f"one business supplies "
                          f"{concentration['top_share']} of "
                          "portfolio verified collected revenue"})
        session = self._session_factory()
        try:
            from ..database.models.economy import EconomicOpportunity
            exposure = sum(
                int(r.estimated_investment_minor or 0) for r in
                session.execute(select(EconomicOpportunity).where(
                    EconomicOpportunity.kind == "market_entry",
                    EconomicOpportunity.stage.notin_(
                        ("rejected", "archived", "active")))).scalars())
        finally:
            session.close()
        scenarios = scoring.stress_scenarios(rows, exposure)
        recommendations = []
        for det in detectors:
            recommendations.append({
                "for_detector": det["kind"],
                "business_id": det["business_id"],
                "action": {
                    "loss_making_business": "cost reduction or "
                        "restructuring review before any new "
                        "commitment (§12)",
                    "platform_dependency": "diversify distribution "
                        "channels; never deepen dependence on one "
                        "platform without a risk assessment",
                    "revenue_concentration": "prioritise revenue "
                        "growth in the other businesses and new "
                        "streams for them (§6)",
                    "no_recurring_revenue": "evaluate a "
                        "subscription or contract stream for this "
                        "business (§6)",
                    "unmeasurable_business": "create the P-07 "
                        "financial profile so this business becomes "
                        "measurable",
                }.get(det["kind"], "owner review")})
        session = self._session_factory()
        try:
            row = RiskAssessment(
                scope="all_businesses", detectors=detectors,
                scenarios=scenarios,
                inputs_snapshot={
                    "businesses": rows,
                    "concentration": concentration,
                    "market_entry_proposed_exposure_minor": exposure,
                    "inputs_at": utcnow().isoformat(),
                    "source": "P-07 live figures"},
                recommendations=recommendations,
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = risk_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.risk_computed", "economy",
                    result["id"], "allow",
                    f"portfolio risk assessment computed: "
                    f"{len(detectors)} detector findings, "
                    f"{len(scenarios)} stress scenarios (SIMULATION)")
        return result

    def latest_risk_assessment(self, principal: Principal) -> dict:
        self._require_reader(principal, "economy.risk")
        session = self._session_factory()
        try:
            row = session.execute(
                select(RiskAssessment).order_by(
                    RiskAssessment.computed_at.desc())).scalars().first()
            if row is None:
                return {"status": "none_computed",
                        "note": "no risk assessment has been "
                                "computed yet; run one to populate "
                                "Panel H"}
            return risk_dict(row)
        finally:
            session.close()

    def list_risk_assessments(self, principal: Principal, *,
                              limit: int = 20) -> dict:
        self._require_reader(principal, "economy.risk")
        session = self._session_factory()
        try:
            rows = session.execute(
                select(RiskAssessment).order_by(
                    RiskAssessment.computed_at.desc())
                .limit(limit)).scalars().all()
            return {"items": [risk_dict(r) for r in rows],
                    "total": len(rows)}
        finally:
            session.close()
