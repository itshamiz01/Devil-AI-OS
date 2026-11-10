from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ...core.application import Application
from ...core.exceptions import AuthenticationError
from ...permissions.models import Principal
from ..dependencies import correlation_id, get_application, get_principal
from ..schemas.common import ok

router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    # Expansion Feature 1 (Identity & Device Security): optional
    # device binding. When either field is presented, verification
    # is mandatory and fail-closed (see AuthService._device_gate).
    device_id: str | None = None
    device_secret: str | None = None


@router.post("/auth/login")
async def login(body: LoginIn, request: Request,
                application: Application = Depends(get_application)):
    token = application.auth.login(body.username, body.password,
                                   device_id=body.device_id,
                                   device_secret=body.device_secret)
    if token is None:
        raise AuthenticationError("invalid username or password")
    return ok({"access_token": token, "token_type": "bearer",
               "principal": f"owner:{body.username}"}, correlation_id(request))


@router.get("/auth/me")
async def me(request: Request, principal: Principal = Depends(get_principal),
             application: Application = Depends(get_application)):
    return ok({"principal_type": principal.type.value, "principal_id": principal.id,
               "auth_mode": application.auth.auth_mode}, correlation_id(request))
