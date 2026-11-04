"""P-03 §18 opportunity validation levels.

The ladder 0-5 exists because "validated" is the word most often used to dress up
an unvalidated idea.  Two rules do the work:

* **Levels are cumulative.**  Level 3 cannot be claimed unless levels 1 and 2 are
  satisfied.  Skipping a rung is refused, not merely discouraged.
* **Levels 4 and 5 have prohibited inputs.**  Search volume, social views, likes,
  AI persona responses, hypothetical surveys, competitor existence and
  model-generated willingness-to-pay may not establish level 4.  A generated
  invoice, an unpaid order, an unverified screenshot, a forecast or a simulated
  transaction may not establish level 5.  These lists live in
  :mod:`app.opportunities.schemas` as data, so the rule is testable and cannot be
  quietly narrowed.

A level that cannot be reached is reported with the reason it could not be
reached.  ``next_level_requirement`` always tells the owner what would move the
opportunity up, which is more useful than a bare number.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from app.opportunities.schemas import (
    ADMISSIBLE_CLASSIFICATIONS,
    EvidenceClassification,
    EvidenceType,
    LEVEL_4_PROHIBITED_INPUTS,
    LEVEL_5_PROHIBITED_INPUTS,
    SourceEvidence,
    ValidationAssessment,
    ValidationLevel,
)

__all__ = [
    "LEVEL_REQUIREMENTS",
    "PERMITTED_LEVEL_4_INPUTS",
    "PERMITTED_LEVEL_5_INPUTS",
    "ValidationEngine",
    "MIN_ADMISSIBLE_PER_LEVEL",
]

#: Evidence types that can satisfy each level's requirement.
LEVEL_EVIDENCE_TYPES: dict[ValidationLevel, frozenset[EvidenceType]] = {
    ValidationLevel.LEVEL_0_IDEA: frozenset(),
    ValidationLevel.LEVEL_1_PROBLEM_EVIDENCE: frozenset(
        {
            EvidenceType.FORUM_POST,
            EvidenceType.MARKETPLACE_REVIEW,
            EvidenceType.COMPETITOR_REVIEW,
            EvidenceType.NEWS_ITEM,
            EvidenceType.OWNER_STATEMENT,
        }
    ),
    ValidationLevel.LEVEL_2_DEMAND_EVIDENCE: frozenset(
        {
            EvidenceType.SEARCH_VOLUME,
            EvidenceType.KEYWORD_TREND,
            EvidenceType.MARKETPLACE_LISTING,
            EvidenceType.SOCIAL_SIGNAL,
            EvidenceType.OFFICIAL_STATISTIC,
        }
    ),
    ValidationLevel.LEVEL_3_COMMERCIAL_EVIDENCE: frozenset(
        {
            EvidenceType.COMPETITOR_PRICING,
            EvidenceType.VENDOR_PRICE_QUOTE,
            EvidenceType.COMPETITOR_FEATURE_SET,
        }
    ),
    # Levels 4 and 5 are gated on TRANSACTION_RECORD plus an explicit, permitted
    # input string; the evidence types alone are never sufficient.
    ValidationLevel.LEVEL_4_WILLINGNESS_TO_PAY: frozenset({EvidenceType.TRANSACTION_RECORD}),
    ValidationLevel.LEVEL_5_ACTUAL_REVENUE: frozenset({EvidenceType.TRANSACTION_RECORD}),
}

#: Inputs that MAY establish level 4.  Anything not on this list cannot, and the
#: prohibited list is checked first so that a near-miss phrasing is refused.
PERMITTED_LEVEL_4_INPUTS: frozenset[str] = frozenset(
    {
        "paid_preorder",
        "paid_pilot",
        "signed_letter_of_intent_with_deposit",
        "completed_paid_engagement",
        "verified_customer_payment",
        "refundable_deposit_collected",
    }
)

#: Inputs that MAY establish level 5.
PERMITTED_LEVEL_5_INPUTS: frozenset[str] = frozenset(
    {
        "settled_payment_received",
        "verified_bank_or_processor_receipt",
        "revenue_recognised_from_delivered_sale",
    }
)

#: How many admissible evidence records of the right type a level needs.
MIN_ADMISSIBLE_PER_LEVEL: dict[ValidationLevel, int] = {
    ValidationLevel.LEVEL_0_IDEA: 0,
    ValidationLevel.LEVEL_1_PROBLEM_EVIDENCE: 1,
    ValidationLevel.LEVEL_2_DEMAND_EVIDENCE: 1,
    ValidationLevel.LEVEL_3_COMMERCIAL_EVIDENCE: 2,
    ValidationLevel.LEVEL_4_WILLINGNESS_TO_PAY: 1,
    ValidationLevel.LEVEL_5_ACTUAL_REVENUE: 1,
}

LEVEL_REQUIREMENTS: dict[ValidationLevel, str] = {
    ValidationLevel.LEVEL_0_IDEA: "no requirement; an unevidenced idea",
    ValidationLevel.LEVEL_1_PROBLEM_EVIDENCE: (
        "at least 1 admissible record showing that real people describe this problem"
    ),
    ValidationLevel.LEVEL_2_DEMAND_EVIDENCE: (
        "at least 1 admissible record of demand: search volume, keyword trend, "
        "marketplace listings, or an official statistic"
    ),
    ValidationLevel.LEVEL_3_COMMERCIAL_EVIDENCE: (
        "at least 2 admissible records establishing that money changes hands in "
        "this market: competitor pricing and/or verified vendor cost quotes"
    ),
    ValidationLevel.LEVEL_4_WILLINGNESS_TO_PAY: (
        "a transaction record PLUS a permitted willingness-to-pay input such as a "
        "paid pre-order or a completed paid engagement. Search volume, social "
        "views, likes, AI persona responses, hypothetical surveys, competitor "
        "existence and model-generated willingness-to-pay are all prohibited here."
    ),
    ValidationLevel.LEVEL_5_ACTUAL_REVENUE: (
        "a transaction record PLUS a permitted revenue input such as a settled "
        "payment received. A generated invoice, an unpaid order, an unverified "
        "screenshot, a forecast or a simulated transaction are all prohibited here."
    ),
}


class ValidationEngine:
    """Determines the highest validation level genuinely supported."""

    def _admissible_of_type(
        self, evidence: Sequence[SourceEvidence], level: ValidationLevel
    ) -> list[SourceEvidence]:
        wanted = LEVEL_EVIDENCE_TYPES[level]
        return [
            e
            for e in evidence
            if e.evidence_type in wanted and e.classification in ADMISSIBLE_CLASSIFICATIONS
        ]

    def determine(
        self,
        evidence: Sequence[SourceEvidence],
        *,
        declared_inputs: Sequence[str] = (),
    ) -> ValidationAssessment:
        """Walk the ladder from 0 upward and stop at the first rung that fails.

        ``declared_inputs`` are the extra claims the caller makes (for example
        ``"paid_preorder"``).  Prohibited inputs are detected and reported even
        when the level being claimed would not have needed them, because their
        presence tells the owner what the analysis was tempted by.
        """
        declared = tuple(dict.fromkeys(i.strip().lower() for i in declared_inputs if i.strip()))
        satisfied: list[str] = []
        rejected: list[str] = []
        evidence_ids: list[str] = []
        blocking: str | None = None

        # Detect prohibited inputs up front and refuse to use them.
        for item in declared:
            if item in LEVEL_4_PROHIBITED_INPUTS or item in LEVEL_5_PROHIBITED_INPUTS:
                rejected.append(item)
                if blocking is None:
                    blocking = (
                        f"the declared input '{item}' is prohibited as a basis for "
                        "level 4 or level 5 validation and was excluded"
                    )

        level = ValidationLevel.LEVEL_0_IDEA
        next_level: ValidationLevel | None = None
        next_requirement: str | None = None

        for candidate in (
            ValidationLevel.LEVEL_1_PROBLEM_EVIDENCE,
            ValidationLevel.LEVEL_2_DEMAND_EVIDENCE,
            ValidationLevel.LEVEL_3_COMMERCIAL_EVIDENCE,
            ValidationLevel.LEVEL_4_WILLINGNESS_TO_PAY,
            ValidationLevel.LEVEL_5_ACTUAL_REVENUE,
        ):
            requirement = LEVEL_REQUIREMENTS[candidate]
            matching = self._admissible_of_type(evidence, candidate)
            enough = len(matching) >= MIN_ADMISSIBLE_PER_LEVEL[candidate]

            if candidate is ValidationLevel.LEVEL_4_WILLINGNESS_TO_PAY:
                permitted = [i for i in declared if i in PERMITTED_LEVEL_4_INPUTS]
                if not permitted:
                    next_level, next_requirement = candidate, requirement
                    if not blocking:
                        blocking = (
                            "level 4 requires a permitted willingness-to-pay input "
                            f"such as {sorted(PERMITTED_LEVEL_4_INPUTS)[0]}; none was declared"
                        )
                    break
                if not enough:
                    next_level, next_requirement = candidate, requirement
                    break
                satisfied.extend(permitted)
                evidence_ids.extend(e.evidence_id for e in matching)
                level = candidate
                continue

            if candidate is ValidationLevel.LEVEL_5_ACTUAL_REVENUE:
                permitted = [i for i in declared if i in PERMITTED_LEVEL_5_INPUTS]
                if not permitted or not enough:
                    next_level, next_requirement = candidate, requirement
                    break
                satisfied.extend(permitted)
                evidence_ids.extend(e.evidence_id for e in matching)
                level = candidate
                continue

            if not enough:
                next_level, next_requirement = candidate, requirement
                break
            satisfied.append(f"{candidate.name.lower()}_evidence:{len(matching)}")
            evidence_ids.extend(e.evidence_id for e in matching)
            level = candidate

        if level is ValidationLevel.LEVEL_0_IDEA and next_level is None:
            next_level = ValidationLevel.LEVEL_1_PROBLEM_EVIDENCE
            next_requirement = LEVEL_REQUIREMENTS[ValidationLevel.LEVEL_1_PROBLEM_EVIDENCE]

        return ValidationAssessment(
            level=level,
            satisfied_inputs=tuple(dict.fromkeys(satisfied)),
            rejected_inputs=tuple(rejected),
            blocking_prohibition=blocking,
            next_level=next_level,
            next_level_requirement=next_requirement,
            evidence_ids=tuple(dict.fromkeys(evidence_ids)),
            assessed_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def summarise(assessment: ValidationAssessment) -> dict[str, object]:
        return {
            "level": assessment.level.value,
            "level_name": assessment.level.name,
            "requirement_met": LEVEL_REQUIREMENTS[assessment.level],
            "satisfied_inputs": list(assessment.satisfied_inputs),
            "rejected_inputs": list(assessment.rejected_inputs),
            "blocking_prohibition": assessment.blocking_prohibition,
            "next_level": assessment.next_level.value if assessment.next_level else None,
            "next_level_requirement": assessment.next_level_requirement,
            "evidence_ids": list(assessment.evidence_ids),
        }

    @staticmethod
    def is_model_generated_only(evidence: Sequence[SourceEvidence]) -> bool:
        """True when every record is model-generated.

        Used by the reporting layer to stamp a warning: an analysis resting
        entirely on model output is not research.
        """
        return bool(evidence) and all(
            e.evidence_type is EvidenceType.MODEL_GENERATED
            or e.reliability.value == "model_generated"
            for e in evidence
        )

    @staticmethod
    def contradicted(evidence: Sequence[SourceEvidence]) -> tuple[str, ...]:
        return tuple(
            e.evidence_id
            for e in evidence
            if e.classification is EvidenceClassification.CONTRADICTED
        )
