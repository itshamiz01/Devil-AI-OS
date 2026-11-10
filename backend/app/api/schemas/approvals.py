from __future__ import annotations

from pydantic import BaseModel, Field


class ApprovalCreate(BaseModel):
    action: str = Field(min_length=1, max_length=200)
    resource: str | None = None
    risk_classification: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    reason: str | None = None
    requested_permissions: list[str] = Field(default_factory=list)
    parameters: dict = Field(default_factory=dict)
    expires_at: str | None = None


class ApprovalDecisionIn(BaseModel):
    approve: bool
    notes: str | None = None


class ApprovalOut(BaseModel):
    id: str
    requesting_principal_type: str
    requesting_principal_id: str
    action: str
    resource: str | None
    risk_classification: str
    reason: str | None
    requested_permissions: list
    parameters: dict
    parameters_hash: str
    status: str
    approver_id: str | None
    decision_at: str | None
    decision_notes: str | None
    expires_at: str | None
    created_at: str

    @classmethod
    def from_model(cls, a) -> "ApprovalOut":
        return cls(
            id=a.id, requesting_principal_type=a.requesting_principal_type,
            requesting_principal_id=a.requesting_principal_id, action=a.action,
            resource=a.resource, risk_classification=a.risk_classification, reason=a.reason,
            requested_permissions=a.requested_permissions, parameters=a.parameters,
            parameters_hash=a.parameters_hash, status=a.status, approver_id=a.approver_id,
            decision_at=a.decision_at.isoformat() if a.decision_at else None,
            decision_notes=a.decision_notes,
            expires_at=a.expires_at.isoformat() if a.expires_at else None,
            created_at=a.created_at.isoformat() if a.created_at else "")
