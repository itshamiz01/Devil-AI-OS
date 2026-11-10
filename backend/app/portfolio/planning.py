"""Planning mixin (§15/§16/§17): strategic planning, new-venture
proposals and portfolio reports.

* Strategy is assembled from live evidence (objectives, P-07
  figures, P-08 concentration, current recommendations) — areas
  where the system lacks data are labelled INSUFFICIENT_DATA, never
  padded with invented numbers (§16 assessment areas).
* A venture proposal is only ever a proposal: approval is the
  owner's, creation belongs to the P-03→P-06 pipeline, and P-13
  never creates a business (§21 Scenario 14).
* Reports are snapshots of live views stored with their sources;
  an export is the same JSON, never a reformatted fiction. PDF
  export is NOT IMPLEMENTED (consistent with P-07/P-11).
"""
from __future__ import annotations

import json

from ..core.exceptions import NotFoundError, ValidationError
from ..database.models.portfolio import NewVentureProposal, PortfolioReport
from ..database.repositories.portfolio import (
    ReportRepository, VentureRepository,
)
from ..permissions.models import Principal
from . import constants as C
from .constants import actor_of


def venture_dict(row: NewVentureProposal) -> dict:
    return {
        "id": row.id, "portfolio_id": row.portfolio_id,
        "name": row.concept, "concept": row.concept,
        "category": row.category,
        "target_customer": row.target_customer,
        "rationale": row.customer_problem,
        "customer_problem": row.customer_problem,
        "evidence": row.market_evidence,
        "market_evidence": row.market_evidence,
        "expected_synergy": {
            "description": row.portfolio_synergy,
            "note": "expected synergy is a hypothesis until P-07 "
                    "records verify it"},
        "estimated_requirements": row.funding_requirements,
        "funding_requirements": row.funding_requirements,
        "risks": (row.risk_analysis or {}).get("risks", []),
        "risk_analysis": row.risk_analysis,
        "overlap_check": row.overlap_check,
        "status": row.status,
        "created_by": row.created_by, "decided_by": row.decided_by,
        "linked_opportunity_id": row.opportunity_id,
        "opportunity_id": row.opportunity_id,
        "creation_authority": "P-06 via the P-03 pipeline — this "
                              "proposal never creates a business",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def report_dict(row: PortfolioReport) -> dict:
    payload = row.payload or {}
    return {
        "id": row.id, "portfolio_id": row.portfolio_id,
        "report_type": row.report_type, "title": row.title,
        "content": payload.get("data", {}),
        "sources": payload.get("sources", []),
        "data_complete": row.data_complete,
        "generated_by": row.generated_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class PlanningMixin:
    # -------------------------------------------------------- ventures
    def propose_venture(self, principal: Principal, portfolio_id: str,
                        data: dict) -> dict:
        self._require_owner(principal, "portfolio.venture_propose")
        self._portfolio_or_404(portfolio_id)
        name = str(data.get("name") or data.get("concept") or "").strip()
        category = str(data.get("category") or "").strip()
        if not name or not category:
            raise ValidationError("a venture proposal requires name "
                                  "and category")
        evidence_status = None
        if data.get("evidence"):
            from .intelligence import validate_evidence
            evidence_status = validate_evidence(
                principal, data.get("evidence"))
        # Anti-duplication overlap check (§15): an existing member in
        # the same category is recorded on the proposal itself.
        members = [self._business_summary(bid) for bid in
                   self._member_business_ids(portfolio_id)]
        overlap = [m["business_id"] for m in members
                   if m["category"] == category]
        synergy = data.get("expected_synergy") or {}
        synergy_text = synergy.get("description", "") \
            if isinstance(synergy, dict) else str(synergy)
        session = self._session_factory()
        try:
            row = VentureRepository(session).add(NewVentureProposal(
                portfolio_id=portfolio_id, concept=name[:300],
                category=category,
                target_customer=str(data.get("target_customer") or ""),
                customer_problem=str(data.get("rationale")
                                     or data.get("customer_problem")
                                     or ""),
                market_evidence=list(data.get("evidence")
                                     or data.get("market_evidence")
                                     or []),
                business_model=str(data.get("business_model") or ""),
                portfolio_synergy=synergy_text,
                funding_requirements=dict(
                    data.get("estimated_requirements")
                    or data.get("funding_requirements") or {}),
                risk_analysis={"risks": list(data.get("risks") or []),
                               "evidence_status":
                                   evidence_status or "UNVERIFIED"},
                overlap_check={
                    "same_category_members": overlap,
                    "duplication_warning": bool(overlap)},
                status="PROPOSED",
                created_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.venture_proposed", "portfolio",
                    portfolio_id, "allow",
                    "new venture proposed (no business created)",
                    {"venture_id": row.id})
        return venture_dict(row)

    def decide_venture(self, principal: Principal, venture_id: str,
                       approve: bool) -> dict:
        self._require_owner(principal, "portfolio.venture_decide")
        session = self._session_factory()
        try:
            repo = VentureRepository(session)
            row = repo.get(venture_id)
            if row is None:
                raise NotFoundError(f"venture proposal {venture_id} "
                                    "not found")
            if row.status != "PROPOSED":
                raise ValidationError(f"venture is already {row.status}")
            row.status = "APPROVED" if approve else "REJECTED"
            row.decided_by = actor_of(principal)
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        return venture_dict(row)

    def handoff_venture(self, principal: Principal, venture_id: str) -> dict:
        """Hand an APPROVED proposal to the P-03 discovery pipeline
        as a level-0 opportunity. P-06 remains the only creation
        authority and applies its own gates from there (§15)."""
        self._require_owner(principal, "portfolio.venture_handoff")
        session = self._session_factory()
        try:
            repo = VentureRepository(session)
            row = repo.get(venture_id)
            if row is None:
                raise NotFoundError(f"venture proposal {venture_id} "
                                    "not found")
            if row.status != "APPROVED":
                raise ValidationError(
                    "only an owner-APPROVED venture proposal can be "
                    "handed to the pipeline")
            venture = venture_dict(row)
        finally:
            session.close()
        if self._discovery is None:
            raise ValidationError("discovery engine unavailable")
        opportunity = self._discovery.create_opportunity(principal, {
            "name": venture["name"], "category": venture["category"],
            "description": venture["rationale"],
            "proposed_solution": "portfolio venture proposal handed "
                                 "off by P-13 for normal P-03 "
                                 "validation",
        })
        opportunity_id = getattr(opportunity, "id", None)
        session = self._session_factory()
        try:
            repo = VentureRepository(session)
            row = repo.get(venture_id)
            row.status = "HANDED_TO_P06"
            row.opportunity_id = opportunity_id
            repo.save(row)
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.venture_handed_off", "portfolio",
                    venture["portfolio_id"], "allow",
                    "venture handed to the P-03→P-06 pipeline; no "
                    "business was created by P-13",
                    {"venture_id": venture_id,
                     "opportunity_id": opportunity_id})
        return venture_dict(row)

    def list_ventures(self, principal: Principal, portfolio_id: str) -> dict:
        self._require_portfolio_reader(principal, "portfolio.ventures")
        session = self._session_factory()
        try:
            rows, _t = VentureRepository(session).list(
                limit=200, portfolio_id=portfolio_id)
            items = [venture_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": len(items)}

    # -------------------------------------------------------- strategy
    def strategy_view(self, principal: Principal, portfolio_id: str,
                      currency: str = "INR") -> dict:
        """§16 strategic planning: the ten assessment areas, each
        computed from live evidence or labelled INSUFFICIENT_DATA."""
        self._require_portfolio_reader(principal, "portfolio.strategy")
        self._portfolio_or_404(portfolio_id)
        finance = self.portfolio_finance(principal, portfolio_id, currency)
        concentration = self.concentration_view(principal, portfolio_id,
                                                currency)
        risk = self.latest_risk(principal, portfolio_id)
        objectives = self.list_objectives(principal, portfolio_id)
        rows = [b for b in finance["businesses"]
                if b.get("net_collected_minor") is not None]
        areas: dict[str, dict] = {}

        def area(name, status, detail, items=None):
            areas[name] = {"status": status, "detail": detail,
                           "items": items or []}

        if rows:
            ranked = sorted(rows, key=lambda r: -r["net_collected_minor"])
            area("strongest_businesses", "ASSESSED",
                 "ranked by verified collected revenue (P-07)",
                 [{"business_id": r["business_id"], "name": r["name"],
                   "net_collected_minor": r["net_collected_minor"]}
                  for r in ranked])
            weak = [r for r in rows if r["net_collected_minor"] == 0]
            area("underperforming_assets", "ASSESSED",
                 "businesses with a P-07 profile but no verified "
                 "collected revenue yet",
                 [{"business_id": r["business_id"], "name": r["name"]}
                  for r in weak])
        else:
            area("strongest_businesses", "INSUFFICIENT_DATA",
                 "no member business has a P-07 financial profile "
                 "with collected revenue yet")
            area("underperforming_assets", "INSUFFICIENT_DATA",
                 "no P-07 financial data to assess")
        at_risk = [b for b in (risk.get("per_business") or [])
                   if b.get("risk_level") in ("high", "critical")]
        area("businesses_needing_support",
             "ASSESSED" if risk.get("risk_level") else "INSUFFICIENT_DATA",
             "from the latest portfolio risk assessment" if
             risk.get("risk_level") else
             "run a risk assessment first",
             at_risk)
        opps = self.list_opportunities(principal, portfolio_id)
        area("growth_opportunities", "ASSESSED",
             "open cross-business opportunities from the last "
             "analysis (evidence-gated)",
             [{"id": o["id"], "category": o["category"],
               "title": o["title"], "evidence_status":
               o["evidence_status"]}
              for o in opps["items"] if o["status"] == "PROPOSED"])
        services = self.list_services(principal)
        area("shared_infrastructure", "ASSESSED",
             "registered shared services and their adoption",
             [{"id": s["id"], "name": s["name"], "status": s["status"]}
              for s in services["items"]])
        area("market_concentration", "ASSESSED",
             "verified collected revenue shares (P-07 figures, "
             "P-13 concentration rules)",
             concentration["businesses"])
        concentrated = any(
            b["share_bps"] >= concentration["threshold_bps"]
            for b in concentration["businesses"])
        area("diversification_needs", "ASSESSED",
             "a single business exceeds the concentration threshold"
             if concentrated else
             "no business exceeds the concentration threshold",
             [])
        recs = self.list_recommendations(principal, portfolio_id)
        capital = [r for r in recs["items"]
                   if r["kind"] == "CAPITAL_ALLOCATION"
                   and r["status"] == "PROPOSED"]
        area("capital_priorities",
             "ASSESSED" if capital else "INSUFFICIENT_DATA",
             "capital-allocation recommendations require P-08 "
             "proposals over verified P-07 figures; none are open"
             if not capital else "open capital-allocation "
                                 "recommendations",
             capital)
        resources = self.resource_view(principal, portfolio_id)
        bottlenecks = [{"kind": k, **v} for k, v in
                       resources["kinds"].items()
                       if v["capacity_units"] > 0
                       and v["available_units"] == 0]
        area("operational_bottlenecks", "ASSESSED",
             "resource kinds at full allocation" if bottlenecks else
             "no configured resource kind is fully allocated",
             bottlenecks)
        area("future_experiments", "ASSESSED",
             "experiments remain P-08-governed (pre-declared, capped "
             "budgets — P-13 proposes none automatically)",
             [])
        return {
            "portfolio_id": portfolio_id,
            "objectives": objectives["items"],
            "areas": areas,
            "open_recommendations": [
                r for r in recs["items"] if r["status"] == "PROPOSED"],
            "note": "every figure traces to P-06/P-07/P-08/P-13 "
                    "records; areas without evidence are labelled "
                    "INSUFFICIENT_DATA rather than estimated",
        }

    # --------------------------------------------------------- reports
    def generate_report(self, principal: Principal, portfolio_id: str,
                        data: dict) -> dict:
        self._require_owner(principal, "portfolio.report_generate")
        self._portfolio_or_404(portfolio_id)
        report_type = str(data.get("report_type") or "SNAPSHOT")
        if report_type not in C.REPORT_TYPES:
            raise ValidationError(f"unknown report type: {report_type}")
        currency = str(data.get("currency") or "INR")
        sources = ["p06.business", "p07.financial_service",
                   "p08.survival", "p13.portfolio"]
        if report_type == "SNAPSHOT":
            content = {
                "overview": self.portfolio_overview(
                    principal, portfolio_id, currency),
                "risk": self.latest_risk(principal, portfolio_id),
            }
        elif report_type == "FINANCIAL":
            content = {"finance": self.portfolio_finance(
                principal, portfolio_id, currency)}
        elif report_type == "COMPARISON":
            ids = list(data.get("business_ids") or
                       self._member_business_ids(portfolio_id))
            content = {"comparison": self.compare_businesses(
                principal, ids[:6], currency)}
        elif report_type == "RISK":
            content = {"risk": self.assess_risk(principal, portfolio_id),
                       "concentration": self.concentration_view(
                           principal, portfolio_id, currency)}
        else:  # STRATEGIC
            content = {"strategy": self.strategy_view(
                principal, portfolio_id, currency)}
        session = self._session_factory()
        try:
            row = ReportRepository(session).add(PortfolioReport(
                portfolio_id=portfolio_id, report_type=report_type,
                title=str(data.get("title") or
                          f"{report_type.title()} report"),
                currency=currency,
                period={"generated_for": "current state"},
                payload={"data": content, "sources": sources},
                data_complete=True,
                generated_by=actor_of(principal)))
            session.expunge(row)
        finally:
            session.close()
        self._audit(principal, "portfolio.report_generated", "portfolio",
                    portfolio_id, "allow",
                    f"{report_type} report generated from live views",
                    {"report_id": row.id})
        return report_dict(row)

    def get_report(self, principal: Principal, report_id: str) -> dict:
        self._require_portfolio_reader(principal, "portfolio.report")
        session = self._session_factory()
        try:
            row = ReportRepository(session).get(report_id)
            if row is None:
                raise NotFoundError(f"report {report_id} not found")
            session.expunge(row)
        finally:
            session.close()
        return report_dict(row)

    def list_reports(self, principal: Principal, portfolio_id: str) -> dict:
        self._require_portfolio_reader(principal, "portfolio.reports")
        session = self._session_factory()
        try:
            rows, total = ReportRepository(session).list(
                limit=200, portfolio_id=portfolio_id)
            items = [report_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": total}

    def export_report(self, principal: Principal, report_id: str) -> dict:
        """JSON export of exactly what was generated. PDF export is
        NOT IMPLEMENTED (consistent with P-07/P-11 statements)."""
        report = self.get_report(principal, report_id)
        return {"format": "json",
                "filename": f"portfolio-report-{report_id}.json",
                "content": json.dumps(report, default=str, indent=2),
                "pdf": "NOT IMPLEMENTED"}
