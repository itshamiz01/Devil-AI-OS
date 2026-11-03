"""Assembly and recovery for the P-03 opportunity subsystem.

Mirrors :mod:`app.intelligence.factory`: ``build_opportunities`` constructs the
subsystem from validated settings and performs no I/O, and ``initialize`` then
restores what was persisted before the last shutdown.

Two decisions here are load-bearing.

**The default source catalog is empty.**  Section 8 requires each source to declare
its licensing, reliability and access method, and section 19 forbids claiming a
source was inspected when it was not.  No external research host is reachable from
this deployment, and none could be verified, so nothing is pre-registered.  A
catalog of plausible-looking descriptors for sites that cannot be reached would
read as authorization that was never granted.  The owner registers sources
explicitly; until then every sweep returns a refusal per source, which the report
states plainly.

**Recovery restores visibility, not activity.**  Persisted opportunities are loaded
back into the engine so they can be read, ranked and reported on.  Nothing is
re-researched, re-scored or re-recommended on startup, and no sweep is dispatched:
autonomous scheduling is P-12.  An opportunity that was mid-research when the
process died comes back in the state it was in, with its history intact.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.database.connection import Database
from app.events.bus import EventBus
from app.opportunities.engine import OpportunityEngine
from app.opportunities.governance import GovernanceGate
from app.opportunities.repository import OpportunityRepository
from app.opportunities.schemas import ValidationLevel
from app.opportunities.sources import HttpSourceAdapter, NetworkPolicy, SourceRegistry

__all__ = [
    "OpportunityServices",
    "build_opportunities",
    "default_source_catalog",
    "initialize",
]

#: Validation levels indexed by their integer value, for reading a persisted
#: minimum back out of settings without a chain of comparisons.
_LEVELS_BY_INT: dict[int, ValidationLevel] = {level.value: level for level in ValidationLevel}


def default_source_catalog() -> tuple[Any, ...]:
    """No source is pre-authorized. See the module docstring for why."""
    return ()


class OpportunityServices:
    """The P-03 subsystem as the rest of the application sees it."""

    def __init__(
        self,
        *,
        settings: Settings,
        db: Database,
        tasks: Any,
        bus: EventBus | None,
        registry: SourceRegistry,
        governance: GovernanceGate,
        repository: OpportunityRepository,
        engine: OpportunityEngine,
        notes: tuple[str, ...] = (),
    ):
        self.settings = settings
        self.db = db
        self.tasks = tasks
        self.bus = bus
        self.registry = registry
        self.governance = governance
        self.repository = repository
        self.engine = engine
        self.notes = list(notes)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "engine": self.engine.status(),
            "notes": tuple(self.notes),
            "source_catalog_default": len(default_source_catalog()),
            "research_host_allowlist": self.settings.research_host_allowlist,
            "minimum_validation_level": self.settings.opportunity_minimum_validation_level,
        }


def build_opportunities(
    settings: Settings,
    db: Database,
    tasks: Any,
    bus: EventBus | None = None,
) -> OpportunityServices:
    """Assemble the subsystem.  Construction performs no I/O and opens no socket."""
    notes: list[str] = []

    allowlist = settings.research_host_allowlist
    # Deny by default.  An empty allowlist is a valid, safe configuration: it means
    # no host may be contacted, and every acquisition returns a refusal.
    policy = NetworkPolicy(
        permitted_hosts=frozenset(allowlist),
        request_timeout_seconds=settings.research_timeout_seconds,
        max_response_chars=settings.research_max_response_bytes,
        max_requests_per_minute_per_source=max(1, settings.research_max_sources_per_sweep),
    )
    if not allowlist:
        notes.append(
            "research_permitted_hosts is empty, so no external source can be "
            "contacted; every acquisition will return a refusal"
        )

    registry = SourceRegistry(policy)
    for descriptor in default_source_catalog():
        registry.register(descriptor, HttpSourceAdapter(descriptor, policy=policy))

    governance = GovernanceGate()
    repository = OpportunityRepository(db)

    minimum_level = _LEVELS_BY_INT.get(
        settings.opportunity_minimum_validation_level,
        ValidationLevel.LEVEL_3_COMMERCIAL_EVIDENCE,
    )
    if minimum_level is ValidationLevel.LEVEL_5_ACTUAL_REVENUE:
        notes.append(
            "the configured minimum validation level is 5 (actual revenue), which "
            "§26 forbids this phase from arranging; no opportunity can be recommended"
        )

    engine = OpportunityEngine(
        registry=registry,
        governance=governance,
        task_manager=tasks,
        minimum_validation_level=minimum_level,
    )
    return OpportunityServices(
        settings=settings,
        db=db,
        tasks=tasks,
        bus=bus,
        registry=registry,
        governance=governance,
        repository=repository,
        engine=engine,
        notes=tuple(notes),
    )


async def initialize(services: OpportunityServices) -> dict[str, int]:
    """Restore persisted sources and opportunities.

    Visibility only: no sweep is dispatched, nothing is re-scored, and no
    opportunity changes state.  A source whose descriptor cannot be rebuilt is
    skipped and counted, rather than aborting recovery for the rest.
    """
    sources_loaded = 0
    sources_failed = 0
    for descriptor in await services.repository.list_sources():
        try:
            if descriptor.source_type.value == "mock":
                services.registry.register(descriptor)
            else:
                services.registry.register(
                    descriptor,
                    HttpSourceAdapter(descriptor, policy=services.registry.policy),
                )
            sources_loaded += 1
        except (ValueError, KeyError):
            sources_failed += 1

    opportunities_restored = 0
    opportunities_failed = 0
    for opportunity in await services.repository.list_opportunities(
        limit=services.settings.opportunity_max_open
    ):
        try:
            services.engine.restore(opportunity)
            opportunities_restored += 1
        except (ValueError, KeyError):
            opportunities_failed += 1

    return {
        "sources_loaded": sources_loaded,
        "sources_failed": sources_failed,
        "opportunities_restored": opportunities_restored,
        "opportunities_failed": opportunities_failed,
    }
