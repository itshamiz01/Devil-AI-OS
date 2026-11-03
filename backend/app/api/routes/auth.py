from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...core.exceptions import UnauthorizedError
from ..dependencies import get_principal, get_services
from ..schemas.common import LoginRequest, PrincipalView, envelope

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(request: Request, body: LoginRequest):
    services = get_services(request)
    client_key = request.client.host if request.client else "unknown"
    token, expires = await services.auth.login(body.username, body.password, client_key)
    return envelope({"access_token": token, "token_type": "bearer", "expires_at": expires.isoformat()})


@router.post("/logout")
async def logout(request: Request, principal=Depends(get_principal)):
    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    await get_services(request).auth.logout(token)
    return envelope({"logged_out": True})


@router.get("/me")
async def me(principal=Depends(get_principal)):
    return envelope(PrincipalView.model_validate(principal).model_dump(mode="json"))
