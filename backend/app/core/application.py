from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..api.routes import agents, approvals, auth, events, health, system, tasks
from ..database.connection import Database
from ..database.repositories import ConfigRepo, PermissionRepo, PrincipalRepo
from ..events.bus import EventBus
from ..events.subscribers import register_default_subscribers
from ..monitoring.metrics import Metrics
from ..monitoring.system_monitor import SystemMonitor
from ..permissions.approvals import ApprovalService
from ..permissions.engine import PermissionEngine
from ..permissions.policies import PERMISSIONS, SYSTEM_PERMISSIONS
from ..tasks.manager import TaskManager
from .auth import AuthService
from .config import Settings, get_settings
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
    tasks: TaskManager
    metrics: Metrics
    lifecycle: Lifecycle
    health: HealthService


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
            task_manager = TaskManager(settings, db, bus, monitor)
            services = Services(settings, db, bus, permissions, approval_service, auth_service, monitor, task_manager, metrics, lifecycle, None)  # type: ignore[arg-type]
            services.health = HealthService(services)
            app.state.services = services
            await bus.start()
            await bus.publish_new("ApplicationStarted", "lifecycle", {})
            await task_manager.start()
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

    for router in (auth.router, health.router, system.router, tasks.router, agents.router, approvals.router, events.router):
        app.include_router(router, prefix="/api/v1")
    return app
