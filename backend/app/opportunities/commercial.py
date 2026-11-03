"""P-03 §13 commercial feasibility.

The brief calls this one of the most important modules, and the reason is worth
stating plainly: an opportunity that cannot be priced, cannot break even, or
does not fit the owner's capital is not an opportunity.  Most of the value in
this phase comes from finding that out early and saying so.

Invariants implemented here
---------------------------
* **All arithmetic is deterministic.**  Every figure is computed from a stated
  cost structure and a stated price.  No model, heuristic or "typical" default
  ever supplies a number.
* **Unknown is not zero.**  A cost line whose provenance is UNKNOWN makes the
  structure unpriceable, and the assessment becomes ``cannot_determine`` rather
  than quietly optimistic.
* **The owner's budget is never increased.**  :meth:`budget_compatibility`
  copies ``available_capital`` in and reports a shortfall.  There is no code
  path that writes back to the :class:`BudgetConstraint`.
* **The three scenarios are fixed.**  Conservative / base / optimistic use the
  volume factors in :data:`SCENARIO_VOLUME_FACTORS`, so results are comparable
  across opportunities and across runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.opportunities.schemas import (
    Assumption,
    BreakEvenResult,
    BudgetCompatibility,
    BudgetConstraint,
    CommercialAssessment,
    CostItem,
    CostStructure,
    FinancialProjection,
    Provenance,
    SCENARIO_VOLUME_FACTORS,
    ScenarioName,
    ScenarioProjection,
)

__all__ = [
    "CommercialFeasibilityEngine",
    "CommercialInputs",
    "MINIMUM_CONTRIBUTION_MARGIN",
]

#: Below this contribution margin a single refund, chargeback or fee change can
#: turn a sale into a loss.  It is a screening threshold, not a rejection: the
#: engine reports it and the scoring layer weighs it.
MINIMUM_CONTRIBUTION_MARGIN = Decimal("0.20")


@dataclass(frozen=True)
class CommercialInputs:
    """The complete, explicit input set for one commercial assessment.

    Frozen and fully typed so that an assessment can always be re-run from this
    record alone - the reproducibility requirement in §16 applied to §13.
    """

    costs: CostStructure
    price_per_unit: Decimal | None
    price_provenance: Provenance
    base_units_monthly: Decimal | None
    units_provenance: Provenance
    budget: BudgetConstraint | None
    period_months: int = 1

    def missing(self) -> tuple[str, ...]:
        gaps = []
        if self.price_per_unit is None:
            gaps.append("price_per_unit")
        elif self.price_provenance is Provenance.UNKNOWN:
            gaps.append("price_provenance")
        if self.base_units_monthly is None:
            gaps.append("base_units_monthly")
        elif self.units_provenance is Provenance.UNKNOWN:
            gaps.append("units_provenance")
        if self.budget is None:
            gaps.append("owner_budget")
        gaps.extend(self.costs.unpriced_items())
        return tuple(dict.fromkeys(gaps))


class CommercialFeasibilityEngine:
    """Deterministic cost, revenue, break-even and budget analysis."""

    def project(
        self,
        costs: CostStructure,
        *,
        price_per_unit: Decimal,
        units_sold: Decimal,
        period_months: int = 1,
        include_startup_in_period: bool = True,
    ) -> FinancialProjection:
        """One period of the §13.4 formula chain.

        ``recurring_fixed_cost`` is scaled to the period length; the startup
        total is charged to the first period only, because that is when the cash
        actually leaves.
        """
        recurring = costs.recurring_monthly_total() * Decimal(period_months)
        one_time = costs.startup_total() if include_startup_in_period else Decimal("0")
        return FinancialProjection(
            period_months=period_months,
            units_sold=units_sold,
            price_per_unit=price_per_unit,
            variable_cost_per_unit=costs.variable_per_unit_total(),
            recurring_fixed_cost=recurring.quantize(Decimal("0.01")),
            one_time_cost_in_period=one_time.quantize(Decimal("0.01")),
            unpriced_cost_items=costs.unpriced_items(),
        )

    def build_scenarios(
        self,
        costs: CostStructure,
        *,
        price_per_unit: Decimal,
        base_units_monthly: Decimal,
        period_months: int = 1,
    ) -> tuple[ScenarioProjection, ...]:
        """The three named scenarios, in order (§13.5).

        Only the volume varies between them.  Costs and price are held constant
        so that the spread between conservative and optimistic reflects demand
        uncertainty alone, not a mixture of unrelated guesses.
        """
        rationale = {
            ScenarioName.CONSERVATIVE: (
                "half the expected volume; the level at which the opportunity "
                "must still survive to be worth pursuing"
            ),
            ScenarioName.BASE: "the expected volume as evidenced",
            ScenarioName.OPTIMISTIC: (
                "1.75x the expected volume; shown to bound the upside, not to "
                "be planned against"
            ),
        }
        out = []
        for name in (
            ScenarioName.CONSERVATIVE,
            ScenarioName.BASE,
            ScenarioName.OPTIMISTIC,
        ):
            factor = SCENARIO_VOLUME_FACTORS[name]
            out.append(
                ScenarioProjection(
                    name=name,
                    volume_factor=factor,
                    rationale=rationale[name],
                    projection=self.project(
                        costs,
                        price_per_unit=price_per_unit,
                        units_sold=(base_units_monthly * factor).quantize(
                            Decimal("0.01")
                        ),
                        period_months=period_months,
                    ),
                )
            )
        return tuple(out)

    def break_even(
        self, costs: CostStructure, *, price_per_unit: Decimal
    ) -> BreakEvenResult:
        """Break-even volume and startup payback (§13.6)."""
        return BreakEvenResult(
            contribution_per_unit=(
                price_per_unit - costs.variable_per_unit_total()
            ).quantize(Decimal("0.01")),
            recurring_fixed_monthly=costs.recurring_monthly_total(),
            startup_cost=costs.startup_total(),
        )

    def budget_compatibility(
        self,
        costs: CostStructure,
        budget: BudgetConstraint,
        *,
        base_units_monthly: Decimal,
    ) -> BudgetCompatibility:
        """Does this fit the owner's stated capital?  (§13.7)

        ``budget`` is read only.  The returned record copies
        ``available_capital`` so that the comparison is auditable after the
        fact, and ``budget_was_modified`` is a literal ``False`` that pydantic
        will refuse to set to anything else.
        """
        startup = costs.startup_total()
        first_period = (
            startup
            + costs.recurring_monthly_total()
            + (costs.variable_per_unit_total() * base_units_monthly).quantize(
                Decimal("0.01")
            )
        )
        return BudgetCompatibility(
            available_capital=budget.available_capital,
            required_startup=startup.quantize(Decimal("0.01")),
            required_first_period_cash=first_period.quantize(Decimal("0.01")),
            unpriced_cost_items=costs.unpriced_items(),
        )

    def assess(self, inputs: CommercialInputs) -> CommercialAssessment:
        """Full §13 assessment.

        The order of the checks matters: the cheapest and most decisive
        rejection is applied first, so an opportunity that cannot be priced is
        never reported as merely "marginal".
        """
        gaps = inputs.missing()
        reasons: list[str] = []
        assumptions: list[Assumption] = []

        # 1. Anything unpriceable stops the analysis here.
        if gaps:
            return CommercialAssessment(
                costs=inputs.costs,
                verdict="cannot_determine",
                viable=False,
                affordable=False,
                reasons=(
                    "commercial analysis could not be completed; unknown inputs: "
                    + ", ".join(gaps),
                ),
                assumptions=tuple(assumptions),
            )

        price = inputs.price_per_unit
        units = inputs.base_units_monthly
        assert price is not None and units is not None  # guaranteed by gaps == ()
        budget = inputs.budget
        assert budget is not None

        scenarios = self.build_scenarios(
            inputs.costs,
            price_per_unit=price,
            base_units_monthly=units,
            period_months=inputs.period_months,
        )
        break_even = self.break_even(inputs.costs, price_per_unit=price)
        compatibility = self.budget_compatibility(
            inputs.costs, budget, base_units_monthly=units
        )
        base = next(s for s in scenarios if s.name is ScenarioName.BASE).projection
        conservative = next(
            s for s in scenarios if s.name is ScenarioName.CONSERVATIVE
        ).projection

        if inputs.price_provenance is Provenance.ESTIMATE:
            assumptions.append(
                Assumption(
                    statement=f"unit price of {price} {budget.currency} is an estimate, not a quoted or verified figure",
                    basis=Provenance.ESTIMATE,
                    affects=("revenue", "break_even", "profit"),
                    sensitivity="high",
                )
            )
        if inputs.units_provenance is Provenance.ESTIMATE:
            assumptions.append(
                Assumption(
                    statement=f"monthly volume of {units} units is an estimate, not observed demand",
                    basis=Provenance.ESTIMATE,
                    affects=("revenue", "profit", "payback"),
                    sensitivity="high",
                )
            )

        # 2. Budget: the most common real-world rejection.
        if not compatibility.compatible:
            reasons.append(compatibility.reason or "budget incompatible")
            return CommercialAssessment(
                costs=inputs.costs,
                scenarios=scenarios,
                break_even=break_even,
                budget_compatibility=compatibility,
                viable=False,
                affordable=False,
                verdict="unaffordable",
                reasons=tuple(reasons),
                assumptions=tuple(assumptions),
            )

        # 3. Break-even achievability.
        if not break_even.achievable:
            reasons.append(break_even.reason or "break-even not achievable")
            return CommercialAssessment(
                costs=inputs.costs,
                scenarios=scenarios,
                break_even=break_even,
                budget_compatibility=compatibility,
                viable=False,
                affordable=True,
                verdict="not_viable",
                reasons=tuple(reasons),
                assumptions=tuple(assumptions),
            )

        # 4. Does the conservative case survive?  This is the real test: an
        #    opportunity that only works at expected volume is fragile.
        if conservative.operating_profit < 0:
            reasons.append(
                "the conservative scenario (half the expected volume) is "
                f"loss-making at {conservative.operating_profit} "
                f"{budget.currency}; the opportunity depends on hitting the "
                "volume estimate"
            )
        if base.contribution_margin is not None and (
            base.contribution_margin < MINIMUM_CONTRIBUTION_MARGIN
        ):
            reasons.append(
                f"contribution margin of {base.contribution_margin} is below the "
                f"{MINIMUM_CONTRIBUTION_MARGIN} screening threshold; one refund "
                "or fee change could make a sale loss-making"
            )
        if inputs.costs.unknown_count():
            reasons.append(
                f"{inputs.costs.unknown_count()} cost line(s) could not be priced"
            )

        low_confidence = (
            inputs.price_provenance is Provenance.ESTIMATE
            or inputs.units_provenance is Provenance.ESTIMATE
        )
        if low_confidence:
            reasons.append(
                "price and/or volume rest on estimates rather than quoted or "
                "verified figures"
            )

        if conservative.operating_profit < 0 or (
            base.contribution_margin is not None
            and base.contribution_margin < MINIMUM_CONTRIBUTION_MARGIN
        ):
            verdict = "marginal"
            viable = False
        else:
            verdict = "viable"
            viable = True
            reasons.append(
                f"break-even at {break_even.monthly_break_even_units} unit(s)/month, "
                f"startup recovered in about {break_even.months_to_recover_startup} "
                f"month(s), conservative operating profit "
                f"{conservative.operating_profit} {budget.currency}"
            )

        return CommercialAssessment(
            costs=inputs.costs,
            scenarios=scenarios,
            break_even=break_even,
            budget_compatibility=compatibility,
            viable=viable,
            affordable=True,
            verdict=verdict,
            reasons=tuple(reasons),
            assumptions=tuple(assumptions),
        )

    # -- helpers used by the discovery and reporting layers ------------------ #
    @staticmethod
    def summarise(assessment: CommercialAssessment, *, currency: str = "USD") -> dict[str, Any]:
        """A flat, presentation-safe summary for reports and the API."""
        base = next(
            (s for s in assessment.scenarios if s.name is ScenarioName.BASE), None
        )
        return {
            "verdict": assessment.verdict,
            "viable": assessment.viable,
            "affordable": assessment.affordable,
            "currency": currency,
            "startup_cost": str(assessment.costs.startup_total()),
            "recurring_monthly": str(assessment.costs.recurring_monthly_total()),
            "variable_per_unit": str(assessment.costs.variable_per_unit_total()),
            "cost_lines": len(assessment.costs.items),
            "unpriced_cost_lines": list(assessment.unpriced_cost_items),
            "provenance_counts": assessment.costs.provenance_counts(),
            "base_revenue": str(base.projection.revenue) if base else None,
            "base_operating_profit": str(base.projection.operating_profit) if base else None,
            "break_even_units_month": (
                assessment.break_even.monthly_break_even_units
                if assessment.break_even
                else None
            ),
            "months_to_recover_startup": (
                assessment.break_even.months_to_recover_startup
                if assessment.break_even
                else None
            ),
            "break_even_achievable": (
                assessment.break_even.achievable if assessment.break_even else None
            ),
            "budget_required_startup": (
                str(assessment.budget_compatibility.required_startup)
                if assessment.budget_compatibility
                else None
            ),
            "budget_available": (
                str(assessment.budget_compatibility.available_capital)
                if assessment.budget_compatibility
                else None
            ),
            "budget_shortfall": (
                str(assessment.budget_compatibility.shortfall)
                if assessment.budget_compatibility
                else None
            ),
            "budget_was_modified": assessment.budget_was_modified,
            "reasons": list(assessment.reasons),
            "assumptions": [a.statement for a in assessment.assumptions],
        }
