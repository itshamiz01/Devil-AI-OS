from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..dependencies import get_services, require_permission
from ..schemas.common import envelope

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live():
    return envelope({"status": "alive"})


@router.get("/health/ready")
async def ready(request: Request):
    services = get_services(request)
    is_ready = await services.health.ready()
    return JSONResponse(status_code=200 if is_ready else 503, content=envelope({"ready": is_ready}))


@router.get("/health")
async def health(request: Request, principal=Depends(require_permission("system.read"))):
    services = get_services(request)
    return envelope(await services.health.detailed())
