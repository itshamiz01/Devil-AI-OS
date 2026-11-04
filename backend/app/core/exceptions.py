from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "app_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class QueueFullError(AppError):
    status_code = 429
    code = "queue_full"


class InvalidTransitionError(AppError):
    status_code = 409
    code = "invalid_task_transition"


class ResourceProtectedError(AppError):
    status_code = 503
    code = "resource_protected"


class EmergencyBlockedError(AppError):
    """Raised when the owner's emergency stop refuses non-essential work.

    503 rather than 403: the principal *is* authorized, the system is simply
    halted. Callers should treat it as retryable-after-clearing, not as a
    permission failure, and it must never be retried automatically.
    """

    status_code = 503
    code = "emergency_stop_active"
