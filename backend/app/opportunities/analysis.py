"""P-03 §10 market, §11 competitor, §12 business-model and §14 distribution
analysis.

These four builders share one discipline, which is the discipline of the whole
phase: **they describe evidence, they do not produce it.**

Each takes a body of :class:`SourceEvidence` and returns an assessment.  When the
evidence does not support a conclusion the assessment says so - ``insufficient_data``,
``unknown``, or an explicit entry in ``data_gaps`` - rather than reaching for a
plausible number.  In particular:

* A TAM/SAM/SOM figure is only constructed when an evidence record actually
  carries one, with provenance, a stated basis and a citation.  The schema refuses
  a value without all three, so there is no path by which an invented market size
  can enter the pipeline.
* A problem-importance rating requires a stated basis and is derived from counted
  observations, not from the tone of a description.
* Competitor price ranges are the min and max of *quoted* prices, never an
  estimate of what a competitor "probably" charges.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.intelligence.schemas import EvidenceReliability
from app.opportunities.schemas import (
    ADMISSIBLE_CLASSIFICATIONS,
    BusinessModelAnalysis,
    BusinessModelType,
    CompetitorAssessment,
    CompetitorProfile,
    DistributionAssessment,
    DistributionChannel,
    EvidenceClassification,
    EvidenceType,
    MarketAssessment,
    MarketSignal,
    MarketSizing,
    Provenance,
    RiskSeverity,
    SizedMarket,
    SourceEvidence,
)

__all__ = [
    "BusinessModelAnalyser",
    "CompetitorAnalyser",
    "DistributionAnalyser",
    "MarketAnalyser",
    "PROVENANCE_FROM_RELIABILITY",
]

#: How a source's reliability maps onto the provenance of a figure taken from it.
#: Note what is missing: nothing maps to VERIFIED.  A figure is only VERIFIED by
#: explicit confirmation, never by virtue of where it came from.
PROVENANCE_FROM_RELIABILITY: dict[EvidenceReliability, Provenance] = {
    EvidenceReliability.AUTHORITATIVE: Provenance.QUOTED,
    EvidenceReliability.TRUSTED: Provenance.QUOTED,
    EvidenceReliability.PLAUSIBLE: Provenance.ESTIMATE,
    EvidenceReliability.UNTRUSTED: Provenance.ESTIMATE,
    EvidenceReliability.MODEL_GENERATED: Provenance.UNKNOWN,
}

DEMAND_TYPES: frozenset[EvidenceType] = frozenset(
    {
        EvidenceType.SEARCH_VOLUME,
        EvidenceType.KEYWORD_TREND,
        EvidenceType.MARKETPLACE_LISTING,
        EvidenceType.OFFICIAL_STATISTIC,
        EvidenceType.SOCIAL_SIGNAL,
    }
)
PROBLEM_TYPES: frozenset[EvidenceType] = frozenset(
    {EvidenceType.FORUM_POST, EvidenceType.MARKETPLACE_REVIEW, EvidenceType.COMPETITOR_REVIEW}
)
PRICING_TYPES: frozenset[EvidenceType] = frozenset(
    {EvidenceType.COMPETITOR_PRICING, EvidenceType.VENDOR_PRICE_QUOTE}
)


def _best_classification(evidence: Sequence[SourceEvidence]) -> EvidenceClassification | None:
    admissible = [e for e in evidence if e.classification in ADMISSIBLE_CLASSIFICATIONS]
    if not admissible:
        return None
    order = {
        EvidenceClassification.VERIFIED: 0,
        EvidenceClassification.CORROBORATED: 1,
        EvidenceClassification.SUPPORTING: 2,
        EvidenceClassification.TENTATIVE: 3,
    }
    return min(admissible, key=lambda e: order[e.classification]).classification


class MarketAnalyser:
    """§10 market and customer analysis."""

    def sizing_from_evidence(
        self,
        evidence: Sequence[SourceEvidence],
        *,
        geography: Sequence[str] = (),
        segments: Sequence[str] = (),
        buying_trigger: str | None = None,
        alternatives: Sequence[str] = (),
    ) -> MarketSizing:
        """Build TAM/SAM/SOM only from evidence that actually carries a figure.

        A record qualifies when it is an OFFICIAL_STATISTIC or a marketplace
        observation with a numeric value, an admissible classification and a named
        source.  Anything else leaves that level unset and records a data gap -
        an unknown market size is a legitimate finding.
        """
        gaps: list[str] = []
        levels: dict[str, SizedMarket | None] = {"tam": None, "sam": None, "som": None}

        for label, wanted_types in (
            ("tam", {EvidenceType.OFFICIAL_STATISTIC}),
            ("sam", {EvidenceType.OFFICIAL_STATISTIC, EvidenceType.MARKETPLACE_LISTING}),
            ("som", {EvidenceType.MARKETPLACE_LISTING}),
        ):
            candidates = [
                e
                for e in evidence
                if e.evidence_type in wanted_types
                and e.numeric_value is not None
                and e.classification in ADMISSIBLE_CLASSIFICATIONS
                and e.source_id is not None
                and label.upper() in (e.claim or "").upper()
            ]
            if not candidates:
                gaps.append(
                    f"{label.upper()} could not be sized: no admissible evidence "
                    f"record carries a {label.upper()} figure"
                )
                continue
            best = candidates[0]
            levels[label] = SizedMarket(
                label=label,  # type: ignore[arg-type]
                value=best.numeric_value,
                unit="currency_per_year" if (best.unit or "").lower() in {"usd", "eur", "gbp", "inr", "currency"} else "customers",
                provenance=PROVENANCE_FROM_RELIABILITY[best.reliability],
                basis=best.claim[:400],
                evidence_ids=(best.evidence_id,),
                as_of=best.collected_at,
                region=geography[0] if geography else None,
            )

        return MarketSizing(
            tam=levels["tam"],
            sam=levels["sam"],
            som=levels["som"],
            geography=tuple(geography),
            customer_segments=tuple(segments),
            buying_trigger=buying_trigger,
            existing_alternatives=tuple(alternatives),
            data_gaps=tuple(gaps),
        )

    def signals_from_evidence(self, evidence: Sequence[SourceEvidence]) -> tuple[MarketSignal, ...]:
        out: list[MarketSignal] = []
        for item in evidence:
            if item.evidence_type not in DEMAND_TYPES:
                continue
            if item.classification not in ADMISSIBLE_CLASSIFICATIONS:
                continue
            out.append(
                MarketSignal(
                    signal=item.claim,
                    metric_name=item.evidence_type.value,
                    metric_value=item.numeric_value,
                    unit=item.unit,
                    observed_at=item.collected_at,
                    evidence_id=item.evidence_id,
                    provenance=(
                        Provenance.UNKNOWN
                        if item.numeric_value is None
                        else PROVENANCE_FROM_RELIABILITY[item.reliability]
                    ),
                )
            )
        return tuple(out)

    def importance_from_evidence(
        self, evidence: Sequence[SourceEvidence]
    ) -> tuple[str, str | None]:
        """Rate problem importance from counted problem observations.

        The rating is a function of how many admissible problem records exist and
        how well they are classified - not of how emphatic their wording is.  With
        no problem evidence the answer is ``unknown``, which is a valid result.
        """
        problem_records = [
            e
            for e in evidence
            if e.evidence_type in PROBLEM_TYPES and e.classification in ADMISSIBLE_CLASSIFICATIONS
        ]
        if not problem_records:
            return "unknown", None
        strong = sum(
            1
            for e in problem_records
            if e.classification in {EvidenceClassification.VERIFIED, EvidenceClassification.CORROBORATED}
        )
        count = len(problem_records)
        if strong >= 2:
            rating, why = "acute", f"{strong} strongly classified problem observations among {count}"
        elif strong == 1:
            rating, why = "significant", f"1 strongly classified problem observation among {count}"
        elif count >= 3:
            rating, why = "moderate", f"{count} weakly classified problem observations"
        elif count == 2:
            rating, why = "minor", f"2 weakly classified problem observations"
        else:
            rating, why = "trivial", "a single weakly classified problem observation"
        return rating, why

    def analyse(
        self,
        evidence: Sequence[SourceEvidence],
        *,
        geography: Sequence[str] = (),
        segments: Sequence[str] = (),
        buying_trigger: str | None = None,
        alternatives: Sequence[str] = (),
    ) -> MarketAssessment:
        demand_evidence = [e for e in evidence if e.evidence_type in DEMAND_TYPES]
        admissible_demand = [
            e for e in demand_evidence if e.classification in ADMISSIBLE_CLASSIFICATIONS
        ]
        contradicted = [
            e for e in demand_evidence if e.classification is EvidenceClassification.CONTRADICTED
        ]
        best = _best_classification(admissible_demand)
        importance, importance_basis = self.importance_from_evidence(evidence)
        sizing = self.sizing_from_evidence(
            evidence,
            geography=geography,
            segments=segments,
            buying_trigger=buying_trigger,
            alternatives=alternatives,
        )
        signals = self.signals_from_evidence(evidence)
        gaps = list(sizing.data_gaps)

        if contradicted and not admissible_demand:
            verdict = "demand_contradicted"
            reasons = tuple(
                f"demand is contradicted: {c.claim[:160]}" for c in contradicted[:3]
            )
        elif not admissible_demand:
            verdict = "insufficient_data"
            reasons = (
                "no admissible demand evidence was collected; demand is neither "
                "demonstrated nor refuted",
            )
            gaps.append("no admissible demand evidence")
        elif best in {EvidenceClassification.VERIFIED, EvidenceClassification.CORROBORATED}:
            verdict = "demand_demonstrated"
            reasons = tuple(
                f"demand evidenced at {best.value}: {e.claim[:160]}" for e in admissible_demand[:3]
            )
        elif best is EvidenceClassification.SUPPORTING:
            verdict = "demand_plausible"
            reasons = tuple(
                f"demand supported but not corroborated: {e.claim[:160]}"
                for e in admissible_demand[:3]
            )
        else:
            verdict = "demand_unproven"
            reasons = ("demand evidence is only tentative",)
            gaps.append("demand evidence is tentative and needs corroboration")

        if not geography:
            gaps.append("no target geography was supplied")

        return MarketAssessment(
            sizing=sizing,
            signals=signals,
            demand_evidence_level=best or EvidenceClassification.UNVERIFIED,
            problem_importance=importance,  # type: ignore[arg-type]
            problem_importance_basis=importance_basis,
            customer_description="; ".join(segments) if segments else None,
            willingness_indicators=tuple(
                e.claim[:160]
                for e in evidence
                if e.evidence_type is EvidenceType.TRANSACTION_RECORD
                and e.classification in ADMISSIBLE_CLASSIFICATIONS
            ),
            data_gaps=tuple(dict.fromkeys(gaps)),
            verdict=verdict,  # type: ignore[arg-type]
            reasons=reasons,
        )


class CompetitorAnalyser:
    """§11 competitor intelligence."""

    def profiles_from_evidence(
        self, evidence: Sequence[SourceEvidence]
    ) -> tuple[CompetitorProfile, ...]:
        """Build one profile per distinct source-identified competitor claim.

        A profile is only created when there is something observed.  Prices are
        attached only from COMPETITOR_PRICING records with a numeric value, and
        carry the provenance implied by the source's reliability.
        """
        prices: dict[str, list[SourceEvidence]] = {}
        for item in evidence:
            if item.evidence_type is EvidenceType.COMPETITOR_PRICING and (
                item.numeric_value is not None
            ) and item.classification in ADMISSIBLE_CLASSIFICATIONS:
                prices.setdefault(item.source_id or "unattributed", []).append(item)
        out: list[CompetitorProfile] = []
        for source_id, items in prices.items():
            values = [i.numeric_value for i in items if i.numeric_value is not None]
            out.append(
                CompetitorProfile(
                    name=items[0].claim[:120] or source_id,
                    price_points=tuple(sorted(set(values))),
                    pricing_provenance=PROVENANCE_FROM_RELIABILITY[items[0].reliability],
                    evidence_ids=tuple(i.evidence_id for i in items),
                    observed_at=items[0].collected_at,
                    inspected=True,
                )
            )
        return tuple(out)

    def analyse(
        self,
        evidence: Sequence[SourceEvidence],
        *,
        competitors: Sequence[CompetitorProfile] = (),
        gaps: Sequence[str] = (),
        differentiation_basis: str | None = None,
    ) -> CompetitorAssessment:
        observed = tuple(competitors) or self.profiles_from_evidence(evidence)
        data_gaps: list[str] = []
        if not observed:
            data_gaps.append(
                "no competitor was observed; the competitive landscape is unknown "
                "rather than empty"
            )
            return CompetitorAssessment(
                competitors=(),
                market_saturation="unknown",
                gaps_identified=tuple(gaps),
                data_gaps=tuple(data_gaps),
                verdict="insufficient_data",
                reasons=("no competitor evidence was collected",),
            )

        count = len(observed)
        inspected = sum(1 for c in observed if c.inspected)
        if inspected < count:
            data_gaps.append(f"{count - inspected} of {count} competitors were not inspected")

        if count == 0:
            saturation = "empty"
        elif count <= 2:
            saturation = "sparse"
        elif count <= 5:
            saturation = "moderate"
        elif count <= 12:
            saturation = "crowded"
        else:
            saturation = "saturated"

        identified = list(gaps)
        for competitor in observed:
            identified.extend(competitor.identified_gaps)
            identified.extend(competitor.complaint_themes)
        identified = list(dict.fromkeys(identified))

        if saturation == "saturated" and not identified:
            verdict, reasons = "saturated_no_entry", (
                f"{count} competitors observed and no gap identified",
            )
        elif saturation in {"saturated", "crowded"}:
            verdict = "crowded_but_viable" if identified else "saturated_no_entry"
            reasons = (
                f"{count} competitors observed, saturation {saturation}"
                + (f", {len(identified)} gap(s) identified" if identified else ", no gap identified"),
            )
        elif identified:
            verdict = "differentiation_required"
            reasons = (f"{count} competitors observed; {len(identified)} gap(s) to differentiate on",)
        else:
            verdict = "open_opportunity" if count == 0 else "differentiation_required"
            reasons = (f"{count} competitors observed",)

        if count > 0 and verdict == "open_opportunity":
            # The schema forbids this combination; fall back rather than raise.
            verdict = "differentiation_required"

        return CompetitorAssessment(
            competitors=observed,
            market_saturation=saturation,  # type: ignore[arg-type]
            gaps_identified=tuple(identified),
            differentiation_available=bool(identified) and differentiation_basis is not None,
            differentiation_basis=differentiation_basis,
            data_gaps=tuple(data_gaps),
            verdict=verdict,  # type: ignore[arg-type]
            reasons=reasons,
        )


class BusinessModelAnalyser:
    """§12 business-model analysis."""

    def derive(
        self,
        evidence: Sequence[SourceEvidence],
        *,
        model_type: BusinessModelType | None = None,
        revenue_mechanism: str | None = None,
        billing_period: str = "once",
        payment_processor: str | None = None,
    ) -> BusinessModelAnalysis | None:
        """Derive a model from observed competitor pricing.

        Returns ``None`` when nothing is observed: the caller records that as a
        data gap rather than inventing a plausible business model.
        """
        prices = [
            e
            for e in evidence
            if e.evidence_type is EvidenceType.COMPETITOR_PRICING
            and e.numeric_value is not None
            and e.classification in ADMISSIBLE_CLASSIFICATIONS
        ]
        quotes = [
            e
            for e in evidence
            if e.evidence_type is EvidenceType.VENDOR_PRICE_QUOTE and e.numeric_value is not None
        ]
        if not prices and not revenue_mechanism:
            return None

        price = None
        provenance = Provenance.UNKNOWN
        evidence_ids: list[str] = []
        if prices:
            values = sorted(p.numeric_value for p in prices if p.numeric_value is not None)
            # The LOWER median, not the mean: a single outlier listing must not
            # set the price of the whole model.  Taking the lower of the two
            # middle values for an even count is deliberate - `len // 2` selects
            # the upper one, which biases every price estimate upward and with it
            # every revenue projection.  Biasing low is the conservative error,
            # and this phase is supposed to be conservative.
            price = values[(len(values) - 1) // 2]
            provenance = PROVENANCE_FROM_RELIABILITY[prices[0].reliability]
            evidence_ids.extend(p.evidence_id for p in prices)

        processor_fee: Decimal | None = None
        fee_provenance = Provenance.UNKNOWN
        for quote in quotes:
            if "processor" in (quote.claim or "").lower() or "fee" in (quote.claim or "").lower():
                processor_fee = quote.numeric_value
                fee_provenance = PROVENANCE_FROM_RELIABILITY[quote.reliability]
                evidence_ids.append(quote.evidence_id)
                break

        weaknesses: list[str] = []
        if provenance is Provenance.ESTIMATE:
            weaknesses.append("the price point rests on an estimate rather than a quote")
        if not prices:
            weaknesses.append("no competitor price was observed; the mechanism is asserted, not evidenced")

        return BusinessModelAnalysis(
            model_type=model_type or BusinessModelType.ONE_TIME_SALE,
            revenue_mechanism=revenue_mechanism
            or (f"selling at an observed competitor price point of {price}" if price else "unspecified"),
            price_point=price,
            price_provenance=provenance if price is not None else Provenance.UNKNOWN,
            billing_period=billing_period,  # type: ignore[arg-type]
            payment_processor=payment_processor,
            processor_fee_pct=processor_fee,
            fee_provenance=fee_provenance if processor_fee is not None else Provenance.UNKNOWN,
            weaknesses=tuple(weaknesses),
            evidence_ids=tuple(dict.fromkeys(evidence_ids)),
        )


class DistributionAnalyser:
    """§14 distribution and customer acquisition."""

    def channels_from_evidence(
        self, evidence: Sequence[SourceEvidence]
    ) -> tuple[DistributionChannel, ...]:
        out: list[DistributionChannel] = []
        seen: set[str] = set()
        for item in evidence:
            if item.evidence_type not in {
                EvidenceType.MARKETPLACE_LISTING,
                EvidenceType.SOCIAL_SIGNAL,
            }:
                continue
            if item.classification not in ADMISSIBLE_CLASSIFICATIONS:
                continue
            name = (item.claim or "")[:100]
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            kind = "marketplace" if item.evidence_type is EvidenceType.MARKETPLACE_LISTING else "social_organic"
            out.append(
                DistributionChannel(
                    channel=name,
                    kind=kind,  # type: ignore[arg-type]
                    platform_controlled=True,
                    dependency_risk="medium",
                    feasible_without_ad_spend=True,
                    evidence_ids=(item.evidence_id,),
                    notes=f"observed via {item.evidence_type.value}",
                )
            )
        return tuple(out)

    def analyse(
        self,
        evidence: Sequence[SourceEvidence],
        *,
        channels: Sequence[DistributionChannel] = (),
    ) -> DistributionAssessment:
        observed = tuple(channels) or self.channels_from_evidence(evidence)
        if not observed:
            return DistributionAssessment(
                channels=(),
                data_gaps=("no distribution channel was observed or supplied",),
                verdict="insufficient_data",
                reasons=("no route to customers could be identified from the evidence",),
            )
        organic = [c for c in observed if c.feasible_without_ad_spend]
        if organic:
            verdict = "clear_path" if len(organic) >= 2 else "plausible_path"
            reasons = (
                f"{len(organic)} channel(s) reachable without advertising spend: "
                + ", ".join(c.channel[:40] for c in organic[:3]),
            )
        else:
            verdict = "requires_ad_spend"
            reasons = ("every observed channel requires advertising spend",)
        return DistributionAssessment(
            channels=observed,
            verdict=verdict,  # type: ignore[arg-type]
            reasons=reasons,
            data_gaps=(
                "channel costs were not observed; acquisition cost is unknown"
                if all(c.cost_provenance is Provenance.UNKNOWN for c in observed)
                else None,
            )
            if any(c.cost_provenance is Provenance.UNKNOWN for c in observed)
            else (),
        )
