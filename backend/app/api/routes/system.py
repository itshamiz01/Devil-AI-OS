from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from pydantic import BaseModel, Field

from ...core.lifecycle import LifecycleState
from ...monitoring.diagnostics import safe_diagnostics
from ..dependencies import get_services, require_permission
from ..schemas.common import envelope


class EmergencyRequest(BaseModel):
    """Reason is mandatory so the audit trail records why the owner acted.

    Bounded length because it is persisted and echoed back to authorized
    callers; it is never written to logs (see core/emergency.py).
    """

    reason: str = Field(min_length=1, max_length=2000)

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


# --- emergency stop ------------------------------------------------------
# Owner-only via the system.emergency permission, which OWNER_PERMISSIONS
# derives automatically and SYSTEM_PERMISSIONS deliberately omits, so no
# non-owner principal can halt or restart the system.


@router.get("/emergency")
async def emergency_status(request: Request, principal=Depends(require_permission("system.read"))):
    services = get_services(request)
    return envelope(await services.emergency.state())


@router.post("/emergency/activate")
async def emergency_activate(request: Request, body: EmergencyRequest, principal=Depends(require_permission("system.emergency"))):
    services = get_services(request)
    correlation_id = getattr(request.state, "correlation_id", None)
    state = await services.emergency.activate(principal.id, body.reason, correlation_id)
    # Cancel/pause eligible in-flight work now, rather than waiting for the next
    # scheduler tick, so the halt takes effect immediately.
    affected = await services.tasks.apply_emergency_stop(correlation_id)
    services.lifecycle.set(LifecycleState.DEGRADED)
    return envelope({**state, "in_flight": affected})


@router.post("/emergency/clear")
async def emergency_clear(request: Request, body: EmergencyRequest, principal=Depends(require_permission("system.emergency"))):
    services = get_services(request)
    correlation_id = getattr(request.state, "correlation_id", None)
    state = await services.emergency.deactivate(principal.id, body.reason, correlation_id)
    # Restoring READY is a health statement, not a resume: paused tasks stay
    # paused until the owner resumes them explicitly.
    services.lifecycle.set(LifecycleState.READY)
    return envelope(state)
