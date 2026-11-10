"""P-17 growth analytics (§19 recommendations, §20 portfolio
growth, §21 budget analysis, §22 attribution, §23 dashboard data)
and retention (§17).

Every figure here is a read over P-07 and the P-17 records: spend
comes from P-07 expenses, revenue from P-07 verified collected
revenue, attribution is labelled ATTRIBUTED and never presented as
collected or causation. Recommendations are mechanically ordered
improve existing businesses → diversify → capital efficiency →
expansion, and expansion entries carry the live P-16 profitability
gate state.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ..database.models.base import as_utc
from ..database.models.growth import (
    CrmCustomer, GrowthLead, MarketingCampaign, MarketingStrategy,
)
from ..permissions.models import Principal
from . import constants as C
from . import scoring


class AnalyticsMixin:
    # --------------------------------------------------- overview (§23A)
    def growth_overview(self, principal: Principal) -> dict:
        self._require_reader(principal, "growth.overview")
        gate = self._gate()
        businesses = []
        totals = {"campaigns_active": 0, "leads": 0, "customers": 0,
                  "spend_minor": 0, "attributed_revenue_minor": 0}
        for business in self._all_businesses():
            summary = self.business_growth(principal, business["id"])
            businesses.append(summary)
            totals["campaigns_active"] += summary["active_campaigns"]
            totals["leads"] += summary["leads_total"]
            totals["customers"] += summary["customers_total"]
            totals["spend_minor"] += summary["spend"]["actual_spend_minor"]
            totals["attributed_revenue_minor"] += (
                summary["attributed_revenue_minor"])
        return {"profitability_gate": gate,
                "totals": totals, "businesses": businesses,
                "labels": {
                    "spend": "P-07 marketing/advertising expenses "
                             "(recorded, approved)",
                    "attributed_revenue": "ATTRIBUTED verified "
                    "collected revenue (P-07, by channel tag); "
                    "attribution is not causation and these totals "
                    "are not collected revenue (§22)"}}

    def business_growth(self, principal: Principal,
                        business_id: str) -> dict:
        self._require_reader(principal, "growth.business")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            campaigns = session.execute(
                select(MarketingCampaign).where(
                    MarketingCampaign.business_id == business_id)
            ).scalars().all()
            leads = session.execute(
                select(GrowthLead).where(
                    GrowthLead.business_id == business_id)).scalars().all()
            customers = session.execute(
                select(CrmCustomer).where(
                    CrmCustomer.business_id == business_id)).scalars().all()
        finally:
            session.close()
        eligible = self._eligible_spend(business_id)
        spend = {"actual_spend_minor": eligible,
                 "source": "P-07 paid P&L expenses in the configured "
                           "marketing categories (§21)"}
        metrics = self._revenue_metrics(business_id)
        by_channel = (metrics or {}).get("by_channel_minor") or {}
        attributed = sum(
            int(v) for k, v in by_channel.items()
            if k.startswith(C.ATTRIBUTION_CHANNEL_PREFIX)
            or k.startswith(C.PARTNER_CHANNEL_PREFIX))
        converted = sum(1 for lead in leads if lead.stage == "converted")
        cac = scoring.cac(eligible or None, converted)
        by_stage: dict[str, int] = {}
        for lead in leads:
            by_stage[lead.stage] = by_stage.get(lead.stage, 0) + 1
        return {
            "business_id": business_id,
            "campaigns_total": len(campaigns),
            "active_campaigns": sum(
                1 for c in campaigns if c.status == "active"),
            "leads_total": len(leads), "leads_by_stage": by_stage,
            "customers_total": len(customers),
            "converted_customers": converted,
            "spend": spend,
            "attributed_revenue_minor": attributed,
            "attributed_revenue_label": "ATTRIBUTED (channel-tagged "
            "verified collected revenue, P-07)",
            "cac": cac,
            "note": "growth health is judged against P-07 verified "
                    "profit, not lead volume alone (§3 rule 12)"}

    # ---------------------------------------------- attribution (§22)
    def attribution(self, principal: Principal, business_id: str) -> dict:
        self._require_reader(principal, "growth.attribution")
        self._business_or_404(business_id)
        metrics = self._revenue_metrics(business_id)
        by_channel = (metrics or {}).get("by_channel_minor") or {}
        session = self._session_factory()
        try:
            customers = session.execute(
                select(CrmCustomer).where(
                    CrmCustomer.business_id == business_id)).scalars().all()
            first_touch: dict[str, int] = {}
            for customer in customers:
                if customer.acquisition_channel:
                    first_touch[customer.acquisition_channel] = \
                        first_touch.get(customer.acquisition_channel, 0) + 1
        finally:
            session.close()
        campaigns = []
        for campaign in self.list_campaigns(
                principal, business_id=business_id)["items"]:
            channel = campaign["attribution_channel"]
            campaigns.append({
                "campaign_id": campaign["id"], "code": campaign["code"],
                "channel_tag": channel,
                "attributed_revenue_minor": int(
                    by_channel.get(channel) or 0)})
        partners = []
        for partner in self.list_partnerships(principal, business_id)["items"]:
            partners.append({
                "partnership_id": partner["id"],
                "partner_name": partner["partner_name"],
                "channel_tag": partner["referral_channel"],
                "attributed_revenue_minor":
                    partner["attributed_revenue_minor"]})
        return {
            "business_id": business_id,
            "methods": {
                "first_touch": {"status": "available",
                                "basis": "CRM customer acquisition "
                                         "channel (§11)",
                                "customer_counts": first_touch},
                "last_touch": {"status": "not_available",
                               "reason": "no last-touch channel is "
                                         "captured per customer — only "
                                         "the acquisition (first-touch) "
                                         "channel is recorded; inventing "
                                         "a last touch would fabricate "
                                         "a journey (§22 honesty)"},
                "multi_touch": {"status": "not_available",
                                "reason": "no journey-level touchpoint "
                                          "capture exists; multi-touch "
                                          "weights would be fabricated "
                                          "(§22 honesty)"}},
            "by_channel_tag": by_channel,
            "campaigns": campaigns, "partners": partners,
            "label": "ATTRIBUTED verified collected revenue from "
                     "P-07, grouped by channel tag. Attribution "
                     "associates revenue with a channel; it does not "
                     "prove the channel caused it, and attributed "
                     "totals are never accounting revenue (§22)"}

    # ---------------------------------------------------- budget (§21)
    def budget_view(self, principal: Principal,
                    business_id: str) -> dict:
        self._require_reader(principal, "growth.budget")
        self._business_or_404(business_id)
        spend = self._eligible_spend(business_id)
        session = self._session_factory()
        try:
            campaigns = session.execute(
                select(MarketingCampaign).where(
                    MarketingCampaign.business_id == business_id)
            ).scalars().all()
            leads = session.execute(
                select(GrowthLead).where(
                    GrowthLead.business_id == business_id)).scalars().all()
        finally:
            session.close()
        rows = []
        total_ceiling = 0
        for campaign in campaigns:
            c_spend = self._campaign_spend(business_id, campaign.id)
            converted = sum(1 for lead in leads
                            if lead.campaign_id == campaign.id
                            and lead.stage == "converted")
            cac = scoring.cac(
                c_spend["actual_spend_minor"] or None, converted)
            ceiling = campaign.budget_ceiling_minor or 0
            total_ceiling += ceiling
            rows.append({
                "campaign_id": campaign.id, "name": campaign.name,
                "status": campaign.status,
                "budget_ceiling_minor": campaign.budget_ceiling_minor,
                "actual_spend_minor": c_spend["actual_spend_minor"],
                "remaining_minor": (ceiling - c_spend["actual_spend_minor"])
                if campaign.budget_ceiling_minor is not None else None,
                "converted_customers": converted, "cac": cac,
                "committed_spend_minor": c_spend["committed_spend_minor"],
                "expense_records": c_spend["expense_records"],
                "spend_request_ids": campaign.spend_request_ids or []})
        return {
            "business_id": business_id,
            "total_ceiling_minor": total_ceiling,
            "actual_spend": {
                "actual_spend_minor": spend,
                "source": "P-07 paid P&L expenses in the configured "
                          "marketing categories"},
            "campaigns": rows,
            "labels": {
                "ceiling": "approved proposal ceiling — not spend",
                "actual": "P-07 recorded marketing/advertising "
                          "expenses — the only spend that exists",
                "cac": "eligible P-07 spend ÷ converted customers; "
                       "INSUFFICIENT_DATA until both exist (§21)"},
            "rules": "budgets are never increased beyond approved "
                     "limits; new expenditure goes through P-07's "
                     "approval workflow (§3 rule 16 / §21)"}

    # ------------------------------------------------- retention (§17)
    def retention_analytics(self, principal: Principal,
                            business_id: str) -> dict:
        """Retention over the recorded CRM base with the §27
        formula (end − new) / start, computed on a 90-day window:
        start = customers recorded before the window; end = all
        customers not recorded churned; new = customers recorded
        inside the window and not churned. Churn counts start-cohort
        customers whose lifecycle is churned. LTV shown is actual
        collected only (a fact); no projection is offered without
        stated margin/period assumptions."""
        self._require_reader(principal, "growth.retention")
        self._business_or_404(business_id)
        session = self._session_factory()
        try:
            customers = session.execute(
                select(CrmCustomer).where(
                    CrmCustomer.business_id == business_id)).scalars().all()
            snapshots = [(c.p07_customer_ref, c.lifecycle_stage,
                          c.created_at) for c in customers]
        finally:
            session.close()
        window_start = datetime.now(timezone.utc) - timedelta(days=90)
        start_cohort = [s for s in snapshots
                        if s[2] is not None
                        and as_utc(s[2]) <= window_start]
        new_in_window = [s for s in snapshots
                         if s[2] is not None
                         and as_utc(s[2]) > window_start]
        end_count = sum(1 for s in snapshots if s[1] != "churned")
        new_count = sum(1 for s in new_in_window if s[1] != "churned")
        churned_start = sum(1 for s in start_cohort if s[1] == "churned")
        retention = scoring.retention_rate(
            len(start_cohort), end_count, new_count)
        churn = scoring.churn_rate(len(start_cohort), churned_start)
        repeat_buyers = 0
        actual_ltvs = []
        for ref, _stage, _created in snapshots:
            purchases = self.customer_purchases(principal, business_id, ref)
            if purchases["count"] >= 2:
                repeat_buyers += 1
            if purchases["count"]:
                actual_ltvs.append(purchases["total_minor"])
        by_lifecycle: dict[str, int] = {}
        for _ref, stage, _created in snapshots:
            by_lifecycle[stage] = by_lifecycle.get(stage, 0) + 1
        return {
            "business_id": business_id,
            "customers_total": len(snapshots),
            "by_lifecycle_stage": by_lifecycle,
            "repeat_purchase_rate": (
                round(repeat_buyers / len(snapshots), 4)
                if snapshots else None),
            "retention_90d": retention, "churn_90d": churn,
            "average_actual_ltv_minor": (
                round(sum(actual_ltvs) / len(actual_ltvs))
                if actual_ltvs else None),
            "labels": {
                "retention": "§27 formula (end − new) / start × 100 "
                             "over the recorded CRM base, 90-day "
                             "window; churned = lifecycle recorded "
                             "as churned",
                "ltv": "actual LTV is a fact over recorded P-07 "
                       "history; no projected LTV is shown without "
                       "stated assumptions (§17)"},
            "note": "support and service history lives in P-18; "
                    "this engine reports acquisition-side retention "
                    "only and never invents satisfaction data"}

    # -------------------------------------------- recommendations (§19)
    def recommendations(self, principal: Principal) -> dict:
        self._require_reader(principal, "growth.recommendations")
        gate = self._gate()
        recs: list[dict] = []

        def add(kind, business_id, title, detail, evidence):
            recs.append({
                "kind": kind,
                "rank": C.RECOMMENDATION_KIND_RANK[kind],
                "business_id": business_id, "title": title,
                "detail": detail, "evidence": evidence,
                "gate_blocked": bool(kind == "expansion"
                                     and gate["state"] == "closed")})

        for business in self._all_businesses():
            business_id = business["id"]
            indicators = self._indicators(business_id)
            if not indicators:
                continue
            net_profit = (indicators.get("profitability") or {}).get(
                "net_profit_minor")
            growth = self.business_growth(principal, business_id)
            if net_profit is not None and net_profit <= 0 and \
                    growth["converted_customers"] == 0 and \
                    growth["spend"]["actual_spend_minor"] > 0:
                add("improve", business_id,
                    "Fix conversion before more acquisition spend",
                    "the business has recorded marketing spend and "
                    "no converted customers, and P-07 shows no "
                    "verified profit — improve the offer and funnel "
                    "first (§3 rule 12)",
                    {"net_profit_minor": net_profit,
                     "spend_minor": growth["spend"]["actual_spend_minor"],
                     "converted_customers": 0})
            collected = indicators.get(
                "verified_collected_revenue_minor") or 0
            expenses_paid = indicators.get("actual_expenses_minor") or 0
            if collected > 0:
                margin = (collected - expenses_paid) / collected
                if margin < 0.3:
                    add("capital_efficiency", business_id,
                        "Improve capital efficiency before scaling spend",
                        f"net margin over verified collected revenue "
                        f"is {round(margin * 100, 1)}% on P-07 figures; "
                        "acquisition spend compounds thin margins",
                        {"net_margin": round(margin, 4),
                         "verified_collected_minor": collected,
                         "actual_expenses_minor": expenses_paid})
        session = self._session_factory()
        try:
            strategies = session.execute(
                select(MarketingStrategy).where(
                    MarketingStrategy.status == "approved")).scalars().all()
            approved_kinds = [(s.kind, s.business_id, s.title)
                              for s in strategies]
        finally:
            session.close()
        for kind, business_id, title in approved_kinds:
            if kind in C.RECOMMENDATION_KIND_RANK:
                add(kind, business_id, f"Execute approved strategy: "
                                       f"{title}",
                    "owner-approved P-17 strategy awaiting execution",
                    {"strategy_kind": kind})
        if gate["state"] == "closed":
            add("expansion", None,
                "Expansion held by the profitability gate",
                f"new acquisition expansion is blocked: "
                f"{gate.get('reason')}. Improve existing businesses "
                "first; the only bypass is a per-item owner override "
                "with a recorded reason (P-16)",
                {"gate": gate})
        recs.sort(key=lambda r: (r["rank"], r["business_id"] or ""))
        return {"items": recs, "count": len(recs),
                "profitability_gate": gate,
                "ordering": "improve → diversify → capital efficiency "
                            "→ expansion (owner priority, P-16)"}

    # ------------------------------------------------ portfolio (§20)
    def portfolio_growth(self, principal: Principal) -> dict:
        self._require_reader(principal, "growth.portfolio")
        businesses = []
        for business in self._all_businesses():
            businesses.append(self.business_growth(
                principal, business["id"]))
        ranked = sorted(
            businesses,
            key=lambda b: (b["attributed_revenue_minor"]
                           - b["spend"]["actual_spend_minor"]),
            reverse=True)
        shared = {
            "brand_assets": "not shared across businesses (isolation)",
            "audiences": "never shared or cross-sold between "
                         "businesses (§20 isolation)",
            "content_templates": "P-17 templates are per-business or "
                                 "explicitly global records; recipient "
                                 "data never crosses businesses",
            "playbooks": "this engine's methods and scores are the "
                         "shared playbook; customer data is not",
        }
        return {
            "businesses": businesses,
            "ranked_by_attributed_contribution": [
                {"business_id": b["business_id"],
                 "attributed_contribution_minor":
                     b["attributed_revenue_minor"]
                     - b["spend"]["actual_spend_minor"]}
                for b in ranked],
            "shared_assets": shared,
            "cross_promotion": {
                "status": "owner_governed",
                "rule": "cross-promotion between businesses happens "
                        "only as an owner-approved partnership or "
                        "campaign per business; audiences are never "
                        "pooled"},
            "profitability_gate": self._gate(),
            "label": "portfolio growth compares ATTRIBUTED figures "
                     "and P-07 spend; portfolio profitability itself "
                     "is judged in P-16/P-07, never here"}
