"""Retry policy: exponential backoff + eligibility (P-01 §7.4)."""
from __future__ import annotations

from .models import NON_RETRYABLE_KINDS, ErrorKind


def backoff_delay(attempt: int, base: float, maximum: float) -> float:
    """Delay before retry number ``attempt`` (1-based)."""
    if attempt < 1:
        attempt = 1
    return min(base * (2 ** (attempt - 1)), maximum)


def is_retryable(kind: ErrorKind) -> bool:
    return kind not in NON_RETRYABLE_KINDS


def classify_exception(exc: BaseException) -> ErrorKind:
    from .models import TaskExecutionError

    if isinstance(exc, TaskExecutionError):
        return exc.kind
    if isinstance(exc, TimeoutError):
        return ErrorKind.TIMEOUT
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return ErrorKind.INVALID_INPUT
    return ErrorKind.UNKNOWN
