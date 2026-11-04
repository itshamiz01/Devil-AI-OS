"""Decision intelligence (P-02 §10) and autonomy levels (P-02 §15).

§10.4 separates three responsibilities that must never be conflated:

* **AI reasoning** evaluates options and *recommends*.
* **The policy engine** determines whether an action is *permitted*.
* **The human owner** holds authority over anything requiring *approval*.

The code enforces that separation structurally: `DecisionEngine` can produce a
`RECOMMENDATION` or a `PROPOSAL`, but it has no method that returns
`AUTHORIZED`. Authorization is only ever recorded by `record_authorization`,
which requires an owner principal id and refuses to accept one supplied by a
model. A high-confidence recommendation therefore cannot become an authorized
decision by any path through this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .schemas import (
    RISK_RANK,
    Decision,
    DecisionOption,
    DecisionStatus,
    RiskLevel,
    UncertaintyLevel,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Scoring (§10.2)
# --------------------------------------------------------------------------- #


#: Default criterion weights. Documented here rather than buried in code so the
#: methodology is inspectable, as §10.2 requires.
#:
#: These weights are a **transparent ordering heuristic**, not a probability
#: model. A score of 0.72 does not mean a 72% chance of success, and nothing in
#: this module reports it that way (§10.2, §16).
DEFAULT_WEIGHTS: dict[str, float] = {
    "estimated_benefit": 0.25,
    "probability_of_success": 0.20,
    "strategic_alignment": 0.15,
    "estimated_cost": -0.10,
    "estimated_time": -0.05,
    "operational_complexity": -0.05,
    "resource_consumption": -0.05,
    "risk_exposure": -0.15,
    # Reversibility is weighted positively and heavily: an option that can be
    # undone is strictly safer than one that cannot (§16).
    "reversibility": 0.10,
}

#: Criteria whose contribution is *subtractive* — higher values are worse.
INVERTED_CRITERIA = frozenset({
    "estimated_cost", "estimated_time", "operational_complexity",
    "resource_consumption", "risk_exposure",
})


@dataclass(frozen=True)
class ScoringBreakdown:
    """Per-criterion contributions, so a score can be explained (§10.2)."""

    option_id: str
    total: float
    contributions: dict[str, float] = field(default_factory=dict)

    def explain(self) -> str:
        parts = ", ".join(f"{k}={v:+.3f}" for k, v in sorted(self.contributions.items()) if abs(v) > 1e-9)
        return f"{self.option_id}: total {self.total:.3f} ({parts or 'no weighted criteria contributed'})"


class DecisionScorer:
    """Configurable, transparent weighted scoring."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = dict(DEFAULT_WEIGHTS if weights is None else weights)
        unknown = set(self.weights) - set(DEFAULT_WEIGHTS)
        if unknown:
            # A typo in a criterion name would silently drop it from the score.
            raise ValueError(f"unknown scoring criteria: {sorted(unknown)}")
        # And the converse: a weight whose name does not match a real
        # DecisionOption field is silently ignored by getattr, which once dropped
        # "benefit" from every score in the system. Verify against the model so
        # the two definitions can never drift apart again.
        real_fields = set(DecisionOption.model_fields)
        dangling = sorted(set(self.weights) - real_fields)
        if dangling:
            raise ValueError(
                f"scoring criteria do not exist on DecisionOption and would be "
                f"silently ignored: {dangling}"
            )

    def score(self, option: DecisionOption) -> ScoringBreakdown:
        contributions: dict[str, float] = {}
        for criterion, weight in self.weights.items():
            raw = getattr(option, criterion, None)
            if raw is None:
                continue
            contributions[criterion] = round(float(raw) * weight, 6)
        total = round(sum(contributions.values()), 6)
        return ScoringBreakdown(option_id=option.option_id, total=total, contributions=contributions)

    def rank(self, options: list[DecisionOption]) -> list[tuple[DecisionOption, ScoringBreakdown]]:
        """Best first. Ties break on option id so ranking is deterministic."""
        scored = [(o, self.score(o)) for o in options]
        scored.sort(key=lambda pair: (-pair[1].total, pair[0].option_id))
        return scored


# --------------------------------------------------------------------------- #
# Risk (§10.3)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RiskFactors:
    """The consequence dimensions §10.3 requires the evaluator to consider."""

    financial_exposure: float = 0.0
    data_sensitivity: float = 0.0
    external_consequences: float = 0.0
    #: 1.0 = fully reversible, 0.0 = irreversible.
    reversibility: float = 1.0
    legal_or_platform_compliance: float = 0.0
    security_impact: float = 0.0
    potential_customer_harm: float = 0.0


class RiskEvaluator:
    """Classifies risk from consequences, not from intent."""

    #: Thresholds on the weighted risk score. Documented because §10.2 forbids
    #: presenting opaque numbers as objective truth.
    MODERATE_AT = 0.20
    HIGH_AT = 0.45
    CRITICAL_AT = 0.70

    def evaluate(self, factors: RiskFactors) -> RiskLevel:
        irreversible = factors.reversibility < 0.5
        score = max(
            factors.financial_exposure,
            factors.data_sensitivity,
            factors.external_consequences,
            factors.legal_or_platform_compliance,
            factors.security_impact,
            factors.potential_customer_harm,
        )
        # An irreversible action is escalated one level: the cost of being wrong
        # cannot be recovered, so the same exposure is more dangerous (§16).
        if irreversible:
            score = min(1.0, score + 0.25)

        if score >= self.CRITICAL_AT:
            return RiskLevel.CRITICAL
        if score >= self.HIGH_AT:
            return RiskLevel.HIGH
        if score >= self.MODERATE_AT:
            return RiskLevel.MODERATE
        return RiskLevel.LOW

    def from_decision_inputs(
        self,
        *,
        financial_amount: float | None = None,
        touches_secrets: bool = False,
        external_effect: bool = False,
        reversible: bool = True,
        compliance_sensitive: bool = False,
        security_relevant: bool = False,
        affects_customers: bool = False,
    ) -> RiskLevel:
        """Convenience mapping from plain facts to a risk level.

        Financial exposure is scaled against a documented reference rather than
        treated as an absolute: the owner's stated $50 starting capital makes a
        $50 operation fully exposure-bearing, which a generic threshold would
        have called negligible.
        """
        reference_capital = 50.0
        financial = 0.0
        if financial_amount is not None and financial_amount > 0:
            financial = min(1.0, financial_amount / reference_capital)
        return self.evaluate(RiskFactors(
            financial_exposure=financial,
            data_sensitivity=1.0 if touches_secrets else 0.0,
            external_consequences=0.8 if external_effect else 0.0,
            reversibility=1.0 if reversible else 0.0,
            legal_or_platform_compliance=0.7 if compliance_sensitive else 0.0,
            security_impact=0.9 if security_relevant else 0.0,
            potential_customer_harm=0.7 if affects_customers else 0.0,
        ))


#: Risk levels that always require owner approval before execution.
APPROVAL_MANDATORY_AT = RiskLevel.HIGH


# --------------------------------------------------------------------------- #
# Decision engine (§10.1, §10.4)
# --------------------------------------------------------------------------- #


class UnauthorizedDecisionError(RuntimeError):
    """Raised when something tries to authorize a decision it may not."""


class DecisionEngine:
    """Evaluates alternatives and recommends. Never authorizes."""

    def __init__(
        self,
        *,
        scorer: DecisionScorer | None = None,
        risk_evaluator: RiskEvaluator | None = None,
    ) -> None:
        self.scorer = scorer or DecisionScorer()
        self.risk = risk_evaluator or RiskEvaluator()
        self.history: list[Decision] = []

    def evaluate(
        self,
        *,
        decision_id: str,
        problem: str,
        options: list[DecisionOption],
        mission_id: str | None = None,
        evidence_refs: list[str] | None = None,
        assumptions: list[str] | None = None,
        constraints: list[str] | None = None,
        uncertainty: UncertaintyLevel = UncertaintyLevel.UNKNOWN,
        risk_factors: RiskFactors | None = None,
        financial_amount: float | None = None,
        external_effect: bool = False,
        reversible: bool = True,
        prohibited_reason: str | None = None,
    ) -> Decision:
        """Score the alternatives and return a RECOMMENDATION.

        If `prohibited_reason` is set, no option is selected: the engine records
        the refusal rather than choosing the least-bad forbidden action. This is
        the path §20 Scenario D takes.
        """
        if not options and not prohibited_reason:
            raise ValueError("a decision needs at least one option")

        risk = self.risk.evaluate(risk_factors) if risk_factors else self.risk.from_decision_inputs(
            financial_amount=financial_amount, external_effect=external_effect, reversible=reversible
        )

        if prohibited_reason:
            decision = Decision(
                decision_id=decision_id,
                mission_id=mission_id,
                problem=problem,
                options=options,
                evidence_refs=list(evidence_refs or []),
                assumptions=list(assumptions or []),
                constraints=list(constraints or []),
                risk=RiskLevel.CRITICAL if risk == RiskLevel.LOW else risk,
                uncertainty=uncertainty,
                approval_required=True,
                status=DecisionStatus.REJECTED,
                refusal_reason=prohibited_reason,
                reasoning_summary=prohibited_reason,
            )
            self.history.append(decision)
            return decision

        ranked = self.scorer.rank(options)
        best, breakdown = ranked[0]
        scores = {r[0].option_id: r[1].total for r in ranked}

        needs_approval = RISK_RANK[risk] >= RISK_RANK[APPROVAL_MANDATORY_AT] or not reversible

        summary = (
            f"Selected {best.option_id!r} with score {breakdown.total:.3f} of "
            f"{len(options)} option(s). Ranking is a transparent weighted heuristic, "
            f"not a probability of success. {breakdown.explain()}"
        )
        if uncertainty in {UncertaintyLevel.UNKNOWN, UncertaintyLevel.ASSUMED, UncertaintyLevel.CONTRADICTED}:
            summary += (
                f" Evidence quality is {uncertainty.value}, so this recommendation "
                "should not be treated as reliable without further verification."
            )

        decision = Decision(
            decision_id=decision_id,
            mission_id=mission_id,
            problem=problem,
            options=options,
            evidence_refs=list(evidence_refs or []),
            assumptions=list(assumptions or []),
            constraints=list(constraints or []),
            scores=scores,
            selected_option_id=best.option_id,
            reasoning_summary=summary,
            risk=risk,
            uncertainty=uncertainty,
            approval_required=needs_approval,
            status=DecisionStatus.RECOMMENDATION,
        )
        self.history.append(decision)
        return decision

    def to_proposal(self, decision: Decision) -> Decision:
        """Promote a recommendation to a proposal awaiting owner decision.

        This is as far as the engine can go on its own. §10.4: the model
        recommends, the owner decides.
        """
        if decision.status != DecisionStatus.RECOMMENDATION:
            raise ValueError(f"only a RECOMMENDATION can become a PROPOSAL, not {decision.status.value}")
        proposed = decision.model_copy(update={"status": DecisionStatus.PROPOSAL})
        self._replace(proposed)
        return proposed

    def record_authorization(
        self,
        decision_id: str,
        *,
        authorizing_principal_id: str,
        authorized_by_owner: bool,
    ) -> Decision:
        """Record that the *owner* authorized a decision.

        `authorized_by_owner` must be established by the permission engine and
        passed in by the API layer. This method deliberately does not accept a
        model identifier, a confidence value, or a recommendation strength: none
        of those can authorize anything (§10.4, §16).
        """
        decision = self.get(decision_id)
        if decision is None:
            raise KeyError(f"unknown decision {decision_id!r}")
        if not authorized_by_owner:
            raise UnauthorizedDecisionError(
                f"decision {decision_id!r} was not authorized by the owner; a model "
                "recommendation, however confident, does not grant authorization"
            )
        if not authorizing_principal_id:
            raise UnauthorizedDecisionError("an authorization must name the authorizing principal")
        authorized = decision.model_copy(update={
            "status": DecisionStatus.AUTHORIZED,
            "reasoning_summary": (decision.reasoning_summary or "")
            + f" | authorized by principal {authorizing_principal_id} at {_now().isoformat()}",
        })
        self._replace(authorized)
        return authorized

    def record_outcome(self, decision_id: str, status: DecisionStatus) -> Decision:
        if status not in {DecisionStatus.COMPLETED, DecisionStatus.REJECTED, DecisionStatus.SUPERSEDED}:
            raise ValueError(f"{status.value} is not a terminal decision outcome")
        decision = self.get(decision_id)
        if decision is None:
            raise KeyError(f"unknown decision {decision_id!r}")
        updated = decision.model_copy(update={"status": status})
        self._replace(updated)
        return updated

    def get(self, decision_id: str) -> Decision | None:
        for decision in self.history:
            if decision.decision_id == decision_id:
                return decision.model_copy(deep=True)
        return None

    def for_mission(self, mission_id: str) -> list[Decision]:
        return [d.model_copy(deep=True) for d in self.history if d.mission_id == mission_id]

    def _replace(self, decision: Decision) -> None:
        for index, existing in enumerate(self.history):
            if existing.decision_id == decision.decision_id:
                self.history[index] = decision
                return
        self.history.append(decision)


__all__ = [
    "APPROVAL_MANDATORY_AT",
    "DEFAULT_WEIGHTS",
    "DecisionEngine",
    "DecisionScorer",
    "INVERTED_CRITERIA",
    "RiskEvaluator",
    "RiskFactors",
    "ScoringBreakdown",
    "UnauthorizedDecisionError",
]
