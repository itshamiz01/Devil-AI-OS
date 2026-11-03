"""P-03 Opportunity Discovery Engine.

A systematic business-research and opportunity-evaluation subsystem.  It is not an
idea generator, and it is not a pile of search results labelled market research.
The design goal stated in the phase brief is that AUTONOMOUS must become better at
**rejecting** bad business opportunities than it is at generating attractive
business ideas, and every module here is shaped by that.

Module map (§4)
---------------
The brief proposed a nested tree of eleven subpackages.  This repository's
established convention - set by P-02's :mod:`app.intelligence` - is a flat package
of single-purpose modules, and §4 explicitly directs adapting to the existing
repository rather than creating unnecessary modules.  The eleven proposed areas
map onto these modules:

===========================  ==================================================
Proposed area                Module
===========================  ==================================================
``core/``                    :mod:`.engine` - the §20 workflow orchestrator
``schemas/``                 :mod:`.schemas` - every enum, constraint and record
``discovery/``               :mod:`.discovery` - the six §7 discovery methods
``research/``                :mod:`.research` - §20 stages, §24 scheduling
``market/``                  :mod:`.analysis` - §10 market and customer analysis
``commercial/``              :mod:`.commercial` - §13 costs, scenarios, break-even
``validation/``              :mod:`.validation` - the §18 ladder 0-5
``scoring/``                 :mod:`.scoring` - §16 weighted scoring and rejections
``monitoring/``              :mod:`.lifecycle` - §17 states and append-only history
``storage/``                 :mod:`.evidence`, ``repository`` - §9/§21 persistence
``integrations/``            :mod:`.sources` - §8 provider-independent adapters
===========================  ==================================================

Two further modules carry cross-cutting concerns: :mod:`.risk` (§15 legal,
platform and ethical risk) and :mod:`.governance` (§26 what the engine may not
do), plus :mod:`.reports` (§23 the nine-section report).

What is deliberately **not** here
---------------------------------
* No duplicate of P-02's reasoning.  Uncertainty, reliability and trust semantics
  are imported from :mod:`app.intelligence.schemas`, and :mod:`.evidence` bridges
  into P-02's ``EvidenceManager`` rather than reimplementing it.
* No independent database.  Persistence goes through the P-01 ``Database`` and
  Alembic migration chain.
* No autonomous scheduling.  §24 provides enqueueing only; deciding when to
  research is P-12.
* No financial execution of any kind (§26).
"""

from __future__ import annotations

from app.opportunities.analysis import (
    PROVENANCE_FROM_RELIABILITY,
    BusinessModelAnalyser,
    CompetitorAnalyser,
    DistributionAnalyser,
    MarketAnalyser,
)
from app.opportunities.commercial import (
    MINIMUM_CONTRIBUTION_MARGIN,
    CommercialFeasibilityEngine,
    CommercialInputs,
)
from app.opportunities.discovery import (
    BUDGET_ARCHETYPES,
    DiscoveryContext,
    DiscoveryEngine,
    DiscoveryReport,
    normalise_title,
)
from app.opportunities.engine import OpportunityEngine, OpportunityRecord
from app.opportunities.evidence import (
    EvidenceExtractor,
    EvidenceQualityStats,
    EvidenceStore,
    claim_key,
    metric_key,
)
from app.opportunities.governance import (
    PERMITTED_ACTIONS,
    PROHIBITED_ACTIONS,
    PROHIBITION_REASONS,
    GovernanceAction,
    GovernanceDecision,
    GovernanceGate,
    GovernanceViolation,
)
from app.opportunities.lifecycle import HistoryEntry, OpportunityLifecycle
from app.opportunities.reports import NO_EVIDENCE_STATEMENT, TEST_DATA_NOTICE, ReportGenerator
from app.opportunities.research import (
    WORKFLOW_STAGES,
    ResearchScheduler,
    ResearchStage,
    StageResult,
    WorkflowReport,
    summarise_refusals,
)
from app.opportunities.risk import (
    PROHIBITED_CATEGORIES,
    ComplianceScreen,
    RiskEngine,
)
from app.opportunities.scoring import (
    MIN_EVIDENCE_COVERAGE_PCT,
    MIN_RECOMMEND_ATTRACTIVENESS,
    RELIABILITY_MULTIPLIER,
    OpportunityScorer,
)
from app.opportunities.sources import (
    MAX_RESPONSE_CHARS,
    FetchResult,
    HttpSourceAdapter,
    MockSourceAdapter,
    NetworkPolicy,
    RefusalCategory,
    SourceAdapter,
    SourceAuthorisationError,
    SourceNotFoundError,
    SourceRefusal,
    SourceRegistry,
    UnreachableSourceAdapter,
)
from app.opportunities.validation import (
    LEVEL_REQUIREMENTS,
    PERMITTED_LEVEL_4_INPUTS,
    PERMITTED_LEVEL_5_INPUTS,
    ValidationEngine,
)
from app.opportunities.schemas import *  # noqa: F401,F403 - re-exported value types
from app.opportunities import schemas as _schemas

__all__ = [
    # engine
    "OpportunityEngine",
    "OpportunityRecord",
    # discovery
    "DiscoveryContext",
    "DiscoveryEngine",
    "DiscoveryReport",
    "BUDGET_ARCHETYPES",
    "normalise_title",
    # research / workflow
    "ResearchStage",
    "WORKFLOW_STAGES",
    "StageResult",
    "WorkflowReport",
    "ResearchScheduler",
    "summarise_refusals",
    # sources
    "SourceRegistry",
    "SourceAdapter",
    "HttpSourceAdapter",
    "MockSourceAdapter",
    "UnreachableSourceAdapter",
    "NetworkPolicy",
    "FetchResult",
    "SourceRefusal",
    "RefusalCategory",
    "SourceNotFoundError",
    "SourceAuthorisationError",
    "MAX_RESPONSE_CHARS",
    # evidence
    "EvidenceStore",
    "EvidenceExtractor",
    "EvidenceQualityStats",
    "claim_key",
    "metric_key",
    # analysis
    "MarketAnalyser",
    "CompetitorAnalyser",
    "BusinessModelAnalyser",
    "DistributionAnalyser",
    "PROVENANCE_FROM_RELIABILITY",
    # commercial
    "CommercialFeasibilityEngine",
    "CommercialInputs",
    "MINIMUM_CONTRIBUTION_MARGIN",
    # risk
    "RiskEngine",
    "ComplianceScreen",
    "PROHIBITED_CATEGORIES",
    # scoring
    "OpportunityScorer",
    "MIN_EVIDENCE_COVERAGE_PCT",
    "MIN_RECOMMEND_ATTRACTIVENESS",
    "RELIABILITY_MULTIPLIER",
    # validation
    "ValidationEngine",
    "LEVEL_REQUIREMENTS",
    "PERMITTED_LEVEL_4_INPUTS",
    "PERMITTED_LEVEL_5_INPUTS",
    # lifecycle
    "OpportunityLifecycle",
    "HistoryEntry",
    # governance
    "GovernanceGate",
    "GovernanceAction",
    "GovernanceDecision",
    "GovernanceViolation",
    "PERMITTED_ACTIONS",
    "PROHIBITED_ACTIONS",
    "PROHIBITION_REASONS",
    # reports
    "ReportGenerator",
    "NO_EVIDENCE_STATEMENT",
    "TEST_DATA_NOTICE",
]

# Re-export every schema name so callers can import from the package root.
__all__ += sorted(_schemas.__all__)
