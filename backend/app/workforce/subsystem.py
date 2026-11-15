"""Assembly for the P-WORKFORCE subsystem.

Mirrors the other four subsystems: ``build_workforce`` constructs the layer
from validated settings and performs no I/O, and ``initialize`` restores what
was persisted before the last shutdown - which, for the workforce, means
running the idempotent baseline seed so the 111-employee organization is
present, and reporting what the registry already holds.

The workforce is built **after** the agent subsystem because it registers its
employees through the existing agent registry and grants capabilities through
the existing capability service. It does not create a second registry,
scheduler, memory engine or financial ledger - it reuses them.
"""

from __future__ import annotations

from typing import Any

from ..core.config import Settings
from ..database.connection import Database
from .ceo import CeoOffice
from .memory import MemoryStore
from .performance import PerformanceEngine
from .registry import ensure_baseline
from .service import WorkforceService

__all__ = ["WorkforceServices", "build_workforce", "initialize"]


class WorkforceServices:
    """The P-WORKFORCE subsystem as the rest of the application sees it."""

    def __init__(self, *, settings: Settings, db: Database,
                 workforce: WorkforceService, ceo: CeoOffice,
                 performance: PerformanceEngine, memory: MemoryStore,
                 notes: tuple[str, ...] = ()) -> None:
        self.settings = settings
        self.db = db
        self.workforce = workforce
        self.ceo = ceo
        self.performance = performance
        self.memory = memory
        self.notes = list(notes)

    def status(self) -> dict[str, Any]:
        """What is assembled, and what is deliberately not yet."""
        return {
            "enabled": True,
            "stage": "P-WORKFORCE: 111-employee virtual organization",
            "organization": True,
            "ceo": True,
            "managers": True,
            "employees": True,
            "work_orders": True,
            "handoffs": True,
            "communication": True,
            "performance": True,
            "memory": True,
            "notes": tuple(self.notes),
        }


def build_workforce(settings: Settings, db: Database, *,
                    capabilities: Any = None,
                    bus: Any = None) -> WorkforceServices:
    """Assemble the workforce layer. Construction performs no I/O.

    ``capabilities`` is the P-04 capability service the baseline seed grants
    through. It is optional so the subsystem can be assembled in tests and
    degraded deployments; without it, the baseline is still registered (identity
    and hierarchy) but no capability grants are made.
    """
    workforce = WorkforceService(settings=settings, db=db)
    ceo = CeoOffice(settings=settings, db=db, workforce=workforce)
    performance = PerformanceEngine(settings=settings, db=db)
    memory = MemoryStore(settings=settings, db=db)
    notes = [
        "the 111-employee baseline is registered through the existing agent "
        "registry and capability catalog - no second registry, scheduler, "
        "memory engine or financial ledger is created",
        "the CEO, managers and employees are deterministic orchestration over "
        "real records; the organization is fully operational with no inference "
        "runtime installed and activates models through the shared ModelRouter "
        "when one is registered",
        "completion is judged, not accepted: a work order reaches COMPLETED "
        "only when its deliverable satisfies the verification requirements and "
        "carries evidence",
        "performance KPIs are computed from verified work-order outcomes, never "
        "self-reported, and a policy violation cannot be offset by productivity",
        "employee memory is scoped and isolated; cross-department access occurs "
        "only through approved handoffs, and credentials are never stored in "
        "ordinary memory",
    ]
    return WorkforceServices(
        settings=settings, db=db, workforce=workforce, ceo=ceo,
        performance=performance, memory=memory, notes=tuple(notes))


async def initialize(services: WorkforceServices, *,
                     capabilities: Any = None,
                     actor_id: str | None = None,
                     bus: Any = None) -> dict[str, Any]:
    """Run the idempotent baseline seed and report the organization state.

    Seeding is keyed on stable employee IDs, so a restart never duplicates an
    employee. An existing baseline is left exactly as it was.

    The baseline grants publish capability events through the bus. These are
    runtime notifications, and the grant itself is already recorded in the
    audit trail (the source of truth). Because seeding runs before the bus
    dispatcher starts, those events would accumulate in the queue and overflow
    its backpressure limit, so the queue is drained here. No audit record is
    lost: every grant is written and committed before its event is published.
    """
    if not services.settings.workforce_seed_baseline:
        return {"seeded": False, "reason": "workforce_seed_baseline is disabled"}
    summary = await ensure_baseline(
        services.db, services.settings,
        capabilities=capabilities, bus=None, actor_id=actor_id)
    if bus is not None:
        # Drain seed-time events: they are notifications, the grants they
        # describe are already audited, and the dispatcher has not started.
        # Each removed item must call task_done(), otherwise the queue's
        # unfinished-task counter stays positive and the eventual
        # queue.join() during shutdown would wait on tasks that were
        # deliberately discarded.
        while not bus.queue.empty():
            try:
                bus.queue.get_nowait()
                bus.queue.task_done()
            except Exception:
                break
    overview = await services.workforce.overview()
    return {
        "seeded": True,
        "seed_summary": summary,
        "organization": {
            "total_employees": overview["total_employees"],
            "department_count": overview["department_count"],
        },
    }
