"""P-05 error categories (§21-style) as typed errors on the P-01
``AutonomusError`` hierarchy, so the existing API error envelope carries
them unchanged. Messages never contain secrets or environment values."""
from __future__ import annotations

from ..core.exceptions import AutonomusError


class ExecutionError(AutonomusError):
    status_code = 500
    code = "EXECUTION_ERROR"


class ExecutionValidationError(ExecutionError):
    status_code = 422
    code = "EXECUTION_VALIDATION"


class ExecutionNotFoundError(ExecutionError):
    status_code = 404
    code = "EXECUTION_NOT_FOUND"


class ToolNotFoundError(ExecutionError):
    status_code = 404
    code = "TOOL_NOT_FOUND"


class ToolUnavailableError(ExecutionError):
    """The tool is disabled, deprecated, or its adapter failed its health
    check — execution is refused rather than simulated."""

    status_code = 409
    code = "TOOL_UNAVAILABLE"


class AdapterUnavailableError(ExecutionError):
    """The adapter (or its backend, e.g. the interactive browser engine)
    is unavailable in this environment. Reported truthfully, never
    worked around (§30 final rule)."""

    status_code = 503
    code = "ADAPTER_UNAVAILABLE"


class CapabilityNotHeldError(ExecutionError):
    status_code = 403
    code = "CAPABILITY_NOT_AUTHORIZED"


class ExecutionPolicyError(ExecutionError):
    """Deterministic policy refusal (§8.1). Carries the failed check name
    in details so the refusal is explainable without leaking internals."""

    status_code = 403
    code = "EXECUTION_POLICY_DENIED"


class RiskProhibitedError(ExecutionError):
    """Risk 3 (§8): rejected by the normal execution system. No approval
    path exists and none is created."""

    status_code = 403
    code = "RISK_PROHIBITED"


class ApprovalRequiredError(ExecutionError):
    status_code = 409
    code = "APPROVAL_REQUIRED"


class ApprovalBindingError(ExecutionError):
    """The approval is missing, expired, rejected, or its parameter hash
    no longer matches the request (§17 fail-closed)."""

    status_code = 409
    code = "APPROVAL_BINDING_FAILED"


class PathValidationError(ExecutionError):
    status_code = 403
    code = "PATH_VALIDATION_FAILED"


class WorkspaceError(ExecutionError):
    status_code = 409
    code = "WORKSPACE_ERROR"


class ResourceLimitExceededError(ExecutionError):
    status_code = 429
    code = "RESOURCE_LIMIT_EXCEEDED"


class ExecutionStateError(ExecutionError):
    status_code = 409
    code = "EXECUTION_STATE_INVALID"


class WorkflowInvalidError(ExecutionError):
    status_code = 422
    code = "WORKFLOW_INVALID"


class WorkflowStateError(ExecutionError):
    status_code = 409
    code = "WORKFLOW_STATE_INVALID"


class StandingAuthorizationError(ExecutionError):
    status_code = 422
    code = "STANDING_AUTHORIZATION_INVALID"


class DangerousCommandError(ExecutionError):
    """The §10.4 screen flagged the submitted code. Depending on the flag
    this is a hard rejection; escalation to approval is decided by the
    policy layer, never by the submitter."""

    status_code = 403
    code = "DANGEROUS_COMMAND"


class EmergencyStopError(ExecutionError):
    status_code = 409
    code = "EXECUTION_EMERGENCY_STOP"
