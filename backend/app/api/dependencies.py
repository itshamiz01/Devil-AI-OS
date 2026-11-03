from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.exceptions import UnauthorizedError
from ..database.models import Principal

bearer = HTTPBearer(auto_error=False)


def get_services(request: Request):
    return request.app.state.services


async def get_principal(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if not credentials:
        raise UnauthorizedError("Authentication required")
    services = get_services(request)
    return await services.auth.authenticate(credentials.credentials)


def require_permission(permission: str, resource: str = "*"):
    async def dependency(request: Request, principal: Principal = Depends(get_principal)) -> Principal:
        services = get_services(request)
        await services.permissions.check(principal.id, permission, resource, getattr(request.state, "correlation_id", None))
        return principal
    return dependency
