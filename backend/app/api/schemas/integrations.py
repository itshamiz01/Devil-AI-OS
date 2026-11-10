"""Universal Integration Framework API schemas (Expansion F02).

Inputs only — outputs are the service layer's plain dicts, which
structurally cannot contain a secret value (no value field exists
anywhere in the framework's data model; credentials appear only as
registry NAMES resolved by P-10 at use time).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CapabilityIn(BaseModel):
    name: str
    description: str = ""
    permission: str = "read_system_data"
    risk_action: str = "read"
    input_schema: dict = Field(default_factory=lambda: {"type": "object"})
    output_schema: dict = Field(default_factory=lambda: {"type": "object"})
    rate_limit_per_minute: int | None = None
    is_sync: bool = False


class ConnectorRegisterIn(BaseModel):
    """A connector DECLARATION. Registering declares intent and the
    capability contract; it never creates a working connector —
    without an implemented adapter the record reports
    requires_owner_configuration."""
    key: str
    name: str
    provider: str
    version: str = "1.0.0"
    kind: str = "custom"
    description: str = ""
    requires_credential: bool = False
    capabilities: list[CapabilityIn] = Field(default_factory=list)


class ConnectorConfigureIn(BaseModel):
    credential_secret_name: str | None = None
    clear_credential: bool = False
    settings: dict | None = None


class ConnectorInvokeIn(BaseModel):
    capability: str
    payload: dict = Field(default_factory=dict)
    approval_id: str | None = None
    capability_id: str | None = None
    idempotency_key: str | None = None
