"""Assembly for the P-04 agent subsystem.

Mirrors :mod:`app.opportunities.factory` and :mod:`app.intelligence.factory`:
``build_agents`` constructs the subsystem from validated settings and performs
no I/O, and ``initialize`` restores what was persisted before the last shutdown.

The module is named ``subsystem`` rather than ``factory`` on purpose. Inside
``app/agents`` the name ``factory`` belongs to the Stage 4 creation engine,
which turns a requirement into a deterministic CREATE / REUSE / ASSIGN / QUEUE /
REQUEST_OWNER_APPROVAL / REJECT decision. Two different things called "factory"
in one package is how a reader ends up wiring the wrong one.

Stage 3 assembles one component, the template service. Stage 4 adds the decision
engine and the executor that acts on its decisions. Stage 5 adds the capability
catalog and the authority that grants against it. Later stages append theirs here
rather than growing a second assembly point, so ``Services.agents`` stays the
single place the rest of the application reaches P-04 through.
"""

from __future__ import annotations

from typing import Any

from ..core.config import Settings
from ..database.connection import Database
from ..database.repositories import AgentCapabilityRepo, AgentRepo, AgentTemplateRepo
from ..events.bus import EventBus
from .capabilities import (
    CapabilityService,
    register_capability_approval_subscribers,
)
from .creation import CreationEngine, register_factory_approval_subscribers
from .factory import LIVE_STATUSES, AgentFactory
from .templates import TemplateService

__all__ = ["AgentServices", "build_agents", "initialize"]


class AgentServices:
    """The P-04 subsystem as the rest of the application sees it."""

    def __init__(self, *, settings: Settings, db: Database, bus: EventBus | None,
                 templates: TemplateService, factory: AgentFactory,
                 creation: CreationEngine, capabilities: CapabilityService,
                 notes: tuple[str, ...] = ()) -> None:
        self.settings = settings
        self.db = db
        self.bus = bus
        self.templates = templates
        self.factory = factory
        self.creation = creation
        self.capabilities = capabilities
        self.notes = list(notes)

    def status(self) -> dict[str, Any]:
        """What is assembled, and what is deliberately not yet.

        Reporting the absent parts is not decoration: a caller that believes
        agent creation exists would otherwise have no way to discover that it
        does not until a request failed.
        """
        return {
            "enabled": True,
            "stage": "P-04 Stage 5 (registry, templates, creation and capabilities)",
            "templates": True,
            "factory": True,
            "capabilities": True,
            "assignments": False,
            "resources": False,
            "monitoring": False,
            "notes": tuple(self.notes),
        }


def build_agents(settings: Settings, db: Database, bus: EventBus | None = None,
                 *, approvals: Any = None, monitor: Any = None,
                 emergency: Any = None, permissions: Any = None) -> AgentServices:
    """Assemble the subsystem. Construction performs no I/O and opens no socket.

    The keyword collaborators are optional on purpose. A creation engine
    built without an approval service still evaluates correctly and refuses a
    gated creation rather than performing it ungated, and one built without the
    permission engine keeps every gated creation gated, because the authority
    check that can shorten a gate is the thing that is missing. So the subsystem
    can be assembled in tests and in degraded deployments without silently
    losing a gate.
    """
    factory = AgentFactory(db, settings, monitor=monitor, emergency=emergency)
    creation = CreationEngine(db, factory, settings, approvals=approvals, bus=bus,
                              permissions=permissions)
    capabilities = CapabilityService(db, settings, approvals=approvals, bus=bus,
                                     emergency=emergency)
    if bus is not None:
        register_factory_approval_subscribers(bus, creation)
        register_capability_approval_subscribers(bus, capabilities)
    notes = [
        "the capability catalog is defined in code and reconciled at startup; "
        "no endpoint can add or edit an entry, so the level a capability carries "
        "cannot depend on who asked",
        "capability grants are governed, but no tool boundary calls check() yet: "
        "adapters and the tool registry are P-05 and assignment output contracts "
        "are P-04 Stage 6",
        "creation decisions are deterministic: no model is consulted, and "
        "ASSIGN_EXISTING is never emitted because assignment validation is "
        "P-04 Stage 6",
        "bringing a new agent to ACTIVE means its principal, registry row and "
        "configuration snapshot exist; no health observation has taken place "
        "yet, which is P-04 Stage 8",
    ]
    return AgentServices(
        settings=settings,
        db=db,
        bus=bus,
        templates=TemplateService(db, settings, bus),
        factory=factory,
        creation=creation,
        capabilities=capabilities,
        notes=tuple(notes),
    )


async def initialize(services: AgentServices) -> dict[str, int]:
    """Report what the registry already holds. Recovery changes nothing.

    Templates and agents are read straight from the database on demand, so there
    is no in-memory state to rebuild; counting them is enough to say the registry
    survived the restart. Nothing is re-validated, re-published, re-created or
    re-approved here, and a queued creation request stays queued until an owner
    drains it: restarting the process must not resume work nobody asked to
    resume.
    """
    # Reconcile the catalog before reporting. Recovery restores *definitions*,
    # which is safe: it writes no grant, widens no authority and cannot lift a
    # prohibition, because the level-3 list is code. Grants that already existed
    # are left exactly as they were, including any that are pending an approval
    # that has not been decided - a restart must not finish anyone's approval.
    reconciled = await services.capabilities.reconcile_catalog()
    async with services.db.session_factory() as session:
        templates = AgentTemplateRepo(session)
        agents = AgentRepo(session)
        capabilities = AgentCapabilityRepo(session)
        return {
            "templates": await templates.count(),
            "published_templates": await templates.count(status="published"),
            "live_agents": await agents.count(statuses=LIVE_STATUSES),
            "capabilities": await capabilities.count(),
            "catalog_created": len(reconciled["created"]),
            "catalog_updated": len(reconciled["updated"]),
        }
