"""Opportunity Discovery API (P-03 §22).

Versioned under ``/api/v1/opportunities``.  Authorization is enforced per
operation, not per router:

* ``opportunities.read``     — list and read opportunities, evidence, reports, status
* ``opportunities.research`` — run discovery and acquisition sweeps
* ``opportunities.manage``   — open, screen, analyse, advance or reject
* ``opportunities.sources``  — register a research source (owner only)

All four are derived into ``OWNER_PERMISSIONS`` and deliberately absent from
``SYSTEM_PERMISSIONS``, so the application can never authorize its own research or
widen the hosts it may reach on its own authority.

**There is no endpoint that spends money.**  §26 prohibits purchasing domains,
subscriptions, datasets or advertising, placing orders, registering businesses,
signing contracts, collecting payments and creating any financial obligation, at
every autonomy level.  That is not a missing feature to be added later with a
permission: the ``GovernanceGate`` refuses those actions outright, and exposing a
route for one would imply a capability that does not exist.

Three disclosure rules shape every response:

* Refusals are returned, not hidden.  A sweep that reached nothing says so per
  source, because an absence of evidence is only interpretable with its reason.
* Reports built from fixture data carry ``is_test_data`` and a notice.  The flag
  defaults to true and cannot be cleared without the caller asserting the data is
  real, which the schema then cross-checks against the presence of a notice.
* No source credential is ever returned.  A descriptor reports that authentication
  is required and by which mechanism, never the secret.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ...core.exceptions import ConflictError, NotFoundError
from ...opportunities.discovery import DiscoveryContext
from ...opportunities.reports import ReportGenerator
from ...opportunities.schemas import (
    BudgetConstraint,
    BusinessCategory,
    CostItem,
    CostStructure,
    OpportunityCandidate,
    OpportunityState,
    Provenance,
)
from ..dependencies import get_services, require_permission
from ..schemas.common import envelope

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


# --------------------------------------------------------------------------- #
# Request schemas
# --------------------------------------------------------------------------- #


class DiscoverRequest(BaseModel):
    """Inputs for candidate generation (§7).

    Every field is optional.  A request carrying nothing but a budget still
    produces budget-driven candidates, and the five evidence-dependent methods
    report that they produced nothing rather than inventing demand.
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
    max_candidates_per_method: int = Field(default=5, ge=1, le=25)


class OpenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: OpportunityCandidate
    budget: BudgetConstraint | None = None


class ScreenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jurisdictions: tuple[str, ...] = ()
    duplicate_of: str | None = Field(default=None, max_length=64)


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(default=None, max_length=512)
    operations: tuple[str, ...] = ("search",)


class AnalyseRequest(BaseModel):
    """Analysis inputs.

    Costs, price and volume are supplied by the caller rather than invented.  Each
    carries its own provenance, and §13 refuses to compute a margin from a figure
    whose origin is unstated.
    """

    model_config = ConfigDict(extra="forbid")

    jurisdictions: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    costs: tuple[CostItem, ...] = ()
    price_per_unit: Decimal | None = None
    price_provenance: Provenance = Provenance.UNKNOWN
    base_units_monthly: Decimal | None = None
    units_provenance: Provenance = Provenance.UNKNOWN
    competitor_gaps: tuple[str, ...] = ()
    differentiation_basis: str | None = Field(default=None, max_length=500)
    revenue_mechanism: str | None = Field(default=None, max_length=200)
    declared_validation_inputs: tuple[str, ...] = ()
    stated_capabilities: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: OpportunityState
    # A transition without a stated reason is not auditable, so this is required.
    reason: str = Field(min_length=1, max_length=2000)


class EnqueueResearchRequest(BaseModel):
    """Submit a research sweep to the P-01 task manager (§24).

    This enqueues work that the owner has asked for now.  It does not schedule
    anything: deciding *when* to research autonomously is P-12, and the engine
    reports ``autonomous_scheduling: false`` rather than implying a capability it
    does not have.
    """

    model_config = ConfigDict(extra="forbid")

    stage: Literal[
        "source_sweep",
        "market_sizing",
        "competitor_scan",
        "cost_verification",
        "demand_verification",
        "compliance_scan",
    ] = "source_sweep"
    query: str | None = Field(default=None, max_length=512)
    source_ids: tuple[str, ...] = ()
    max_items: int = Field(default=25, ge=1, le=1000)


class SourceRegisterRequest(BaseModel):
    """A source declaration (§8).

    No credential field exists here.  Authentication is declared by mechanism; the
    secret is never accepted, stored or returned.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    source_type: str = Field(min_length=1, max_length=32)
    access_method: str = Field(min_length=1, max_length=32)
    licensing: str = Field(min_length=1, max_length=400)
    requires_auth: bool = False
    auth_mechanism: Literal["none", "api_key", "oauth2", "owner_session"] = "none"
    reliability: str = "untrusted"
    supported_operations: tuple[str, ...] = ("search",)
    refresh_frequency: Literal["realtime", "daily", "weekly", "monthly", "manual"] = "manual"
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=10_000)
    returned_fields: tuple[str, ...] = ()
    endpoint_template: str | None = Field(default=None, max_length=512)
    notes: str | None = Field(default=None, max_length=2000)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _services(request: Request) -> Any:
    services = get_services(request)
    if getattr(services, "opportunities", None) is None:
        raise ConflictError(
            "the opportunity discovery engine is not enabled",
            details={"hint": "set AUTONOMUS_OPPORTUNITIES_ENABLED=true"},
        )
    return services.opportunities


def _record(services: Any, opportunity_id: str) -> Any:
    try:
        return services.engine.get(opportunity_id)
    except KeyError as exc:
        raise NotFoundError(str(exc)) from None


async def _persist(services: Any, record: Any) -> None:
    """Best-effort persistence of everything learned about one opportunity.

    A storage failure must not discard an analysis that was already computed, so
    each write is independent and failures are reported in the response rather
    than raised.  The engine stays the source of truth for the in-process view.
    """
    repo = services.repository
    oid = record.opportunity_id
    errors: dict[str, str] = {}
    for label, coro in (
        ("opportunity", repo.save_opportunity(record.opportunity)),
        ("history", None),
        ("market", repo.save_market_analysis(oid, record.market) if record.market else None),
        ("competitors", (
            repo.save_competitor_assessment(oid, record.competitors) if record.competitors else None
        )),
        ("commercial", (
            repo.save_commercial_analysis(oid, record.commercial) if record.commercial else None
        )),
        ("risk", repo.save_risk_assessment(oid, record.risk) if record.risk else None),
        ("scoring", repo.save_scoring_outcome(oid, record.outcome) if record.outcome else None),
    ):
        if coro is None:
            continue
        try:
            await coro
        except Exception as exc:  # noqa: BLE001 - reported, never fatal
            errors[label] = f"{type(exc).__name__}: {exc}"
    return errors


def _candidate_view(record: Any) -> dict[str, Any]:
    opp = record.opportunity
    score = opp.score
    return {
        "opportunity_id": opp.opportunity_id,
        "candidate_id": opp.candidate.candidate_id,
        "title": opp.candidate.title,
        "category": opp.candidate.category.value,
        "discovery_method": opp.candidate.discovery_method.value,
        "state": opp.state.value,
        "final_classification": (
            opp.final_classification.value if opp.final_classification else None
        ),
        "recommendable": opp.final_classification is not None
        and opp.final_classification.value == "recommended",
        "validation_level": opp.validation.level.value if opp.validation else 0,
        "attractiveness": str(score.attractiveness) if score else None,
        "evidence_quality": str(score.evidence_quality) if score else None,
        "evidence_coverage_pct": str(score.coverage_pct) if score else None,
        "evidence_count": len(opp.evidence_ids),
        "rejection_reasons": list(opp.rejection_reasons),
        "budget_available_capital": (
            str(opp.budget.available_capital) if opp.budget else None
        ),
    }


# --------------------------------------------------------------------------- #
# Status and discovery.  The literal paths must be declared before
# /{opportunity_id} or FastAPI matches "status" as an identifier.
# --------------------------------------------------------------------------- #


@router.get("/status")
async def get_status(
    request: Request,
    _perm: Any = Depends(require_permission("opportunities.read")),
) -> Any:
    services = _services(request)
    return envelope(services.status())


@router.get("/governance")
async def get_governance(
    request: Request,
    _perm: Any = Depends(require_permission("opportunities.read")),
) -> Any:
    """What §26 permits and prohibits, and what has been refused so far."""
    services = _services(request)
    return envelope(services.governance.snapshot())


@router.get("/sources")
async def list_sources(
    request: Request,
    _perm: Any = Depends(require_permission("opportunities.read")),
) -> Any:
    services = _services(request)
    snapshot = services.registry.snapshot()
    # No credential is returned: the snapshot carries the descriptor's declaration
    # of how it authenticates, never a secret.
    return envelope(snapshot, allowlist=list(services.settings.research_host_allowlist))


@router.post("/sources")
async def register_source(
    body: SourceRegisterRequest,
    request: Request,
    _perm: Any = Depends(require_permission("opportunities.sources")),
) -> Any:
    from ...opportunities.schemas import SourceDescriptor
    from ...intelligence.schemas import EvidenceReliability
    from ...opportunities.schemas import (
        AcquisitionMethod,
        SourceStatus,
        SourceType,
    )
    from ...opportunities.sources import HttpSourceAdapter

    services = _services(request)
    try:
        descriptor = SourceDescriptor(
            source_id=body.source_id,
            name=body.name,
            source_type=SourceType(body.source_type),
            access_method=AcquisitionMethod(body.access_method),
            requires_auth=body.requires_auth,
            auth_mechanism=body.auth_mechanism,
            licensing=body.licensing,
            reliability=EvidenceReliability(body.reliability),
            supported_operations=body.supported_operations,
            refresh_frequency=body.refresh_frequency,
            rate_limit_per_minute=body.rate_limit_per_minute,
            returned_fields=body.returned_fields,
            endpoint_template=body.endpoint_template,
            notes=body.notes,
            status=SourceStatus.AUTHORIZED,
        )
    except ValueError as exc:
        raise ConflictError(f"the source declaration was refused: {exc}") from None

    adapter = (
        None
        if descriptor.source_type.value == "mock"
        else HttpSourceAdapter(descriptor, policy=services.registry.policy)
    )
    try:
        services.registry.register(descriptor, adapter)
    except ValueError as exc:
        raise ConflictError(str(exc)) from None
    await services.repository.save_source(descriptor)
    return envelope(
        {"source_id": descriptor.source_id, "status": descriptor.status.value},
        note="registering a source does not place its host on the network allowlist",
    )


@router.get("/ranked")
async def list_ranked(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    _perm: Any = Depends(require_permission("opportunities.read")),
) -> Any:
    """Reproducible ranking (§16).

    Ordering is by the deterministic ranking key with the opportunity id as a final
    tie-break, so the result never depends on insertion or iteration order.
    """
    services = _services(request)
    ranked = services.engine.rank()[:limit]
    return envelope(
        [_candidate_view(r) for r in ranked],
        count=len(ranked),
        weights_fingerprint=services.engine.scorer.weights_fingerprint,
    )


@router.post("/discover")
async def discover(
    body: DiscoverRequest,
    request: Request,
    _perm: Any = Depends(require_permission("opportunities.research")),
) -> Any:
    services = _services(request)
    context = DiscoveryContext(**body.model_dump())
    report = services.engine.discover(context)
    return envelope(
        {
            "candidates": [c.model_dump(mode="json") for c in report.candidates],
            "per_method": dict(report.per_method),
            "empty_methods": list(report.empty_methods),
            "duplicates_suppressed": report.duplicates_suppressed,
            "inputs_available": report.inputs_available,
            "notes": list(report.notes),
        },
        count=len(report.candidates),
    )


@router.get("")
async def list_opportunities(
    request: Request,
    state: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=50, ge=1, le=500),
    _perm: Any = Depends(require_permission("opportunities.read")),
) -> Any:
    services = _services(request)
    records = services.engine.list_records()
    if state is not None:
        records = [r for r in records if r.opportunity.state.value == state]
    records = records[:limit]
    return envelope([_candidate_view(r) for r in records], count=len(records))


@router.post("")
async def open_opportunity(
    body: OpenRequest,
    request: Request,
    _perm: Any = Depends(require_permission("opportunities.manage")),
) -> Any:
    services = _services(request)
    if len(services.engine.list_records()) >= services.settings.opportunity_max_open:
        raise ConflictError(
            "the open-opportunity limit has been reached",
            details={"limit": services.settings.opportunity_max_open},
        )
    record = services.engine.open(body.candidate, budget=body.budget, actor="owner")
    await services.bus.publish_new(
        "OpportunityOpened",
        "opportunities",
        {"opportunity_id": record.opportunity_id, "title": body.candidate.title},
    )
    errors = await _persist(services, record)
    return envelope(_candidate_view(record), persistence_errors=errors or None)


# --------------------------------------------------------------------------- #
# Per-opportunity operations
# --------------------------------------------------------------------------- #


@router.get("/{opportunity_id}")
async def get_opportunity(
    opportunity_id: str,
    request: Request,
    _perm: Any = Depends(require_permission("opportunities.read")),
) -> Any:
    services = _services(request)
    record = _record(services, opportunity_id)
    view = _candidate_view(record)
    view["description"] = record.opportunity.candidate.description
    view["problem_addressed"] = record.opportunity.candidate.problem_addressed
    view["proposed_offering"] = record.opportunity.candidate.proposed_offering
    view["assumptions"] = [a.model_dump(mode="json") for a in record.opportunity.assumptions]
    view["evidence_ids"] = list(record.opportunity.evidence_ids)
    # Sections E and G of the report describe these, so they must be readable here
    # too. Both are None/empty until analysis has run, which is itself information:
    # an absent business model means none was derived, not that one was assumed.
    view["business_model"] = (
        record.opportunity.business_model.model_dump(mode="json")
        if record.opportunity.business_model
        else None
    )
    view["distribution"] = [d.model_dump(mode="json") for d in record.opportunity.distribution]
    if record.outcome is not None:
        view["score"] = record.outcome.score.model_dump(mode="json")
        view["hard_rejections"] = list(record.outcome.hard_rejections)
        view["scoring_reasons"] = list(record.outcome.reasons)
    if record.market is not None:
        view["market"] = record.market.model_dump(mode="json")
    if record.competitors is not None:
        view["competitors"] = record.competitors.model_dump(mode="json")
    if record.commercial is not None:
        view["commercial"] = record.commercial.model_dump(mode="json")
    if record.risk is not None:
        view["risk"] = record.risk.model_dump(mode="json")
    if record.opportunity.validation is not None:
        view["validation"] = record.opportunity.validation.model_dump(mode="json")
    if record.workflow is not None:
        view["workflow"] = record.workflow.model_dump(mode="json")
    return envelope(view)


@router.post("/{opportunity_id}/screen")
async def screen_opportunity(
    opportunity_id: str,
    body: ScreenRequest,
    request: Request,
    _perm: Any = Depends(require_permission("opportunities.manage")),
) -> Any:
    services = _services(request)
    record = _record(services, opportunity_id)
    result = services.engine.screen(
        record, jurisdictions=body.jurisdictions, duplicate_of=body.duplicate_of, actor="owner"
    )
    if result.compliance_blocked:
        await services.bus.publish_new(
            "ComplianceBlocked",
            "opportunities",
            {"opportunity_id": opportunity_id, "rejections": list(result.rejections)},
            severity="warning",
        )
    errors = await _persist(services, record)
    return envelope(result.model_dump(mode="json"), persistence_errors=errors or None)


@router.post("/{opportunity_id}/research")
async def research_opportunity(
    opportunity_id: str,
    body: ResearchRequest,
    request: Request,
    _perm: Any = Depends(require_permission("opportunities.research")),
) -> Any:
    """Run the acquisition stages (§20).

    A sweep that reaches no source still completes: it reports one refusal per
    source attempted.  That is the finding, not a failure to hide.
    """
    services = _services(request)
    record = _record(services, opportunity_id)
    workflow = services.engine.research(
        record, query=body.query, operations=body.operations, actor="owner"
    )
    refusals = [r for stage in workflow.stages for r in stage.refusals]
    await services.bus.publish_new(
        "ResearchSweepCompleted",
        "opportunities",
        {
            "opportunity_id": opportunity_id,
            "completed": workflow.completed,
            "responses_obtained": sum(s.items_produced for s in workflow.stages),
            "refusals": len(refusals),
        },
    )
    for refusal in refusals:
        await services.bus.publish_new(
            "SourceRefused",
            "opportunities",
            {"opportunity_id": opportunity_id, **refusal},
            severity="warning",
        )
    await services.repository.record_sweep(
        opportunity_id=opportunity_id,
        stage="acquisition",
        operation=",".join(body.operations)[:64],
        query=body.query,
        source_ids=tuple(
            s["source_id"] for s in services.registry.snapshot().get("sources", ())
        ),
        responses_obtained=sum(
            s.items_produced for s in workflow.stages if s.stage.value == "acquisition"
        ),
        evidence_extracted=sum(
            s.items_produced for s in workflow.stages if s.stage.value == "evidence_extraction"
        ),
        refusals=tuple(refusals),
        started_at=workflow.stages[0].started_at if workflow.stages else None,
        finished_at=workflow.finished_at,
    )
    errors = await _persist(services, record)
    return envelope(
        workflow.model_dump(mode="json"),
        refusals=len(refusals),
        persistence_errors=errors or None,
    )


@router.post("/{opportunity_id}/enqueue-research")
async def enqueue_research(
    opportunity_id: str,
    body: EnqueueResearchRequest,
    request: Request,
    principal: Any = Depends(require_permission("opportunities.research")),
) -> Any:
    """Hand a research sweep to the P-01 task manager (§24).

    The response reports whether the task was actually dispatched.  When no task
    manager is wired, or the submission is refused, that is stated plainly instead
    of the task being presented as queued.
    """
    services = _services(request)
    _record(services, opportunity_id)  # 404 if unknown
    spec = services.engine.scheduler.build_spec(
        opportunity_id,
        body.stage,
        source_ids=body.source_ids,
        query=body.query,
        max_items=body.max_items,
    )
    principal_id = getattr(principal, "principal_id", None) or getattr(principal, "id", None) or "owner"
    submission = services.engine.scheduler.enqueue(spec, principal_id=str(principal_id))
    if submission.get("dispatched"):
        await services.bus.publish_new(
            "ResearchSweepCompleted",
            "opportunities",
            {
                "opportunity_id": opportunity_id,
                "stage": body.stage,
                "task_id": submission.get("task_id"),
                "note": "enqueued, not yet executed",
            },
            severity="info",
        )
    return envelope(
        submission,
        dispatched=bool(submission.get("dispatched")),
        reason=submission.get("reason"),
        autonomous_scheduling=False,
    )


@router.post("/{opportunity_id}/analyse")
async def analyse_opportunity(
    opportunity_id: str,
    body: AnalyseRequest,
    request: Request,
    _perm: Any = Depends(require_permission("opportunities.manage")),
) -> Any:
    services = _services(request)
    record = _record(services, opportunity_id)
    costs = CostStructure(items=body.costs) if body.costs else None
    services.engine.analyse(
        record,
        jurisdictions=body.jurisdictions,
        platforms=body.platforms,
        costs=costs,
        price_per_unit=body.price_per_unit,
        price_provenance=body.price_provenance,
        base_units_monthly=body.base_units_monthly,
        units_provenance=body.units_provenance,
        competitor_gaps=body.competitor_gaps,
        differentiation_basis=body.differentiation_basis,
        revenue_mechanism=body.revenue_mechanism,
        declared_validation_inputs=body.declared_validation_inputs,
        stated_capabilities=body.stated_capabilities,
        required_capabilities=body.required_capabilities,
        actor="owner",
    )
    outcome = record.outcome
    event = (
        "OpportunityRecommended"
        if outcome is not None and outcome.recommendable
        else "OpportunityRejected"
    )
    await services.bus.publish_new(
        event,
        "opportunities",
        {
            "opportunity_id": opportunity_id,
            "final_classification": (
                outcome.final_classification.value if outcome is not None else None
            ),
            "hard_rejections": list(outcome.hard_rejections) if outcome is not None else [],
        },
        severity="info" if event == "OpportunityRecommended" else "warning",
    )
    errors = await _persist(services, record)
    return envelope(
        {
            "score": outcome.score.model_dump(mode="json") if outcome else None,
            "hard_rejections": list(outcome.hard_rejections) if outcome else [],
            "recommendable": bool(outcome.recommendable) if outcome else False,
            "final_classification": (
                outcome.final_classification.value if outcome is not None else None
            ),
            "reasons": list(outcome.reasons) if outcome else [],
            "opportunity": _candidate_view(record),
        },
        persistence_errors=errors or None,
    )


@router.post("/{opportunity_id}/transition")
async def transition_opportunity(
    opportunity_id: str,
    body: TransitionRequest,
    request: Request,
    _perm: Any = Depends(require_permission("opportunities.manage")),
) -> Any:
    services = _services(request)
    record = _record(services, opportunity_id)
    try:
        opportunity = services.engine.advance(
            record, body.target, reason=body.reason, actor="owner"
        )
    except ValueError as exc:
        # A domain state machine refusing an illegal transition is a conflict, not
        # a server error.
        raise ConflictError(str(exc)) from None
    await services.repository.append_history(
        opportunity_id=opportunity_id,
        from_state=record.opportunity.state.value,
        to_state=opportunity.state.value,
        reason=body.reason,
        actor="owner",
    )
    await services.bus.publish_new(
        "OpportunityStateChanged",
        "opportunities",
        {"opportunity_id": opportunity_id, "to_state": opportunity.state.value},
    )
    errors = await _persist(services, record)
    return envelope(_candidate_view(record), persistence_errors=errors or None)


@router.get("/{opportunity_id}/report")
async def get_report(
    opportunity_id: str,
    request: Request,
    is_test_data: bool = Query(
        default=True,
        description="Must be set false explicitly to assert the figures are real acquired data.",
    ),
    _perm: Any = Depends(require_permission("opportunities.read")),
) -> Any:
    """The nine-section report (§23).

    ``is_test_data`` defaults to true.  Asserting otherwise is an explicit claim
    that every figure came from a real authorized source, and the schema refuses a
    report that makes that claim while a test-data notice is still present.
    """
    services = _services(request)
    record = _record(services, opportunity_id)
    if record.outcome is None:
        raise ConflictError(
            "the opportunity has not been analysed yet, so there is nothing to report",
            details={"hint": f"POST /api/v1/opportunities/{opportunity_id}/analyse"},
        )
    try:
        report = services.engine.report(record, is_test_data=is_test_data)
    except ValueError as exc:
        raise ConflictError(str(exc)) from None
    await services.repository.save_report(opportunity_id, report)
    return envelope(
        {
            "report_id": report.report_id,
            "title": report.title,
            "final_classification": report.final_classification.value,
            "is_test_data": report.is_test_data,
            "test_data_notice": report.test_data_notice,
            "headline_metrics": report.headline_metrics,
            "sections": {k.value: v for k, v in report.sections.items()},
            "refusals": list(report.refusals),
            "assumptions": [a.model_dump(mode="json") for a in report.assumptions],
            "markdown": ReportGenerator.to_markdown(report),
        }
    )


@router.get("/{opportunity_id}/evidence")
async def get_evidence(
    opportunity_id: str,
    request: Request,
    _perm: Any = Depends(require_permission("opportunities.read")),
) -> Any:
    services = _services(request)
    _record(services, opportunity_id)  # 404 if unknown
    evidence = services.engine.evidence.for_opportunity(opportunity_id)
    stats = services.engine.evidence.stats(opportunity_id)
    return envelope(
        [e.model_dump(mode="json") for e in evidence],
        count=len(evidence),
        # EvidenceQualityStats is a plain class with as_dict(), not a pydantic
        # model, so model_dump() does not exist on it.
        quality=stats.as_dict(),
    )


@router.get("/{opportunity_id}/history")
async def get_history(
    opportunity_id: str,
    request: Request,
    _perm: Any = Depends(require_permission("opportunities.read")),
) -> Any:
    services = _services(request)
    _record(services, opportunity_id)
    stored = await services.repository.list_history(opportunity_id)
    _record(services, opportunity_id)  # 404 if unknown
    # History lives on the lifecycle manager, keyed by opportunity, not on the
    # Opportunity schema.
    in_memory = [
        h.model_dump(mode="json")
        for h in services.engine.lifecycle.history(opportunity_id)
    ]
    return envelope(
        # Both views are returned rather than merged: the in-memory history is what
        # this process recorded, the persisted history is what survived a restart.
        # They differ after a recovery, and silently preferring one would hide that.
        {"persisted": stored, "in_memory": in_memory},
        persisted_count=len(stored),
        in_memory_count=len(in_memory),
    )
