"""P-03 §7 opportunity discovery.

Six methods, and one rule that governs all of them: **a method with no inputs
produces no candidates.**  Discovery is derivation from something the owner said
or something a source returned - never invention.  This is the §19
anti-hallucination requirement applied at the very first stage, where it is
cheapest to honour and most tempting to violate, because an empty result set
looks like failure.

It is not failure.  In a deployment with no reachable research sources, four of
the six methods will correctly return nothing, and the two that still work are
the ones driven by what the owner supplied: their capabilities and their budget.
That is a truthful result and it is reported as one.

Every candidate records ``derived_from`` naming the observation, capability or
band it came from, so a reviewer can always ask "why does this exist?" and get an
answer.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.intelligence.schemas import EvidenceReliability
from app.opportunities.schemas import (
    BudgetBand,
    BudgetConstraint,
    BusinessCategory,
    DiscoveryMethod,
    EvidenceClassification,
    EvidenceType,
    OpportunityCandidate,
    SourceEvidence,
)

__all__ = [
    "BUDGET_ARCHETYPES",
    "DiscoveryContext",
    "DiscoveryEngine",
    "DiscoveryReport",
    "normalise_title",
]

#: Evidence types that constitute a demand signal for the demand-driven method.
DEMAND_EVIDENCE_TYPES: frozenset[EvidenceType] = frozenset(
    {
        EvidenceType.SEARCH_VOLUME,
        EvidenceType.KEYWORD_TREND,
        EvidenceType.MARKETPLACE_LISTING,
        EvidenceType.OFFICIAL_STATISTIC,
    }
)

#: Evidence types that constitute a problem statement for the customer-problem
#: method.  Review and forum content is where people describe what frustrates
#: them; a listing is not a problem statement.
PROBLEM_EVIDENCE_TYPES: frozenset[EvidenceType] = frozenset(
    {
        EvidenceType.FORUM_POST,
        EvidenceType.MARKETPLACE_REVIEW,
        EvidenceType.COMPETITOR_REVIEW,
        EvidenceType.NEWS_ITEM,
    }
)

TREND_EVIDENCE_TYPES: frozenset[EvidenceType] = frozenset(
    {EvidenceType.KEYWORD_TREND, EvidenceType.SOCIAL_SIGNAL, EvidenceType.NEWS_ITEM}
)


def normalise_title(title: str) -> str:
    """A stable key for duplicate detection.

    Case, punctuation and repeated whitespace are removed so that "Notion
    Templates!" and "notion  templates" are recognisably the same idea.  Words are
    kept in order: reordering changes the meaning.
    """
    lowered = title.strip().lower()
    cleaned = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return " ".join(cleaned.split())


#: §7 budget-driven archetypes.  These are *shapes* of business that a given
#: capital band can plausibly support, not claims that any of them has demand.
#: A candidate produced from this table starts at validation level 0 and must earn
#: everything above it from evidence like any other candidate.
BUDGET_ARCHETYPES: dict[BudgetBand, tuple[tuple[str, BusinessCategory, str], ...]] = {
    BudgetBand.UNDER_10: (
        ("a single digital download sold on an existing marketplace", BusinessCategory.DIGITAL_PRODUCT,
         "the marketplace supplies both distribution and payment handling, so no infrastructure spend is required"),
        ("a productized one-off service delivered with tools already owned", BusinessCategory.FREELANCE_PRODUCTIZED_SERVICE,
         "no inventory and no hosting; the only input is the owner's time"),
    ),
    BudgetBand.TEN_TO_50: (
        ("a domain plus a single-page offer for a productized service", BusinessCategory.FREELANCE_PRODUCTIZED_SERVICE,
         "a domain and basic hosting fit inside the band"),
        ("a small batch of digital templates sold directly", BusinessCategory.DIGITAL_PRODUCT,
         "template production costs nothing beyond time; a storefront fits the band"),
        ("a niche newsletter with a paid tier", BusinessCategory.CONTENT,
         "hosting platforms offer a free tier that covers the early subscriber count"),
    ),
    BudgetBand.FIFTY_TO_100: (
        ("a short online course hosted on an existing platform", BusinessCategory.ONLINE_EDUCATION,
         "platform hosting removes the need for a learning-management system"),
        ("a micro-SaaS tool solving one narrow workflow problem", BusinessCategory.SOFTWARE_TECH_SERVICE,
         "infrastructure and a domain fit the band; the constraint is build time, not capital"),
        ("a curated digital asset library", BusinessCategory.DIGITAL_PRODUCT,
         "storage and a payment processor fit the band"),
    ),
    BudgetBand.ONE_HUNDRED_TO_500: (
        ("a productized B2B service with a repeatable delivery process", BusinessCategory.B2B,
         "the band covers tooling, a domain and a modest paid acquisition test"),
        ("a cohort-based online course", BusinessCategory.ONLINE_EDUCATION,
         "covers platform fees, hosting and initial marketing material"),
        ("a niche e-commerce store selling digital distribution of licensed assets", BusinessCategory.ECOMMERCE_DIGITAL_DISTRIBUTION,
         "covers storefront subscription and a first advertising test"),
    ),
    BudgetBand.FIVE_HUNDRED_TO_1000: (
        ("a subscription software product with paid acquisition", BusinessCategory.SOFTWARE_TECH_SERVICE,
         "covers infrastructure, a payment processor and a measurable advertising budget"),
        ("a done-for-you B2B service with subcontracted delivery", BusinessCategory.B2B,
         "covers the working capital needed before the first client pays"),
        ("an online education programme with a sales funnel", BusinessCategory.ONLINE_EDUCATION,
         "covers production, hosting and funnel advertising"),
    ),
    BudgetBand.OVER_1000: (
        ("a software product with a full launch campaign", BusinessCategory.SOFTWARE_TECH_SERVICE,
         "capital supports sustained acquisition rather than a single test"),
        ("an inventory-light e-commerce brand", BusinessCategory.ECOMMERCE_DIGITAL_DISTRIBUTION,
         "covers initial stock or licensing plus advertising"),
        ("a B2B service company with hired delivery capacity", BusinessCategory.B2B,
         "covers payroll before receivables arrive"),
    ),
    BudgetBand.CUSTOM: (),
}


class DiscoveryContext(BaseModel):
    """Everything discovery is allowed to derive from.

    Any field left empty means the corresponding method returns nothing.  There
    is no default content anywhere in this model.
    """

    model_config = ConfigDict(extra="forbid")

    owner_capabilities: tuple[str, ...] = ()
    budget: BudgetConstraint | None = None
    jurisdictions: tuple[str, ...] = ()
    stated_problems: tuple[str, ...] = ()
    stated_trends: tuple[str, ...] = ()
    preferred_categories: tuple[BusinessCategory, ...] = ()
    competitor_gaps: tuple[str, ...] = ()
    competitor_complaints: tuple[str, ...] = ()
    evidence: tuple[SourceEvidence, ...] = ()
    existing_titles: tuple[str, ...] = ()
    max_candidates_per_method: int = Field(default=5, ge=1, le=50)

    @model_validator(mode="after")
    def _no_empty_strings(self) -> "DiscoveryContext":
        for name in (
            "owner_capabilities",
            "stated_problems",
            "stated_trends",
            "competitor_gaps",
            "competitor_complaints",
        ):
            values = getattr(self, name)
            if any(not v.strip() for v in values):
                raise ValueError(f"{name} contains an empty entry")
        return self

    def admissible_evidence(self) -> tuple[SourceEvidence, ...]:
        """Evidence discovery is allowed to derive candidates from.

        Two exclusions, both deliberate:

        * **Inadmissible classifications.**  CONTRADICTED, UNVERIFIED and
          OUTDATED records cannot seed a candidate.
        * **Model-generated records.**  A MODEL_GENERATED record can legitimately
          carry a TENTATIVE classification, so filtering on classification alone
          would let imagined observations seed real candidates.  Excluding them
          here is the §19 anti-hallucination rule applied at the point where an
          invention would otherwise enter the pipeline as if it had been observed.
        """
        admissible = {
            EvidenceClassification.VERIFIED,
            EvidenceClassification.CORROBORATED,
            EvidenceClassification.SUPPORTING,
            EvidenceClassification.TENTATIVE,
        }
        return tuple(
            e
            for e in self.evidence
            if e.classification in admissible
            and e.evidence_type is not EvidenceType.MODEL_GENERATED
            and e.reliability is not EvidenceReliability.MODEL_GENERATED
        )


class DiscoveryReport(BaseModel):
    """What each method produced, including the methods that produced nothing.

    Reporting the empty methods is not decoration: it is how the owner learns
    *why* discovery was thin, which is usually that the inputs were thin.
    """

    model_config = ConfigDict(extra="forbid")

    candidates: tuple[OpportunityCandidate, ...] = ()
    per_method: dict[str, int] = {}
    empty_methods: tuple[str, ...] = ()
    duplicates_suppressed: int = 0
    inputs_available: dict[str, bool] = {}
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _totals_agree(self) -> "DiscoveryReport":
        if sum(self.per_method.values()) != len(self.candidates):
            raise ValueError(
                f"per_method counts ({sum(self.per_method.values())}) do not "
                f"equal the number of candidates ({len(self.candidates)})"
            )
        return self


class DiscoveryEngine:
    """Generates candidates from the six §7 methods."""

    def _dedupe(
        self, candidates: Sequence[OpportunityCandidate], existing: Sequence[str]
    ) -> tuple[list[OpportunityCandidate], int]:
        seen = {normalise_title(t) for t in existing}
        out: list[OpportunityCandidate] = []
        suppressed = 0
        for candidate in candidates:
            key = normalise_title(candidate.title)
            if key in seen:
                suppressed += 1
                continue
            seen.add(key)
            out.append(candidate)
        return out, suppressed

    # ------------------------------------------------------------------ #
    def from_customer_problems(self, context: DiscoveryContext) -> list[OpportunityCandidate]:
        out: list[OpportunityCandidate] = []
        for problem in context.stated_problems:
            out.append(
                OpportunityCandidate(
                    title=f"Solve: {problem.strip()[:150]}",
                    description=(
                        f"An offering addressing a problem the owner supplied: "
                        f"'{problem.strip()[:300]}'"
                    ),
                    category=self._category_for(context, BusinessCategory.SOFTWARE_TECH_SERVICE),
                    discovery_method=DiscoveryMethod.CUSTOMER_PROBLEM,
                    derived_from="owner_stated_problem",
                    problem_addressed=problem.strip(),
                    generated_by="owner_supplied",
                )
            )
        for evidence in context.admissible_evidence():
            if evidence.evidence_type not in PROBLEM_EVIDENCE_TYPES:
                continue
            out.append(
                OpportunityCandidate(
                    title=f"Address: {evidence.claim.strip()[:140]}",
                    description=(
                        f"Problem statement observed in {evidence.evidence_type.value} "
                        f"evidence classified {evidence.classification.value}"
                    ),
                    category=self._category_for(context, BusinessCategory.SOFTWARE_TECH_SERVICE),
                    discovery_method=DiscoveryMethod.CUSTOMER_PROBLEM,
                    derived_from=evidence.evidence_id,
                    problem_addressed=evidence.claim.strip(),
                    generated_by="deterministic_rule",
                )
            )
        return out[: context.max_candidates_per_method]

    def from_demand_signals(self, context: DiscoveryContext) -> list[OpportunityCandidate]:
        out: list[OpportunityCandidate] = []
        for evidence in context.admissible_evidence():
            if evidence.evidence_type not in DEMAND_EVIDENCE_TYPES:
                continue
            value = (
                f"{evidence.numeric_value} {evidence.unit}"
                if evidence.numeric_value is not None
                else evidence.claim.strip()[:120]
            )
            out.append(
                OpportunityCandidate(
                    title=f"Serve demand: {value[:140]}",
                    description=(
                        f"Demand signal from {evidence.evidence_type.value} "
                        f"(classification {evidence.classification.value}, source "
                        f"{evidence.source_id or 'unattributed'})"
                    ),
                    category=self._category_for(context, BusinessCategory.DIGITAL_PRODUCT),
                    discovery_method=DiscoveryMethod.DEMAND_DRIVEN,
                    derived_from=evidence.evidence_id,
                    generated_by="deterministic_rule",
                )
            )
        return out[: context.max_candidates_per_method]

    def from_competitor_gaps(self, context: DiscoveryContext) -> list[OpportunityCandidate]:
        out: list[OpportunityCandidate] = []
        for gap in context.competitor_gaps:
            out.append(
                OpportunityCandidate(
                    title=f"Gap: {gap.strip()[:150]}",
                    description=(
                        f"A gap in competitor offerings supplied for analysis: "
                        f"'{gap.strip()[:300]}'"
                    ),
                    category=self._category_for(context, BusinessCategory.SOFTWARE_TECH_SERVICE),
                    discovery_method=DiscoveryMethod.COMPETITOR_GAP,
                    derived_from="owner_stated_competitor_gap",
                    problem_addressed=gap.strip(),
                    generated_by="owner_supplied",
                )
            )
        for complaint in context.competitor_complaints:
            out.append(
                OpportunityCandidate(
                    title=f"Fix complaint: {complaint.strip()[:140]}",
                    description=(
                        f"A recurring competitor complaint supplied for analysis: "
                        f"'{complaint.strip()[:300]}'"
                    ),
                    category=self._category_for(context, BusinessCategory.SOFTWARE_TECH_SERVICE),
                    discovery_method=DiscoveryMethod.COMPETITOR_GAP,
                    derived_from="owner_stated_competitor_complaint",
                    problem_addressed=complaint.strip(),
                    generated_by="owner_supplied",
                )
            )
        for evidence in context.admissible_evidence():
            if evidence.evidence_type not in {
                EvidenceType.COMPETITOR_REVIEW,
                EvidenceType.COMPETITOR_FEATURE_SET,
            }:
                continue
            out.append(
                OpportunityCandidate(
                    title=f"Competitor gap: {evidence.claim.strip()[:130]}",
                    description=(
                        f"Derived from {evidence.evidence_type.value} evidence "
                        f"classified {evidence.classification.value}"
                    ),
                    category=self._category_for(context, BusinessCategory.SOFTWARE_TECH_SERVICE),
                    discovery_method=DiscoveryMethod.COMPETITOR_GAP,
                    derived_from=evidence.evidence_id,
                    generated_by="deterministic_rule",
                )
            )
        return out[: context.max_candidates_per_method]

    def from_trends(self, context: DiscoveryContext) -> list[OpportunityCandidate]:
        out: list[OpportunityCandidate] = []
        for trend in context.stated_trends:
            out.append(
                OpportunityCandidate(
                    title=f"Ride trend: {trend.strip()[:150]}",
                    description=(
                        f"An emerging trend the owner supplied for analysis: "
                        f"'{trend.strip()[:300]}'"
                    ),
                    category=self._category_for(context, BusinessCategory.CONTENT),
                    discovery_method=DiscoveryMethod.EMERGING_TREND,
                    derived_from="owner_stated_trend",
                    generated_by="owner_supplied",
                )
            )
        for evidence in context.admissible_evidence():
            if evidence.evidence_type not in TREND_EVIDENCE_TYPES:
                continue
            out.append(
                OpportunityCandidate(
                    title=f"Trend: {evidence.claim.strip()[:150]}",
                    description=(
                        f"Trend signal from {evidence.evidence_type.value} evidence "
                        f"classified {evidence.classification.value}"
                    ),
                    category=self._category_for(context, BusinessCategory.CONTENT),
                    discovery_method=DiscoveryMethod.EMERGING_TREND,
                    derived_from=evidence.evidence_id,
                    generated_by="deterministic_rule",
                )
            )
        return out[: context.max_candidates_per_method]

    def from_capabilities(self, context: DiscoveryContext) -> list[OpportunityCandidate]:
        """Skill/capability-driven: what the owner can actually deliver.

        This method works with no external data at all, which is why it matters in
        a sandboxed deployment.  It produces one candidate per stated capability,
        in the categories where that capability is directly sellable.
        """
        out: list[OpportunityCandidate] = []
        categories = context.preferred_categories or (
            BusinessCategory.FREELANCE_PRODUCTIZED_SERVICE,
            BusinessCategory.ONLINE_EDUCATION,
        )
        for capability in context.owner_capabilities:
            name = capability.strip()
            for category in categories[:2]:
                out.append(
                    OpportunityCandidate(
                        title=f"Productize {name} for {category.value.replace('_',' ')}",
                        description=(
                            f"A productized offering built on the owner's stated "
                            f"capability '{name}', in the {category.value.replace('_',' ')} category"
                        ),
                        category=category,
                        discovery_method=DiscoveryMethod.SKILL_CAPABILITY,
                        derived_from=f"owner_capability:{name.lower()}",
                        proposed_offering=f"productized {name} service",
                        budget_band=context.budget.band if context.budget else None,
                        generated_by="owner_supplied",
                    )
                )
        return out[: context.max_candidates_per_method]

    def from_budget_band(self, context: DiscoveryContext) -> list[OpportunityCandidate]:
        """Budget-driven: the archetypes a capital band can plausibly support.

        These candidates begin at validation level 0.  The archetype table states
        what a band makes *affordable*, never that anything has demand - that has
        to be earned from evidence afterwards, exactly as for any other candidate.
        """
        if context.budget is None:
            return []
        archetypes = BUDGET_ARCHETYPES.get(context.budget.band, ())
        out: list[OpportunityCandidate] = []
        for offering, category, rationale in archetypes:
            out.append(
                OpportunityCandidate(
                    title=offering[:200].capitalize(),
                    description=(
                        f"Budget-driven archetype for the "
                        f"{context.budget.band.value} band "
                        f"({context.budget.available_capital} {context.budget.currency}): "
                        f"{offering}. Rationale: {rationale}. This candidate asserts "
                        "affordability only; it carries no demand evidence and starts "
                        "at validation level 0."
                    ),
                    category=category,
                    discovery_method=DiscoveryMethod.BUDGET_DRIVEN,
                    derived_from=f"budget_band:{context.budget.band.value}",
                    proposed_offering=offering,
                    budget_band=context.budget.band,
                    generated_by="deterministic_rule",
                )
            )
        return out[: context.max_candidates_per_method]

    # ------------------------------------------------------------------ #
    @staticmethod
    def _category_for(
        context: DiscoveryContext, fallback: BusinessCategory
    ) -> BusinessCategory:
        return context.preferred_categories[0] if context.preferred_categories else fallback

    def generate(self, context: DiscoveryContext) -> DiscoveryReport:
        """Run all six methods and report what each produced."""
        methods = {
            DiscoveryMethod.CUSTOMER_PROBLEM: self.from_customer_problems,
            DiscoveryMethod.DEMAND_DRIVEN: self.from_demand_signals,
            DiscoveryMethod.COMPETITOR_GAP: self.from_competitor_gaps,
            DiscoveryMethod.EMERGING_TREND: self.from_trends,
            DiscoveryMethod.SKILL_CAPABILITY: self.from_capabilities,
            DiscoveryMethod.BUDGET_DRIVEN: self.from_budget_band,
        }
        raw: list[OpportunityCandidate] = []
        generated: dict[str, int] = {}
        for method, fn in methods.items():
            produced = fn(context)
            generated[method.value] = len(produced)
            raw.extend(produced)

        kept, suppressed = self._dedupe(raw, context.existing_titles)
        # Counted AFTER deduplication, so per_method always sums to the number of
        # candidates the report actually returns.  Counting what was generated
        # would make the report describe work it then threw away.
        per_method = {method.value: 0 for method in methods}
        for candidate in kept:
            per_method[candidate.discovery_method.value] += 1

        inputs = {
            "owner_capabilities": bool(context.owner_capabilities),
            "budget": context.budget is not None,
            "stated_problems": bool(context.stated_problems),
            "stated_trends": bool(context.stated_trends),
            "competitor_gaps": bool(context.competitor_gaps),
            "competitor_complaints": bool(context.competitor_complaints),
            "admissible_evidence": bool(context.admissible_evidence()),
        }
        notes: list[str] = []
        empty = tuple(m.value for m in methods if per_method[m.value] == 0)
        fully_empty = tuple(m.value for m in methods if generated[m.value] == 0)
        if not inputs["admissible_evidence"]:
            notes.append(
                "no admissible evidence was available, so the customer-problem, "
                "demand-driven, competitor-gap and emerging-trend methods could "
                "only derive from owner-supplied input"
            )
        if fully_empty:
            notes.append(
                f"{len(fully_empty)} of 6 discovery methods produced nothing for lack of "
                f"input: {', '.join(fully_empty)}. This is a property of the inputs, not "
                "a failure of the methods."
            )
        if suppressed:
            notes.append(
                f"{suppressed} generated candidate(s) were suppressed as duplicates "
                "of titles already under evaluation"
            )
        return DiscoveryReport(
            candidates=tuple(kept),
            per_method=per_method,
            empty_methods=empty,
            duplicates_suppressed=suppressed,
            inputs_available=inputs,
            notes=tuple(notes),
        )

    def summarise(self, report: DiscoveryReport) -> dict[str, Any]:
        return {
            "total": len(report.candidates),
            "per_method": dict(report.per_method),
            "empty_methods": list(report.empty_methods),
            "duplicates_suppressed": report.duplicates_suppressed,
            "inputs_available": dict(report.inputs_available),
            "notes": list(report.notes),
            "by_category": _count_by(report.candidates, "category"),
            "by_generated_by": _count_by(report.candidates, "generated_by"),
        }


def _count_by(candidates: Sequence[OpportunityCandidate], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for candidate in candidates:
        value = getattr(candidate, attr)
        key = value.value if hasattr(value, "value") else str(value)
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))
