"""Agent Template API (P-04 Stage 3).

Versioned under ``/api/v1/agent-templates``. Authorization is enforced per
operation, not per router:

* ``agents.templates.read``  — list and read templates, versions and diffs
* ``agents.templates.write`` — create, revise, validate, publish, deprecate,
  restore and clone

Both are derived into ``OWNER_PERMISSIONS`` and deliberately absent from
``SYSTEM_PERMISSIONS``, so the application can never define, validate or
publish the template that governs its own agents.

Every operation also answers 409 — not 500 — when ``AUTONOMUS_AGENTS_ENABLED``
is false, naming the setting to change. A disabled phase reports that it is
disabled.

Three disclosure rules shape every response.

* **A refusal carries its reasons.** Publishing an unvalidated version returns
  409 with the recorded issues in ``details``, and a configuration that does not
  parse returns 422 with every issue listed. "Rejected" without a reason is not
  an answer an owner can act on.
* **A verdict is evidence about one document.** The response reports the
  ``configuration_fingerprint`` the verdict was reached against, and states
  plainly that the capability catalog is not yet cross-checked — a verdict that
  quietly implied more checking than happened would be a false claim.
* **Versions are immutable.** No endpoint edits a stored configuration; the only
  write to an existing version is its validation verdict, and that lands in its
  own column.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ...agents.schemas import AgentTemplateVersionView, AgentTemplateView
from ...core.exceptions import ConflictError
from ..dependencies import get_services, require_permission
from ..schemas.common import envelope

router = APIRouter(prefix="/agent-templates", tags=["agents"])


def _templates(request: Request) -> Any:
    """The template service, or a 409 that names the setting to change.

    ``AUTONOMUS_AGENTS_ENABLED=false`` leaves ``services.agents`` unassigned.
    Without this guard every operation here would raise an AttributeError and
    reach the caller as a 500, reporting a server fault for what is a
    configuration choice the owner made deliberately.
    """
    services = get_services(request)
    if getattr(services, "agents", None) is None:
        raise ConflictError(
            "the agent subsystem is not enabled",
            details={"hint": "set AUTONOMUS_AGENTS_ENABLED=true"},
        )
    return services.agents.templates


# --------------------------------------------------------------------------- #
# Request schemas
# --------------------------------------------------------------------------- #
class TemplateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=2000)
    configuration: dict[str, Any] = Field(min_length=1)


class TemplateReviseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configuration: dict[str, Any] = Field(min_length=1)
    reason: str = Field(default="", max_length=500)


class TemplateVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int | None = Field(default=None, ge=1)


class TemplateDeprecateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)


class TemplateCloneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    version: int | None = Field(default=None, ge=1)


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
@router.get("")
async def list_templates(
    request: Request,
    status: str | None = Query(None, max_length=32),
    category: str | None = Query(None, max_length=64),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal=Depends(require_permission("agents.templates.read")),
):
    templates = _templates(request)
    rows, total = await templates.list_templates(
        status=status, category=category, limit=limit, offset=offset)
    return envelope(
        [AgentTemplateView.from_row(r).model_dump(mode="json") for r in rows],
        limit=limit, offset=offset, total=total,
    )


@router.get("/{template_id}")
async def get_template(template_id: str, request: Request,
                       principal=Depends(require_permission("agents.templates.read"))):
    templates = _templates(request)
    row = await templates.get_template(template_id)
    return envelope(AgentTemplateView.from_row(row).model_dump(mode="json"))


@router.get("/{template_id}/versions")
async def list_template_versions(template_id: str, request: Request,
                                 principal=Depends(require_permission("agents.templates.read"))):
    templates = _templates(request)
    rows = await templates.list_versions(template_id)
    return envelope([AgentTemplateVersionView.from_row(r).model_dump(mode="json")
                     for r in rows], count=len(rows))


@router.get("/{template_id}/versions/{version}")
async def get_template_version(template_id: str, version: int, request: Request,
                               principal=Depends(require_permission("agents.templates.read"))):
    templates = _templates(request)
    row = await templates.get_version(template_id, version)
    return envelope(AgentTemplateVersionView.from_row(row).model_dump(mode="json"))


@router.get("/{template_id}/compare")
async def compare_template_versions(
    template_id: str,
    request: Request,
    left: int = Query(..., ge=1),
    right: int = Query(..., ge=1),
    principal=Depends(require_permission("agents.templates.read")),
):
    """Deterministic field diff of two versions. No model is involved."""
    templates = _templates(request)
    return envelope(await templates.compare(template_id, left, right))


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #
@router.post("", status_code=201)
async def create_template(payload: TemplateCreateRequest, request: Request,
                          principal=Depends(require_permission("agents.templates.write"))):
    templates = _templates(request)
    result = await templates.create_template(
        name=payload.name, category=payload.category, description=payload.description,
        configuration=payload.configuration, created_by=principal.id)
    return envelope({
        "template": AgentTemplateView.from_row(result["template"]).model_dump(mode="json"),
        "version": AgentTemplateVersionView.from_row(result["version"]).model_dump(mode="json"),
    })


@router.post("/{template_id}/versions", status_code=201)
async def revise_template(template_id: str, payload: TemplateReviseRequest, request: Request,
                          principal=Depends(require_permission("agents.templates.write"))):
    templates = _templates(request)
    row = await templates.revise(
        template_id, configuration=payload.configuration,
        created_by=principal.id, reason=payload.reason)
    return envelope(AgentTemplateVersionView.from_row(row).model_dump(mode="json"))


@router.post("/{template_id}/validate")
async def validate_template_version(template_id: str, payload: TemplateVersionRequest,
                                    request: Request,
                                    principal=Depends(require_permission("agents.templates.write"))):
    templates = _templates(request)
    return envelope(await templates.validate(template_id, payload.version))


@router.post("/{template_id}/publish")
async def publish_template(template_id: str, payload: TemplateVersionRequest, request: Request,
                           principal=Depends(require_permission("agents.templates.write"))):
    templates = _templates(request)
    row = await templates.publish(template_id, payload.version)
    return envelope(AgentTemplateView.from_row(row).model_dump(mode="json"))


@router.post("/{template_id}/deprecate")
async def deprecate_template(template_id: str, payload: TemplateDeprecateRequest,
                             request: Request,
                             principal=Depends(require_permission("agents.templates.write"))):
    templates = _templates(request)
    row = await templates.deprecate(template_id, reason=payload.reason)
    return envelope(AgentTemplateView.from_row(row).model_dump(mode="json"))


@router.post("/{template_id}/restore")
async def restore_template(template_id: str, request: Request,
                           principal=Depends(require_permission("agents.templates.write"))):
    templates = _templates(request)
    row = await templates.restore(template_id)
    return envelope(AgentTemplateView.from_row(row).model_dump(mode="json"))


@router.post("/{template_id}/clone", status_code=201)
async def clone_template(template_id: str, payload: TemplateCloneRequest, request: Request,
                         principal=Depends(require_permission("agents.templates.write"))):
    templates = _templates(request)
    result = await templates.clone(
        template_id, new_name=payload.name, version=payload.version, created_by=principal.id)
    return envelope({
        "template": AgentTemplateView.from_row(result["template"]).model_dump(mode="json"),
        "version": AgentTemplateVersionView.from_row(result["version"]).model_dump(mode="json"),
        "cloned_from": result["cloned_from"],
    })
