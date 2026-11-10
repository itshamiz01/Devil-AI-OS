"""P-11 Command Center API: scoped aggregation + dashboard-owned state.

Every route requires authentication; read routes require the existing
``read_system_data`` permission (P-01 engine decides — the dashboard adds
no authority of its own). Preferences are scoped to the calling principal.
No route returns another engine's raw records beyond what that engine's
own endpoints already expose to the same principal.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ...core.application import Application
from ...dashboard.service import DashboardService
from ...permissions.models import Principal
from ..dependencies import correlation_id, get_application, get_principal, require_permission
from ..schemas.common import ok

router = APIRouter(tags=["dashboard"])

READ = require_permission("read_system_data")


def _svc(application: Application) -> DashboardService:
    return DashboardService(application)


class PreferencesIn(BaseModel):
    # extra="forbid": a misspelled preference key must fail loudly, not
    # silently no-op (the service enforces the same rule for direct
    # callers).
    model_config = ConfigDict(extra="forbid")

    sidebar_collapsed: bool | None = None
    default_view: str | None = Field(default=None, max_length=60)
    timezone: str | None = Field(default=None, max_length=60)
    currency: str | None = Field(default=None, max_length=8)
    density: str | None = Field(default=None, pattern="^(comfortable|compact)$")
    reduce_motion: bool | None = None


@router.get("/dashboard/overview")
async def overview(request: Request, currency: str = Query("INR"),
                   application: Application = Depends(get_application),
                   _: Principal = Depends(READ)):
    return ok(_svc(application).overview(currency), correlation_id(request))


@router.get("/dashboard/system-health")
async def system_health(request: Request,
                        application: Application = Depends(get_application),
                        _: Principal = Depends(READ)):
    return ok(await _svc(application).system_health(), correlation_id(request))


@router.get("/dashboard/activity")
async def activity(request: Request, limit: int = Query(50, ge=1, le=200),
                   application: Application = Depends(get_application),
                   _: Principal = Depends(READ)):
    return ok(_svc(application).activity(limit), correlation_id(request))


@router.get("/dashboard/attention")
async def attention(request: Request,
                    application: Application = Depends(get_application),
                    _: Principal = Depends(READ)):
    return ok(_svc(application).attention(), correlation_id(request))


@router.get("/dashboard/agents/summary")
async def agents_summary(request: Request,
                         application: Application = Depends(get_application),
                         _: Principal = Depends(READ)):
    return ok(_svc(application).agents_summary(), correlation_id(request))


@router.get("/dashboard/businesses/summary")
async def businesses_summary(request: Request,
                             application: Application = Depends(get_application),
                             _: Principal = Depends(READ)):
    return ok(_svc(application).businesses_summary(), correlation_id(request))


@router.get("/dashboard/opportunities/summary")
async def opportunities_summary(request: Request,
                                application: Application = Depends(get_application),
                                _: Principal = Depends(READ)):
    return ok(_svc(application).opportunities_summary(), correlation_id(request))


@router.get("/dashboard/execution/summary")
async def execution_summary(request: Request,
                            application: Application = Depends(get_application),
                            _: Principal = Depends(READ)):
    return ok(_svc(application).execution_summary(), correlation_id(request))


@router.get("/dashboard/finance/summary")
async def finance_summary(request: Request, currency: str = Query("INR"),
                          application: Application = Depends(get_application),
                          _: Principal = Depends(READ)):
    return ok(_svc(application).finance_summary(currency), correlation_id(request))


@router.get("/dashboard/security/summary")
async def security_summary(request: Request,
                           application: Application = Depends(get_application),
                           _: Principal = Depends(READ)):
    return ok(_svc(application).security_summary(), correlation_id(request))


@router.get("/dashboard/survival/overview")
async def survival_overview(request: Request,
                            application: Application = Depends(get_application),
                            _: Principal = Depends(READ)):
    return ok(_svc(application).survival_overview(), correlation_id(request))


@router.get("/dashboard/approvals/summary")
async def approvals_summary(request: Request,
                            application: Application = Depends(get_application),
                            _: Principal = Depends(READ)):
    return ok(_svc(application).approvals_summary(), correlation_id(request))


@router.get("/dashboard/notifications")
async def notifications(request: Request,
                        application: Application = Depends(get_application),
                        principal: Principal = Depends(READ)):
    return ok(_svc(application).notifications(principal), correlation_id(request))


@router.post("/dashboard/notifications/{notification_id:path}/read")
async def notification_read(notification_id: str, request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(READ)):
    return ok(_svc(application).mark_notification_read(principal, notification_id),
              correlation_id(request))


@router.post("/dashboard/notifications/{notification_id:path}/dismiss")
async def notification_dismiss(notification_id: str, request: Request,
                               application: Application = Depends(get_application),
                               principal: Principal = Depends(READ)):
    return ok(_svc(application).dismiss_notification(principal, notification_id),
              correlation_id(request))


@router.get("/dashboard/search")
async def search(request: Request, q: str = Query(min_length=2, max_length=200),
                 application: Application = Depends(get_application),
                 _: Principal = Depends(READ)):
    return ok(_svc(application).search(q), correlation_id(request))


@router.get("/dashboard/preferences")
async def get_preferences(request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal)):
    return ok(_svc(application).get_preferences(principal), correlation_id(request))


@router.put("/dashboard/preferences")
async def put_preferences(body: PreferencesIn, request: Request,
                          application: Application = Depends(get_application),
                          principal: Principal = Depends(get_principal)):
    patch = body.model_dump(exclude_unset=True, exclude_none=True)
    return ok(_svc(application).put_preferences(principal, patch),
              correlation_id(request))
