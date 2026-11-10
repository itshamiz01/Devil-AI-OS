from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ...core.application import Application
from ...core.health import liveness, readiness
from ...monitoring.diagnostics import diagnostics
from ...permissions.models import Principal
from ..dependencies import correlation_id, get_application, require_permission
from ..schemas.common import ok

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def health_live(request: Request, application: Application = Depends(get_application)):
    """Liveness is intentionally unauthenticated and reveals nothing beyond
    the fact that the process responds (P-01 §10.1/§13)."""
    return ok(liveness(application.lifecycle.state.value), correlation_id(request))


@router.get("/health/ready")
async def health_ready(request: Request, application: Application = Depends(get_application),
                       _: Principal = Depends(require_permission("read_system_data"))):
    violations = application.monitor.threshold_violations()
    body, is_ready = readiness(application.lifecycle.state.value,
                               application.monitor.database_healthy(), violations)
    status_code = 200 if is_ready else 503
    return JSONResponse(status_code=status_code,
                        content=ok(body, correlation_id(request)))


@router.get("/health")
async def health(request: Request, application: Application = Depends(get_application),
                 _: Principal = Depends(require_permission("read_system_data"))):
    body, _ = readiness(application.lifecycle.state.value,
                        application.monitor.database_healthy(),
                        application.monitor.threshold_violations())
    body["diagnostics"] = diagnostics(application.settings, application.lifecycle.state.value,
                                      application.monitor.database_healthy())
    body["auth_mode"] = application.auth.auth_mode
    body["recovered_tasks"] = len(application.recovered_task_ids)
    return ok(body, correlation_id(request))
