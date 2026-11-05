from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..api.routes import (
    agent_assignments,
    agent_capabilities,
    agent_factory,
    agent_templates,
    agents,
    approvals,
    auth,
    events,
    health,
    intelligence,
    opportunities,
    system,
    tasks,
)
from ..database.connection import Database
from ..database.repositories import AuditRepo, ConfigRepo, PermissionRepo, PrincipalRepo
from ..events.bus import EventBus
from ..events.subscribers import register_default_subscribers, register_task_approval_subscribers
from ..monitoring.metrics import Metrics
from ..monitoring.system_monitor import SystemMonitor
from ..permissions.approvals import ApprovalService
from ..permissions.engine import PermissionEngine
from ..intelligence.factory import build_intelligence, initialize as initialize_intelligence
from ..opportunities.factory import build_opportunities, initialize as initialize_opportunities
from ..agents.subsystem import build_agents, initialize as initialize_agents
from ..tasks.handlers import clear_research_backend, set_research_backend
from ..permissions.policies import OWNER_PERMISSIONS, PERMISSIONS, SYSTEM_PERMISSIONS
from ..tasks.manager import TaskManager
from .auth import AuthService
from .config import Settings, get_settings
from .emergency import EmergencyController
from .exceptions import AppError
from .health import HealthService
from .lifecycle import Lifecycle, LifecycleState
from .logging import setup_logging

logger = logging.getLogger(__name__)


@dataclass
class Services:
    settings: Settings
    db: Database
    bus: EventBus
    permissions: PermissionEngine
    approvals: ApprovalService
    auth: AuthService
    monitor: SystemMonitor
    emergency: EmergencyController
    tasks: TaskManager
    metrics: Metrics
    lifecycle: Lifecycle
    health: HealthService
    # None when AUTONOMUS_INTELLIGENCE_ENABLED is false. Optional so the P-01
    # application still constructs and shuts down cleanly without P-02.
    intelligence: Any = None
    # None when AUTONOMUS_OPPORTUNITIES_ENABLED is false, for the same reason.
    opportunities: Any = None
    # P-04 agent subsystem. Always assembled, with no phase flag of its own:
    # Stage 3 stores and validates template definitions, which cannot execute
    # anything. The creation engine that does change system behaviour (Stage 4)
    # is what gets a flag, so that a deployment can hold definitions it is not
    # yet allowed to act on.
    agents: Any = None


async def seed_core_data(db: Database, settings: Settings) -> None:
    async with db.session_factory() as session:
        perms = PermissionRepo(session)
        for code, category, description in PERMISSIONS:
            await perms.upsert_definition(code, category, description)
        principals = PrincipalRepo(session)
        system = await principals.by_name("system")
        if not system:
            system = await principals.create("system", "system")
        for code in SYSTEM_PERMISSIONS:
            await perms.assign(system.id, code)
        # Reconcile owner assignments on every startup. The definitions above are
        # upserted, but grant_owner_permissions only runs during bootstrap_owner,
        # so an owner whose database predates a newly added permission would
        # never receive it and could be locked out of a safety control such as
        # system.emergency. Only kind == "owner" is touched: agents, services and
        # the system principal are never widened by this path. Audited only when
        # something actually changed, so normal startups stay quiet.
        for owner in await principals.by_kind("owner"):
            held = {a.permission_code for a in await perms.assignments(owner.id) if a.effect == "allow"}
            missing = [code for code in OWNER_PERMISSIONS if code not in held]
            for code in missing:
                await perms.assign(owner.id, code)
            if missing:
                await AuditRepo(session).record(
                    "permission.owner_reconciled", "allowed", principal_id=owner.id,
                    action="reconcile_owner_permissions", payload={"granted": missing},
                )
        await ConfigRepo(session).set("phase", {"value": "P-01", "external_execution": False, "financial_execution": False})
        await session.commit()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging(settings)
        lifecycle = Lifecycle()
        lifecycle.set(LifecycleState.STARTING)
        db = Database(settings)
        try:
            await db.initialize()
            await seed_core_data(db, settings)
            bus = EventBus(db)
            register_default_subscribers(bus)
            monitor = SystemMonitor(settings)
            permissions = PermissionEngine(db)
            auth_service = AuthService(settings, db)
            approval_service = ApprovalService(db, bus)
            metrics = Metrics()
            # Emergency state is loaded before the task manager starts so that
            # admission checks see it, and it is never cleared here: an emergency
            # that was active when the process died is still active now.
            emergency = EmergencyController(db, bus)
            emergency_state = await emergency.load()
            task_manager = TaskManager(settings, db, bus, monitor, emergency)
            register_task_approval_subscribers(bus, task_manager)
            # Built after the task manager because the orchestrator dispatches
            # through it. Construction performs no I/O and starts no model:
            # health probing is lazy, so an absent runtime cannot delay startup.
            intelligence_services = (
                build_intelligence(settings, db, task_manager)
                if settings.intelligence_enabled else None
            )
            if intelligence_services is not None:
                # Persists configured model registrations and reloads missions
                # stored before the last shutdown (§17, §19.5). Recovery restores
                # visibility only: nothing is re-planned, re-dispatched or
                # re-authorized, and tasks already dispatched stay the task
                # manager's responsibility.
                await initialize_intelligence(intelligence_services)
            # Built after the task manager because research sweeps are submitted
            # through it (§24). Construction opens no socket: the network allowlist
            # starts empty, so nothing is contacted until a source is registered.
            opportunity_services = (
                build_opportunities(settings, db, task_manager, bus)
                if settings.opportunities_enabled else None
            )
            if opportunity_services is not None:
                # Restores persisted sources and opportunities for reading, ranking
                # and reporting. Recovery restores visibility only: nothing is
                # re-researched, re-scored or re-recommended, and no sweep is
                # dispatched, because autonomous scheduling is P-12.
                await initialize_opportunities(opportunity_services)
                # Binds the engine so `research.sweep` tasks can execute. The
                # binding is explicit rather than implicit application state, and
                # the handler fails loudly when it is missing.
                set_research_backend(opportunity_services)
            # Built last, and only when enabled. Construction performs no I/O,
            # and recovery only reports what the registry already holds: nothing
            # is re-validated, re-published, re-created or re-approved on
            # startup, and a queued creation request stays queued until an owner
            # drains it.
            #
            # The approval service, monitor and emergency controller are passed
            # in so a creation decision can see the same facts the rest of the
            # system acts on: an emergency stop must refuse a creation, resource
            # pressure must queue one, and a gated creation must open a real
            # approval rather than a private one.
            agent_services = (
                build_agents(settings, db, bus, approvals=approval_service,
                             monitor=monitor, emergency=emergency,
                             permissions=permissions)
                if settings.agents_enabled else None
            )
            if agent_services is not None:
                await initialize_agents(agent_services)
            services = Services(
                settings=settings, db=db, bus=bus, permissions=permissions,
                approvals=approval_service, auth=auth_service, monitor=monitor,
                emergency=emergency, tasks=task_manager, metrics=metrics,
                lifecycle=lifecycle, health=None,  # type: ignore[arg-type]
                intelligence=intelligence_services,
                opportunities=opportunity_services,
                agents=agent_services,
            )
            services.health = HealthService(services)
            app.state.services = services
            await bus.start()
            await bus.publish_new("ApplicationStarted", "lifecycle", {})
            await task_manager.start()
            if emergency_state["active"]:
                # Recovery re-queued work while the process was down; bring it
                # back under the still-active emergency stop.
                await task_manager.apply_emergency_stop()
                lifecycle.set(LifecycleState.DEGRADED)
            else:
                lifecycle.set(LifecycleState.READY)
            await bus.publish_new("ApplicationReady", "lifecycle", {})
            yield
        except Exception as exc:
            lifecycle.set(LifecycleState.FAILED, str(exc))
            logger.exception("Application startup failed", extra={"component": "lifecycle"})
            raise
        finally:
            if hasattr(app.state, "services"):
                services = app.state.services
                lifecycle.set(LifecycleState.STOPPING)
                try:
                    await services.bus.publish_new("ApplicationStopping", "lifecycle", {})
                    await services.tasks.shutdown()
                    await services.bus.drain()
                    await services.bus.publish_new("ApplicationStopped", "lifecycle", {})
                    await services.bus.drain()
                    await services.bus.stop()
                finally:
                    # Unbind before the database goes away, so a late research task
                    # cannot reach a disposed engine.
                    clear_research_backend()
                    await services.db.dispose()
                lifecycle.set(LifecycleState.STOPPED)

    app = FastAPI(
        title="AUTONOMUS Core OS API",
        version="0.1.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        correlation_id = request.headers.get("x-correlation-id") or str(uuid4())
        request.state.correlation_id = correlation_id
        if hasattr(app.state, "services"):
            app.state.services.metrics.increment("http_requests")
        response = await call_next(request)
        response.headers["x-correlation-id"] = correlation_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}, "correlation_id": getattr(request.state, "correlation_id", None)})

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": "Request validation failed", "details": exc.errors()}, "correlation_id": getattr(request.state, "correlation_id", None)})

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logger.exception("Unhandled API error", extra={"component": "api", "correlation_id": getattr(request.state, "correlation_id", None)})
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Internal server error"}, "correlation_id": getattr(request.state, "correlation_id", None)})

    for router in (
        auth.router, health.router, system.router, tasks.router, agents.router,
        agent_templates.router, agent_factory.router,
        agent_assignments.router, agent_capabilities.router, approvals.router,
        events.router,
        intelligence.router, opportunities.router,
    ):
        app.include_router(router, prefix="/api/v1")
    return app
