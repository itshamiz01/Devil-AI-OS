"""Assembly for the P-04 agent subsystem.

Mirrors :mod:`app.opportunities.factory` and :mod:`app.intelligence.factory`:
``build_agents`` constructs the subsystem from validated settings and performs
no I/O, and ``initialize`` restores what was persisted before the last shutdown.

The module is named ``subsystem`` rather than ``factory`` on purpose. Inside
``app/agents`` the name ``factory`` belongs to the Stage 4 creation engine,
which turns a requirement into a deterministic CREATE / REUSE / ASSIGN / QUEUE /
REQUEST_OWNER_APPROVAL / REJECT decision. Two different things called "factory"
in one package is how a reader ends up wiring the wrong one.

Stage 3 assembles one component, the template service. Later stages append
theirs here rather than growing a second assembly point, so ``Services.agents``
stays the single place the rest of the application reaches P-04 through.
"""

from __future__ import annotations

from typing import Any

from ..core.config import Settings
from ..database.connection import Database
from ..database.repositories import AgentTemplateRepo
from ..events.bus import EventBus
from .templates import TemplateService

__all__ = ["AgentServices", "build_agents", "initialize"]


class AgentServices:
    """The P-04 subsystem as the rest of the application sees it."""

    def __init__(self, *, settings: Settings, db: Database, bus: EventBus | None,
                 templates: TemplateService, notes: tuple[str, ...] = ()) -> None:
        self.settings = settings
        self.db = db
        self.bus = bus
        self.templates = templates
        self.notes = list(notes)

    def status(self) -> dict[str, Any]:
        """What is assembled, and what is deliberately not yet.

        Reporting the absent parts is not decoration: a caller that believes
        agent creation exists would otherwise have no way to discover that it
        does not until a request failed.
        """
        return {
            "enabled": True,
            "stage": "P-04 Stage 3 (registry and templates)",
            "templates": True,
            "factory": False,
            "capabilities": False,
            "assignments": False,
            "resources": False,
            "monitoring": False,
            "notes": tuple(self.notes),
        }


def build_agents(settings: Settings, db: Database,
                 bus: EventBus | None = None) -> AgentServices:
    """Assemble the subsystem. Construction performs no I/O and opens no socket."""
    notes = [
        "the capability catalog is empty until P-04 Stage 5, so template "
        "validation checks structure and intent but cannot yet cross-check a "
        "capability key against it",
        "no agent can be created through this subsystem yet: the creation "
        "engine is P-04 Stage 4",
    ]
    return AgentServices(
        settings=settings,
        db=db,
        bus=bus,
        templates=TemplateService(db, settings, bus),
        notes=tuple(notes),
    )


async def initialize(services: AgentServices) -> dict[str, int]:
    """Report what the registry already holds. Recovery changes nothing.

    Templates are read straight from the database on demand, so there is no
    in-memory state to rebuild; counting them is enough to say the registry
    survived the restart, and nothing is re-validated or re-published here.
    """
    async with services.db.session_factory() as session:
        repo = AgentTemplateRepo(session)
        return {
            "templates": await repo.count(),
            "published_templates": await repo.count(status="published"),
        }
