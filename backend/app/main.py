"""FastAPI entry point (P-01 §12). Run with:
    uvicorn app.main:app --host 127.0.0.1 --port 8000
Loopback binding is the default (settings.host); see scripts/ for launchers.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api.routes import (
    agent_factory, agents, approvals, auth, business, dashboard, economy,
    events, experience, growth, integrations, knowledge, voice,
    operations, portfolio,
    execution, financial, health, intelligence, memory, opportunities,
    security, survival, system, tasks, reliability,
)
from .core.application import Application
from .core.config import Settings
from .core.exceptions import AutonomusError
from .core.version import APP_VERSION

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    application = Application(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await application.startup()
        yield
        await application.shutdown()

    app = FastAPI(title=settings.app_name, version=APP_VERSION, lifespan=lifespan)
    app.state.application = application

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        request.state.correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        # P-14 Stage B (DEF-I2): the request's correlation id is also
        # the ambient event correlation for everything this request
        # triggers, so bus events join the request's trace chain.
        from .events.bus import correlation_context
        token = correlation_context.set(request.state.correlation_id)
        try:
            response = await call_next(request)
        finally:
            correlation_context.reset(token)
        response.headers["x-correlation-id"] = request.state.correlation_id
        return response

    @app.exception_handler(AutonomusError)
    async def autonomus_error_handler(request: Request, exc: AutonomusError):
        return JSONResponse(status_code=exc.status_code, content={
            "success": False, "data": None,
            "error": {"code": exc.code, "message": exc.message, "details": exc.details},
            "correlation_id": getattr(request.state, "correlation_id", None), "meta": None})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={
            "success": False, "data": None,
            "error": {"code": "validation_error", "message": "request validation failed",
                      "details": {"errors": exc.errors()}},
            "correlation_id": getattr(request.state, "correlation_id", None), "meta": None})

    for router in (health.router, system.router, auth.router, tasks.router,
                   agents.router, approvals.router, events.router, intelligence.router,
                   opportunities.router, agent_factory.router, execution.router,
                   business.router, financial.router, survival.router, memory.router,
                   security.router, dashboard.router, operations.router,
                   portfolio.router, reliability.router, economy.router,
                   growth.router, experience.router, integrations.router,
                   voice.router, knowledge.router):
        app.include_router(router, prefix=API_PREFIX)

    # Expansion Feature 2: publish each operation's required
    # permission + authorization depth as OpenAPI extensions
    # (x-required-permission / x-authorization-depth) — the Gate 2
    # review §2 fix for permission names being invisible in the
    # schema. Additive metadata; no route behaviour changes.
    from .integrations.catalogue import decorate_openapi
    decorate_openapi(app)

    # P-11 Command Center: serve the built frontend (frontend/dist) from the
    # same process when a build exists — local-first, single process. The API
    # stays authoritative under /api/v1; the SPA is presentation only.
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/app", StaticFiles(directory=str(frontend_dist), html=True),
                  name="command-center")
    return app


app = create_app()
