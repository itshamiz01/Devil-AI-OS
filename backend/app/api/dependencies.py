"""API dependencies: application access, correlation IDs, authentication."""
from __future__ import annotations

import uuid

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.application import Application
from ..core.exceptions import AuthenticationError, PermissionDeniedError
from ..permissions.models import Principal

_bearer = HTTPBearer(auto_error=False)


def get_application(request: Request) -> Application:
    return request.app.state.application


def correlation_id(request: Request) -> str:
    cid = getattr(request.state, "correlation_id", None)
    if not cid:
        cid = str(uuid.uuid4())
        request.state.correlation_id = cid
    return cid


def get_principal(request: Request,
                  credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Principal:
    application: Application = request.app.state.application
    token = credentials.credentials if credentials else None
    principal = application.auth.resolve_bearer(token)
    if principal is None:
        raise AuthenticationError("missing or invalid credentials")
    return principal


def require_permission(permission: str):
    def _dependency(request: Request, principal: Principal = Depends(get_principal)) -> Principal:
        application: Application = request.app.state.application
        decision = application.permissions.check(
            principal, permission, correlation_id=correlation_id(request))
        if not decision.allowed:
            raise PermissionDeniedError(
                f"permission '{permission}' denied", details={"reason": decision.reason})
        return principal

    # Expansion Feature 2: record the permission on the closure so
    # the integration framework's API catalogue can publish it as
    # OpenAPI metadata (x-required-permission). Metadata only — the
    # decision logic above is unchanged (Gate 2 review §2 fix 1).
    _dependency.__permission__ = str(getattr(permission, "value", permission))
    return _dependency
