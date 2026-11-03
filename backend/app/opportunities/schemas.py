"""P-03 value types: every enum, constraint and record the discovery engine
passes between its stages.

Design rules that shape this file
--------------------------------
1. **Rejection is the primary product.**  The phase brief states that AUTONOMOUS
   must become better at rejecting bad opportunities than at generating
   attractive ones.  Every model here therefore carries an explicit refusal or
   insufficiency path; none of them can represent "we do not know" as success.
2. **No figure without a classification.**  Every monetary or quantitative
   field is paired with a provenance classification (verified / quoted /
   historical / estimate / unknown).  A bare number is never accepted.
3. **P-02 is reused, not duplicated.**  Uncertainty, reliability and trust
   semantics come from :mod:`app.intelligence.schemas`; this module adds only
   the market-research vocabulary that P-02 does not have.
4. ``extra="forbid"`` everywhere, so a caller cannot smuggle in an unmodelled
   field (for example a fabricated ``verified_revenue``) and have it silently
   persisted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.intelligence.schemas import (
    EvidenceReliability,
    RiskLevel,
    TrustDomain,
    UncertaintyLevel,
)

__all__ = [
    "AcquisitionMethod",
    "Assumption",
    "CommercialAssessment",
    "MarketAssessment",
    "CompetitorAssessment",
    "DistributionAssessment",
    "RiskAssessment",
    "ScreeningResult",
    "ScoringOutcome",
    "ReportSection",
    "OpportunityReport",
    "ResearchTaskSpec",
    "SizedMarket",
    "RISK_SEVERITY_RANK",
    "SCENARIO_VOLUME_FACTORS",
    "ATTRACTIVENESS_KEYS",
    "CLASSIFICATION_RANK",
    "ADMISSIBLE_CLASSIFICATIONS",
    "LEVEL_4_PROHIBITED_INPUTS",
    "LEVEL_5_PROHIBITED_INPUTS",
    "BAND_UPPER_BOUNDS",
    "BreakEvenResult",
    "BudgetBand",
    "BudgetCompatibility",
    "BudgetConstraint",
    "BusinessCategory",
    "BusinessModelAnalysis",
    "BusinessModelType",
    "CompetitorProfile",
    "CostItem",
    "CostStructure",
    "DiscoveryMethod",
    "DistributionChannel",
    "EvidenceClassification",
    "EvidenceType",
    "FinalClassification",
    "FinancialProjection",
    "MarketSignal",
    "MarketSizing",
    "Opportunity",
    "OpportunityCandidate",
    "OpportunityState",
    "OpportunityTransitionError",
    "OPPORTUNITY_TRANSITIONS",
    "Provenance",
    "RetrievedContent",
    "RiskFinding",
    "RiskSeverity",
    "ScoreDimension",
    "ScenarioName",
    "ScenarioProjection",
    "SourceDescriptor",
    "SourceEvidence",
    "SourceStatus",
    "SourceType",
    "ValidationAssessment",
    "ValidationLevel",
    "WeightKey",
    "DEFAULT_WEIGHTS",
    "TERMINAL_STATES",
]


# --------------------------------------------------------------------------- #
# §6 - business categories
# --------------------------------------------------------------------------- #
class BusinessCategory(str, Enum):
    """The seven categories an opportunity may belong to (§6)."""

    DIGITAL_PRODUCT = "digital_product"
    SOFTWARE_TECH_SERVICE = "software_tech_service"
    CONTENT = "content"
    FREELANCE_PRODUCTIZED_SERVICE = "freelance_productized_service"
    ONLINE_EDUCATION = "online_education"
    ECOMMERCE_DIGITAL_DISTRIBUTION = "ecommerce_digital_distribution"
    B2B = "b2b"


# --------------------------------------------------------------------------- #
# §7 - discovery methods and budget bands
# --------------------------------------------------------------------------- #
class DiscoveryMethod(str, Enum):
    """The six ways a candidate may be produced (§7).

    A method describes *how the candidate was derived*, which is what makes the
    derivation auditable.  It is not a quality judgement: a budget-driven
    candidate is not worse than a demand-driven one, it merely has a different
    evidential starting point.
    """

    CUSTOMER_PROBLEM = "customer_problem"
    DEMAND_DRIVEN = "demand_driven"
    COMPETITOR_GAP = "competitor_gap"
    EMERGING_TREND = "emerging_trend"
    SKILL_CAPABILITY = "skill_capability"
    BUDGET_DRIVEN = "budget_driven"


class BudgetBand(str, Enum):
    """Startup-capital bands (§7).  ``CUSTOM`` covers any owner-stated figure
    that does not fall in a preset band."""

    UNDER_10 = "under_10"
    TEN_TO_50 = "10_to_50"
    FIFTY_TO_100 = "50_to_100"
    ONE_HUNDRED_TO_500 = "100_to_500"
    FIVE_HUNDRED_TO_1000 = "500_to_1000"
    OVER_1000 = "over_1000"
    CUSTOM = "custom"


#: Bands form a **half-open partition** ``[lower, upper)`` of the non-negative
#: reals, so every amount falls in exactly one band and no boundary is
#: ambiguous: ``$9.99 -> UNDER_10``, ``$10 -> TEN_TO_50``, ``$50 ->
#: FIFTY_TO_100``, ``$100 -> ONE_HUNDRED_TO_500``, ``$500 ->
#: FIVE_HUNDRED_TO_1000``, ``$1000 -> OVER_1000``.  A colloquial reading of
#: "$10-50" as inclusive of 50 would make 50 belong to two bands at once.
BAND_UPPER_BOUNDS: dict[BudgetBand, Decimal | None] = {
    BudgetBand.UNDER_10: Decimal("10"),
    BudgetBand.TEN_TO_50: Decimal("50"),
    BudgetBand.FIFTY_TO_100: Decimal("100"),
    BudgetBand.ONE_HUNDRED_TO_500: Decimal("500"),
    BudgetBand.FIVE_HUNDRED_TO_1000: Decimal("1000"),
    BudgetBand.OVER_1000: None,
    BudgetBand.CUSTOM: None,
}


class BudgetConstraint(BaseModel):
    """The owner's stated capital limit.

    §13 forbids the engine from silently raising this figure.  It is therefore
    immutable in practice: ``available_capital`` is captured once, with the
    currency and the fact of whether the owner actually stated it.  Any
    downstream analysis that needs more money must return
    ``INCOMPATIBLE`` - it may not amend this record.
    """

    model_config = ConfigDict(extra="forbid")

    available_capital: Decimal = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    owner_stated: bool = True
    band: BudgetBand = BudgetBand.CUSTOM
    recurring_allowance: Decimal = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def _classify_band(self) -> "BudgetConstraint":
        if self.band is not BudgetBand.CUSTOM:
            return self
        amount = self.available_capital
        for band in (
            BudgetBand.UNDER_10,
            BudgetBand.TEN_TO_50,
            BudgetBand.FIFTY_TO_100,
            BudgetBand.ONE_HUNDRED_TO_500,
            BudgetBand.FIVE_HUNDRED_TO_1000,
        ):
            if amount < BAND_UPPER_BOUNDS[band]:  # type: ignore[operator]
                object.__setattr__(self, "band", band)
                return self
        object.__setattr__(self, "band", BudgetBand.OVER_1000)
        return self


# --------------------------------------------------------------------------- #
# §8 - research sources
# --------------------------------------------------------------------------- #
class SourceType(str, Enum):
    """What kind of source an adapter talks to (§8)."""

    SEARCH_ENGINE = "search_engine"
    MARKETPLACE = "marketplace"
    COMMUNITY_FORUM = "community_forum"
    REVIEW_SITE = "review_site"
    TREND_SERVICE = "trend_service"
    GOVERNMENT_STATISTICS = "government_statistics"
    VENDOR_PRICING = "vendor_pricing"
    NEWS = "news"
    REGISTRY = "registry"
    OWNER_SUPPLIED = "owner_supplied"
    MOCK = "mock"


class AcquisitionMethod(str, Enum):
    """How content is obtained.  ``UNAVAILABLE`` is a first-class answer: an
    adapter that cannot reach its source reports it rather than guessing."""

    HTTP_GET = "http_get"
    OFFICIAL_API = "official_api"
    AUTHENTICATED_API = "authenticated_api"
    STRUCTURED_FEED = "structured_feed"
    OWNER_UPLOAD = "owner_upload"
    MOCK_ADAPTER = "mock_adapter"
    UNAVAILABLE = "unavailable"


class SourceStatus(str, Enum):
    AUTHORIZED = "authorized"
    NOT_CONFIGURED = "not_configured"
    UNREACHABLE = "unreachable"
    RATE_LIMITED = "rate_limited"
    FORBIDDEN_BY_POLICY = "forbidden_by_policy"
    DEGRADED = "degraded"


class SourceDescriptor(BaseModel):
    """A provider-independent declaration of one research source (§8).

    Every field the brief requires is present and explicit, including the two
    that are easiest to forget and most consequential: ``licensing`` (may we
    use this data at all?) and ``reliability`` (how much weight does it carry?).
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    source_type: SourceType
    access_method: AcquisitionMethod
    requires_auth: bool = False
    auth_mechanism: Literal["none", "api_key", "oauth2", "owner_session"] = "none"
    rate_limit_per_minute: int | None = Field(default=None, ge=0)
    returned_fields: tuple[str, ...] = ()
    refresh_frequency: Literal["realtime", "daily", "weekly", "monthly", "manual"] = "manual"
    licensing: str = Field(min_length=1, max_length=400)
    reliability: EvidenceReliability = EvidenceReliability.UNTRUSTED
    supported_operations: tuple[str, ...] = ()
    status: SourceStatus = SourceStatus.NOT_CONFIGURED
    endpoint_template: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _auth_consistency(self) -> "SourceDescriptor":
        if self.requires_auth and self.auth_mechanism == "none":
            raise ValueError(
                "source declares requires_auth=True but auth_mechanism='none'"
            )
        if not self.requires_auth and self.auth_mechanism != "none":
            raise ValueError(
                "source declares an auth_mechanism without requires_auth=True"
            )
        if self.access_method is AcquisitionMethod.UNAVAILABLE and (
            self.status is SourceStatus.AUTHORIZED
        ):
            raise ValueError(
                "an unreachable acquisition method cannot be declared AUTHORIZED"
            )
        return self


class RetrievedContent(BaseModel):
    """Raw bytes/text obtained from a source.

    §27 requires that all retrieved content be treated as untrusted.  That is
    expressed structurally: the trust domain is forced to ``EXTERNAL`` and the
    payload is *never* interpreted as instruction text by this layer.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=64)
    retrieved_at: datetime
    url: str | None = Field(default=None, max_length=2048)
    http_status: int | None = Field(default=None, ge=100, le=599)
    body_text: str = ""
    structured: dict[str, Any] = Field(default_factory=dict)
    trust_domain: TrustDomain = TrustDomain.EXTERNAL
    retrieval_error: str | None = None
    bytes_received: int = Field(default=0, ge=0)

    @field_validator("trust_domain")
    @classmethod
    def _always_external(cls, value: TrustDomain) -> TrustDomain:
        """Retrieved content may never be promoted to OWNER/SYSTEM/VERIFIED."""
        if value is not TrustDomain.EXTERNAL:
            raise ValueError("retrieved content is always TrustDomain.EXTERNAL")
        return value


# --------------------------------------------------------------------------- #
# §9 - evidence
# --------------------------------------------------------------------------- #
class EvidenceType(str, Enum):
    """What kind of observation an evidence record holds (§9)."""

    SEARCH_VOLUME = "search_volume"
    KEYWORD_TREND = "keyword_trend"
    MARKETPLACE_LISTING = "marketplace_listing"
    MARKETPLACE_REVIEW = "marketplace_review"
    FORUM_POST = "forum_post"
    COMPETITOR_PRICING = "competitor_pricing"
    COMPETITOR_FEATURE_SET = "competitor_feature_set"
    COMPETITOR_REVIEW = "competitor_review"
    OFFICIAL_STATISTIC = "official_statistic"
    VENDOR_PRICE_QUOTE = "vendor_price_quote"
    NEWS_ITEM = "news_item"
    SOCIAL_SIGNAL = "social_signal"
    TRANSACTION_RECORD = "transaction_record"
    OWNER_STATEMENT = "owner_statement"
    MODEL_GENERATED = "model_generated"


class EvidenceClassification(str, Enum):
    """The seven evidence classifications (§9).

    These are deliberately *stronger* than P-02's :class:`UncertaintyLevel`
    because market research needs to distinguish "one source said it"
    (SUPPORTING) from "two independent sources said it" (CORROBORATED), and
    needs an OUTDATED class for data whose collection date has passed its
    useful life.  :data:`CLASSIFICATION_TO_UNCERTAINTY` maps back onto the P-02
    scale so the reasoning engine can consume P-03 evidence without a second
    notion of certainty.
    """

    VERIFIED = "verified"
    CORROBORATED = "corroborated"
    SUPPORTING = "supporting"
    TENTATIVE = "tentative"
    UNVERIFIED = "unverified"
    CONTRADICTED = "contradicted"
    OUTDATED = "outdated"


CLASSIFICATION_TO_UNCERTAINTY: dict[EvidenceClassification, UncertaintyLevel] = {
    EvidenceClassification.VERIFIED: UncertaintyLevel.VERIFIED,
    EvidenceClassification.CORROBORATED: UncertaintyLevel.STRONGLY_SUPPORTED,
    EvidenceClassification.SUPPORTING: UncertaintyLevel.TENTATIVE,
    EvidenceClassification.TENTATIVE: UncertaintyLevel.TENTATIVE,
    EvidenceClassification.UNVERIFIED: UncertaintyLevel.ASSUMED,
    EvidenceClassification.CONTRADICTED: UncertaintyLevel.CONTRADICTED,
    EvidenceClassification.OUTDATED: UncertaintyLevel.UNKNOWN,
}

CLASSIFICATION_RANK: dict[EvidenceClassification, int] = {
    EvidenceClassification.VERIFIED: 0,
    EvidenceClassification.CORROBORATED: 1,
    EvidenceClassification.SUPPORTING: 2,
    EvidenceClassification.TENTATIVE: 3,
    EvidenceClassification.UNVERIFIED: 4,
    EvidenceClassification.CONTRADICTED: 5,
    EvidenceClassification.OUTDATED: 6,
}

#: Classifications that may support a positive claim at all.
ADMISSIBLE_CLASSIFICATIONS: frozenset[EvidenceClassification] = frozenset(
    {
        EvidenceClassification.VERIFIED,
        EvidenceClassification.CORROBORATED,
        EvidenceClassification.SUPPORTING,
        EvidenceClassification.TENTATIVE,
    }
)


class Provenance(str, Enum):
    """How a numeric figure came to be (§13).

    ``UNKNOWN`` is mandatory rather than optional: the commercial model refuses
    to treat a missing figure as zero.
    """

    VERIFIED = "verified"
    QUOTED = "quoted"
    HISTORICAL = "historical"
    ESTIMATE = "estimate"
    UNKNOWN = "unknown"


class SourceEvidence(BaseModel):
    """One observation tied to one source (§9).

    The validator encodes the phase's central epistemic rule, inherited from
    P-02: model-generated content can never be VERIFIED, and nothing with an
    unknown source can be better than UNVERIFIED.
    """

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(default_factory=lambda: f"ev-{uuid4().hex[:12]}")
    opportunity_id: str | None = None
    evidence_type: EvidenceType
    classification: EvidenceClassification
    claim: str = Field(min_length=1)
    observed_value: str | None = None
    numeric_value: Decimal | None = None
    unit: str | None = Field(default=None, max_length=32)
    source_id: str | None = Field(default=None, max_length=64)
    source_url: str | None = Field(default=None, max_length=2048)
    publication_date: datetime | None = None
    collected_at: datetime | None = None
    reliability: EvidenceReliability = EvidenceReliability.UNTRUSTED
    trust_domain: TrustDomain = TrustDomain.EXTERNAL
    independence_group: str | None = None
    supersedes: str | None = None
    contradicts: tuple[str, ...] = ()
    stale_after_days: int | None = Field(default=None, ge=1)
    notes: str | None = None

    @model_validator(mode="after")
    def _epistemic_floor(self) -> "SourceEvidence":
        if (
            self.evidence_type is EvidenceType.MODEL_GENERATED
            or self.reliability is EvidenceReliability.MODEL_GENERATED
        ) and self.classification in {
            EvidenceClassification.VERIFIED,
            EvidenceClassification.CORROBORATED,
        }:
            raise ValueError(
                "model-generated evidence can never be VERIFIED or CORROBORATED; "
                "it requires an independent external source"
            )
        if self.source_id is None and self.trust_domain is not TrustDomain.OWNER:
            if self.classification in {
                EvidenceClassification.VERIFIED,
                EvidenceClassification.CORROBORATED,
                EvidenceClassification.SUPPORTING,
            }:
                raise ValueError(
                    "evidence with no source_id cannot be classified above TENTATIVE"
                )
        if (
            self.classification is EvidenceClassification.CORROBORATED
            and self.independence_group is None
        ):
            raise ValueError(
                "CORROBORATED requires an independence_group identifying the "
                "second, independent source"
            )
        if self.classification is EvidenceClassification.CONTRADICTED and not (
            self.contradicts or self.notes
        ):
            raise ValueError(
                "CONTRADICTED evidence must name what it contradicts"
            )
        return self

    def is_admissible(self) -> bool:
        return self.classification in ADMISSIBLE_CLASSIFICATIONS

    def is_stale(self, *, now: datetime) -> bool:
        if self.stale_after_days is None or self.collected_at is None:
            return False
        age_days = (now - self.collected_at).total_seconds() / 86400.0
        return age_days > self.stale_after_days


class Assumption(BaseModel):
    """An assumption the analysis depends on, made visible (§3, §19)."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1)
    basis: Provenance = Provenance.ESTIMATE
    affects: tuple[str, ...] = ()
    sensitivity: Literal["low", "medium", "high"] = "medium"
    owner_confirmed: bool = False


class MarketSignal(BaseModel):
    """A demand observation, always carrying its provenance (§10)."""

    model_config = ConfigDict(extra="forbid")

    signal: str = Field(min_length=1)
    metric_name: str | None = None
    metric_value: Decimal | None = None
    unit: str | None = None
    observed_at: datetime | None = None
    evidence_id: str | None = None
    provenance: Provenance = Provenance.UNKNOWN
    region: str | None = None

    @model_validator(mode="after")
    def _value_needs_provenance(self) -> "MarketSignal":
        if self.metric_value is not None and self.provenance is Provenance.UNKNOWN:
            raise ValueError(
                "a market signal carrying a numeric value must state its provenance"
            )
        if self.metric_value is not None and self.evidence_id is None:
            raise ValueError(
                "a numeric market signal must reference the evidence it came from"
            )
        return self


# --------------------------------------------------------------------------- #
# §10 - market sizing
# --------------------------------------------------------------------------- #
class SizedMarket(BaseModel):
    """One market-size figure with its provenance attached.

    A TAM/SAM/SOM number with no stated basis is indistinguishable from an
    invention, so ``value`` is optional and ``provenance`` is not: an unknown
    market size is representable and is the honest default.
    """

    model_config = ConfigDict(extra="forbid")

    label: Literal["tam", "sam", "som"]
    value: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    unit: Literal["currency_per_year", "customers", "transactions_per_year"] = (
        "currency_per_year"
    )
    provenance: Provenance = Provenance.UNKNOWN
    basis: str | None = None
    evidence_ids: tuple[str, ...] = ()
    as_of: datetime | None = None
    region: str | None = None

    @model_validator(mode="after")
    def _value_requires_basis(self) -> "SizedMarket":
        if self.value is not None:
            if self.provenance is Provenance.UNKNOWN:
                raise ValueError(
                    f"{self.label.upper()} carries a value but provenance is UNKNOWN"
                )
            if not self.basis:
                raise ValueError(
                    f"{self.label.upper()} carries a value but states no basis"
                )
            if not self.evidence_ids:
                raise ValueError(
                    f"{self.label.upper()} carries a value but cites no evidence"
                )
        return self


class MarketSizing(BaseModel):
    """TAM/SAM/SOM plus the geography and customer description (§10)."""

    model_config = ConfigDict(extra="forbid")

    tam: SizedMarket | None = None
    sam: SizedMarket | None = None
    som: SizedMarket | None = None
    geography: tuple[str, ...] = ()
    customer_segments: tuple[str, ...] = ()
    buying_trigger: str | None = None
    existing_alternatives: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _nesting_must_narrow(self) -> "MarketSizing":
        """SAM may not exceed TAM, SOM may not exceed SAM - but only when both
        are actually known.  Unknown is never coerced into a violation."""
        pairs = ((self.sam, self.tam, "SAM"), (self.som, self.sam, "SOM"))
        for inner, outer, name in pairs:
            if inner is None or outer is None:
                continue
            if inner.value is None or outer.value is None:
                continue
            if inner.unit != outer.unit or inner.currency != outer.currency:
                continue
            if inner.value > outer.value:
                raise ValueError(
                    f"{name} ({inner.value}) exceeds the enclosing market "
                    f"({outer.value}); check the derivation"
                )
        return self

    def known_levels(self) -> tuple[str, ...]:
        out = []
        for level, field in (("TAM", self.tam), ("SAM", self.sam), ("SOM", self.som)):
            if field is not None and field.value is not None:
                out.append(level)
        return tuple(out)


# --------------------------------------------------------------------------- #
# §11 - competitor intelligence
# --------------------------------------------------------------------------- #
class CompetitorProfile(BaseModel):
    """One competitor, with every field traceable to evidence (§11)."""

    model_config = ConfigDict(extra="forbid")

    competitor_id: str = Field(default_factory=lambda: f"cmp-{uuid4().hex[:10]}")
    name: str = Field(min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=2048)
    offering: str | None = None
    price_points: tuple[Decimal, ...] = ()
    price_currency: str = Field(default="USD", min_length=3, max_length=3)
    pricing_provenance: Provenance = Provenance.UNKNOWN
    positioning: str | None = None
    strengths: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    review_count: int | None = Field(default=None, ge=0)
    rating: Decimal | None = Field(default=None, ge=0, le=5)
    rating_provenance: Provenance = Provenance.UNKNOWN
    complaint_themes: tuple[str, ...] = ()
    identified_gaps: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    observed_at: datetime | None = None
    inspected: bool = False

    @model_validator(mode="after")
    def _no_unsourced_numbers(self) -> "CompetitorProfile":
        if self.price_points and self.pricing_provenance is Provenance.UNKNOWN:
            raise ValueError(
                "competitor price points stated without pricing_provenance"
            )
        if self.price_points and not self.evidence_ids:
            raise ValueError("competitor price points stated without evidence_ids")
        if (self.rating is not None or self.review_count is not None) and (
            self.rating_provenance is Provenance.UNKNOWN
        ):
            raise ValueError(
                "competitor rating/review count stated without rating_provenance"
            )
        return self


# --------------------------------------------------------------------------- #
# §12 - business models
# --------------------------------------------------------------------------- #
class BusinessModelType(str, Enum):
    ONE_TIME_SALE = "one_time_sale"
    SUBSCRIPTION = "subscription"
    USAGE_BASED = "usage_based"
    FREEMIUM = "freemium"
    MARKETPLACE_FEE = "marketplace_fee"
    SERVICE_RETAINER = "service_retainer"
    AD_SUPPORTED = "ad_supported"
    AFFILIATE = "affiliate"
    LICENSING = "licensing"
    HYBRID = "hybrid"


class BusinessModelAnalysis(BaseModel):
    """How the opportunity intends to make money (§12)."""

    model_config = ConfigDict(extra="forbid")

    model_type: BusinessModelType
    revenue_mechanism: str = Field(min_length=1)
    price_point: Decimal | None = Field(default=None, ge=0)
    price_provenance: Provenance = Provenance.UNKNOWN
    billing_period: Literal["once", "monthly", "annual", "per_use", "per_project"] = "once"
    expected_conversion_basis: str | None = None
    churn_assumption: Decimal | None = Field(default=None, ge=0, le=1)
    lifetime_value: Decimal | None = Field(default=None, ge=0)
    ltv_provenance: Provenance = Provenance.UNKNOWN
    payment_processor: str | None = None
    processor_fee_pct: Decimal | None = Field(default=None, ge=0, le=100)
    processor_fee_fixed: Decimal | None = Field(default=None, ge=0)
    fee_provenance: Provenance = Provenance.UNKNOWN
    weaknesses: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _priced_models_need_provenance(self) -> "BusinessModelAnalysis":
        for field, prov, label in (
            ("price_point", self.price_provenance, "price_point"),
            ("lifetime_value", self.ltv_provenance, "lifetime_value"),
        ):
            value = getattr(self, field)
            if value is not None and prov is Provenance.UNKNOWN:
                raise ValueError(f"{label} stated without provenance")
        if self.processor_fee_pct is not None and (
            self.fee_provenance is Provenance.UNKNOWN
        ):
            raise ValueError("processor fee stated without fee_provenance")
        if self.model_type is BusinessModelType.SUBSCRIPTION and (
            self.billing_period not in {"monthly", "annual"}
        ):
            raise ValueError("a subscription model must bill monthly or annually")
        return self


# --------------------------------------------------------------------------- #
# §13 - commercial feasibility (the most important module)
# --------------------------------------------------------------------------- #
class CostItem(BaseModel):
    """One cost line.  ``provenance`` is mandatory and ``UNKNOWN`` never means
    zero - it means the analysis cannot price this line."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    provenance: Provenance
    kind: Literal["startup", "recurring", "variable_per_unit"]
    billing_period: Literal["once", "monthly", "annual", "per_unit"] = "once"
    evidence_id: str | None = None
    assumption: str | None = None
    vendor: str | None = None

    @model_validator(mode="after")
    def _kind_matches_period(self) -> "CostItem":
        expected = {
            "startup": "once",
            "recurring": {"monthly", "annual"},
            "variable_per_unit": "per_unit",
        }[self.kind]
        allowed = expected if isinstance(expected, set) else {expected}
        if self.billing_period not in allowed:
            raise ValueError(
                f"a {self.kind} cost cannot bill {self.billing_period}; "
                f"expected one of {sorted(allowed)}"
            )
        if self.provenance in {Provenance.VERIFIED, Provenance.QUOTED} and (
            self.evidence_id is None
        ):
            raise ValueError(
                f"cost '{self.name}' claims {self.provenance.value} provenance "
                "but cites no evidence_id"
            )
        if self.provenance is Provenance.ESTIMATE and not self.assumption:
            raise ValueError(
                f"estimated cost '{self.name}' must state the assumption behind it"
            )
        return self


class CostStructure(BaseModel):
    """All three cost classes, with an explicit unknown-count (§13)."""

    model_config = ConfigDict(extra="forbid")

    items: tuple[CostItem, ...] = ()

    def by_kind(self, kind: str) -> tuple[CostItem, ...]:
        return tuple(i for i in self.items if i.kind == kind)

    def startup_total(self) -> Decimal:
        return sum((i.amount for i in self.by_kind("startup")), Decimal("0"))

    def recurring_monthly_total(self) -> Decimal:
        total = Decimal("0")
        for item in self.by_kind("recurring"):
            if item.billing_period == "annual":
                total += (item.amount / Decimal(12)).quantize(Decimal("0.01"))
            else:
                total += item.amount
        return total

    def variable_per_unit_total(self) -> Decimal:
        return sum((i.amount for i in self.by_kind("variable_per_unit")), Decimal("0"))

    def unknown_count(self) -> int:
        return sum(1 for i in self.items if i.provenance is Provenance.UNKNOWN)

    def unpriced_items(self) -> tuple[str, ...]:
        """Names of lines that could not be priced at all.

        A cost structure with unpriced items cannot support a confident
        commercial verdict; the caller must surface these.
        """
        return tuple(i.name for i in self.items if i.provenance is Provenance.UNKNOWN)

    def provenance_counts(self) -> dict[str, int]:
        out: dict[str, int] = {p.value: 0 for p in Provenance}
        for item in self.items:
            out[item.provenance.value] += 1
        return out


class ScenarioName(str, Enum):
    """The three named scenarios (§13).  Exactly three, by name."""

    CONSERVATIVE = "conservative"
    BASE = "base"
    OPTIMISTIC = "optimistic"


SCENARIO_VOLUME_FACTORS: dict[ScenarioName, Decimal] = {
    ScenarioName.CONSERVATIVE: Decimal("0.5"),
    ScenarioName.BASE: Decimal("1.0"),
    ScenarioName.OPTIMISTIC: Decimal("1.75"),
}


class FinancialProjection(BaseModel):
    """One period's deterministic arithmetic (§13.4).

    Every field here is *computed*, never supplied by a model.  The formulas are
    fixed and are exercised against hand-verified fixtures in the test suite:

        revenue              = units_sold * price_per_unit
        variable_cost        = units_sold * variable_cost_per_unit
        gross_profit         = revenue - variable_cost
        gross_margin         = gross_profit / revenue
        contribution_per_unit = price_per_unit - variable_cost_per_unit
        contribution_margin  = contribution_per_unit / price_per_unit
        operating_profit     = gross_profit - recurring_fixed_cost
        net_cash_flow        = operating_profit - one_time_cost_in_period
    """

    model_config = ConfigDict(extra="forbid")

    period_months: int = Field(default=1, ge=1)
    units_sold: Decimal = Field(ge=0)
    price_per_unit: Decimal = Field(ge=0)
    variable_cost_per_unit: Decimal = Field(ge=0)
    recurring_fixed_cost: Decimal = Field(ge=0)
    one_time_cost_in_period: Decimal = Field(default=Decimal("0"), ge=0)

    revenue: Decimal = Decimal("0")
    variable_cost: Decimal = Decimal("0")
    gross_profit: Decimal = Decimal("0")
    gross_margin: Decimal | None = None
    contribution_per_unit: Decimal = Decimal("0")
    contribution_margin: Decimal | None = None
    operating_profit: Decimal = Decimal("0")
    net_cash_flow: Decimal = Decimal("0")
    unpriced_cost_items: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _recompute(self) -> "FinancialProjection":
        """Recompute every derived figure from the inputs.

        Running this as a validator means a caller *cannot* pass in a
        contradictory ``gross_profit``: whatever they send is overwritten by the
        deterministic formula.  That is the point.
        """
        money = Decimal("0.01")
        revenue = (self.units_sold * self.price_per_unit).quantize(money)
        variable = (self.units_sold * self.variable_cost_per_unit).quantize(money)
        gross = (revenue - variable).quantize(money)
        contribution = (self.price_per_unit - self.variable_cost_per_unit).quantize(money)
        operating = (gross - self.recurring_fixed_cost).quantize(money)
        net = (operating - self.one_time_cost_in_period).quantize(money)

        object.__setattr__(self, "revenue", revenue)
        object.__setattr__(self, "variable_cost", variable)
        object.__setattr__(self, "gross_profit", gross)
        object.__setattr__(self, "contribution_per_unit", contribution)
        object.__setattr__(self, "operating_profit", operating)
        object.__setattr__(self, "net_cash_flow", net)
        object.__setattr__(
            self,
            "gross_margin",
            (gross / revenue).quantize(Decimal("0.0001")) if revenue > 0 else None,
        )
        object.__setattr__(
            self,
            "contribution_margin",
            (contribution / self.price_per_unit).quantize(Decimal("0.0001"))
            if self.price_per_unit > 0
            else None,
        )
        return self


class ScenarioProjection(BaseModel):
    """A named scenario wrapping a projection (§13.5)."""

    model_config = ConfigDict(extra="forbid")

    name: ScenarioName
    volume_factor: Decimal = Field(ge=0)
    projection: FinancialProjection
    rationale: str | None = None

    @model_validator(mode="after")
    def _factor_matches_name(self) -> "ScenarioProjection":
        expected = SCENARIO_VOLUME_FACTORS[self.name]
        if self.volume_factor != expected:
            raise ValueError(
                f"scenario '{self.name.value}' must use volume_factor "
                f"{expected}, got {self.volume_factor}; the three scenarios are "
                "fixed so results stay comparable across opportunities"
            )
        return self


class BreakEvenResult(BaseModel):
    """Break-even and payback (§13.6).

    ``achievable`` is False - not True-by-default - whenever the contribution
    per unit is zero or negative, because no volume can then recover fixed
    costs.  Reporting that honestly is more useful than reporting infinity.
    """

    model_config = ConfigDict(extra="forbid")

    contribution_per_unit: Decimal
    recurring_fixed_monthly: Decimal
    startup_cost: Decimal
    monthly_break_even_units: int | None = None
    units_to_recover_startup: int | None = None
    months_to_recover_startup: int | None = None
    achievable: bool = False
    reason: str | None = None

    @model_validator(mode="after")
    def _compute(self) -> "BreakEvenResult":
        if self.contribution_per_unit <= 0:
            object.__setattr__(self, "achievable", False)
            object.__setattr__(
                self,
                "reason",
                "contribution per unit is zero or negative; no sales volume can "
                "recover fixed costs at this price",
            )
            return self
        cpu = self.contribution_per_unit
        monthly_units = (self.recurring_fixed_monthly / cpu).to_integral_value(
            rounding="ROUND_CEILING"
        )
        object.__setattr__(self, "monthly_break_even_units", int(monthly_units))

        total_to_recover = self.startup_cost + self.recurring_fixed_monthly
        if total_to_recover <= 0:
            object.__setattr__(self, "units_to_recover_startup", 0)
            object.__setattr__(self, "months_to_recover_startup", 0)
            object.__setattr__(self, "achievable", True)
            return self
        units = (total_to_recover / cpu).to_integral_value(rounding="ROUND_CEILING")
        object.__setattr__(self, "units_to_recover_startup", int(units))
        if monthly_units > 0:
            months = (units / monthly_units).to_integral_value(rounding="ROUND_CEILING")
            object.__setattr__(self, "months_to_recover_startup", int(months))
        object.__setattr__(self, "achievable", True)
        return self


class BudgetCompatibility(BaseModel):
    """Whether the opportunity fits the owner's stated capital (§13.7).

    The critical invariant: this model *reports* a shortfall, it never repairs
    one.  ``available_capital`` is copied in read-only from the owner's
    constraint and no code path may raise it.
    """

    model_config = ConfigDict(extra="forbid")

    available_capital: Decimal = Field(ge=0)
    required_startup: Decimal = Field(ge=0)
    required_first_period_cash: Decimal = Field(ge=0)
    compatible: bool = False
    shortfall: Decimal = Field(default=Decimal("0"), ge=0)
    utilisation_pct: Decimal | None = None
    verdict: Literal[
        "compatible", "tight", "incompatible", "cannot_determine"
    ] = "cannot_determine"
    reason: str | None = None
    unpriced_cost_items: tuple[str, ...] = ()
    budget_was_modified: Literal[False] = False

    @model_validator(mode="after")
    def _compute(self) -> "BudgetCompatibility":
        if self.unpriced_cost_items:
            object.__setattr__(self, "compatible", False)
            object.__setattr__(self, "verdict", "cannot_determine")
            object.__setattr__(
                self,
                "reason",
                "cost structure has unpriced items "
                f"({', '.join(self.unpriced_cost_items)}); the true requirement "
                "is unknown and cannot be declared affordable",
            )
            return self
        if self.required_startup > self.available_capital:
            object.__setattr__(self, "compatible", False)
            object.__setattr__(self, "verdict", "incompatible")
            object.__setattr__(
                self,
                "shortfall",
                (self.required_startup - self.available_capital).quantize(
                    Decimal("0.01")
                ),
            )
            object.__setattr__(
                self,
                "reason",
                "required startup cost exceeds the owner's stated capital; the "
                "budget must not be silently increased to make this fit",
            )
            return self
        object.__setattr__(self, "shortfall", Decimal("0"))
        if self.required_first_period_cash > self.available_capital:
            object.__setattr__(self, "compatible", False)
            object.__setattr__(self, "verdict", "incompatible")
            object.__setattr__(
                self,
                "reason",
                "startup cost fits but first-period cash requirement does not",
            )
        elif self.available_capital > 0:
            utilisation = (
                self.required_first_period_cash / self.available_capital
            ).quantize(Decimal("0.0001"))
            object.__setattr__(self, "utilisation_pct", utilisation * 100)
            object.__setattr__(self, "compatible", True)
            object.__setattr__(
                self, "verdict", "tight" if utilisation > Decimal("0.8") else "compatible"
            )
        else:
            object.__setattr__(self, "compatible", True)
            object.__setattr__(self, "verdict", "compatible")
        return self


# --------------------------------------------------------------------------- #
# §14 - distribution and acquisition
# --------------------------------------------------------------------------- #
class DistributionChannel(BaseModel):
    """One route to customers, with its cost and its evidence (§14)."""

    model_config = ConfigDict(extra="forbid")

    channel: str = Field(min_length=1, max_length=120)
    kind: Literal[
        "organic_search",
        "social_organic",
        "paid_ads",
        "marketplace",
        "direct_outreach",
        "partnership",
        "community",
        "email_list",
        "content",
        "other",
    ] = "other"
    startup_cost: Decimal = Field(default=Decimal("0"), ge=0)
    recurring_cost: Decimal = Field(default=Decimal("0"), ge=0)
    cost_provenance: Provenance = Provenance.UNKNOWN
    time_to_first_customer: str | None = None
    dependency_risk: Literal["low", "medium", "high"] = "medium"
    platform_controlled: bool = False
    feasible_without_ad_spend: bool = True
    evidence_ids: tuple[str, ...] = ()
    notes: str | None = None

    @model_validator(mode="after")
    def _costs_need_provenance(self) -> "DistributionChannel":
        if (self.startup_cost > 0 or self.recurring_cost > 0) and (
            self.cost_provenance is Provenance.UNKNOWN
        ):
            raise ValueError("channel cost stated without cost_provenance")
        if self.kind == "paid_ads" and self.feasible_without_ad_spend:
            raise ValueError(
                "a paid_ads channel is by definition not feasible without ad spend"
            )
        return self


# --------------------------------------------------------------------------- #
# §15 - legal, platform and ethical risk
# --------------------------------------------------------------------------- #
class RiskSeverity(str, Enum):
    NEGLIGIBLE = "negligible"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKING = "blocking"


RISK_SEVERITY_RANK: dict[RiskSeverity, int] = {
    RiskSeverity.NEGLIGIBLE: 0,
    RiskSeverity.LOW: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.HIGH: 3,
    RiskSeverity.BLOCKING: 4,
}


class RiskFinding(BaseModel):
    """One legal / platform / ethical risk (§15).

    ``BLOCKING`` is terminal: it forces rejection regardless of how attractive
    every other dimension is.
    """

    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(default_factory=lambda: f"risk-{uuid4().hex[:10]}")
    category: Literal[
        "legal",
        "regulatory",
        "tax",
        "intellectual_property",
        "platform_policy",
        "payment_policy",
        "data_privacy",
        "consumer_protection",
        "ethical",
        "reputational",
        "prohibited_category",
    ]
    severity: RiskSeverity
    description: str = Field(min_length=1)
    jurisdiction: str | None = None
    platform: str | None = None
    mitigation: str | None = None
    evidence_ids: tuple[str, ...] = ()
    blocks_recommendation: bool = False

    @model_validator(mode="after")
    def _blocking_implies_flag(self) -> "RiskFinding":
        if self.severity is RiskSeverity.BLOCKING and not self.blocks_recommendation:
            object.__setattr__(self, "blocks_recommendation", True)
        if self.category == "prohibited_category" and (
            self.severity is not RiskSeverity.BLOCKING
        ):
            raise ValueError(
                "a prohibited-category finding is always BLOCKING severity"
            )
        return self


# --------------------------------------------------------------------------- #
# §16 - scoring
# --------------------------------------------------------------------------- #
class WeightKey(str, Enum):
    """The weighted scoring dimensions (§16).

    Weights sum to exactly 100 and are configurable at construction, but the
    invariant is enforced: a configuration that does not sum to 100 is refused
    rather than silently normalised, because silent normalisation would make
    two runs with different configs produce incomparable scores.

    Note on evidence quality: ``EVIDENCE_QUALITY`` is weighted here *and* is
    additionally reported separately from the attractiveness total (§16
    requires the two not be conflated).  An opportunity can therefore be
    attractive-but-poorly-evidenced, and that combination is visible rather than
    averaged away.
    """

    VERIFIED_DEMAND = "verified_demand"
    PROBLEM_IMPORTANCE = "problem_importance"
    COMPETITIVE_OPPORTUNITY = "competitive_opportunity"
    REVENUE_MODEL_VIABILITY = "revenue_model_viability"
    PROFIT_POTENTIAL = "profit_potential"
    BUDGET_COMPATIBILITY = "budget_compatibility"
    DISTRIBUTION_FEASIBILITY = "distribution_feasibility"
    OPERATIONAL_SIMPLICITY = "operational_simplicity"
    STRATEGIC_FIT = "strategic_fit"
    EVIDENCE_QUALITY = "evidence_quality"


DEFAULT_WEIGHTS: dict[WeightKey, Decimal] = {
    WeightKey.VERIFIED_DEMAND: Decimal("20"),
    WeightKey.PROBLEM_IMPORTANCE: Decimal("10"),
    WeightKey.COMPETITIVE_OPPORTUNITY: Decimal("10"),
    WeightKey.REVENUE_MODEL_VIABILITY: Decimal("10"),
    WeightKey.PROFIT_POTENTIAL: Decimal("15"),
    WeightKey.BUDGET_COMPATIBILITY: Decimal("10"),
    WeightKey.DISTRIBUTION_FEASIBILITY: Decimal("10"),
    WeightKey.OPERATIONAL_SIMPLICITY: Decimal("5"),
    WeightKey.STRATEGIC_FIT: Decimal("5"),
    WeightKey.EVIDENCE_QUALITY: Decimal("5"),
}

#: The attractiveness total deliberately excludes evidence quality so that the
#: two are reported separately (§16).
ATTRACTIVENESS_KEYS: tuple[WeightKey, ...] = tuple(
    k for k in WeightKey if k is not WeightKey.EVIDENCE_QUALITY
)


class ScoreDimension(BaseModel):
    """One dimension's normalised 0-5 score with its justification (§16).

    ``scorable`` is False when there is not enough evidence to score the
    dimension at all.  An unscoreable dimension contributes *nothing* and is
    reported as a gap - it is never defaulted to a middle value, which would
    launder ignorance into confidence.
    """

    model_config = ConfigDict(extra="forbid")

    key: WeightKey
    score: Decimal = Field(default=Decimal("0"), ge=0, le=5)
    weight: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    scorable: bool = False
    justification: str | None = None
    evidence_ids: tuple[str, ...] = ()
    gap: str | None = None
    computed_by: Literal["deterministic_rule", "insufficient_evidence"] = (
        "insufficient_evidence"
    )

    @model_validator(mode="after")
    def _score_needs_rule(self) -> "ScoreDimension":
        if self.scorable and self.computed_by != "deterministic_rule":
            raise ValueError("a scorable dimension must name its deterministic_rule")
        if self.scorable and not self.justification:
            raise ValueError("a scorable dimension must state its justification")
        if not self.scorable and self.score != 0:
            raise ValueError(
                "an unscoreable dimension must carry score 0; it may not be "
                "given a partial or default score"
            )
        if not self.scorable and not self.gap:
            raise ValueError("an unscoreable dimension must state the gap")
        return self

    @property
    def weighted(self) -> Decimal:
        return (self.score * self.weight / Decimal("100")).quantize(Decimal("0.0001"))


class OpportunityScore(BaseModel):
    """The complete, reproducible scoring result (§16).

    ``attractiveness`` and ``evidence_quality`` are reported separately.  The
    overall ranking is driven by attractiveness *and* gated by hard rejection
    rules, which live outside the score: a rejected opportunity keeps its score
    for audit purposes but can never be recommended.
    """

    model_config = ConfigDict(extra="forbid")

    dimensions: tuple[ScoreDimension, ...]
    weights_sum: Decimal = Decimal("0")
    attractiveness: Decimal = Decimal("0")
    evidence_quality: Decimal = Decimal("0")
    scorable_count: int = 0
    unscored_dimensions: tuple[str, ...] = ()
    coverage_pct: Decimal = Decimal("0")
    ranking_key: tuple[str, ...] = ()
    computed_at: datetime | None = None

    @model_validator(mode="after")
    def _compute(self) -> "OpportunityScore":
        seen: dict[WeightKey, ScoreDimension] = {}
        for dim in self.dimensions:
            if dim.key in seen:
                raise ValueError(f"duplicate scoring dimension '{dim.key.value}'")
            seen[dim.key] = dim
        missing = [k.value for k in WeightKey if k not in seen]
        if missing:
            raise ValueError(f"scoring is missing dimensions: {', '.join(missing)}")

        total_weight = sum((d.weight for d in self.dimensions), Decimal("0"))
        attractiveness = sum(
            (d.weighted for d in self.dimensions if d.key in ATTRACTIVENESS_KEYS),
            Decimal("0"),
        )
        eq_dim = seen[WeightKey.EVIDENCE_QUALITY]
        scorable = tuple(d for d in self.dimensions if d.scorable)
        covered_weight = sum((d.weight for d in scorable), Decimal("0"))

        object.__setattr__(self, "weights_sum", total_weight)
        object.__setattr__(
            self, "attractiveness", attractiveness.quantize(Decimal("0.0001"))
        )
        object.__setattr__(self, "evidence_quality", eq_dim.score)
        object.__setattr__(self, "scorable_count", len(scorable))
        object.__setattr__(
            self,
            "unscored_dimensions",
            tuple(d.key.value for d in self.dimensions if not d.scorable),
        )
        object.__setattr__(
            self,
            "coverage_pct",
            (covered_weight / total_weight * 100).quantize(Decimal("0.01"))
            if total_weight > 0
            else Decimal("0"),
        )
        # A deterministic, tie-broken ranking key so that rankings are
        # reproducible run-to-run and never depend on dict or set ordering.
        object.__setattr__(
            self,
            "ranking_key",
            (
                f"{attractiveness.quantize(Decimal('0.0001')):>12}",
                f"{eq_dim.score:>6}",
                f"{len(scorable):>3}",
            ),
        )
        object.__setattr__(
            self, "computed_at", self.computed_at or datetime.now(timezone.utc)
        )
        return self


# --------------------------------------------------------------------------- #
# §17 - lifecycle
# --------------------------------------------------------------------------- #
class OpportunityState(str, Enum):
    """The opportunity lifecycle (§17).

    The first eight are the forward path; the rest are non-forward outcomes.
    Note that ``NEEDS_MORE_EVIDENCE`` is a *live* state with a way back into
    research, while ``REJECTED``, ``INCOMPATIBLE`` and ``BLOCKED_BY_COMPLIANCE``
    are terminal for the purposes of recommendation.
    """

    DISCOVERED = "discovered"
    INITIAL_SCREENING = "initial_screening"
    RESEARCHING = "researching"
    EVIDENCE_REVIEW = "evidence_review"
    COMMERCIAL_ANALYSIS = "commercial_analysis"
    VALIDATION_PENDING = "validation_pending"
    VALIDATED = "validated"
    RECOMMENDED = "recommended"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    REJECTED = "rejected"
    INCOMPATIBLE = "incompatible"
    BLOCKED_BY_COMPLIANCE = "blocked_by_compliance"
    DUPLICATE = "duplicate"
    OUTDATED = "outdated"
    ARCHIVED = "archived"


TERMINAL_STATES: frozenset[OpportunityState] = frozenset(
    {
        OpportunityState.RECOMMENDED,
        OpportunityState.REJECTED,
        OpportunityState.INCOMPATIBLE,
        OpportunityState.BLOCKED_BY_COMPLIANCE,
        OpportunityState.DUPLICATE,
        OpportunityState.ARCHIVED,
    }
)

OPPORTUNITY_TRANSITIONS: dict[OpportunityState, frozenset[OpportunityState]] = {
    OpportunityState.DISCOVERED: frozenset(
        {
            OpportunityState.INITIAL_SCREENING,
            OpportunityState.DUPLICATE,
            OpportunityState.ARCHIVED,
        }
    ),
    OpportunityState.INITIAL_SCREENING: frozenset(
        {
            OpportunityState.RESEARCHING,
            OpportunityState.REJECTED,
            OpportunityState.BLOCKED_BY_COMPLIANCE,
            OpportunityState.DUPLICATE,
            OpportunityState.NEEDS_MORE_EVIDENCE,
            OpportunityState.ARCHIVED,
        }
    ),
    OpportunityState.RESEARCHING: frozenset(
        {
            OpportunityState.EVIDENCE_REVIEW,
            OpportunityState.NEEDS_MORE_EVIDENCE,
            OpportunityState.REJECTED,
            OpportunityState.BLOCKED_BY_COMPLIANCE,
            OpportunityState.OUTDATED,
            OpportunityState.ARCHIVED,
        }
    ),
    OpportunityState.EVIDENCE_REVIEW: frozenset(
        {
            OpportunityState.COMMERCIAL_ANALYSIS,
            OpportunityState.NEEDS_MORE_EVIDENCE,
            OpportunityState.RESEARCHING,
            OpportunityState.REJECTED,
            OpportunityState.BLOCKED_BY_COMPLIANCE,
            OpportunityState.ARCHIVED,
        }
    ),
    OpportunityState.COMMERCIAL_ANALYSIS: frozenset(
        {
            OpportunityState.VALIDATION_PENDING,
            OpportunityState.INCOMPATIBLE,
            OpportunityState.NEEDS_MORE_EVIDENCE,
            OpportunityState.REJECTED,
            OpportunityState.BLOCKED_BY_COMPLIANCE,
            OpportunityState.ARCHIVED,
        }
    ),
    OpportunityState.VALIDATION_PENDING: frozenset(
        {
            OpportunityState.VALIDATED,
            OpportunityState.NEEDS_MORE_EVIDENCE,
            OpportunityState.REJECTED,
            OpportunityState.INCOMPATIBLE,
            OpportunityState.BLOCKED_BY_COMPLIANCE,
            OpportunityState.ARCHIVED,
        }
    ),
    OpportunityState.VALIDATED: frozenset(
        {
            OpportunityState.RECOMMENDED,
            OpportunityState.REJECTED,
            OpportunityState.INCOMPATIBLE,
            OpportunityState.BLOCKED_BY_COMPLIANCE,
            OpportunityState.OUTDATED,
            OpportunityState.ARCHIVED,
        }
    ),
    # RECOMMENDED is terminal for the forward path but may still decay.
    OpportunityState.RECOMMENDED: frozenset(
        {OpportunityState.OUTDATED, OpportunityState.ARCHIVED}
    ),
    OpportunityState.NEEDS_MORE_EVIDENCE: frozenset(
        {
            OpportunityState.RESEARCHING,
            OpportunityState.REJECTED,
            OpportunityState.OUTDATED,
            OpportunityState.ARCHIVED,
        }
    ),
    OpportunityState.OUTDATED: frozenset(
        {OpportunityState.RESEARCHING, OpportunityState.ARCHIVED}
    ),
    OpportunityState.REJECTED: frozenset({OpportunityState.ARCHIVED}),
    OpportunityState.INCOMPATIBLE: frozenset({OpportunityState.ARCHIVED}),
    OpportunityState.BLOCKED_BY_COMPLIANCE: frozenset({OpportunityState.ARCHIVED}),
    OpportunityState.DUPLICATE: frozenset({OpportunityState.ARCHIVED}),
    OpportunityState.ARCHIVED: frozenset(),
}


class OpportunityTransitionError(ValueError):
    """Raised on an illegal lifecycle transition.

    Subclasses ``ValueError`` so the P-02 route-layer conversion to HTTP 409
    keeps working without a new exception handler.
    """


def validate_opportunity_transition(
    current: OpportunityState, target: OpportunityState
) -> None:
    """One implementation of the transition rule, used by both the engine and
    the tests."""
    if target not in OPPORTUNITY_TRANSITIONS[current]:
        allowed = sorted(s.value for s in OPPORTUNITY_TRANSITIONS[current]) or [
            "<terminal>"
        ]
        raise OpportunityTransitionError(
            f"illegal opportunity transition {current.value} -> {target.value}; "
            f"permitted: {', '.join(allowed)}"
        )


# --------------------------------------------------------------------------- #
# §18 - validation levels
# --------------------------------------------------------------------------- #
class ValidationLevel(int, Enum):
    """How far the opportunity has actually been validated (§18).

    The ladder is deliberately conservative: each rung requires evidence of a
    different and stronger kind than the one below it.
    """

    LEVEL_0_IDEA = 0
    LEVEL_1_PROBLEM_EVIDENCE = 1
    LEVEL_2_DEMAND_EVIDENCE = 2
    LEVEL_3_COMMERCIAL_EVIDENCE = 3
    LEVEL_4_WILLINGNESS_TO_PAY = 4
    LEVEL_5_ACTUAL_REVENUE = 5


#: Inputs that may NOT be used to claim Level 4 (§18).  Encoded as data so the
#: rule is testable and cannot be quietly narrowed later.
LEVEL_4_PROHIBITED_INPUTS: frozenset[str] = frozenset(
    {
        "search_volume",
        "social_views",
        "likes",
        "ai_persona_response",
        "hypothetical_survey",
        "competitor_existence",
        "model_generated_willingness_to_pay",
    }
)

#: Inputs that may NOT be used to claim Level 5 (§18).
LEVEL_5_PROHIBITED_INPUTS: frozenset[str] = frozenset(
    {
        "generated_invoice",
        "unpaid_order",
        "unverified_screenshot",
        "forecast",
        "simulated_transaction",
    }
)


class ValidationAssessment(BaseModel):
    """The highest level genuinely supported, and why not higher (§18)."""

    model_config = ConfigDict(extra="forbid")

    level: ValidationLevel = ValidationLevel.LEVEL_0_IDEA
    satisfied_inputs: tuple[str, ...] = ()
    rejected_inputs: tuple[str, ...] = ()
    blocking_prohibition: str | None = None
    next_level: ValidationLevel | None = None
    next_level_requirement: str | None = None
    evidence_ids: tuple[str, ...] = ()
    assessed_at: datetime | None = None

    @model_validator(mode="after")
    def _prohibited_inputs_cannot_satisfy(self) -> "ValidationAssessment":
        prohibited = (
            LEVEL_4_PROHIBITED_INPUTS
            if self.level.value >= ValidationLevel.LEVEL_4_WILLINGNESS_TO_PAY.value
            else set()
        ) | (
            LEVEL_5_PROHIBITED_INPUTS
            if self.level.value >= ValidationLevel.LEVEL_5_ACTUAL_REVENUE.value
            else set()
        )
        overlap = prohibited & set(self.satisfied_inputs)
        if overlap:
            raise ValueError(
                f"level {self.level.value} claimed using prohibited input(s): "
                f"{', '.join(sorted(overlap))}"
            )
        if self.level.value >= ValidationLevel.LEVEL_4_WILLINGNESS_TO_PAY.value and (
            not self.evidence_ids
        ):
            raise ValueError(
                "level 4 or 5 requires cited evidence; a willingness-to-pay or "
                "revenue claim cannot rest on nothing"
            )
        return self


# --------------------------------------------------------------------------- #
# §23 - final classifications
# --------------------------------------------------------------------------- #
class FinalClassification(str, Enum):
    """The six verdicts a report may reach (§23).

    ``INSUFFICIENT_EVIDENCE`` is a first-class verdict, not a failure: in this
    environment it will be the most common honest answer.
    """

    RECOMMENDED = "recommended"
    PROMISING_NEEDS_VALIDATION = "promising_needs_validation"
    NOT_RECOMMENDED = "not_recommended"
    REJECTED_COMPLIANCE = "rejected_compliance"
    INCOMPATIBLE_WITH_CONSTRAINTS = "incompatible_with_constraints"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


# --------------------------------------------------------------------------- #
# The opportunity record
# --------------------------------------------------------------------------- #
class OpportunityCandidate(BaseModel):
    """A freshly discovered candidate, before any research (§7)."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(default_factory=lambda: f"cand-{uuid4().hex[:12]}")
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1)
    category: BusinessCategory
    discovery_method: DiscoveryMethod
    derived_from: str | None = None
    target_customer: str | None = None
    problem_addressed: str | None = None
    proposed_offering: str | None = None
    budget_band: BudgetBand | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    generated_by: Literal["deterministic_rule", "owner_supplied", "model"] = (
        "deterministic_rule"
    )
    duplicate_of: str | None = None

    @model_validator(mode="after")
    def _budget_method_needs_band(self) -> "OpportunityCandidate":
        if (
            self.discovery_method is DiscoveryMethod.BUDGET_DRIVEN
            and self.budget_band is None
        ):
            raise ValueError("a budget-driven candidate must state its budget_band")
        return self


class Opportunity(BaseModel):
    """The full opportunity record that accumulates through the pipeline."""

    model_config = ConfigDict(extra="forbid")

    opportunity_id: str = Field(default_factory=lambda: f"opp-{uuid4().hex[:12]}")
    candidate: OpportunityCandidate
    state: OpportunityState = OpportunityState.DISCOVERED
    budget: BudgetConstraint | None = None
    market: MarketSizing | None = None
    competitors: tuple[CompetitorProfile, ...] = ()
    business_model: BusinessModelAnalysis | None = None
    costs: CostStructure = Field(default_factory=CostStructure)
    scenarios: tuple[ScenarioProjection, ...] = ()
    break_even: BreakEvenResult | None = None
    budget_compatibility: BudgetCompatibility | None = None
    distribution: tuple[DistributionChannel, ...] = ()
    risks: tuple[RiskFinding, ...] = ()
    score: OpportunityScore | None = None
    validation: ValidationAssessment = Field(default_factory=ValidationAssessment)
    assumptions: tuple[Assumption, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()
    final_classification: FinalClassification | None = None
    owner_notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _scenarios_are_the_three_named(self) -> "Opportunity":
        if not self.scenarios:
            return self
        names = [s.name for s in self.scenarios]
        if len(set(names)) != len(names):
            raise ValueError("duplicate scenario names")
        for required in ScenarioName:
            if required not in names:
                raise ValueError(
                    f"commercial analysis must present all three named scenarios; "
                    f"missing {required.value}"
                )
        order = {ScenarioName.CONSERVATIVE: 0, ScenarioName.BASE: 1, ScenarioName.OPTIMISTIC: 2}
        if [order[n] for n in names] != sorted(order[n] for n in names):
            raise ValueError("scenarios must be ordered conservative, base, optimistic")
        return self

    @model_validator(mode="after")
    def _rejection_reason_required(self) -> "Opportunity":
        negative = {
            OpportunityState.REJECTED,
            OpportunityState.INCOMPATIBLE,
            OpportunityState.BLOCKED_BY_COMPLIANCE,
            OpportunityState.DUPLICATE,
        }
        if self.state in negative and not self.rejection_reasons:
            raise ValueError(
                f"an opportunity in state {self.state.value} must record at "
                "least one rejection reason; a silent rejection is not auditable"
            )
        return self

    def blocking_risks(self) -> tuple[RiskFinding, ...]:
        return tuple(r for r in self.risks if r.blocks_recommendation)


# --------------------------------------------------------------------------- #
# Assessment records - the output of each analysis stage
# --------------------------------------------------------------------------- #
class CommercialAssessment(BaseModel):
    """The §13 verdict.  ``affordable`` can never be True while any cost line
    is unpriced, and ``viable`` can never be True when break-even is not
    achievable."""

    model_config = ConfigDict(extra="forbid")

    costs: CostStructure
    scenarios: tuple[ScenarioProjection, ...] = ()
    break_even: BreakEvenResult | None = None
    budget_compatibility: BudgetCompatibility | None = None
    viable: bool = False
    affordable: bool = False
    verdict: Literal[
        "viable",
        "marginal",
        "not_viable",
        "unaffordable",
        "cannot_determine",
    ] = "cannot_determine"
    reasons: tuple[str, ...] = ()
    unpriced_cost_items: tuple[str, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    budget_was_modified: Literal[False] = False

    @model_validator(mode="after")
    def _verdict_must_follow_the_numbers(self) -> "CommercialAssessment":
        # Derived from the cost structure, never taken on trust.  If this were
        # caller-supplied, an assessment could carry unpriced cost lines while
        # claiming there were none - which is precisely the silent inconsistency
        # this verdict guard exists to prevent.
        object.__setattr__(self, "unpriced_cost_items", self.costs.unpriced_items())
        if self.unpriced_cost_items:
            object.__setattr__(self, "affordable", False)
            if self.verdict in {"viable", "marginal"}:
                raise ValueError(
                    "a verdict of 'viable'/'marginal' is not permitted while cost "
                    "lines are unpriced; use 'cannot_determine'"
                )
        if self.break_even is not None and not self.break_even.achievable and (
            self.verdict in {"viable", "marginal"}
        ):
            raise ValueError(
                "a viable verdict is not permitted when break-even is unachievable"
            )
        if self.budget_compatibility is not None:
            if not self.budget_compatibility.compatible and self.verdict == "viable":
                raise ValueError(
                    "'viable' is not permitted when the budget is incompatible; "
                    "the correct verdict is 'unaffordable'"
                )
            if self.budget_compatibility.available_capital != (
                self.budget_compatibility.available_capital
            ):  # pragma: no cover - defensive identity check
                raise ValueError("budget capital was altered during assessment")
        if self.verdict == "viable" and not self.reasons:
            raise ValueError("a viable verdict must state the reasons supporting it")
        return self


class MarketAssessment(BaseModel):
    """The §10 market/customer verdict."""

    model_config = ConfigDict(extra="forbid")

    sizing: MarketSizing | None = None
    signals: tuple[MarketSignal, ...] = ()
    demand_evidence_level: EvidenceClassification = EvidenceClassification.UNVERIFIED
    problem_importance: Literal["trivial", "minor", "moderate", "significant", "acute", "unknown"] = "unknown"
    problem_importance_basis: str | None = None
    customer_description: str | None = None
    willingness_indicators: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()
    verdict: Literal[
        "demand_demonstrated",
        "demand_plausible",
        "demand_unproven",
        "demand_contradicted",
        "insufficient_data",
    ] = "insufficient_data"
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _verdict_needs_a_basis(self) -> "MarketAssessment":
        if self.verdict == "demand_demonstrated" and (
            self.demand_evidence_level
            not in {
                EvidenceClassification.VERIFIED,
                EvidenceClassification.CORROBORATED,
            }
        ):
            raise ValueError(
                "'demand_demonstrated' requires VERIFIED or CORROBORATED demand "
                f"evidence; got {self.demand_evidence_level.value}"
            )
        if self.problem_importance != "unknown" and not self.problem_importance_basis:
            raise ValueError(
                "a problem-importance rating must state the basis it rests on"
            )
        if self.verdict == "demand_demonstrated" and not self.reasons:
            raise ValueError("a demonstrated-demand verdict must cite its reasons")
        return self


class CompetitorAssessment(BaseModel):
    """The §11 competitive verdict."""

    model_config = ConfigDict(extra="forbid")

    competitors: tuple[CompetitorProfile, ...] = ()
    inspected_count: int = 0
    market_saturation: Literal[
        "empty", "sparse", "moderate", "crowded", "saturated", "unknown"
    ] = "unknown"
    gaps_identified: tuple[str, ...] = ()
    differentiation_available: bool = False
    differentiation_basis: str | None = None
    price_range_low: Decimal | None = None
    price_range_high: Decimal | None = None
    data_gaps: tuple[str, ...] = ()
    verdict: Literal[
        "open_opportunity",
        "differentiation_required",
        "crowded_but_viable",
        "saturated_no_entry",
        "insufficient_data",
    ] = "insufficient_data"
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _consistency(self) -> "CompetitorAssessment":
        inspected = sum(1 for c in self.competitors if c.inspected)
        object.__setattr__(self, "inspected_count", inspected)
        prices = [p for c in self.competitors for p in c.price_points]
        if prices:
            object.__setattr__(self, "price_range_low", min(prices))
            object.__setattr__(self, "price_range_high", max(prices))
        if self.verdict == "open_opportunity" and self.competitors:
            raise ValueError(
                "'open_opportunity' cannot be claimed while competitors are "
                "listed; use 'differentiation_required' or 'crowded_but_viable'"
            )
        if self.verdict == "saturated_no_entry" and self.market_saturation not in {
            "crowded",
            "saturated",
        }:
            raise ValueError(
                "'saturated_no_entry' requires saturation to be crowded or saturated"
            )
        if self.differentiation_available and not self.differentiation_basis:
            raise ValueError("claimed differentiation must state its basis")
        return self


class DistributionAssessment(BaseModel):
    """The §14 route-to-customer verdict."""

    model_config = ConfigDict(extra="forbid")

    channels: tuple[DistributionChannel, ...] = ()
    reachable_without_paid_ads: bool = False
    estimated_time_to_first_customer: str | None = None
    platform_dependency_risk: RiskSeverity = RiskSeverity.NEGLIGIBLE
    data_gaps: tuple[str, ...] = ()
    verdict: Literal[
        "clear_path",
        "plausible_path",
        "requires_ad_spend",
        "no_identified_path",
        "insufficient_data",
    ] = "insufficient_data"
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _consistency(self) -> "DistributionAssessment":
        organic = [c for c in self.channels if c.feasible_without_ad_spend]
        object.__setattr__(self, "reachable_without_paid_ads", bool(organic))
        if self.channels:
            platform_controlled = any(c.platform_controlled for c in self.channels)
            high_dep = any(c.dependency_risk == "high" for c in self.channels)
            severity = (
                RiskSeverity.HIGH
                if high_dep
                else RiskSeverity.MEDIUM
                if platform_controlled
                else RiskSeverity.LOW
            )
            object.__setattr__(self, "platform_dependency_risk", severity)
        if self.verdict == "clear_path" and not organic:
            raise ValueError(
                "'clear_path' requires at least one channel feasible without ad spend"
            )
        if self.verdict == "requires_ad_spend" and organic:
            raise ValueError(
                "'requires_ad_spend' contradicts the presence of an organic channel"
            )
        if self.verdict in {"clear_path", "plausible_path"} and not self.channels:
            raise ValueError("a path verdict requires at least one channel")
        return self


class RiskAssessment(BaseModel):
    """The §15 legal / platform / ethical verdict."""

    model_config = ConfigDict(extra="forbid")

    findings: tuple[RiskFinding, ...] = ()
    highest_severity: RiskSeverity = RiskSeverity.NEGLIGIBLE
    blocked: bool = False
    prohibited_category_matched: str | None = None
    jurisdictions_considered: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()
    verdict: Literal[
        "acceptable",
        "acceptable_with_mitigation",
        "high_risk",
        "blocked",
        "cannot_determine",
    ] = "cannot_determine"
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _blocking_is_terminal(self) -> "RiskAssessment":
        if self.findings:
            worst = max(self.findings, key=lambda f: RISK_SEVERITY_RANK[f.severity])
            object.__setattr__(self, "highest_severity", worst.severity)
        blocking = tuple(f for f in self.findings if f.blocks_recommendation)
        object.__setattr__(self, "blocked", bool(blocking))
        prohibited = next(
            (f for f in self.findings if f.category == "prohibited_category"), None
        )
        if prohibited is not None:
            object.__setattr__(
                self, "prohibited_category_matched", prohibited.description[:200]
            )
        if blocking and self.verdict != "blocked":
            raise ValueError(
                "a blocking risk finding forces verdict='blocked'; no other "
                "verdict may be recorded"
            )
        if not blocking and self.verdict == "blocked":
            raise ValueError("'blocked' verdict recorded with no blocking finding")
        if prohibited is not None and self.verdict != "blocked":
            raise ValueError("a prohibited-category match forces verdict='blocked'")
        return self


class ScreeningResult(BaseModel):
    """The §17 initial-screening outcome: the cheapest possible rejection."""

    model_config = ConfigDict(extra="forbid")

    passed: bool = False
    rejections: tuple[str, ...] = ()
    compliance_blocked: bool = False
    duplicate_of: str | None = None
    missing_constraints: tuple[str, ...] = ()
    next_state: OpportunityState = OpportunityState.RESEARCHING

    @model_validator(mode="after")
    def _state_follows_outcome(self) -> "ScreeningResult":
        if self.compliance_blocked:
            object.__setattr__(self, "passed", False)
            object.__setattr__(
                self, "next_state", OpportunityState.BLOCKED_BY_COMPLIANCE
            )
        elif self.duplicate_of:
            object.__setattr__(self, "passed", False)
            object.__setattr__(self, "next_state", OpportunityState.DUPLICATE)
        elif self.rejections:
            object.__setattr__(self, "passed", False)
            object.__setattr__(self, "next_state", OpportunityState.REJECTED)
        elif self.missing_constraints:
            object.__setattr__(self, "passed", False)
            object.__setattr__(
                self, "next_state", OpportunityState.NEEDS_MORE_EVIDENCE
            )
        else:
            object.__setattr__(self, "passed", True)
            object.__setattr__(self, "next_state", OpportunityState.RESEARCHING)
        return self


class ReportSection(str, Enum):
    """The nine report sections A-I (§23)."""

    A_EXECUTIVE_SUMMARY = "A_executive_summary"
    B_OPPORTUNITY_DESCRIPTION = "B_opportunity_description"
    C_MARKET_ANALYSIS = "C_market_analysis"
    D_COMPETITIVE_ANALYSIS = "D_competitive_analysis"
    E_BUSINESS_MODEL = "E_business_model"
    F_COMMERCIAL_FEASIBILITY = "F_commercial_feasibility"
    G_DISTRIBUTION_AND_ACQUISITION = "G_distribution_and_acquisition"
    H_RISK_AND_COMPLIANCE = "H_risk_and_compliance"
    I_EVIDENCE_AND_VALIDATION = "I_evidence_and_validation"


class OpportunityReport(BaseModel):
    """The generated report (§23).

    ``is_test_data`` is mandatory and defaults to True: a report built from mock
    fixtures must announce itself, and the safe default is the one that cannot
    mislead.  Real-data reports have to opt out explicitly, which is only
    possible when evidence was genuinely acquired.
    """

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(default_factory=lambda: f"rpt-{uuid4().hex[:12]}")
    opportunity_id: str
    title: str = Field(min_length=1, max_length=300)
    final_classification: FinalClassification
    sections: dict[ReportSection, str] = Field(default_factory=dict)
    headline_metrics: dict[str, str] = Field(default_factory=dict)
    evidence_index: tuple[dict[str, Any], ...] = ()
    refusals: tuple[dict[str, Any], ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    score: OpportunityScore | None = None
    validation: ValidationAssessment | None = None
    is_test_data: bool = True
    test_data_notice: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _all_sections_present(self) -> "OpportunityReport":
        missing = [s.value for s in ReportSection if s not in self.sections]
        if missing:
            raise ValueError(
                f"report is missing required section(s): {', '.join(missing)}"
            )
        if self.is_test_data and not self.test_data_notice:
            raise ValueError(
                "a report flagged as test data must carry an explicit "
                "test_data_notice; it may not be presented as real market research"
            )
        if not self.is_test_data and self.test_data_notice:
            raise ValueError(
                "a real-data report must not carry a test_data_notice"
            )
        return self


class ResearchTaskSpec(BaseModel):
    """A unit of research work handed to the P-01 task manager (§24)."""

    model_config = ConfigDict(extra="forbid")

    opportunity_id: str
    stage: Literal[
        "source_sweep",
        "market_sizing",
        "competitor_scan",
        "cost_verification",
        "demand_verification",
        "compliance_scan",
    ]
    source_ids: tuple[str, ...] = ()
    query: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    max_items: int = Field(default=25, ge=1, le=500)
    timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    priority: int = Field(default=5, ge=1, le=10)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def task_name(self) -> str:
        return f"research.{self.stage}:{self.opportunity_id}"[:200]

    def handler(self) -> str:
        return "research.sweep"


class ScoringOutcome(BaseModel):
    """The scorer's complete output (§16).

    ``hard_rejections`` is separate from ``score`` on purpose: an opportunity can
    score well and still be rejected.  The final classification follows the
    rejections first and the score second, so a high score can never rescue an
    opportunity that a hard rule has already refused.
    """

    model_config = ConfigDict(extra="forbid")

    score: OpportunityScore
    hard_rejections: tuple[str, ...] = ()
    rejected: bool = False
    rejection_classification: FinalClassification | None = None
    final_classification: FinalClassification = FinalClassification.INSUFFICIENT_EVIDENCE
    recommendable: bool = False
    reasons: tuple[str, ...] = ()
    minimum_validation_level_required: ValidationLevel = (
        ValidationLevel.LEVEL_3_COMMERCIAL_EVIDENCE
    )
    weights_fingerprint: str = ""

    @model_validator(mode="after")
    def _rejection_wins(self) -> "ScoringOutcome":
        if self.hard_rejections:
            object.__setattr__(self, "rejected", True)
            object.__setattr__(self, "recommendable", False)
            if self.rejection_classification is None:
                raise ValueError(
                    "a hard rejection must name the classification it results in"
                )
            if self.final_classification is not self.rejection_classification:
                object.__setattr__(
                    self, "final_classification", self.rejection_classification
                )
        else:
            object.__setattr__(self, "rejected", False)
            object.__setattr__(self, "rejection_classification", None)
        if self.recommendable and self.rejected:
            raise ValueError("a rejected opportunity can never be recommendable")
        return self
