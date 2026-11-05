"""Execution tool registry API (P-05 Stage 2).

* ``GET /api/v1/execution/tools`` - discovery (§7): what exists, what it does,
  what it costs in capabilities and risk. Never configuration references.
* ``POST /api/v1/execution/tools/register`` and the validate/disable
  operations - registry administration.

Authorization splits the way the registry's own risk does:

* ``execution.read`` - discovery. Reading the catalog is separated from
  administering it for the reason the capability catalog separates read from
  grant: an agent may need to know what a tool costs without being able to
  make one available.
* ``execution.admin`` - register, validate, disable. Making a tool AVAILABLE
  changes what the whole system may be asked to do, so it is an
  administrative act, and validating is grouped with it rather than with
  registration: registration declares, validation admits.

Browser and desktop routes from the brief's §21 are **not registered**. Their
adapters cannot run in this environment, and an endpoint that cannot work
must not exist; the tools themselves are in the registry, DISABLED, with the
reason recorded.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ...execution.schemas import ToolRegistrationInput
from ..dependencies import require_permission
from ..schemas.common import envelope
from .execution_requests import _execution

router = APIRouter(prefix="/execution", tags=["execution"])


class DisableToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="", max_length=1000)


def _correlation(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


@router.get("/tools")
async def list_tools(
    request: Request,
    status: str | None = Query(default=None, max_length=32),
    adapter_type: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal=Depends(require_permission("execution.read")),
):
    execution = _execution(request)
    rows, total = await execution.registry.list_tools(
        status=status, adapter_type=adapter_type, limit=limit, offset=offset)
    return envelope(rows, limit=limit, offset=offset, total=total)


@router.get("/tools/{tool_id}")
async def get_tool(
    tool_id: str,
    request: Request,
    principal=Depends(require_permission("execution.read")),
):
    execution = _execution(request)
    view = await execution.registry.get_tool(tool_id)
    return envelope(view.model_dump(mode="json"))


@router.post("/tools/register", status_code=201)
async def register_tool(
    request: Request,
    payload: ToolRegistrationInput,
    principal=Depends(require_permission("execution.admin")),
):
    """Declare a tool. It lands REGISTERED: registration declares, validation
    admits, and a tool that could declare itself available would make the
    health gate decorative."""
    execution = _execution(request)
    view = await execution.registry.register(
        payload, actor=principal.id, correlation_id=_correlation(request))
    return envelope(view.model_dump(mode="json"))


@router.post("/tools/{tool_id}/validate")
async def validate_tool(
    tool_id: str,
    request: Request,
    principal=Depends(require_permission("execution.admin")),
):
    """Run the configuration and health gates. AVAILABLE only if all pass;
    the response lists every check, including the ones that passed, because
    "which gate failed" is the question the caller is asking."""
    execution = _execution(request)
    result = await execution.registry.validate_tool(
        tool_id, actor=principal.id, correlation_id=_correlation(request))
    return envelope(result.as_dict())


@router.post("/tools/{tool_id}/disable")
async def disable_tool(
    tool_id: str,
    request: Request,
    payload: DisableToolRequest | None = None,
    principal=Depends(require_permission("execution.admin")),
):
    """Take a tool out of routing. Reachable from any state except REMOVED:
    turning something off must never be blocked by where it happens to be."""
    execution = _execution(request)
    view = await execution.registry.disable_tool(
        tool_id, reason=(payload.reason if payload else ""),
        actor=principal.id, correlation_id=_correlation(request))
    return envelope(view.model_dump(mode="json"))
