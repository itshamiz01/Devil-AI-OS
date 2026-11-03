from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...monitoring.diagnostics import safe_diagnostics
from ..dependencies import get_services, require_permission
from ..schemas.common import envelope

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
async def status(request: Request, principal=Depends(require_permission("system.read"))):
    services = get_services(request)
    return envelope({
        "lifecycle": services.lifecycle.state.value,
        "uptime_seconds": services.lifecycle.uptime_seconds(),
        "tasks": await services.tasks.health(),
        "diagnostics": safe_diagnostics(services.settings),
        "metrics": services.metrics.snapshot(),
    })


@router.get("/resources")
async def resources(request: Request, principal=Depends(require_permission("system.read"))):
    services = get_services(request)
    return envelope(services.monitor.snapshot())
