from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...core.exceptions import NotFoundError
from ...database.repositories import AgentRepo
from ..dependencies import get_services, require_permission
from ..schemas.common import AgentView, envelope

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
async def list_agents(request: Request, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), principal=Depends(require_permission("agents.read"))):
    services = get_services(request)
    async with services.db.session_factory() as session:
        agents = await AgentRepo(session).list(limit, offset)
    return envelope([AgentView.model_validate(a).model_dump(mode="json") for a in agents], limit=limit, offset=offset)


@router.get("/{agent_id}")
async def get_agent(agent_id: str, request: Request, principal=Depends(require_permission("agents.read"))):
    services = get_services(request)
    async with services.db.session_factory() as session:
        agent = await AgentRepo(session).get(agent_id)
    if not agent:
        raise NotFoundError("Agent not found")
    return envelope(AgentView.model_validate(agent).model_dump(mode="json"))
