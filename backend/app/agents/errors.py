"""P-04 error categories (prompt §21) as typed errors on the P-01
``AutonomusError`` hierarchy, so the existing API error envelope carries
them unchanged. Messages never contain secrets or environment values."""
from __future__ import annotations

from ..core.exceptions import AutonomusError


class FactoryError(AutonomusError):
    status_code = 500
    code = "factory_error"


class TemplateInvalidError(FactoryError):
    status_code = 422
    code = "TEMPLATE_INVALID"


class AgentNotFoundError(FactoryError):
    status_code = 404
    code = "AGENT_NOT_FOUND"


class AgentNotActiveError(FactoryError):
    status_code = 409
    code = "AGENT_NOT_ACTIVE"


class CapabilityNotAuthorizedError(FactoryError):
    status_code = 403
    code = "CAPABILITY_NOT_AUTHORIZED"


class CapabilityProhibitedError(FactoryError):
    """Level-3 (§8.3): prohibited outright — not requestable, and not
    owner-approvable through the agent approval path."""

    status_code = 403
    code = "CAPABILITY_PROHIBITED"


class CapabilityUnsupportedError(FactoryError):
    """The capability is catalogued but no existing module backs it in
    this build (§8.1: never simulate unsupported capabilities)."""

    status_code = 422
    code = "CAPABILITY_UNSUPPORTED"


class ApprovalRequiredError(FactoryError):
    status_code = 409
    code = "APPROVAL_REQUIRED"


class ResourceLimitExceededError(FactoryError):
    status_code = 429
    code = "RESOURCE_LIMIT_EXCEEDED"


class CreationLimitReachedError(FactoryError):
    status_code = 429
    code = "CREATION_LIMIT_REACHED"


class AssignmentRejectedError(FactoryError):
    """Assignment refused with a structured rule-by-rule reason (§9.2)."""

    status_code = 409
    code = "ASSIGNMENT_REJECTED"


class LifecycleTransitionInvalidError(FactoryError):
    status_code = 409
    code = "LIFECYCLE_TRANSITION_INVALID"


class ModelProviderUnavailableError(FactoryError):
    status_code = 503
    code = "MODEL_PROVIDER_UNAVAILABLE"


class InitializationFailedError(FactoryError):
    status_code = 422
    code = "INITIALIZATION_FAILED"


class ExecutionTimeoutError(FactoryError):
    status_code = 408
    code = "EXECUTION_TIMEOUT"


class ConfigurationVersionConflictError(FactoryError):
    status_code = 409
    code = "CONFIGURATION_VERSION_CONFLICT"
