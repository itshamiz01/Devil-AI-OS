from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...database.repositories import AuditRepo, EventRepo
from ..dependencies import get_services, require_permission
from ..schemas.common import AuditView, EventView, envelope

router = APIRouter(tags=["events"])


@router.get("/events")
async def list_events(request: Request, event_type: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), principal=Depends(require_permission("events.read"))):
    services = get_services(request)
    async with services.db.session_factory() as session:
        events = await EventRepo(session).list(limit, offset, event_type)
    return envelope([EventView.model_validate(e).model_dump(mode="json") for e in events], limit=limit, offset=offset)


@router.get("/audit")
async def list_audit(request: Request, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), principal=Depends(require_permission("audit.read"))):
    services = get_services(request)
    async with services.db.session_factory() as session:
        events = await AuditRepo(session).list(limit, offset)
    return envelope([AuditView.model_validate(e).model_dump(mode="json") for e in events], limit=limit, offset=offset)
