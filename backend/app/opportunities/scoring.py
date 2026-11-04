"""P-03 §16 opportunity scoring.

The brief's central instruction is that AUTONOMOUS must be better at *rejecting*
bad opportunities than at generating attractive ones.  This module is where that
becomes executable, via three separate mechanisms:

1. **A dimension is either scored from evidence or it is not scored at all.**
   There is no default, no midpoint and no imputation.  An unscoreable
   dimension contributes zero *and* is listed as a gap, so low evidence coverage
   is visible as low coverage rather than as a mediocre-looking score.
2. **Hard rejection rules run after scoring and override it.**  A compliance
   block, an unaffordable cost structure or contradicted demand ends the
   evaluation whatever the weighted total says.
3. **Evidence quality is scored separately from attractiveness.**  An
   opportunity that looks good on weak evidence is reported as exactly that:
   high attractiveness, low evidence quality, insufficient coverage.

Every score here is a pure function of its inputs.  No timestamps, no random
seeds and no model output enter the arithmetic, so a ranking computed today is
byte-identical to one computed tomorrow from the same records (§16
reproducibility).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from app.opportunities.schemas import (
    ATTRACTIVENESS_KEYS,
    BusinessModelAnalysis,
    CompetitorAssessment,
    CommercialAssessment,
    DEFAULT_WEIGHTS,
    DistributionAssessment,
    EvidenceClassification,
    FinalClassification,
    MarketAssessment,
    OpportunityScore,
    Provenance,
    RiskAssessment,
    ScoreDimension,
    ScoringOutcome,
    SourceEvidence,
    ValidationAssessment,
    ValidationLevel,
    WeightKey,
)
from app.intelligence.schemas import EvidenceReliability

__all__ = [
    "MIN_EVIDENCE_COVERAGE_PCT",
    "MIN_RECOMMEND_ATTRACTIVENESS",
    "OpportunityScorer",
    "RELIABILITY_MULTIPLIER",
]

#: Below this weighted coverage of the scoring dimensions the outcome is
#: ``INSUFFICIENT_EVIDENCE`` regardless of how the scored dimensions look.
MIN_EVIDENCE_COVERAGE_PCT = Decimal("60")

#: Minimum attractiveness for a RECOMMENDED classification.  Deliberately high:
#: recommending is the expensive error, passing is the cheap one.
MIN_RECOMMEND_ATTRACTIVENESS = Decimal("3.0000")

#: How much a source's reliability discounts its evidence.  An authoritative
#: source counts fully; an untrusted or model-generated one counts for a tenth.
RELIABILITY_MULTIPLIER: dict[EvidenceReliability, Decimal] = {
    EvidenceReliability.AUTHORITATIVE: Decimal("1.00"),
    EvidenceReliability.TRUSTED: Decimal("0.80"),
    EvidenceReliability.PLAUSIBLE: Decimal("0.50"),
    EvidenceReliability.UNTRUSTED: Decimal("0.20"),
    EvidenceReliability.MODEL_GENERATED: Decimal("0.10"),
}

#: Weight of each classification when computing evidence quality.
CLASSIFICATION_VALUE: dict[EvidenceClassification, Decimal] = {
    EvidenceClassification.VERIFIED: Decimal("1.00"),
    EvidenceClassification.CORROBORATED: Decimal("0.85"),
    EvidenceClassification.SUPPORTING: Decimal("0.55"),
    EvidenceClassification.TENTATIVE: Decimal("0.30"),
    EvidenceClassification.UNVERIFIED: Decimal("0.05"),
    EvidenceClassification.CONTRADICTED: Decimal("0.00"),
    EvidenceClassification.OUTDATED: Decimal("0.00"),
}


class OpportunityScorer:
    """Deterministic, weighted, reject-first opportunity scoring."""

    def __init__(self, weights: dict[WeightKey, Decimal] | None = None):
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        self._validate_weights()

    # ------------------------------------------------------------------ #
    def _validate_weights(self) -> None:
        missing = [k.value for k in WeightKey if k not in self.weights]
        if missing:
            raise ValueError(f"weights are missing dimensions: {', '.join(missing)}")
        unknown = [
            str(k) for k in self.weights if not isinstance(k, WeightKey)
        ]
        if unknown:
            # Guard against the defect class where a weights dict keyed by a
            # *string* silently matches no dimension and is therefore ignored.
            raise ValueError(
                f"weight keys must be WeightKey members, got: {', '.join(unknown)}"
            )
        total = sum(self.weights.values(), Decimal("0"))
        if total != Decimal("100"):
            raise ValueError(
                f"weights must sum to exactly 100, got {total}; refusing to "
                "normalise silently because two runs with different weights "
                "would then produce incomparable scores"
            )
        for key, value in self.weights.items():
            if value < 0:
                raise ValueError(f"weight for {key.value} is negative")

    @property
    def weights_fingerprint(self) -> str:
        """A stable hash of the weight configuration.

        Recorded on every outcome so that two rankings can be compared only when
        they were produced under the same weights.
        """
        blob = "|".join(
            f"{k.value}={self.weights[k]}" for k in sorted(WeightKey, key=lambda x: x.value)
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    # ------------------------------------------------------------------ #
    # Individual dimension rules.  Each returns (score 0-5, justification, gap)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _demand(market: MarketAssessment | None) -> tuple[Decimal | None, str, str]:
        if market is None:
            return None, "", "no market assessment was produced"
        table = {
            "demand_demonstrated": (Decimal(5), "demand demonstrated on admissible evidence"),
            "demand_plausible": (Decimal(3), "demand plausible but not demonstrated"),
            "demand_unproven": (Decimal(1), "demand asserted but unproven"),
            "demand_contradicted": (Decimal(0), "demand contradicted by evidence"),
        }
        if market.verdict == "insufficient_data":
            return None, "", "market assessment reached no verdict on the available data"
        score, why = table[market.verdict]
        # A demonstrated verdict resting on merely CORROBORATED evidence is one
        # rung below one resting on VERIFIED evidence.
        if market.verdict == "demand_demonstrated" and (
            market.demand_evidence_level is EvidenceClassification.CORROBORATED
        ):
            score, why = Decimal(4), "demand corroborated by independent sources"
        return score, f"{why}: {market.reasons[0] if market.reasons else market.verdict}", ""

    @staticmethod
    def _importance(market: MarketAssessment | None) -> tuple[Decimal | None, str, str]:
        if market is None or market.problem_importance == "unknown":
            return None, "", "problem importance was not established"
        table = {
            "acute": Decimal(5),
            "significant": Decimal(4),
            "moderate": Decimal(3),
            "minor": Decimal(2),
            "trivial": Decimal(1),
        }
        score = table[market.problem_importance]
        return score, f"problem importance rated {market.problem_importance}: {market.problem_importance_basis}", ""

    @staticmethod
    def _competition(comp: CompetitorAssessment | None) -> tuple[Decimal | None, str, str]:
        if comp is None or comp.verdict == "insufficient_data":
            return None, "", "no competitive assessment was produced"
        table = {
            "open_opportunity": Decimal(5),
            "differentiation_required": Decimal(4),
            "crowded_but_viable": Decimal(3),
            "saturated_no_entry": Decimal(0),
        }
        score = table[comp.verdict]
        why = comp.reasons[0] if comp.reasons else comp.verdict
        return score, f"{comp.verdict.replace('_',' ')}: {why}", ""

    @staticmethod
    def _revenue_model(model: BusinessModelAnalysis | None) -> tuple[Decimal | None, str, str]:
        if model is None:
            return None, "", "no business model was analysed"
        base = {
            Provenance.VERIFIED: Decimal(5),
            Provenance.QUOTED: Decimal(4),
            Provenance.HISTORICAL: Decimal(3),
            Provenance.ESTIMATE: Decimal(2),
            Provenance.UNKNOWN: None,
        }[model.price_provenance]
        if base is None:
            return None, "", "the revenue model states no price provenance"
        why = f"price provenance is {model.price_provenance.value}"
        if model.weaknesses:
            base = max(Decimal(0), base - Decimal(1))
            why += f"; discounted for {len(model.weaknesses)} model weakness(es)"
        return base, why, ""

    @staticmethod
    def _profit(commercial: CommercialAssessment | None) -> tuple[Decimal | None, str, str]:
        if commercial is None or commercial.verdict == "cannot_determine":
            return None, "", "commercial feasibility could not be determined"
        if commercial.verdict == "unaffordable":
            return Decimal(0), "outside the owner's stated budget", ""
        if commercial.verdict == "not_viable":
            return Decimal(0), "break-even is not achievable at this price", ""
        base = next(
            (s for s in commercial.scenarios if s.name.value == "base"), None
        )
        cons = next(
            (s for s in commercial.scenarios if s.name.value == "conservative"), None
        )
        if base is None:
            return None, "", "no base scenario was projected"
        margin = base.projection.contribution_margin or Decimal(0)
        if commercial.verdict == "marginal":
            return Decimal(2), f"marginal: contribution margin {margin}", ""
        score = Decimal(4)
        why = f"viable at base volume; contribution margin {margin}"
        if cons is not None and cons.projection.operating_profit > 0 and margin >= Decimal("0.50"):
            score = Decimal(5)
            why += "; profitable even at half the expected volume"
        return score, why, ""

    @staticmethod
    def _budget(commercial: CommercialAssessment | None) -> tuple[Decimal | None, str, str]:
        if commercial is None or commercial.budget_compatibility is None:
            return None, "", "budget compatibility was not assessed"
        bc = commercial.budget_compatibility
        if bc.verdict == "cannot_determine":
            return None, "", bc.reason or "cost structure is unpriced"
        if bc.verdict == "incompatible":
            return Decimal(0), f"shortfall of {bc.shortfall} against stated capital", ""
        utilisation = (bc.utilisation_pct or Decimal(0)) / Decimal(100)
        if utilisation <= Decimal("0.50"):
            score, why = Decimal(5), f"uses {bc.utilisation_pct}% of stated capital"
        elif utilisation <= Decimal("0.80"):
            score, why = Decimal(4), f"uses {bc.utilisation_pct}% of stated capital"
        else:
            score, why = Decimal(3), f"tight: uses {bc.utilisation_pct}% of stated capital"
        return score, why, ""

    @staticmethod
    def _distribution(dist: DistributionAssessment | None) -> tuple[Decimal | None, str, str]:
        if dist is None or dist.verdict == "insufficient_data":
            return None, "", "no distribution assessment was produced"
        table = {
            "clear_path": Decimal(5),
            "plausible_path": Decimal(4),
            "requires_ad_spend": Decimal(2),
            "no_identified_path": Decimal(0),
        }
        score = table[dist.verdict]
        if dist.verdict in {"clear_path", "plausible_path"} and (
            dist.platform_dependency_risk.value in {"high", "blocking"}
        ):
            score = max(Decimal(0), score - Decimal(1))
        why = dist.reasons[0] if dist.reasons else dist.verdict.replace("_", " ")
        return score, f"{dist.verdict.replace('_',' ')}: {why}", ""

    @staticmethod
    def _simplicity(
        commercial: CommercialAssessment | None, dist: DistributionAssessment | None
    ) -> tuple[Decimal | None, str, str]:
        if commercial is None:
            return None, "", "operational complexity could not be derived without a cost structure"
        lines = len(commercial.costs.items)
        channels = len(dist.channels) if dist else 0
        score = Decimal(5)
        reasons = [f"{lines} cost line(s)"]
        if lines > 8:
            score -= Decimal(2)
            reasons.append("many cost lines implies operational overhead")
        elif lines > 4:
            score -= Decimal(1)
            reasons.append("several cost lines to manage")
        if channels > 3:
            score -= Decimal(1)
            reasons.append(f"{channels} channels to operate simultaneously")
        if dist is not None and dist.platform_dependency_risk.value in {"high", "blocking"}:
            score -= Decimal(1)
            reasons.append("high platform dependency")
        return max(Decimal(0), score), "; ".join(reasons), ""

    @staticmethod
    def _strategic_fit(
        stated_capabilities: Sequence[str], required_capabilities: Sequence[str]
    ) -> tuple[Decimal | None, str, str]:
        """Fit against the owner's *stated* capabilities.

        If either list is empty the dimension is unscoreable.  Strategic fit is
        never inferred from the business category - that would be a guess
        dressed as an assessment.
        """
        if not stated_capabilities or not required_capabilities:
            return None, "", "owner capabilities or required capabilities were not stated"
        stated = {s.strip().lower() for s in stated_capabilities if s.strip()}
        required = {r.strip().lower() for r in required_capabilities if r.strip()}
        if not stated or not required:
            return None, "", "capability lists were empty after normalisation"
        overlap = sorted(stated & required)
        ratio = Decimal(len(overlap)) / Decimal(len(required))
        score = (ratio * Decimal(5)).quantize(Decimal("0.01"))
        if overlap:
            why = f"owner capabilities cover {len(overlap)}/{len(required)} required: {', '.join(overlap)}"
        else:
            why = f"no overlap between stated capabilities and the {len(required)} required"
        return score, why, ""

    def evidence_quality_dimension(
        self, evidence: Sequence[SourceEvidence]
    ) -> ScoreDimension:
        """Score evidence quality on its own terms (§16).

        Quality is the reliability-weighted mean classification value, scaled to
        0-5.  Contradicted and outdated evidence counts for nothing but still
        occupies the denominator, so a body of evidence containing contradictions
        scores worse than a small clean one - which is the correct behaviour.
        """
        weight = self.weights[WeightKey.EVIDENCE_QUALITY]
        if not evidence:
            return ScoreDimension(
                key=WeightKey.EVIDENCE_QUALITY,
                weight=weight,
                score=Decimal(0),
                scorable=False,
                gap="no evidence was collected for this opportunity",
            )
        total = Decimal(0)
        for item in evidence:
            total += CLASSIFICATION_VALUE[item.classification] * RELIABILITY_MULTIPLIER[
                item.reliability
            ]
        mean = total / Decimal(len(evidence))
        score = (mean * Decimal(5)).quantize(Decimal("0.01"))
        admissible = sum(1 for e in evidence if e.is_admissible())
        contradicted = sum(
            1 for e in evidence if e.classification is EvidenceClassification.CONTRADICTED
        )
        why = (
            f"{len(evidence)} evidence record(s); {admissible} admissible; "
            f"{contradicted} contradicted; reliability-weighted mean "
            f"{mean.quantize(Decimal('0.0001'))}"
        )
        return ScoreDimension(
            key=WeightKey.EVIDENCE_QUALITY,
            weight=weight,
            score=min(score, Decimal(5)),
            scorable=True,
            justification=why,
            evidence_ids=tuple(e.evidence_id for e in evidence),
            computed_by="deterministic_rule",
        )

    # ------------------------------------------------------------------ #
    def score(
        self,
        *,
        market: MarketAssessment | None = None,
        competitors: CompetitorAssessment | None = None,
        business_model: BusinessModelAnalysis | None = None,
        commercial: CommercialAssessment | None = None,
        distribution: DistributionAssessment | None = None,
        risk: RiskAssessment | None = None,
        validation: ValidationAssessment | None = None,
        evidence: Sequence[SourceEvidence] = (),
        stated_capabilities: Sequence[str] = (),
        required_capabilities: Sequence[str] = (),
        minimum_validation_level: ValidationLevel = ValidationLevel.LEVEL_3_COMMERCIAL_EVIDENCE,
    ) -> ScoringOutcome:
        """Score one opportunity and decide its final classification."""
        rules: dict[WeightKey, Any] = {
            WeightKey.VERIFIED_DEMAND: lambda: self._demand(market),
            WeightKey.PROBLEM_IMPORTANCE: lambda: self._importance(market),
            WeightKey.COMPETITIVE_OPPORTUNITY: lambda: self._competition(competitors),
            WeightKey.REVENUE_MODEL_VIABILITY: lambda: self._revenue_model(business_model),
            WeightKey.PROFIT_POTENTIAL: lambda: self._profit(commercial),
            WeightKey.BUDGET_COMPATIBILITY: lambda: self._budget(commercial),
            WeightKey.DISTRIBUTION_FEASIBILITY: lambda: self._distribution(distribution),
            WeightKey.OPERATIONAL_SIMPLICITY: lambda: self._simplicity(commercial, distribution),
            WeightKey.STRATEGIC_FIT: lambda: self._strategic_fit(
                stated_capabilities, required_capabilities
            ),
        }
        dimensions: list[ScoreDimension] = []
        for key in WeightKey:
            weight = self.weights[key]
            if key is WeightKey.EVIDENCE_QUALITY:
                dimensions.append(self.evidence_quality_dimension(evidence))
                continue
            value, justification, gap = rules[key]()
            if value is None:
                dimensions.append(
                    ScoreDimension(
                        key=key,
                        weight=weight,
                        score=Decimal(0),
                        scorable=False,
                        gap=gap,
                    )
                )
            else:
                dimensions.append(
                    ScoreDimension(
                        key=key,
                        weight=weight,
                        score=min(max(value, Decimal(0)), Decimal(5)),
                        scorable=True,
                        justification=justification,
                        evidence_ids=tuple(evidence_ids_for(key, evidence)),
                        computed_by="deterministic_rule",
                    )
                )
        score = OpportunityScore(dimensions=tuple(dimensions))

        # ---------------- hard rejection rules (override any score) --------- #
        rejections: list[str] = []
        classification: FinalClassification | None = None

        if risk is not None and risk.verdict == "blocked":
            rejections.append(
                "compliance block: " + (risk.reasons[0] if risk.reasons else "blocking risk finding")
            )
            classification = FinalClassification.REJECTED_COMPLIANCE
        elif commercial is not None and commercial.verdict == "unaffordable":
            shortfall = (
                commercial.budget_compatibility.shortfall
                if commercial.budget_compatibility
                else None
            )
            rejections.append(
                f"outside the owner's stated budget (shortfall {shortfall}); "
                "the budget must not be increased to make this fit"
            )
            classification = FinalClassification.INCOMPATIBLE_WITH_CONSTRAINTS
        elif market is not None and market.verdict == "demand_contradicted":
            rejections.append(
                "demand is contradicted by the evidence: "
                + (market.reasons[0] if market.reasons else "no reason recorded")
            )
            classification = FinalClassification.NOT_RECOMMENDED
        elif commercial is not None and commercial.verdict == "not_viable":
            rejections.append(
                "break-even is not achievable: "
                + (commercial.reasons[0] if commercial.reasons else "no reason recorded")
            )
            classification = FinalClassification.NOT_RECOMMENDED

        if not rejections and score.coverage_pct < MIN_EVIDENCE_COVERAGE_PCT:
            rejections.append(
                f"evidence coverage {score.coverage_pct}% is below the "
                f"{MIN_EVIDENCE_COVERAGE_PCT}% minimum; unscored dimensions: "
                + (", ".join(score.unscored_dimensions) or "none")
            )
            classification = FinalClassification.INSUFFICIENT_EVIDENCE

        if not rejections and commercial is not None and (
            commercial.verdict == "cannot_determine"
        ):
            rejections.append(
                "commercial feasibility could not be determined: "
                + ", ".join(commercial.reasons)
            )
            classification = FinalClassification.INSUFFICIENT_EVIDENCE

        if rejections:
            return ScoringOutcome(
                score=score,
                hard_rejections=tuple(rejections),
                rejection_classification=classification,
                final_classification=classification
                or FinalClassification.INSUFFICIENT_EVIDENCE,
                recommendable=False,
                reasons=tuple(rejections),
                minimum_validation_level_required=minimum_validation_level,
                weights_fingerprint=self.weights_fingerprint,
            )

        # ---------------- recommendation gate ------------------------------- #
        level = validation.level if validation else ValidationLevel.LEVEL_0_IDEA
        reasons: list[str] = []
        strong_enough = score.attractiveness >= MIN_RECOMMEND_ATTRACTIVENESS
        validated_enough = level.value >= minimum_validation_level.value
        commercially_sound = commercial is not None and commercial.verdict == "viable"

        if strong_enough and validated_enough and commercially_sound:
            final = FinalClassification.RECOMMENDED
            recommendable = True
            reasons.append(
                f"attractiveness {score.attractiveness} meets the "
                f"{MIN_RECOMMEND_ATTRACTIVENESS} threshold, validation reached "
                f"level {level.value}, and commercial feasibility is viable"
            )
        elif strong_enough and commercially_sound:
            final = FinalClassification.PROMISING_NEEDS_VALIDATION
            recommendable = False
            reasons.append(
                f"attractiveness {score.attractiveness} is sufficient and the "
                f"economics are viable, but validation reached only level "
                f"{level.value} of the required {minimum_validation_level.value}"
            )
        elif not strong_enough:
            final = FinalClassification.NOT_RECOMMENDED
            recommendable = False
            reasons.append(
                f"attractiveness {score.attractiveness} is below the "
                f"{MIN_RECOMMEND_ATTRACTIVENESS} recommendation threshold"
            )
        else:
            final = FinalClassification.PROMISING_NEEDS_VALIDATION
            recommendable = False
            reasons.append(
                "commercial feasibility is not 'viable', so the opportunity "
                "cannot be recommended on the current analysis"
            )

        if score.coverage_pct < Decimal("100"):
            reasons.append(
                f"note: {len(score.unscored_dimensions)} dimension(s) unscored "
                f"({', '.join(score.unscored_dimensions)}); coverage "
                f"{score.coverage_pct}%"
            )
        return ScoringOutcome(
            score=score,
            final_classification=final,
            recommendable=recommendable,
            reasons=tuple(reasons),
            minimum_validation_level_required=minimum_validation_level,
            weights_fingerprint=self.weights_fingerprint,
        )


def evidence_ids_for(key: WeightKey, evidence: Sequence[SourceEvidence]) -> tuple[str, ...]:
    """Attach the evidence ids that actually drove a dimension.

    Traceability requirement (§3): a score with no link back to the observations
    behind it is not auditable.
    """
    mapping = {
        WeightKey.VERIFIED_DEMAND: {
            "search_volume", "keyword_trend", "marketplace_listing", "forum_post",
            "social_signal", "official_statistic",
        },
        WeightKey.PROBLEM_IMPORTANCE: {"forum_post", "marketplace_review", "competitor_review"},
        WeightKey.COMPETITIVE_OPPORTUNITY: {
            "competitor_pricing", "competitor_feature_set", "competitor_review",
            "marketplace_listing",
        },
        WeightKey.REVENUE_MODEL_VIABILITY: {"competitor_pricing", "marketplace_listing"},
        WeightKey.PROFIT_POTENTIAL: {"vendor_price_quote", "competitor_pricing"},
        WeightKey.BUDGET_COMPATIBILITY: {"vendor_price_quote"},
        WeightKey.DISTRIBUTION_FEASIBILITY: {"marketplace_listing", "social_signal"},
        WeightKey.OPERATIONAL_SIMPLICITY: {"vendor_price_quote"},
        WeightKey.STRATEGIC_FIT: {"owner_statement"},
    }
    wanted = mapping.get(key)
    if not wanted:
        return ()
    return tuple(
        e.evidence_id for e in evidence if e.evidence_type.value in wanted
    )
