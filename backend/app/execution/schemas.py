"""Pydantic payload schemas for P-05 (validated BEFORE policy, §6).

Two layers:
- request-level schemas (what a submitter may ask for), and
- per-action parameter models the adapters validate again at execution
  time (defense in depth — the stored parameters are re-validated after
  any approval wait, so a drifted payload cannot ride an old approval).

Secret hygiene (§19): :func:`reject_secret_values` walks submitted
parameters and refuses any secret-looking key whose value is not a
credential *reference* (``env:NAME``). Raw secrets therefore cannot enter
an execution table through the front door.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from . import constants as C
from .errors import ExecutionValidationError

CREDENTIAL_REF_PREFIX = "env:"


def reject_secret_values(value: Any, path: str = "parameters") -> None:
    """Raise ExecutionValidationError if a secret-looking key carries a
    raw value anywhere inside ``value`` (dicts/lists walked recursively)."""
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(hint in lowered for hint in C.SECRET_KEY_HINTS):
                if not (isinstance(item, str) and item.startswith(CREDENTIAL_REF_PREFIX)):
                    raise ExecutionValidationError(
                        f"{path}.{key}: raw secret values are never accepted; "
                        f"use a credential reference of the form 'env:NAME'",
                        details={"error_category": "SECRET_VALUE_REJECTED", "field": f"{path}.{key}"})
            reject_secret_values(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_secret_values(item, f"{path}[{index}]")


class ExecutionRequestIn(BaseModel):
    """§6 universal execution request (submitter view). ``agent_id`` names
    the agent the request is FOR; the engine verifies it server-side and
    never trusts it as the caller's identity (audit §5)."""

    agent_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    action: str = Field(min_length=1)
    parameters: dict = Field(default_factory=dict)
    task_id: str | None = None
    business_ref: str | None = None
    input_refs: list = Field(default_factory=list)
    requested_scope: str | None = None
    priority: int = Field(default=5, ge=1, le=10)
    timeout_seconds: float | None = Field(default=None, gt=0)
    retry_policy: dict = Field(default_factory=dict)
    expected_outcome: dict = Field(default_factory=dict)
    idempotency_key: str | None = None
    approval_id: str | None = None


class WorkflowDefinitionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: int = Field(default=1, ge=1)
    description: str | None = None
    definition: dict = Field(default_factory=dict)


class WorkflowRunIn(BaseModel):
    agent_id: str = Field(min_length=1)
    inputs: dict = Field(default_factory=dict)
    task_id: str | None = None
    # P-06 additive extension: a run-level business reference, propagated
    # to every step's execution request so the P-05 workspace policy can
    # authorise writes to businesses/projects workspaces (which require
    # a business_ref). Default None preserves P-05 behaviour exactly.
    business_ref: str | None = None


class StandingAuthorizationIn(BaseModel):
    tool_name: str = Field(min_length=1)
    action_name: str = Field(min_length=1)
    scope_pattern: str = Field(min_length=1)
    agent_id: str | None = None
    role: str | None = None
    limits: dict = Field(default_factory=dict)
    # §17: bounded by construction — both are REQUIRED and positive.
    max_uses: int = Field(ge=1, le=10_000)
    expires_in_minutes: int = Field(ge=1, le=60 * 24 * 365)


class ExecutionSettingsIn(BaseModel):
    """Partial update of execution settings; unknown keys are rejected by
    the service against DEFAULT_SETTINGS (P-04 pattern)."""

    values: dict = Field(default_factory=dict)


# ------------------------------------------------------------ action params
class FsPathParams(BaseModel):
    workspace: str = Field(min_length=1)
    path: str = Field(default="")


class FsWriteParams(FsPathParams):
    content: str = ""


class FsAppendParams(FsPathParams):
    content: str = ""


class FsCopyMoveParams(BaseModel):
    source_workspace: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    dest_workspace: str = Field(min_length=1)
    dest_path: str = Field(min_length=1)


class FsSearchParams(FsPathParams):
    query: str = Field(min_length=1)
    max_results: int = Field(default=50, ge=1, le=500)


class CodeRunParams(BaseModel):
    code: str = Field(min_length=1)
    inputs: dict = Field(default_factory=dict)


class ApiRequestParams(BaseModel):
    url: str = Field(min_length=1)
    headers: dict = Field(default_factory=dict)
    body: Any = None
    credential_ref: str | None = None
    credential_header: str = "Authorization"
    credential_scheme: str = "Bearer"


class BrowserNavigateParams(BaseModel):
    session_id: str = Field(min_length=1)
    url: str = Field(min_length=1)


class BrowserSessionParams(BaseModel):
    allowed_domains: list[str] = Field(default_factory=list)
    permission_profile: str = "read_only"
