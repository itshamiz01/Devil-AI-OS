"""Typed application exceptions mapped to the API error envelope."""
from __future__ import annotations


class AutonomusError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(AutonomusError):
    status_code = 500
    code = "configuration_error"


class ValidationError(AutonomusError):
    status_code = 422
    code = "validation_error"


class NotFoundError(AutonomusError):
    status_code = 404
    code = "not_found"


class AuthenticationError(AutonomusError):
    status_code = 401
    code = "unauthorized"


class PermissionDeniedError(AutonomusError):
    status_code = 403
    code = "permission_denied"


class InvalidStateTransitionError(AutonomusError):
    status_code = 409
    code = "invalid_state_transition"


class QueueFullError(AutonomusError):
    status_code = 429
    code = "queue_full"


class ResourceBlockedError(AutonomusError):
    status_code = 429
    code = "resource_blocked"


class ApprovalError(AutonomusError):
    status_code = 409
    code = "approval_error"
