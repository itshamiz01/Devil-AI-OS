from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...core.application import Application
from ...permissions.models import Principal
from ..dependencies import correlation_id, get_application, require_permission
from ..schemas.common import ok

router = APIRouter(tags=["system"])


@router.get("/system/status")
async def system_status(request: Request, application: Application = Depends(get_application),
                        _: Principal = Depends(require_permission("read_system_data"))):
    return ok(application.monitor.status(application.lifecycle.state.value),
              correlation_id(request))


@router.get("/system/resources")
async def system_resources(request: Request, application: Application = Depends(get_application),
                           _: Principal = Depends(require_permission("read_system_data"))):
    resources = application.monitor.resources()
    return ok({"resources": resources,
               "threshold_violations": application.monitor.threshold_violations(resources)},
              correlation_id(request))
