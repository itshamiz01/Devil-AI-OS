"""Agent capability API (P-04 Stage 5).

Two resource families, one authority behind them:

* ``/api/v1/agent-capabilities`` — the catalog. Read-only, and deliberately so:
  the catalog is defined in code and reconciled at startup, because a capability
  that could be added over HTTP could be added at level 0 by whoever holds the
  grant permission.
* ``/api/v1/agents/{agent_id}/permissions`` — the grants against it.

Authorization is enforced per operation:

* ``agents.capabilities.read``  — read the catalog, the grants and the status
* ``agents.permissions.grant``  — grant and revoke

Both derive into ``OWNER_PERMISSIONS`` and neither is in ``SYSTEM_PERMISSIONS``,
so the application can never widen its own authority. Deciding a level-2 grant is
**not** exposed here: it goes through ``POST /approvals/{id}/decision`` under the
pre-existing ``approvals.decide``, so the owner has one approval queue for every
gated action in the system.

Four disclosure rules shape the responses.

* **A refusal carries its reason and its level.** Granting a prohibited
  capability is a `403` with code `capability_prohibited` and the reason the
  catalog states; a disabled one is a `409` naming what has to exist first.
  "Denied" without a reason is not an answer an owner can act on.
* **A grant reports the conditions that were checked**, not just the outcome, so
  a level-1 grant can be seen to have satisfied its conditions rather than
  merely succeeded.
* **A level-2 grant returns `pending`**, with the approval id. It is a `201`
  because a request for authority was recorded; it is not a `200` with an active
  grant, because the authority does not exist yet.
* **The status endpoint says what is not enforced yet.** `check()` is the single
  enforcement point, but no tool boundary calls it until P-05 adapters and Stage
  6 assignments exist. Reporting the catalog as governing execution before
  anything calls it would be a false assurance.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ...agents.schemas import AgentCapabilityView, AgentPermissionView
from ...core.exceptions import ConflictError, NotFoundError
from ..dependencies import get_services, require_permission
from ..schemas.common import envelope

router = APIRouter(tags=["agents"])


class CapabilityGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_key: str = Field(min_length=1, max_length=128)
    scope: str = Field(default="", max_length=256)
    reason: str = Field(default="", max_length=2000)
    expires_at: datetime | None = None


class CapabilityRevokeRequest(BaseModel):
    """A revocation needs a reason: taking authority away is an audit event."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)


def _agents(request: Request) -> Any:
    """The assembled subsystem, or a 409 that names the setting to change."""
    services = get_services(request)
    if getattr(services, "agents", None) is None:
        raise ConflictError(
            "the agent subsystem is not enabled",
            details={"hint": "set AUTONOMUS_AGENTS_ENABLED=true"},
        )
    return services.agents


def _correlation(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


@router.get("/agent-capabilities/status")
async def capability_status(
    request: Request,
    principal=Depends(require_permission("agents.capabilities.read")),
):
    """What the catalog holds, and what it does not yet govern.

    Declared before ``/{capability_key}`` so the literal path is never captured
    as a key.
    """
    agents = _agents(request)
    return envelope(await agents.capabilities.status())


@router.get("/agent-capabilities")
async def list_capabilities(
    request: Request,
    category: str | None = Query(None, max_length=64),
    risk_level: str | None = Query(None, max_length=32),
    approval_level: int | None = Query(None, ge=0, le=3),
    enabled: bool | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal=Depends(require_permission("agents.capabilities.read")),
):
    """The catalog, most-restrictive level first."""
    agents = _agents(request)
    rows, total = await agents.capabilities.list_capabilities(
        category=category, risk_level=risk_level, approval_level=approval_level,
        enabled=enabled, limit=limit, offset=offset)
    return envelope(
        [AgentCapabilityView.from_row(r).model_dump(mode="json") for r in rows],
        limit=limit, offset=offset, total=total)


@router.get("/agent-capabilities/{capability_key:path}")
async def get_capability(
    capability_key: str,
    request: Request,
    principal=Depends(require_permission("agents.capabilities.read")),
):
    """One catalog entry, including why a prohibited one is prohibited."""
    agents = _agents(request)
    row = await agents.capabilities.get_capability(capability_key)
    if row is None:
        raise NotFoundError("capability not found",
                            {"capability_key": capability_key})
    return envelope(AgentCapabilityView.from_row(row).model_dump(mode="json"))


@router.get("/agents/{agent_id}/permissions")
async def list_agent_permissions(
    agent_id: str,
    request: Request,
    status: str | None = Query(None, max_length=32),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    principal=Depends(require_permission("agents.capabilities.read")),
):
    """What one agent holds. Nothing is implicit: an unlisted capability is not
    held, whatever the agent's template says it may be allowed."""
    agents = _agents(request)
    rows, total = await agents.capabilities.list_permissions(
        agent_id, status=status, limit=limit, offset=offset)
    return envelope(
        [AgentPermissionView.from_row(row, key).model_dump(mode="json")
         for row, key in rows],
        limit=limit, offset=offset, total=total)


@router.post("/agents/{agent_id}/permissions", status_code=201)
async def grant_capability(
    agent_id: str,
    request: Request,
    payload: CapabilityGrantRequest,
    principal=Depends(require_permission("agents.permissions.grant")),
):
    """Grant one capability, or refuse and say why.

    `201` for both an active grant and a pending one: the resource created is the
    grant record, and a level-2 grant is `pending` until its owner decides. A
    refusal is an error rather than a `200` with a sad field in it, because a
    caller must not be able to ignore a prohibition.
    """
    agents = _agents(request)
    result = await agents.capabilities.grant(
        agent_id, payload.capability_key, scope=payload.scope,
        granted_by=principal.id, reason=payload.reason,
        expires_at=payload.expires_at, correlation_id=_correlation(request))
    return envelope(result.as_dict())


@router.post("/agents/{agent_id}/permissions/{permission_id}/revoke")
async def revoke_capability(
    agent_id: str,
    permission_id: str,
    request: Request,
    payload: CapabilityRevokeRequest,
    principal=Depends(require_permission("agents.permissions.grant")),
):
    """Take a capability away. Requires a reason, and is never blocked by the
    emergency stop: removing authority is what an emergency calls for."""
    agents = _agents(request)
    rows, _total = await agents.capabilities.list_permissions(agent_id, limit=500)
    if not any(row.id == permission_id for row, _key in rows):
        raise NotFoundError("capability grant not found for this agent",
                            {"agent_id": agent_id, "permission_id": permission_id})
    result = await agents.capabilities.revoke(
        permission_id, revoked_by=principal.id, reason=payload.reason,
        correlation_id=_correlation(request))
    return envelope(result)
