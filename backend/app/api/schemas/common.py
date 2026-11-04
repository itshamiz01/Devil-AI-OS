from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class PrincipalView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kind: str
    name: str
    active: bool


class AgentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    principal_id: str | None
    name: str
    role: str
    #: One of the eleven lifecycle states (ADR-0024). Uppercase, unlike every
    #: other status in this API; the vocabulary is enforced by a CHECK constraint.
    status: str
    metadata_json: dict[str, Any]
    # Added by P-04 Stage 2. Optional so an agent that predates the extension,
    # or one not created from a template, still serialises.
    template_id: str | None = None
    template_version: int | None = None
    configuration_version: int | None = None
    parent_agent_id: str | None = None
    business_id: str | None = None
    retired_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    event_type: str
    source: str
    correlation_id: str | None
    task_id: str | None
    severity: str
    payload: dict[str, Any]
    created_at: datetime


class AuditView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    event_type: str
    principal_id: str | None
    resource: str
    action: str
    outcome: str
    correlation_id: str | None
    payload: dict[str, Any]
    created_at: datetime


def envelope(data: Any, **meta: Any) -> dict:
    return {"data": data, "meta": meta}
