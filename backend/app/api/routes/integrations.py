"""Universal Integration Framework routes (/api/v1/integrations/...).

Expansion Feature 2. Authorization follows the Gate 2 review §4.2
inheritance contract and this feature's own standard — BOTH depths,
deliberately: routes gate on the ``Permission`` enum (reads:
``read_system_data``; configuration: ``modify_system_config``;
invocation: ``execute_tools`` at the route), and governed
execution additionally passes through the P-10 PermissionBroker in
the service layer. Owner-only lifecycle acts are re-checked in the
service layer (the backend is the authority, never the caller).

No route accepts or returns a secret value: configuration carries
a P-10 secret registry NAME, and values are resolved by P-10 at
invocation time only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...core.application import Application
from ...permissions.models import Permission, Principal
from ..dependencies import (
    correlation_id, get_application, get_principal, require_permission,
)
from ..schemas.common import PageMeta, ok, page
from ..schemas.integrations import (
    ConnectorConfigureIn, ConnectorInvokeIn, ConnectorRegisterIn,
)

router = APIRouter(tags=["integrations"])

READ = require_permission(Permission.READ_SYSTEM_DATA)
CONFIG = require_permission(Permission.MODIFY_SYSTEM_CONFIG)
INVOKE = require_permission(Permission.EXECUTE_TOOLS)


def _svc(application: Application):
    return application.integrations


# ------------------------------------------------------------ framework
@router.get("/integrations/framework/status")
async def framework_status(request: Request,
                           application: Application = Depends(get_application),
                           _: Principal = Depends(READ)):
    return ok(_svc(application).framework_status(), correlation_id(request))


@router.get("/integrations/api-catalogue")
async def api_catalogue(request: Request,
                        _: Principal = Depends(READ)):
    """The machine-readable API contract catalogue: every
    operation's required permission + authorization depth, built
    from the live application (Gate 2 review §2 fixes 1 + 3)."""
    from ...integrations.catalogue import build_catalogue
    return ok(build_catalogue(request.app), correlation_id(request))


# -------------------------------------------------------------- registry
@router.get("/integrations")
async def list_connectors(request: Request,
                          application: Application = Depends(get_application),
                          _: Principal = Depends(READ),
                          lifecycle_status: str | None = Query(default=None),
                          state: str | None = Query(default=None),
                          source: str | None = Query(default=None),
                          limit: int = Query(default=100, ge=1, le=500),
                          offset: int = Query(default=0, ge=0)):
    rows, total = _svc(application).list_connectors(
        lifecycle_status=lifecycle_status, state=state, source=source,
        limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.post("/integrations", status_code=201)
async def register_connector(body: ConnectorRegisterIn, request: Request,
                             application: Application = Depends(get_application),
                             principal: Principal = Depends(CONFIG)):
    result = _svc(application).register_connector(
        principal, body.model_dump())
    return ok(result, correlation_id(request))


@router.get("/integrations/invocations")
async def list_all_invocations(request: Request,
                               application: Application = Depends(get_application),
                               _: Principal = Depends(READ),
                               outcome: str | None = Query(default=None),
                               limit: int = Query(default=50, ge=1, le=200),
                               offset: int = Query(default=0, ge=0)):
    rows, total = _svc(application).list_invocations(
        outcome=outcome, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))


@router.get("/integrations/{key}")
async def get_connector(key: str, request: Request,
                        application: Application = Depends(get_application),
                        _: Principal = Depends(READ)):
    return ok(_svc(application).get_connector(key), correlation_id(request))


@router.post("/integrations/{key}/configure")
async def configure_connector(key: str, body: ConnectorConfigureIn,
                              request: Request,
                              application: Application = Depends(get_application),
                              principal: Principal = Depends(CONFIG)):
    result = _svc(application).configure_connector(
        principal, key, body.model_dump())
    return ok(result, correlation_id(request))


@router.post("/integrations/{key}/enable")
async def enable_connector(key: str, request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(CONFIG)):
    return ok(_svc(application).set_enabled(principal, key, True),
              correlation_id(request))


@router.post("/integrations/{key}/disable")
async def disable_connector(key: str, request: Request,
                            application: Application = Depends(get_application),
                            principal: Principal = Depends(CONFIG)):
    return ok(_svc(application).set_enabled(principal, key, False),
              correlation_id(request))


@router.post("/integrations/{key}/health")
async def health_connector(key: str, request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(READ)):
    result = await _svc(application).health_check(principal, key)
    return ok(result, correlation_id(request))


@router.post("/integrations/{key}/invoke")
async def invoke_connector(key: str, body: ConnectorInvokeIn,
                           request: Request,
                           application: Application = Depends(get_application),
                           principal: Principal = Depends(INVOKE)):
    result = await _svc(application).invoke(
        principal, key, body.capability, body.payload,
        approval_id=body.approval_id, capability_id=body.capability_id,
        idempotency_key=body.idempotency_key,
        correlation_id=correlation_id(request))
    return ok(result, correlation_id(request))


@router.get("/integrations/{key}/invocations")
async def list_connector_invocations(
        key: str, request: Request,
        application: Application = Depends(get_application),
        _: Principal = Depends(READ),
        outcome: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0)):
    rows, total = _svc(application).list_invocations(
        connector_key=key, outcome=outcome, limit=limit, offset=offset)
    return page(rows, total, limit, offset, correlation_id(request))
