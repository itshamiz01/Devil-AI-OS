"""VenturesMixin — §7 asset commercialization, §11 economic
experiment proposals, and §17 pattern detection.

Boundaries held throughout:

* A commercialization proposal never sells, licenses or publishes
  anything. Approval requires verified ownership and commercial-use
  permission; the handoff creates a P-03 opportunity (the P-13
  venture pattern) and P-06's governed gates decide creation.
* An experiment proposal is a pre-declaration (Constitution rule):
  hypothesis, budget ceiling, duration, success/failure metrics and
  stop conditions must all exist before approval. Execution lives
  in P-08 — the handoff creates the real P-08 experiment, which
  binds a P-07 budget and enforces the mechanical stop-loss. A
  proposal without a business has no execution path and stays a
  validated design.
* Experiment proposals are NOT blocked by the profitability gate:
  controlled experiments on existing businesses are the owner's
  first instrument for *making* the portfolio profitable. Their
  budgets remain bounded and P-08-governed.
"""
from __future__ import annotations

from sqlalchemy import select

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.base import utcnow
from ..database.models.economy import (
    CommercialAsset, CommercializationProposal, EconomicDecision,
    ExperimentProposal,
)
from ..permissions.models import Principal
from . import constants as C


def _iso(value):
    from ..database.models.base import as_utc
    value = as_utc(value)
    return value.isoformat() if value else None


def asset_dict(row: CommercialAsset) -> dict:
    return {"id": row.id, "name": row.name, "kind": row.kind,
            "owner_business_id": row.owner_business_id,
            "ownership_status": row.ownership_status,
            "commercial_use_permitted": row.commercial_use_permitted,
            "description": row.description,
            "assessment": row.assessment or {},
            "is_fixture": row.is_fixture,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def proposal_dict(row: CommercializationProposal) -> dict:
    return {"id": row.id, "asset_id": row.asset_id,
            "title": row.title, "rationale": row.rationale,
            "pricing_model": row.pricing_model,
            "estimated_cost_minor": row.estimated_cost_minor,
            "estimated_cost_label": "estimate only (§7)",
            "status": row.status,
            "decision_reason": row.decision_reason,
            "p03_opportunity_id": row.p03_opportunity_id,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def experiment_dict(row: ExperimentProposal) -> dict:
    return {"id": row.id, "title": row.title,
            "hypothesis": row.hypothesis,
            "target_market": row.target_market,
            "business_id": row.business_id,
            "opportunity_id": row.opportunity_id,
            "market_tag": row.market_tag,
            "budget_ceiling_minor": row.budget_ceiling_minor,
            "budget_label": "PROPOSED ceiling — on handoff P-08 "
                            "creates the real P-07 budget and "
                            "enforces the stop-loss against it",
            "duration_days": row.duration_days,
            "success_metrics": row.success_metrics or [],
            "failure_metrics": row.failure_metrics or [],
            "risk_assessment": row.risk_assessment,
            "stop_conditions": row.stop_conditions or [],
            "problem": row.problem,
            "target_customer": row.target_customer,
            "expected_outcome": row.expected_outcome,
            "minimum_evidence": row.minimum_evidence,
            "evaluation_schedule": row.evaluation_schedule,
            "max_acceptable_loss_minor": row.max_acceptable_loss_minor,
            "status": row.status, "approval_id": row.approval_id,
            "p08_experiment_id": row.p08_experiment_id,
            "outcome": row.outcome,
            "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


class VenturesMixin:
    # ------------------------------------------------------- §7 assets
    def create_asset(self, principal: Principal, data: dict) -> dict:
        self._require_owner(principal, "economy.asset.create")
        if data.get("kind") not in C.ASSET_KINDS:
            raise ValidationError(
                f"kind must be one of {list(C.ASSET_KINDS)} (§7)")
        if not (data.get("name") or "").strip():
            raise ValidationError("an asset requires a name")
        if data.get("ownership_status") and \
                data["ownership_status"] not in C.OWNERSHIP_STATES:
            raise ValidationError(
                f"ownership_status must be one of "
                f"{list(C.OWNERSHIP_STATES)}")
        if data.get("owner_business_id"):
            self._business_or_404(data["owner_business_id"])
        session = self._session_factory()
        try:
            row = CommercialAsset(
                name=data["name"], kind=data["kind"],
                owner_business_id=data.get("owner_business_id"),
                ownership_status=data.get("ownership_status")
                or "unverified",
                commercial_use_permitted=bool(
                    data.get("commercial_use_permitted")),
                description=data.get("description") or "",
                assessment=data.get("assessment") or {},
                is_fixture=bool(data.get("is_fixture")),
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = asset_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.asset_created", "economy",
                    result["id"], "allow",
                    "commercial asset registered (§7)")
        return result

    def list_assets(self, principal: Principal, *,
                    limit: int = 100) -> dict:
        self._require_reader(principal, "economy.assets")
        session = self._session_factory()
        try:
            rows = session.execute(
                select(CommercialAsset).order_by(
                    CommercialAsset.created_at.desc())
                .limit(limit)).scalars().all()
            return {"items": [asset_dict(r) for r in rows],
                    "total": len(rows)}
        finally:
            session.close()

    # ------------------------------------------- §7 commercialization
    def create_commercialization(self, principal: Principal,
                                 data: dict) -> dict:
        self._require_owner(principal, "economy.commercialization.create")
        session = self._session_factory()
        try:
            asset = session.get(CommercialAsset, data.get("asset_id"))
            if asset is None:
                raise NotFoundError(
                    f"asset {data.get('asset_id')} not found")
            rights_warning = None
            if asset.ownership_status != "verified_owner" or \
                    not asset.commercial_use_permitted:
                rights_warning = (
                    "rights not fully verified: approval and "
                    "handoff are blocked until ownership is "
                    "verified_owner and commercial use is permitted "
                    "(§7)")
            row = CommercializationProposal(
                asset_id=asset.id,
                title=data.get("title") or
                f"Commercialize: {asset.name}",
                rationale=data.get("rationale") or "",
                pricing_model=data.get("pricing_model") or "",
                estimated_cost_minor=data.get("estimated_cost_minor"),
                status="proposed",
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = proposal_dict(row)
            result["rights_warning"] = rights_warning
        finally:
            session.close()
        self._audit(principal, "economy.commercialization_created",
                    "economy", result["id"], "allow",
                    "commercialization proposal created (§7)")
        return result

    def list_commercialization(self, principal: Principal, *,
                               limit: int = 100) -> dict:
        self._require_reader(principal, "economy.commercialization")
        session = self._session_factory()
        try:
            rows = session.execute(
                select(CommercializationProposal).order_by(
                    CommercializationProposal.created_at.desc())
                .limit(limit)).scalars().all()
            return {"items": [proposal_dict(r) for r in rows],
                    "total": len(rows)}
        finally:
            session.close()

    def decide_commercialization(self, principal: Principal,
                                 proposal_id: str, *, approve: bool,
                                 reason: str = "") -> dict:
        self._require_owner(principal,
                            "economy.commercialization.decide")
        session = self._session_factory()
        try:
            row = session.get(CommercializationProposal, proposal_id)
            if row is None:
                raise NotFoundError(
                    f"proposal {proposal_id} not found")
            if row.status != "proposed":
                raise ValidationError(
                    f"proposal is {row.status}; only a proposed one "
                    "can be decided")
            asset = session.get(CommercialAsset, row.asset_id)
            if approve:
                if asset is None or \
                        asset.ownership_status != "verified_owner" or \
                        not asset.commercial_use_permitted:
                    raise PermissionDeniedError(
                        "commercialization approval refused: "
                        "ownership must be verified_owner and "
                        "commercial use permitted before an asset "
                        "may be turned into a product (§7 — never "
                        "sell or license what the owner does not "
                        "own or may not use)")
                row.status = "approved"
            else:
                row.status = "rejected"
            row.decision_reason = reason or None
            session.commit()
            session.refresh(row)
            result = proposal_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.commercialization_decided",
                    "economy", proposal_id, "allow",
                    f"proposal {'approved' if approve else 'rejected'}")
        return result

    def handoff_commercialization(self, principal: Principal,
                                  proposal_id: str) -> dict:
        """Approved proposal → P-03 opportunity at level 0 (the
        P-13 venture pattern). P-06 remains the only creation
        authority and applies its own gates from there."""
        self._require_owner(principal,
                            "economy.commercialization.handoff")
        session = self._session_factory()
        try:
            row = session.get(CommercializationProposal, proposal_id)
            if row is None:
                raise NotFoundError(
                    f"proposal {proposal_id} not found")
            if row.status != "approved":
                raise ValidationError(
                    "only an owner-APPROVED commercialization "
                    "proposal can be handed to the pipeline")
            snapshot = proposal_dict(row)
            asset = session.get(CommercialAsset, row.asset_id)
            asset_name = asset.name if asset else snapshot["title"]
        finally:
            session.close()
        if self._discovery is None:
            raise ValidationError("discovery engine unavailable")
        opportunity = self._discovery.create_opportunity(principal, {
            "name": snapshot["title"],
            "category": "digital_products",
            "description": snapshot["rationale"] or
                           f"commercialization of asset {asset_name}",
            "proposed_solution": "P-16 commercialization proposal "
                                 "handed off for normal P-03 "
                                 "validation; P-06 gates decide "
                                 "creation",
        })
        opportunity_id = getattr(opportunity, "id", None)
        session = self._session_factory()
        try:
            row = session.get(CommercializationProposal, proposal_id)
            row.status = "handed_off"
            row.p03_opportunity_id = opportunity_id
            session.commit()
            session.refresh(row)
            result = proposal_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.commercialization_handed_off",
                    "economy", proposal_id, "allow",
                    "handed to the P-03→P-06 pipeline; no business "
                    "was created by P-16",
                    {"p03_opportunity_id": opportunity_id})
        return result

    # ------------------------------------------------ §11 experiments
    def create_experiment_proposal(self, principal: Principal,
                                   data: dict) -> dict:
        self._require_owner(principal, "economy.experiment.create")
        missing = [field for field in
                   ("hypothesis", "success_metrics", "failure_metrics",
                    "stop_conditions")
                   if data.get(field) in (None, "", [])]
        if missing:
            raise ValidationError(
                "experiment pre-declaration is incomplete "
                f"(Constitution rule): missing {missing}. Nothing "
                "is approved on a partial declaration.")
        if not (data.get("title") or "").strip():
            raise ValidationError("an experiment proposal requires "
                                  "a title")
        if int(data.get("budget_ceiling_minor") or 0) <= 0:
            raise ValidationError("budget_ceiling_minor must be "
                                  "positive (§11)")
        if int(data.get("duration_days") or 0) <= 0:
            raise ValidationError("duration_days must be positive")
        if data.get("business_id"):
            self._business_or_404(data["business_id"])
        session = self._session_factory()
        try:
            row = ExperimentProposal(
                title=data["title"], hypothesis=data["hypothesis"],
                target_market=data.get("target_market") or "",
                business_id=data.get("business_id"),
                opportunity_id=data.get("opportunity_id"),
                market_tag=data.get("market_tag"),
                budget_ceiling_minor=int(data["budget_ceiling_minor"]),
                duration_days=int(data["duration_days"]),
                success_metrics=data["success_metrics"],
                failure_metrics=data["failure_metrics"],
                risk_assessment=data.get("risk_assessment") or "",
                stop_conditions=data["stop_conditions"],
                problem=data.get("problem") or "",
                target_customer=data.get("target_customer") or "",
                expected_outcome=data.get("expected_outcome") or "",
                minimum_evidence=data.get("minimum_evidence") or "",
                evaluation_schedule=data.get("evaluation_schedule")
                or "",
                max_acceptable_loss_minor=data.get(
                    "max_acceptable_loss_minor"),
                status="proposed",
                created_by=C.actor_of(principal))
            session.add(row)
            session.commit()
            session.refresh(row)
            result = experiment_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.experiment_created",
                    "economy", result["id"], "allow",
                    "experiment pre-declaration recorded (§11); "
                    "budgets never auto-increase — scaling requires "
                    "sufficient evidence and a new decision")
        return result

    def list_experiment_proposals(self, principal: Principal, *,
                                  business_id: str | None = None,
                                  limit: int = 100) -> dict:
        self._require_reader(principal, "economy.experiments")
        session = self._session_factory()
        try:
            stmt = select(ExperimentProposal)
            if business_id:
                stmt = stmt.where(
                    ExperimentProposal.business_id == business_id)
            rows = session.execute(
                stmt.order_by(ExperimentProposal.created_at.desc())
                .limit(limit)).scalars().all()
            return {"items": [experiment_dict(r) for r in rows],
                    "total": len(rows)}
        finally:
            session.close()

    def approve_experiment_proposal(self, principal: Principal,
                                    proposal_id: str,
                                    approval_id: str | None = None
                                    ) -> dict:
        self._require_owner(principal, "economy.experiment.approve")
        session = self._session_factory()
        try:
            row = session.get(ExperimentProposal, proposal_id)
            if row is None:
                raise NotFoundError(
                    f"experiment proposal {proposal_id} not found")
            if row.status != "proposed":
                raise ValidationError(
                    f"proposal is {row.status}; only a proposed one "
                    "can be approved")
            snapshot = experiment_dict(row)
        finally:
            session.close()
        params = {"proposal_id": proposal_id,
                  "budget_ceiling_minor": snapshot["budget_ceiling_minor"],
                  "business_id": snapshot["business_id"]}
        bound = self._owner_approval(
            principal, action=C.APPROVAL_ACTION_EXPERIMENT,
            resource=proposal_id, parameters=params,
            reason="P-16 economic experiment pre-approval (§11/§18 "
                   "level 3): budget-limited, stop conditions "
                   "declared",
            approval_id=approval_id)
        session = self._session_factory()
        try:
            row = session.get(ExperimentProposal, proposal_id)
            row.status = "approved"
            row.approval_id = bound
            session.commit()
            session.refresh(row)
            result = experiment_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.experiment_approved",
                    "economy", proposal_id, "allow",
                    "experiment approved under a hash-bound P-01 "
                    "approval; execution still requires the P-08 "
                    "handoff")
        return result

    def handoff_experiment_proposal(self, principal: Principal,
                                    proposal_id: str) -> dict:
        """Approved proposal → real P-08 experiment (which creates
        the P-07 budget and enforces the stop-loss). Requires
        economy autonomy level 3 (§18) and a business: without one
        there is no governed execution path, and the proposal
        honestly stays a validated design."""
        self._require_owner(principal, "economy.experiment.handoff")
        settings = self.get_settings()
        if settings["expansion_paused"]:
            raise PermissionDeniedError(
                "expansion is paused by the owner (§18); experiment "
                "handoffs are refused until resumed")
        if settings["autonomy_level"] < 3:
            raise PermissionDeniedError(
                "experiment execution requires economy autonomy "
                "level 3 (controlled experimentation, §18); "
                f"current level is {settings['autonomy_level']}")
        session = self._session_factory()
        try:
            row = session.get(ExperimentProposal, proposal_id)
            if row is None:
                raise NotFoundError(
                    f"experiment proposal {proposal_id} not found")
            if row.status != "approved":
                raise ValidationError(
                    "only an APPROVED experiment proposal can be "
                    "handed to P-08")
            snapshot = experiment_dict(row)
        finally:
            session.close()
        if not snapshot["business_id"]:
            raise ValidationError(
                "this proposal has no business attached; P-08 "
                "experiments are business-scoped, so there is no "
                "governed execution path — the proposal remains a "
                "validated design")
        if self._survival is None:
            raise ValidationError("survival engine unavailable")
        declaration = {
            "name": snapshot["title"],
            "hypothesis": snapshot["hypothesis"],
            "problem": snapshot["problem"] or
                       snapshot["target_market"] or
                       "economic experiment (P-16 proposal)",
            "target_customer": snapshot["target_customer"] or
                               snapshot["target_market"] or
                               "existing customers",
            "expected_outcome": snapshot["expected_outcome"] or
                                "; ".join(snapshot["success_metrics"]),
            "success_metric": "; ".join(snapshot["success_metrics"]),
            "failure_metric": "; ".join(snapshot["failure_metrics"]),
            "minimum_evidence": snapshot["minimum_evidence"] or
                                "declared success/failure metrics "
                                "observed over the experiment "
                                "duration",
            "evaluation_schedule": snapshot["evaluation_schedule"]
                                   or "end of duration",
            "max_duration_days": snapshot["duration_days"],
            "approved_budget_minor": snapshot["budget_ceiling_minor"],
            "max_acceptable_loss_minor":
                snapshot["max_acceptable_loss_minor"]
                if snapshot.get("max_acceptable_loss_minor")
                is not None else snapshot["budget_ceiling_minor"],
            "currency": "INR",
        }
        experiment = self._survival.experiments.create_experiment(
            principal, snapshot["business_id"], declaration)
        self._survival.experiments.approve_experiment(
            principal, experiment["id"], {})
        session = self._session_factory()
        try:
            row = session.get(ExperimentProposal, proposal_id)
            row.status = "handed_off"
            row.p08_experiment_id = experiment["id"]
            session.commit()
            session.refresh(row)
            result = experiment_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.experiment_handed_off",
                    "economy", proposal_id, "allow",
                    "handed to P-08; the P-07 budget it created is "
                    "the stop-loss enforcement surface",
                    {"p08_experiment_id": experiment["id"]})
        return result

    def sync_experiment_outcome(self, principal: Principal,
                                proposal_id: str) -> dict:
        """Read the P-08 evaluation back into the proposal and feed
        the verified outcome to P-09 (§17). Until P-08 records an
        evaluation, the outcome stays honestly unknown."""
        self._require_owner(principal, "economy.experiment.sync")
        session = self._session_factory()
        try:
            row = session.get(ExperimentProposal, proposal_id)
            if row is None:
                raise NotFoundError(
                    f"experiment proposal {proposal_id} not found")
            snapshot = experiment_dict(row)
        finally:
            session.close()
        if not snapshot["p08_experiment_id"]:
            raise ValidationError(
                "proposal has not been handed to P-08; there is no "
                "outcome to sync")
        evaluations = self._survival.experiments.list_evaluations(
            snapshot["p08_experiment_id"])
        if not evaluations:
            return {**snapshot, "outcome_sync": "no P-08 evaluation "
                    "recorded yet; outcome remains unknown"}
        latest = evaluations[-1]
        classification = str(latest.get("classification") or "")
        if "VALID" in classification and "INVALID" not in classification:
            result_value = "success"
        elif "INVALID" in classification or "FAIL" in classification:
            result_value = "failure"
        else:
            result_value = "mixed"
        outcome = {"result": result_value,
                   "p08_classification": classification,
                   "evaluation": latest,
                   "synced_at": utcnow().isoformat()}
        session = self._session_factory()
        try:
            row = session.get(ExperimentProposal, proposal_id)
            row.outcome = outcome
            row.status = "evaluated"
            session.commit()
            session.refresh(row)
            result = experiment_dict(row)
        finally:
            session.close()
        self._audit(principal, "economy.experiment_outcome_synced",
                    "economy", proposal_id, "allow",
                    f"P-08 evaluation synced: {classification}")
        self._feed_memory(
            principal,
            title=f"Experiment outcome: {result_value}",
            content=(f"Experiment '{snapshot['title']}' "
                     f"(market: {snapshot['market_tag'] or 'untagged'})"
                     f" evaluated by P-08 as {classification}."),
            source_ref=f"p16:experiment:{proposal_id}",
            business_id=snapshot["business_id"])
        return result

    # ------------------------------------------------ §17 patterns
    def market_patterns(self, principal: Principal) -> dict:
        """§17: recurring patterns over recorded outcomes. Two or
        more failed experiments in one market tag produce a
        deprioritisation pattern. Correlation is labelled as
        correlation — the pattern lowers priority; it does not
        prove causation."""
        self._require_reader(principal, "economy.patterns")
        session = self._session_factory()
        try:
            proposals = session.execute(
                select(ExperimentProposal).where(
                    ExperimentProposal.outcome.is_not(None))).scalars().all()
            decisions = session.execute(
                select(EconomicDecision).where(
                    EconomicDecision.outcome.is_not(None))).scalars().all()
        finally:
            session.close()
        by_market: dict[str, dict] = {}
        for row in proposals:
            tag = row.market_tag or "untagged"
            entry = by_market.setdefault(
                tag, {"market_tag": tag, "failures": 0, "successes": 0,
                      "mixed": 0})
            result = (row.outcome or {}).get("result")
            if result == "failure":
                entry["failures"] += 1
            elif result == "success":
                entry["successes"] += 1
            else:
                entry["mixed"] += 1
        patterns = []
        for tag, entry in by_market.items():
            if entry["failures"] >= 2:
                patterns.append({
                    **entry, "pattern": "repeated_failure",
                    "effect": "opportunities with this market tag "
                              "are deprioritised in recommendations "
                              "until contrary evidence is recorded",
                    "caution": "correlation, not proven causation "
                               "(§17)"})
        return {"patterns": patterns,
                "market_outcomes": list(by_market.values()),
                "decision_outcomes_recorded": len(decisions),
                "basis": "recorded P-16 experiment outcomes and "
                         "decision outcomes only"}
