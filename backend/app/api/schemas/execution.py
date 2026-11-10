"""Execution API schemas (P-05). Request payloads reuse the engine's own
validated schemas (``app.execution.schemas``); this module adds the
convenience-wrapper payload and the response serializers."""
from __future__ import annotations

from pydantic import BaseModel, Field


class WrapperIn(BaseModel):
    """Convenience wrapper payload: one tool action, optionally executed
    immediately (submit + execute in one call when policy allows)."""

    agent_id: str = Field(min_length=1)
    parameters: dict = Field(default_factory=dict)
    task_id: str | None = None
    business_ref: str | None = None
    requested_scope: str | None = None
    priority: int = Field(default=5, ge=1, le=10)
    timeout_seconds: float | None = Field(default=None, gt=0)
    retry_policy: dict = Field(default_factory=dict)
    expected_outcome: dict = Field(default_factory=dict)
    idempotency_key: str | None = None
    approval_id: str | None = None
    auto_execute: bool = True


def workspace_to_dict(row) -> dict:
    return {
        "id": row.id, "name": row.name, "owner_type": row.owner_type,
        "owner_id": row.owner_id, "kind": row.kind, "root_path": row.root_path,
        "permission_scope": row.permission_scope, "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def workflow_definition_to_dict(row) -> dict:
    return {
        "id": row.id, "name": row.name, "version": row.version,
        "description": row.description, "definition": row.definition,
        "required_capabilities": row.required_capabilities, "status": row.status,
        "validation_errors": row.validation_errors,
        "created_by": ({"type": row.created_by_type, "id": row.created_by_id}
                       if row.created_by_id else None),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def workflow_run_to_dict(row, steps: list | None = None) -> dict:
    data = {
        "id": row.id, "definition_id": row.definition_id,
        "workflow_name": row.workflow_name, "workflow_version": row.workflow_version,
        "requesting_agent_id": row.requesting_agent_id, "task_id": row.task_id,
        "status": row.status, "current_step": row.current_step,
        "checkpoint": row.checkpoint, "inputs": row.inputs, "result": row.result,
        "submitted_by": {"type": row.submitted_by_type, "id": row.submitted_by_id},
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if steps is not None:
        data["steps"] = [{
            "step_id": s.step_id, "status": s.status,
            "execution_request_id": s.execution_request_id,
            "input_ref": s.input_ref, "output_ref": s.output_ref,
            "error_details": s.error_details,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        } for s in steps]
    return data


def standing_authorization_to_dict(row) -> dict:
    return {
        "id": row.id, "tool_name": row.tool_name, "action_name": row.action_name,
        "scope_pattern": row.scope_pattern, "agent_id": row.agent_id, "role": row.role,
        "limits": row.limits, "max_uses": row.max_uses, "uses": row.uses,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "status": row.status,
        "created_by": ({"type": row.created_by_type, "id": row.created_by_id}
                       if row.created_by_id else None),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def browser_session_to_dict(row) -> dict:
    return {
        "id": row.id, "agent_id": row.agent_id, "browser_type": row.browser_type,
        "allowed_domains": row.allowed_domains,
        "permission_profile": row.permission_profile, "status": row.status,
        "current_url": row.current_url,
        "last_activity": row.last_activity.isoformat() if row.last_activity else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
