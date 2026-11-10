"""P-10 security API schemas. Inputs only — outputs are the service
layer's plain dicts, which structurally cannot contain secret values
(no value field exists anywhere in the P-10 data model)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class PolicyUpdateIn(BaseModel):
    patch: dict
    reason: str | None = None


class PolicyRollbackIn(BaseModel):
    version: int
    reason: str | None = None


class PermissionCheckIn(BaseModel):
    """A broker authorization request (§7.1). ``principal_*`` fields
    describe the AGENT on whose behalf the check runs; the caller
    must itself be authenticated (owner/service) or be that agent's
    supervisor path — the broker's decision is about the described
    principal, and every check is audited under the caller."""
    principal_type: str = "agent"
    principal_id: str
    permission: str
    action: str
    resource: str | None = None
    business_ref: str | None = None
    task_id: str | None = None
    parameters: dict = Field(default_factory=dict)
    approval_id: str | None = None
    capability_id: str | None = None


class CapabilityIssueIn(BaseModel):
    holder_type: str = "agent"
    holder_id: str
    permission: str
    resource: str | None = None
    business_ref: str | None = None
    task_id: str | None = None
    ttl_minutes: int | None = None
    reason: str | None = None


class EscalationRequestIn(BaseModel):
    principal_type: str = "agent"
    principal_id: str
    permission: str
    action: str
    resource: str | None = None
    reason: str
    parameters: dict = Field(default_factory=dict)


class SecretRegisterIn(BaseModel):
    name: str
    reference: str
    purpose: str | None = None
    classification: int = 4
    expires_at: dt.datetime | None = None


class SecretAccessCheckIn(BaseModel):
    principal_type: str = "agent"
    principal_id: str
    purpose: str | None = None


class FilesystemGuardIn(BaseModel):
    principal_type: str = "agent"
    principal_id: str
    operation: str = "read"
    path: str


class CommandGuardIn(BaseModel):
    principal_type: str = "agent"
    principal_id: str
    argv: list[str]
    working_dir: str = ""


class DownloadGuardIn(BaseModel):
    filename: str
    size_bytes: int
    content_type: str | None = None


class EgressCheckIn(BaseModel):
    url: str


class RedirectChainIn(BaseModel):
    urls: list[str]


class ContentScreenIn(BaseModel):
    text: str
    source: str = "external_content"


class OutboundScreenIn(BaseModel):
    text: str


class HandoffValidateIn(BaseModel):
    envelope: dict


class FinancialAuthorizeIn(BaseModel):
    principal_type: str = "agent"
    principal_id: str
    action: str
    business_id: str
    amount_minor: int | None = None
    currency: str | None = None
    recipient: str | None = None
    approval_id: str | None = None


class EmergencyModeIn(BaseModel):
    mode: str
    reason: str | None = None


class FinancialSuspensionIn(BaseModel):
    suspended: bool
    reason: str | None = None


class RestrictionIn(BaseModel):
    agent_id: str
    restriction: str = "suspended"
    reason: str | None = None


class ClassificationIn(BaseModel):
    resource_ref: str
    classification: int
    business_ref: str | None = None
    retention_days: int | None = None
    notes: str | None = None


class IncidentIn(BaseModel):
    title: str
    category: str = "general"
    severity: str = "medium"
    description: str = ""
    related_ref: str | None = None


class IncidentUpdateIn(BaseModel):
    status: str | None = None
    resolution: str | None = None
    severity: str | None = None


class AlertStatusIn(BaseModel):
    status: str


class TotpVerifyIn(BaseModel):
    code: str


# ------------------------------------------------- Expansion Feature 1
# Identity & Device Security: device registry + MFA recovery codes.
# Inputs only — the device secret and recovery codes are OUTPUTS of
# exactly one response each (enrolment/rotation, generation) and
# are never accepted back as stored data anywhere.
class DeviceEnrolIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    platform: str | None = Field(default=None, max_length=100)
    device_name: str | None = Field(default=None, max_length=200)


class DeviceRelabelIn(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    platform: str | None = Field(default=None, max_length=100)
    device_name: str | None = Field(default=None, max_length=200)


class RecoveryCodesGenerateIn(BaseModel):
    count: int = 10


class RecoveryCodeVerifyIn(BaseModel):
    code: str


class BackupRestoreIn(BaseModel):
    # P-14 Stage B (DEF-A4): the approval that hash-binds this restore.
    approval_id: str
