"""Events API: persisted critical events only, permission-filtered."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...core.application import Application
from ...database.repositories.core import SystemEventRepository
from ...permissions.models import Principal
from ..dependencies import correlation_id, get_application, require_permission
from ..schemas.common import page

router = APIRouter(tags=["events"])


@router.get("/events")
async def list_events(request: Request, event_type: str | None = None,
                      limit: int = Query(default=50, ge=1, le=200),
                      offset: int = Query(default=0, ge=0),
                      application: Application = Depends(get_application),
                      _: Principal = Depends(require_permission("read_system_data"))):
    session = application.session_factory()
    try:
        rows, total = SystemEventRepository(session).list(event_type, limit, offset)
        data = [{
            "event_id": e.event_id, "event_type": e.event_type, "source": e.source,
            "correlation_id": e.correlation_id, "task_id": e.task_id,
            "business_id": e.business_id, "workflow_id": e.workflow_id,
            "processing_status": e.processing_status,
            "severity": e.severity, "payload": e.payload,
            "created_at": e.created_at.isoformat() if e.created_at else "",
        } for e in rows]
        return page(data, total, limit, offset, correlation_id(request))
    finally:
        session.close()
