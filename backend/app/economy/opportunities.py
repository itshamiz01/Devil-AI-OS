"""OpportunitiesMixin — §4.2 opportunity pipeline, §4.3 scoring,
§4.4 expansion strategies, deterministic discovery detectors and
§15 Panel I strategic recommendations.

The pipeline never turns a discovery into a business by itself:
launch_approved only records that the governed path may proceed —
creation remains P-06's, on a P-03 opportunity, under P-06's own
gates. Two mechanical gates guard the pipeline:

* the **evidence gate** (§4.3): approval_pending requires the
  configured minimum confidence and evidence count, whatever the
  score — a high score on weak evidence stays in research;
* the **owner's profitability gate**: new_business / market_entry
  opportunities cannot pass financial_evaluation while the
  portfolio is not verifiably profitable, unless the owner records
  an explicit per-item override.
"""
from __future__ import annotations

from sqlalchemy import select

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.base import utcnow
from ..database.models.economy import (
    CommercialAsset, EconomicOpportunity, ExpansionStrategy,
)
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from . import scoring


def _iso(value):
    from ..database.models.base import as_utc
    value = as_utc(value)
    return value.isoformat() if value else None


def opportunity_dict(row: EconomicOpportunity) -> dict:
    return {"id": row.id, "title": row.title, "kind": row.kind,
            "source_kind": row.source_kind, "stage": row.stage,
            "description": row.description,
            "market_report_id": row.market_report_id,
            "p03_opportunity_id": row.p03_opportunity_id,
            "business_id": row.business_id,
            "market_tag": row.market_tag,
            "factor_scores": row.factor_scores or {},
            "total_score": row.total_score,
            "confidence": row.confidence,
            "classification_band": row.classification_band,
            "evidence": row.evidence or [],
            "estimated_investment_minor": row.estimated_investment_minor,
            "estimated_investment_label": "estimate only — never a "
                                          "commitment (§4.2)",
            "gate_override": row.gate_override,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at)}


def strategy_dict(row: ExpansionStrategy) -> dict:
    return {"id": row.id, "title": row.title, "horizon": row.horizon,
            "kind": row.kind, "objective": row.objective,
            "business_id": row.business_id,
            "opportunity_id": row.opportunity_id,
            "financial_requirements": row.financial_requirements or {},
            "timeline": row.timeline,
            "required_resources": row.required_resources or [],
            "dependencies": row.dependencies or [],
            "expected_outcomes": row.expected_outcomes,
            "kpis": row.kpis or [], "risks": row.risks or [],
            "exit_conditions": row.exit_conditions,
            "status": row.status, "approval_id": row.approval_id,
            "gate_override": row.gate_override,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


class OpportunitiesMixin:
    # ------------------------------------------------ §4.2 pipeline
    def create_opportunity(self, principal: Principal,
                           data: dict) -> dict:
        self._require_owner(principal, "economy.opportunity.create")
        if data.get("kind") not in C.OPPORTUNITY_KINDS:
            raise ValidationError(
                f"kind must be one of {list(C.OPPORTUNITY_KINDS)}")
        if not (data.get("title") or "").strip():
            raise ValidationError("an opportunity requires a title")
        self._check_factor_keys(data.get("factor_scores") or {})
        if data.get("business_id"):
            self._business_or_404(data["business_id"])
        return self._insert_opportunity(
            principal, data, source_kind=data.get("source_kind")
            or "manual")

    @staticmethod
    def _check_factor_keys(factors: dict) -> None:
        """Unknown factor keys are refused, never silently ignored:
        a mistyped key would otherwise change a score invisibly."""
        unknown = sorted(set(factors) - set(C.DEFAULT_FACTOR_WEIGHTS))
        if unknown:
            raise ValidationError(
                f"unknown §4.3 factor keys: {unknown}; valid keys "
                f"are {sorted(C.DEFAULT_FACTOR_WEIGHTS)}")

    def _insert_opportunity(self, principal, data, *, source_kind):
        session = self._session_factory()
        try:
            row = EconomicOpportunity(
                title=data["title"], kind=data["kind"],
                source_kind=source_kind,
                stage="discovered",
                description=data.get("description") or "",
                market_report_id=data.get("market_report_id"),
                p03_opportunity_id=data.get("p03_opportunity_id"),
                business_id=data.get("business_id"),
                market_tag=data.get("market_tag"),
                factor_scores=data.get("factor_scores") or {},
                evidence=data.get("evidence") or [],
                estimated_investment_minor=data.get(
                    "estimated_investment_minor"),
                created_by=C.actor_of(principal))
            if row.factor_scores:
                scored = scoring.score_opportunity(
                    row.factor_scores,
                    self.get_settings()["factor_weights"])
                row.total_score = scored["total_score"]
                row.classification_band = scored["band"]
            row.confidence = scoring.confidence_from_evidence(row.evidence)
            session.add(row)
            session.commit()
            session.refresh(row)
            result = opportunity_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.opportunity_created", "economy",
                    result["id"], "allow",
                    f"opportunity discovered ({source_kind}); the "
                    "pipeline requires evidence and approvals before "
                    "anything launches (§4.2)")
        return result

    def list_opportunities(self, principal: Principal, *,
                           stage: str | None = None,
                           kind: str | None = None,
                           limit: int = 100) -> dict:
        self._require_reader(principal, "economy.opportunities")
        session = self._session_factory()
        try:
            stmt = select(EconomicOpportunity)
            if stage:
                stmt = stmt.where(EconomicOpportunity.stage == stage)
            if kind:
                stmt = stmt.where(EconomicOpportunity.kind == kind)
            rows = session.execute(
                stmt.order_by(EconomicOpportunity.created_at.desc())
                .limit(limit)).scalars().all()
            items = [opportunity_dict(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": len(items),
                "funnel": self._funnel_counts(),
                "note": "funnel counts are inventory, not success "
                        "metrics (§21)"}

    def _funnel_counts(self) -> dict:
        session = self._session_factory()
        try:
            rows = session.execute(
                select(EconomicOpportunity.stage)).scalars().all()
        finally:
            session.close()
        counts = {stage: 0 for stage in C.OPPORTUNITY_STAGES}
        for stage in rows:
            counts[stage] = counts.get(stage, 0) + 1
        return counts

    def get_opportunity(self, principal: Principal,
                        opportunity_id: str) -> dict:
        self._require_reader(principal, "economy.opportunities")
        session = self._session_factory()
        try:
            row = session.get(EconomicOpportunity, opportunity_id)
            if row is None:
                raise NotFoundError(
                    f"opportunity {opportunity_id} not found")
            return opportunity_dict(row)
        finally:
            session.close()

    def score_opportunity(self, principal: Principal,
                          opportunity_id: str,
                          factors: dict | None = None) -> dict:
        """§4.3: (re)score with the owner's weights. Confidence is
        always recomputed from the attached evidence — it is never
        a caller-supplied number."""
        self._require_owner(principal, "economy.opportunity.score")
        settings = self.get_settings()
        session = self._session_factory()
        try:
            row = session.get(EconomicOpportunity, opportunity_id)
            if row is None:
                raise NotFoundError(
                    f"opportunity {opportunity_id} not found")
            if factors:
                self._check_factor_keys(factors)
                row.factor_scores = factors
            scored = scoring.score_opportunity(
                row.factor_scores or {}, settings["factor_weights"])
            row.total_score = scored["total_score"]
            row.classification_band = scored["band"]
            row.confidence = scoring.confidence_from_evidence(
                row.evidence or [])
            session.commit()
            session.refresh(row)
            result = opportunity_dict(row)
            result["scoring"] = scored
            result["confidence_basis"] = (
                "computed from attached evidence: source-backed "
                "items weigh most; corroboration (3+) adds a bonus")
        finally:
            session.close()
        self._audit(principal, "economy.opportunity_scored", "economy",
                    opportunity_id, "allow",
                    f"score {result['total_score']} "
                    f"({result['classification_band']}), confidence "
                    f"{result['confidence']}")
        return result

    def advance_opportunity(self, principal: Principal,
                            opportunity_id: str, target: str) -> dict:
        self._require_owner(principal, "economy.opportunity.advance")
        if target not in C.OPPORTUNITY_STAGES:
            raise ValidationError(f"unknown stage: {target}")
        settings = self.get_settings()
        session = self._session_factory()
        try:
            row = session.get(EconomicOpportunity, opportunity_id)
            if row is None:
                raise NotFoundError(
                    f"opportunity {opportunity_id} not found")
            current = row.stage
            if current in C.OPPORTUNITY_TERMINAL:
                raise ValidationError(
                    f"opportunity is {current} (terminal); it cannot "
                    "move further")
            if target in ("rejected", "archived"):
                pass  # exits are always available
            elif target == "active":
                if current != "launch_approved":
                    raise ValidationError(
                        "active requires launch_approved first")
            else:
                chain = C.OPPORTUNITY_CHAIN
                if chain.index(target) <= chain.index(current):
                    raise ValidationError(
                        f"cannot move from {current} back/sideways "
                        f"to {target}; the pipeline moves forward")
                # --- gates on boundary crossings
                if settings["expansion_paused"]:
                    raise PermissionDeniedError(
                        "expansion is paused by the owner (§18); "
                        "pipeline movement is refused until resumed")
                if target == "approval_pending":
                    confidence = scoring.confidence_from_evidence(
                        row.evidence or [])
                    row.confidence = confidence
                    if confidence < settings[
                            "evidence_gate_min_confidence"] or \
                            len(row.evidence or []) < settings[
                                "evidence_gate_min_items"]:
                        raise ValidationError(
                            "evidence gate (§4.3): approval_pending "
                            f"requires confidence >= {settings['evidence_gate_min_confidence']} "
                            f"and >= {settings['evidence_gate_min_items']} "
                            "evidence items; a high score with weak "
                            "evidence must not receive approval")
                if row.kind in C.GATE_BLOCKED_OPPORTUNITY_KINDS and \
                        chain.index(target) > chain.index(
                            "financial_evaluation") and \
                        chain.index(current) <= chain.index(
                            "financial_evaluation"):
                    gate = self._gate()
                    if gate["state"] == "closed" and not row.gate_override:
                        raise PermissionDeniedError(
                            "owner's profitability gate is closed: "
                            f"{gate['reason']}. New-business and "
                            "market-entry opportunities cannot pass "
                            "financial_evaluation until the existing "
                            "portfolio is verifiably profitable, or "
                            "the owner records an explicit override")
                if target == "experimentation" and \
                        settings["autonomy_level"] < 3:
                    raise PermissionDeniedError(
                        "experimentation requires economy autonomy "
                        "level 3 (controlled experimentation, §18); "
                        f"current level is {settings['autonomy_level']}")
            row.stage = target
            session.commit()
            session.refresh(row)
            result = opportunity_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.opportunity_advanced",
                    "economy", opportunity_id, "allow",
                    f"{current} -> {target}")
        return result

    def record_opportunity_override(self, principal: Principal,
                                    opportunity_id: str,
                                    reason: str) -> dict:
        """Owner-only profitability-gate override for one
        opportunity, with a mandatory recorded reason (§18: the
        user retains final authority; the system never overrides
        itself)."""
        self._require_owner(principal, "economy.opportunity.override")
        if not (reason or "").strip():
            raise ValidationError("a gate override requires a reason")
        session = self._session_factory()
        try:
            row = session.get(EconomicOpportunity, opportunity_id)
            if row is None:
                raise NotFoundError(
                    f"opportunity {opportunity_id} not found")
            row.gate_override = {
                "by": C.actor_of(principal), "reason": reason,
                "at": utcnow().isoformat(),
                "gate_reason_at_override": self._gate()["reason"]}
            session.commit()
            session.refresh(row)
            result = opportunity_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.gate_override", "economy",
                    opportunity_id, "allow",
                    f"owner overrode the profitability gate: {reason}")
        return result

    # ------------------------------------------------- §4.2 detectors
    def run_discovery(self, principal: Principal) -> dict:
        """Deterministic discovery over live P-07/P-13/P-16 state.
        No external research is claimed (DEF-A2 posture): detectors
        read the portfolio's own verified figures and records.
        Deduplicated on (detector key, business/asset)."""
        self._require_owner(principal, "economy.discovery.run")
        from ..permissions.models import PrincipalType as PT
        system = Principal(PT.SYSTEM, "p16-discovery")
        created = []
        session = self._session_factory()
        try:
            existing = {(r.market_tag, r.business_id) for r in
                        session.execute(select(EconomicOpportunity)
                                        .where(EconomicOpportunity
                                               .source_kind == "detector")
                                        ).scalars()
                        if r.stage not in ("rejected", "archived")}
            assets_without_proposal = self._assets_without_proposals(
                session)
        finally:
            session.close()

        def maybe(tag, business_id, payload):
            if (tag, business_id) in existing:
                return
            created.append(self._insert_opportunity(
                system, payload, source_kind="detector"))

        gate = self._gate()
        for prow in self._profitability_rows():
            bid = prow["business_id"]
            if not prow["has_profile"]:
                continue
            if prow["net_profit_minor"] is not None and \
                    prow["net_profit_minor"] < 0:
                maybe(f"detector:loss_making:{bid}", bid, {
                    "title": f"Improve profitability of {prow['name']}",
                    "kind": "existing_business_expansion",
                    "business_id": bid,
                    "market_tag": f"detector:loss_making:{bid}",
                    "description": "detector: this business is "
                                   "loss-making on verified P-07 "
                                   "figures; the owner's priority is "
                                   "profitability of existing "
                                   "businesses before new ones"})
            summary = self._financial.business_summary(bid)
            metrics = summary["revenue"]
            if (metrics.get("net_collected_minor") or 0) > 0 and \
                    (metrics.get("mrr_minor") or 0) == 0:
                maybe(f"detector:no_recurring:{bid}", bid, {
                    "title": f"Add a recurring revenue stream to "
                             f"{prow['name']}",
                    "kind": "new_revenue_stream",
                    "business_id": bid,
                    "market_tag": f"detector:no_recurring:{bid}",
                    "description": "detector: verified collected "
                                   "revenue exists but recurring "
                                   "revenue (MRR) is zero (§6 "
                                   "diversification warning)"})
        concentration = self._revenue_concentration(
            self._profitability_rows())
        if concentration["overconcentrated"] and \
                concentration["top_business_id"]:
            bid = concentration["top_business_id"]
            maybe(f"detector:concentration:{bid}", bid, {
                "title": "Reduce single-business revenue "
                         "concentration",
                "kind": "new_revenue_stream",
                "business_id": bid,
                "market_tag": f"detector:concentration:{bid}",
                "description": f"detector: one business supplies "
                               f"{concentration['top_share']} of "
                               "verified collected revenue, above the "
                               "owner's threshold "
                               f"{concentration['threshold_share']} "
                               "(§5.1/§6)"})
        for asset in assets_without_proposal:
            maybe(f"detector:asset:{asset['id']}", None, {
                "title": f"Commercialize asset: {asset['name']}",
                "kind": "asset_commercialization",
                "market_tag": f"detector:asset:{asset['id']}",
                "description": "detector: a registered asset has "
                               "no commercialization proposal (§7)"})
        return {"created": created, "created_count": len(created),
                "profitability_gate": gate,
                "note": "detectors read verified internal figures "
                        "only; no external market research is "
                        "claimed (DEF-A2)"}

    def _assets_without_proposals(self, session) -> list[dict]:
        from ..database.models.economy import (
            CommercialAsset as Asset, CommercializationProposal as Prop,
        )
        proposed = {r.asset_id for r in session.execute(
            select(Prop)).scalars()}
        return [{"id": r.id, "name": r.name} for r in session.execute(
            select(Asset)).scalars() if r.id not in proposed]

    # ------------------------------------------------ §4.4 strategies
    def create_strategy(self, principal: Principal, data: dict) -> dict:
        self._require_owner(principal, "economy.strategy.create")
        if data.get("horizon") not in C.STRATEGY_HORIZONS:
            raise ValidationError(
                f"horizon must be one of {list(C.STRATEGY_HORIZONS)}")
        if data.get("kind") not in C.STRATEGY_KINDS:
            raise ValidationError(
                f"kind must be one of {list(C.STRATEGY_KINDS)}")
        if not (data.get("title") or "").strip():
            raise ValidationError("a strategy requires a title")
        if data.get("business_id"):
            self._business_or_404(data["business_id"])
        session = self._session_factory()
        try:
            row = ExpansionStrategy(
                title=data["title"], horizon=data["horizon"],
                kind=data["kind"],
                objective=data.get("objective") or "",
                business_id=data.get("business_id"),
                opportunity_id=data.get("opportunity_id"),
                financial_requirements=data.get(
                    "financial_requirements") or {},
                timeline=data.get("timeline") or "",
                required_resources=data.get("required_resources") or [],
                dependencies=data.get("dependencies") or [],
                expected_outcomes=data.get("expected_outcomes") or "",
                kpis=data.get("kpis") or [],
                risks=data.get("risks") or [],
                exit_conditions=data.get("exit_conditions") or "",
                status="proposed",
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = self._strategy_view(row)
        finally:
            session.close()
        self._audit(principal, "economy.strategy_created", "economy",
                    result["id"], "allow",
                    "expansion strategy proposed (§4.4)")
        return result

    def _strategy_view(self, row: ExpansionStrategy) -> dict:
        view = strategy_dict(row)
        gate = self._gate()
        view["blocked_by_profitability_gate"] = bool(
            row.kind in C.GATE_BLOCKED_STRATEGY_KINDS
            and gate["state"] == "closed" and not row.gate_override
            and row.status in ("draft", "proposed"))
        view["profitability_gate_state"] = gate["state"]
        return view

    def list_strategies(self, principal: Principal, *,
                        horizon: str | None = None,
                        status: str | None = None,
                        limit: int = 100) -> dict:
        self._require_reader(principal, "economy.strategies")
        session = self._session_factory()
        try:
            stmt = select(ExpansionStrategy)
            if horizon:
                stmt = stmt.where(ExpansionStrategy.horizon == horizon)
            if status:
                stmt = stmt.where(ExpansionStrategy.status == status)
            rows = session.execute(
                stmt.order_by(ExpansionStrategy.created_at.desc())
                .limit(limit)).scalars().all()
            items = [self._strategy_view(r) for r in rows]
        finally:
            session.close()
        items.sort(key=lambda s: (
            C.RECOMMENDATION_PRIORITY.get(s["kind"], 5),
            s["created_at"] or ""))
        return {"items": items, "total": len(items),
                "ordering": "owner's priority: improve existing, "
                            "diversify, capital efficiency, then new "
                            "ventures"}

    def approve_strategy(self, principal: Principal, strategy_id: str,
                         approval_id: str | None = None) -> dict:
        self._require_owner(principal, "economy.strategy.approve")
        session = self._session_factory()
        try:
            row = session.get(ExpansionStrategy, strategy_id)
            if row is None:
                raise NotFoundError(f"strategy {strategy_id} not found")
            if row.status != "proposed":
                raise ValidationError(
                    f"strategy is {row.status}; only a proposed "
                    "strategy can be approved")
            snapshot = strategy_dict(row)
        finally:
            session.close()
        if snapshot["kind"] in C.GATE_BLOCKED_STRATEGY_KINDS:
            gate = self._gate()
            if gate["state"] == "closed" and not snapshot["gate_override"]:
                self._audit(principal, "economy.strategy_approve",
                            "economy", strategy_id, "deny",
                            "profitability gate closed for a "
                            "new-business/market-entry strategy")
                raise PermissionDeniedError(
                    "owner's profitability gate is closed: "
                    f"{gate['reason']}. A {snapshot['kind']} strategy "
                    "cannot be approved until the existing portfolio "
                    "is verifiably profitable, or the owner records "
                    "an explicit override on this strategy")
        params = {"strategy_id": strategy_id, "kind": snapshot["kind"],
                  "horizon": snapshot["horizon"]}
        bound = self._owner_approval(
            principal, action=C.APPROVAL_ACTION_STRATEGY,
            resource=strategy_id, parameters=params,
            reason="P-16 expansion strategy approval (§4.4)",
            approval_id=approval_id)
        session = self._session_factory()
        try:
            row = session.get(ExpansionStrategy, strategy_id)
            row.status = "approved"
            row.approval_id = bound
            session.commit()
            session.refresh(row)
            result = self._strategy_view(row)
        finally:
            session.close()
        self._audit(principal, "economy.strategy_approved", "economy",
                    strategy_id, "allow",
                    "strategy approved under a hash-bound P-01 "
                    "approval; approval authorises the plan, it "
                    "executes nothing")
        return result

    def reject_strategy(self, principal: Principal, strategy_id: str,
                        reason: str = "") -> dict:
        self._require_owner(principal, "economy.strategy.reject")
        session = self._session_factory()
        try:
            row = session.get(ExpansionStrategy, strategy_id)
            if row is None:
                raise NotFoundError(f"strategy {strategy_id} not found")
            if row.status not in ("draft", "proposed"):
                raise ValidationError(
                    f"strategy is {row.status}; it cannot be rejected")
            row.status = "rejected"
            session.commit()
            session.refresh(row)
            result = self._strategy_view(row)
        finally:
            session.close()
        self._audit(principal, "economy.strategy_rejected", "economy",
                    strategy_id, "allow", reason or "owner rejected")
        return result

    def record_strategy_override(self, principal: Principal,
                                 strategy_id: str, reason: str) -> dict:
        self._require_owner(principal, "economy.strategy.override")
        if not (reason or "").strip():
            raise ValidationError("a gate override requires a reason")
        session = self._session_factory()
        try:
            row = session.get(ExpansionStrategy, strategy_id)
            if row is None:
                raise NotFoundError(f"strategy {strategy_id} not found")
            row.gate_override = {
                "by": C.actor_of(principal), "reason": reason,
                "at": utcnow().isoformat(),
                "gate_reason_at_override": self._gate()["reason"]}
            session.commit()
            session.refresh(row)
            result = self._strategy_view(row)
        finally:
            session.close()
        self._audit(principal, "economy.gate_override", "economy",
                    strategy_id, "allow",
                    f"owner overrode the profitability gate: {reason}")
        return result

    # ------------------------------------------- §15I recommendations
    def strategic_recommendations(self, principal: Principal) -> dict:
        """Deterministic recommendations in the owner's priority
        order: (0) fix existing profitability, (1) diversify
        existing revenue, (2) capital efficiency, (3)
        commercialize assets, (4) new ventures/markets — the last
        only actionable while the gate is open."""
        self._require_reader(principal, "economy.recommendations")
        gate = self._gate()
        items: list[dict] = []

        def add(priority, kind, title, rationale, **refs):
            items.append({"priority": priority, "kind": kind,
                          "title": title, "rationale": rationale,
                          "gate_blocked": bool(
                              kind in C.GATE_BLOCKED_STRATEGY_KINDS
                              and gate["state"] == "closed"),
                          **refs})

        if gate["state"] == "closed":
            add(0, "improve_existing",
                "Restore portfolio profitability before expanding",
                f"profitability gate is closed: {gate['reason']}")
        for prow in self._profitability_rows():
            if prow["has_profile"] and prow["net_profit_minor"] is not None \
                    and prow["net_profit_minor"] < 0:
                add(0, "improve_existing",
                    f"Make {prow['name']} profitable",
                    "verified net profit is negative on P-07 figures",
                    business_id=prow["business_id"])
        classifications = self.list_classifications(principal)
        for flag in classifications["overconcentration_flags"]:
            add(1, "diversification",
                "Reduce single-business revenue concentration",
                f"one business supplies {flag['revenue_share']} of "
                "verified collected revenue",
                business_id=flag["business_id"])
        session = self._session_factory()
        try:
            uncommercialized = self._assets_without_proposals(session)
            open_opportunities = [opportunity_dict(r) for r in
                                  session.execute(
                                      select(EconomicOpportunity)
                                      .where(EconomicOpportunity.stage
                                             .notin_(("rejected",
                                                      "archived",
                                                      "active"))))
                                  .scalars()]
            # §17 pattern consumption: a market tag with two or
            # more recorded experiment failures deprioritises
            # opportunities carrying that tag (correlation, not
            # causation — the rationale says so on the item).
            from ..database.models.economy import ExperimentProposal
            failures_by_tag: dict[str, int] = {}
            for proposal in session.execute(
                    select(ExperimentProposal).where(
                        ExperimentProposal.outcome.is_not(None))
            ).scalars():
                if (proposal.outcome or {}).get("result") == "failure" \
                        and proposal.market_tag:
                    failures_by_tag[proposal.market_tag] = \
                        failures_by_tag.get(proposal.market_tag, 0) + 1
            failed_tags = {tag for tag, n in failures_by_tag.items()
                           if n >= 2}
        finally:
            session.close()
        for asset in uncommercialized:
            add(3, "commercialization",
                f"Evaluate commercializing: {asset['name']}",
                "registered asset with no commercialization "
                "proposal (§7)", asset_id=asset["id"])
        for opp in open_opportunities:
            if opp["classification_band"] in (
                    "strong_candidate", "strategic_candidate") and \
                    opp["stage"] in ("market_validation",
                                     "financial_evaluation",
                                     "risk_assessment",
                                     "approval_pending"):
                priority = C.RECOMMENDATION_PRIORITY.get(opp["kind"], 5) \
                    if opp["kind"] in C.GATE_BLOCKED_OPPORTUNITY_KINDS \
                    else 4
                rationale = (f"score {opp['total_score']} "
                             f"({opp['classification_band']}), confidence "
                             f"{opp['confidence']}")
                if opp.get("market_tag") in failed_tags:
                    priority += 3
                    rationale += (
                        f"; deprioritised: market tag "
                        f"'{opp['market_tag']}' has "
                        f"{failures_by_tag[opp['market_tag']]} recorded "
                        "experiment failures (§17 pattern — correlation, "
                        "not proven causation)")
                add(priority, opp["kind"],
                    f"Advance opportunity: {opp['title']}",
                    rationale, opportunity_id=opp["id"])
        items.sort(key=lambda i: (i["priority"], i["title"]))
        return {"items": items, "total": len(items),
                "profitability_gate": gate,
                "ordering": "owner's priority: profitability, "
                            "diversification, capital efficiency, "
                            "then new ventures",
                "generated_at": utcnow().isoformat()}
