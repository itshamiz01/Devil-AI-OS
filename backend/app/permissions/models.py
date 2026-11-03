from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def canonical_payload_hash(action: str, resource: str, permissions: list[str], parameters: dict[str, Any]) -> str:
    canonical = json.dumps({"action": action, "resource": resource, "permissions": sorted(permissions), "parameters": parameters}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class ApprovalCreateRequest(BaseModel):
    action: str = Field(min_length=1, max_length=128)
    resource: str = Field(min_length=1, max_length=256)
    risk: Literal["low", "medium", "high", "critical"] = "medium"
    reason: str = Field(min_length=1, max_length=2000)
    requested_permissions: list[str] = Field(default_factory=list, max_length=32)
    parameters: dict[str, Any] = Field(default_factory=dict)
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    notes: str = Field(default="", max_length=2000)


class ApprovalView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    requester_id: str
    action: str
    resource: str
    risk: str
    reason: str
    requested_permissions: list[str]
    payload_hash: str
    status: str
    approver_id: str | None
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    notes: str | None
