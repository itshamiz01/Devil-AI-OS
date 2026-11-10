"""§15 Portfolio management + §16 capital allocation + §17 resource
allocation.

Consolidated figures come from P-07 only: ``FinancialService.
consolidated`` for portfolio money, and each business's P-07
indicators for capital inputs. Concentration is computed from P-07's
collected-by-channel shares and P-06's channel records — ten
businesses on one platform are named a concentration risk, never
counted as diversification (§15.2).

Capital allocation produces PROPOSALS (§16.4): explainable,
risk-adjusted, capped by available capital and the per-business
share limit, and structurally blocked when the source touches
protected reserves (Scenario 12). Resource proposals measure real
workload first (P-04 metrics, P-01 task manager) and consider
reassignment before creation; creation itself only ever happens
through P-04 (§17.2).
"""
from __future__ import annotations

from decimal import Decimal

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.survival import (
    CapitalAllocationProposal, ResourceAllocationProposal,
)
from ..database.repositories.survival import (
    CapitalAllocationRepository, ResourceAllocationRepository,
)
from ..permissions.models import PrincipalType
from . import constants as C


def allocation_dict(row: CapitalAllocationProposal) -> dict:
    return {
        "id": row.id, "business_id": row.business_id,
        "category": row.category, "status": row.status,
        "amount_minor": row.amount_minor, "currency": row.currency,
        "source_kind": row.source_kind, "purpose": row.purpose,
        "expected_result": row.expected_result,
        "max_loss_minor": row.max_loss_minor, "score_bps": row.score_bps,
        "rationale": row.rationale, "approval_id": row.approval_id,
        "review_on": row.review_on, "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
        "note": "proposal only — actual financial movement is "
                "outside P-08 (§16.4)",
    }


def resource_dict(row: ResourceAllocationProposal) -> dict:
    return {
        "id": row.id, "business_id": row.business_id,
        "status": row.status,
        "requested_agents": row.requested_agents,
        "recommended_agents": row.recommended_agents,
        "workload": row.workload, "alternatives": row.alternatives,
        "rationale": row.rationale, "approval_id": row.approval_id,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
    }


class PortfolioService:
    def __init__(self, session_factory, financial, business, monitoring,
                 health, agents, tasks, settings_getter, audit):
        self._session_factory = session_factory
        self._financial = financial
        self._business = business
        self._monitoring = monitoring
        self._health = health
        self._agents = agents
        self._tasks = tasks
        self._settings = settings_getter
        self._audit = audit

    # ------------------------------------------------------------- overview
    def overview(self, currency: str = "INR") -> dict:
        businesses, _total = self._business.list_businesses(limit=500)
        consolidated = self._financial.consolidated(currency)
        by_status: dict[str, int] = {}
        by_overlay: dict[str, int] = {}
        at_risk = []
        for business in businesses:
            by_status[business["status"]] = \
                by_status.get(business["status"], 0) + 1
            snapshot = self._health.latest_snapshot(business["id"])
            overlay = (snapshot or {}).get("overlay_state") \
                or C.P06_TO_OVERLAY.get(business["status"],
                                        "EARLY_OPERATIONS")
            by_overlay[overlay] = by_overlay.get(overlay, 0) + 1
            if snapshot and snapshot["classification"] in (
                    "AT_RISK", "CRITICAL"):
                at_risk.append({
                    "business_id": business["id"],
                    "name": business["name"],
                    "classification": snapshot["classification"]})
        return {
            "business_count": len(businesses),
            "by_p06_status": by_status, "by_overlay": by_overlay,
            "at_risk": at_risk,
            "consolidated": consolidated,
            "consolidated_source": "p07.financial.consolidated "
                                   "(verbatim; internal transfers "
                                   "excluded by P-07, §18)",
            "note": "portfolio money is read from P-07 only (§15.1)",
        }

    def concentration(self, currency: str = "INR") -> dict:
        """Channel/platform concentration from P-07 collected shares
        (per business, via its own metrics) aggregated as record
        counts and P-07 share readings — P-08 sums no money: the
        portfolio-level share uses P-07's consolidated collected
        figure as denominator against per-business P-07 readings is
        NOT done; instead each business's dominant channel share
        (a P-07 ratio per business) is reported and any business over
        threshold names the platform."""
        settings = self._settings()
        threshold = Decimal(settings["concentration_threshold"])
        businesses, _total = self._business.list_businesses(limit=500)
        platform_businesses: dict[str, list[str]] = {}
        dominant: list[dict] = []
        for business in businesses:
            channels, _t = self._business.list_channels(business["id"])
            for channel in channels:
                platform_businesses.setdefault(
                    channel["platform"], []).append(business["id"])
            profile = self._financial.get_profile(business["id"])
            if profile is None:
                continue
            metrics = self._financial.revenue.metrics(
                business["id"], profile["base_currency"])
            by_channel = metrics.get("by_channel_minor") or {}
            gross = metrics.get("collected_gross_minor") or 0
            if gross > 0 and by_channel:
                top, amount = max(by_channel.items(),
                                  key=lambda kv: kv[1])
                share = Decimal(amount) / Decimal(gross)
                if share > threshold:
                    dominant.append({
                        "business_id": business["id"],
                        "platform": top, "share": str(share),
                        "source": "p07.revenue.metrics.by_channel"})
        risks = []
        for platform, ids in platform_businesses.items():
            if len(ids) >= 2:
                risks.append({
                    "kind": "platform_dependency",
                    "platform": platform,
                    "business_count": len(set(ids)),
                    "detail": f"{len(set(ids))} businesses depend on "
                              f"{platform}; separate business records "
                              "do not diversify platform risk (§15.2)"})
        for entry in dominant:
            risks.append({
                "kind": "revenue_concentration", **entry,
                "detail": "one channel carries more than the "
                          "configured share of this business's "
                          "verified collected revenue"})
        return {
            "risks": risks, "platform_businesses": {
                k: sorted(set(v)) for k, v in platform_businesses.items()},
            "threshold": str(threshold),
            "diversification_note": "diversification is recommended "
                                    "only where it has a defensible "
                                    "strategic and financial purpose "
                                    "(§15.3)",
        }

    # ------------------------------------------------ capital allocation
    def propose_allocations(self, principal, data: dict) -> dict:
        """Risk-adjusted allocation proposals across competing
        businesses (Scenario 10). Inputs: P-07 available capital per
        business + health/scaling state. The total proposed never
        exceeds portfolio available capital; obligations and
        commitments are already excluded inside P-07's available
        cash figure. Protected reserves are never a source."""
        currency = data.get("currency") or "INR"
        source_kind = data.get("source_kind") or "available_capital"
        requests = data.get("requests") or []
        if not requests:
            raise ValidationError("allocation requests are required")
        settings = self._settings()
        share_cap = Decimal(settings["max_business_capital_share"])
        if source_kind in ("protected_reserves", "reserve",
                           "emergency_reserve"):
            # Stored as a BLOCKED proposal: the record is the audit
            # trail of the refusal (Scenario 12).
            first = requests[0]
            session = self._session_factory()
            try:
                row = CapitalAllocationRepository(session).add(
                    CapitalAllocationProposal(
                        business_id=first["business_id"],
                        category=data.get("category") or "growth",
                        status="BLOCKED",
                        amount_minor=int(first.get("amount_minor") or 0),
                        currency=currency, source_kind=source_kind,
                        purpose=first.get("purpose") or "",
                        expected_result="",
                        rationale={
                            "blocked_reason": "protected reserves "
                                              "cannot be allocated "
                                              "(§16.4/§3.1); only "
                                              "an owner policy "
                                              "change through P-07 "
                                              "governance could alter "
                                              "reserves — no agent "
                                              "path exists",
                            "gate": "protected_reserve"},
                        created_by=_actor(principal)))
                blocked = allocation_dict(row)
            finally:
                session.close()
            self._audit(principal, "survival.allocation_blocked",
                        "business", first["business_id"], "deny",
                        "protected reserve allocation blocked (§16.4)")
            return {"proposals": [blocked],
                    "blocked": True,
                    "note": "protected reserves cannot be allocated; "
                            "the proposal is recorded BLOCKED"}
        # Portfolio available capital: sum of per-business P-07
        # available figures is NOT computed by P-08. Instead each
        # business's own available capital caps its own proposal, and
        # the per-business share cap applies to that business's
        # available capital. Cross-business pooling would require a
        # P-07 portfolio-available figure; the consolidated report
        # provides totals read verbatim for context.
        proposals = []
        for request in requests:
            business_id = request["business_id"]
            indicators = self._financial.p08_indicators(business_id)
            available = indicators["available_capital_minor"] or 0
            snapshot = self._health.latest_snapshot(business_id)
            classification = (snapshot or {}).get(
                "classification", "INSUFFICIENT_DATA")
            requested = int(request.get("amount_minor") or 0)
            cap = int((Decimal(available) * share_cap)
                      .to_integral_value())
            amount = min(requested, cap, available)
            score = (snapshot or {}).get("score_bps")
            status = "PROPOSED" if amount > 0 else "BLOCKED"
            rationale = {
                "available_capital_minor": available,
                "available_source": "p07.p08_indicators",
                "requested_minor": requested,
                "share_cap": str(share_cap),
                "health_classification": classification,
                "health_score_bps": score,
                "committed_and_obligations": "already excluded inside "
                                             "P-07 available cash "
                                             "(§9.4 formula)",
                "reason": ("within caps" if amount == requested else
                           "clamped to the per-business share of "
                           "available capital; proposals never "
                           "over-allocate (§16)"),
            }
            if classification in ("AT_RISK", "CRITICAL",
                                  "INSUFFICIENT_DATA"):
                rationale["risk_note"] = (
                    f"health is {classification}: allocation to this "
                    "business carries elevated risk and requires "
                    "explicit owner review")
            session = self._session_factory()
            try:
                row = CapitalAllocationRepository(session).add(
                    CapitalAllocationProposal(
                        business_id=business_id,
                        category=request.get("category") or "growth",
                        status=status, amount_minor=amount,
                        currency=indicators["currency"],
                        source_kind=source_kind,
                        purpose=request.get("purpose") or "",
                        expected_result=request.get(
                            "expected_result") or "",
                        max_loss_minor=request.get("max_loss_minor"),
                        score_bps=score, rationale=rationale,
                        review_on=request.get("review_on"),
                        created_by=_actor(principal)))
                proposals.append(allocation_dict(row))
            finally:
                session.close()
        self._audit(principal, "survival.allocations_proposed",
                    "business", None, "allow",
                    f"{len(proposals)} proposal(s)")
        return {"proposals": proposals, "blocked": False,
                "note": "proposals only; no financial movement "
                        "occurs in P-08 (§16.4)"}

    def list_allocations(self, *, business_id: str | None = None,
                         limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = CapitalAllocationRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [allocation_dict(r) for r in rows], total
        finally:
            session.close()

    # ------------------------------------------------ resource allocation
    def propose_resources(self, principal, business_id: str,
                          data: dict) -> dict:
        """§17: workload is measured first. Sources: P-04 assignment
        metrics for the business's assigned agents and the P-01 task
        queue posture. Reassignment/optimisation alternatives are
        always listed before any creation recommendation, and the
        recommendation respects the hardware profile in settings."""
        self._business.get_business(business_id)
        requested = int(data.get("requested_agents") or 0)
        if requested <= 0:
            raise ValidationError("requested_agents must be positive")
        settings = self._settings()
        assignments = self._business.assignments(business_id)
        agent_ids = sorted({a["agent_id"] for a in assignments[0]}
                           ) if isinstance(assignments, tuple) \
            else sorted({a["agent_id"] for a in assignments})
        measured = []
        total_completed = 0
        total_failed = 0
        for agent_id in agent_ids:
            try:
                metrics = self._agents.agent_metrics(agent_id)
            except Exception:
                continue
            completed = metrics["aggregates"]["tasks_completed"]["value"]
            failed = metrics["aggregates"]["tasks_failed"]["value"]
            total_completed += completed
            total_failed += failed
            measured.append({"agent_id": agent_id,
                             "tasks_completed": completed,
                             "tasks_failed": failed,
                             "source": "p04.agent_factory.agent_metrics "
                                       "(measured)"})
        workload = {
            "assigned_agents": len(agent_ids),
            "agent_metrics": measured,
            "tasks_completed": total_completed,
            "tasks_failed": total_failed,
            "hardware": {
                "max_concurrent_agents": settings[
                    "max_concurrent_agents"],
                "inference_slots": settings["inference_slots"],
                "note": "owner's CPU-only machine (P-00 verdict): "
                        "one shared inference slot; agent count is "
                        "not throughput"},
        }
        alternatives = [
            {"kind": "reassign_existing",
             "summary": "Reassign existing agents or raise their "
                        "priority before creating new ones (§17.2)"},
            {"kind": "optimise_workflow",
             "summary": "Improve workflows / remove failing steps "
                        "before adding capacity"},
            {"kind": "pause_idle",
             "summary": "Pause idle workloads to free the shared "
                        "inference slot"},
        ]
        headroom = max(0, settings["max_concurrent_agents"]
                       - len(agent_ids))
        if total_completed == 0 and total_failed == 0:
            recommended = 0
            rationale = (
                "no measured workload exists for this business's "
                "agents: creating agents now would simulate "
                "productivity, not add it (§17/§32 rule 16). "
                "Recommendation: 0 new agents; measure first.")
        else:
            recommended = min(requested, headroom)
            rationale = (
                f"measured workload: {total_completed} completed / "
                f"{total_failed} failed across {len(agent_ids)} "
                f"assigned agent(s); hardware headroom is {headroom} "
                f"agent(s). Recommended {recommended}; any creation "
                "runs through P-04's reuse-first gates.")
        session = self._session_factory()
        try:
            row = ResourceAllocationRepository(session).add(
                ResourceAllocationProposal(
                    business_id=business_id, status="PROPOSED",
                    requested_agents=requested,
                    recommended_agents=recommended, workload=workload,
                    alternatives=alternatives, rationale=rationale,
                    created_by=_actor(principal)))
            result = resource_dict(row)
        finally:
            session.close()
        self._audit(principal, "survival.resources_proposed", "business",
                    business_id, "allow",
                    f"requested={requested} recommended={recommended}")
        return result

    def list_resource_proposals(self, *, business_id: str | None = None,
                                limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = ResourceAllocationRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [resource_dict(r) for r in rows], total
        finally:
            session.close()


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}" if principal else "system"
