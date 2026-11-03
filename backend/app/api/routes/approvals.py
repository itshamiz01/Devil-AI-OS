from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ...permissions.models import ApprovalCreateRequest, ApprovalDecisionRequest, ApprovalView
from ..dependencies import get_services, require_permission
from ..schemas.common import envelope

router = APIRouter(prefix="/approvals", tags=["approvals"])


def view(approval) -> dict:
    return ApprovalView.model_validate(approval).model_dump(mode="json")


@router.post("", status_code=201)
async def create(request: Request, body: ApprovalCreateRequest, principal=Depends(require_permission("approvals.request"))):
    services = get_services(request)
    approval = await services.approvals.create(principal.id, body, getattr(request.state, "correlation_id", None))
    return envelope(view(approval))


@router.get("")
async def list_approvals(request: Request, status: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), principal=Depends(require_permission("approvals.request"))):
    services = get_services(request)
    from ...database.repositories import ApprovalRepo
    async with services.db.session_factory() as session:
        approvals = await ApprovalRepo(session).list(status, limit, offset)
    return envelope([view(a) for a in approvals], limit=limit, offset=offset)


@router.get("/{approval_id}")
async def get_approval(approval_id: str, request: Request, principal=Depends(require_permission("approvals.request"))):
    services = get_services(request)
    return envelope(view(await services.approvals.get(approval_id)))


@router.post("/{approval_id}/decision")
async def decide(approval_id: str, request: Request, body: ApprovalDecisionRequest, principal=Depends(require_permission("approvals.decide"))):
    services = get_services(request)
    approval = await services.approvals.decide(principal.id, approval_id, body, getattr(request.state, "correlation_id", None))
    return envelope(view(approval))
