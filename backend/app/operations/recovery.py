"""Failure classification, retry policy and circuit breakers (§13).

Classification is deterministic: explicit signals first (P-05
verification vocabulary, P-07 budget decisions, P-08 pause state,
HTTP-ish status hints in error payloads), then conservative
defaults. Unknown failures are NOT retried automatically — §13
reserves automatic retry for known transient classes, and
permission/policy/budget failures escalate instead, always.
"""
from __future__ import annotations

import random
import time

from ..tasks.scheduler import backoff_delay
from . import constants as C


def classify_failure(*, error: dict | None = None,
                     substrate_status: str | None = None,
                     verification_status: str | None = None,
                     budget_status: str | None = None,
                     business_paused: bool = False,
                     permission_denied: bool = False) -> str:
    """Map an observed failure onto the §13 taxonomy."""
    if permission_denied:
        return "permission_failure"
    if budget_status in ("exceeded", "blocked"):
        return "budget_failure"
    if business_paused:
        return "business_paused"
    if verification_status == "failed":
        return "invalid_output"
    err = error or {}
    code = str(err.get("code") or err.get("error") or "").lower()
    message = str(err.get("message") or "").lower()
    text = f"{code} {message}"
    if "rate" in text and "limit" in text:
        return "rate_limit"
    if "timeout" in text or "timed out" in text:
        return "temporary_network_failure"
    if "unavailable" in text or "503" in text or "502" in text:
        return "external_service_unavailable"
    if "overload" in text or "capacity" in text:
        return "system_overload"
    if "missing" in text and ("input" in text or "key" in text):
        return "missing_input"
    if "conflict" in text or "version" in text:
        return "data_conflict"
    if substrate_status in ("failed", "error"):
        return "tool_failure"
    if substrate_status == "cancelled":
        return "agent_failure"
    return "unknown_failure"


def retry_eligible(category: str, attempts: int, max_retries: int) -> bool:
    """§13: retry only transient classes, only up to the policy cap,
    and never permission/policy/budget failures."""
    if category in C.NON_RETRYABLE_CATEGORIES:
        return False
    if category not in C.RETRYABLE_CATEGORIES:
        return False
    return attempts <= max_retries


def retry_delay(attempts: int, base: float, cap: float,
                rng: random.Random | None = None) -> float:
    """Exponential backoff (P-01's policy) plus up to 25% jitter."""
    delay = backoff_delay(attempts, base, cap)
    jitter = (rng or random).uniform(0, delay * 0.25)
    return delay + jitter


class CircuitBreaker:
    """Per-target breaker (§13): opens after N consecutive failures,
    half-opens for one probe after the cooldown. State is process
    memory (it protects this process's substrates); every transition
    is persisted as a recovery record by the service."""

    def __init__(self, target: str, threshold: int = 3,
                 cooldown_seconds: float = 300.0):
        self.target = target
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.state = "closed"  # closed|open|half_open
        self.consecutive_failures = 0
        self.opened_at: float | None = None
        self.total_opens = 0

    def allow(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if self.state == "closed":
            return True
        if self.state == "open":
            if self.opened_at is not None and \
                    now - self.opened_at >= self.cooldown_seconds:
                self.state = "half_open"
                return True
            return False
        return True  # half_open: one probe permitted

    def record_success(self) -> str | None:
        previous = self.state
        self.consecutive_failures = 0
        self.state = "closed"
        self.opened_at = None
        return "closed" if previous != "closed" else None

    def record_failure(self, now: float | None = None) -> str | None:
        now = time.time() if now is None else now
        self.consecutive_failures += 1
        if self.state == "half_open":
            self.state = "open"
            self.opened_at = now
            self.total_opens += 1
            return "opened"
        if self.state == "closed" and \
                self.consecutive_failures >= self.threshold:
            self.state = "open"
            self.opened_at = now
            self.total_opens += 1
            return "opened"
        return None

    def view(self, now: float | None = None) -> dict:
        return {"target": self.target, "state": self.state,
                "consecutive_failures": self.consecutive_failures,
                "threshold": self.threshold,
                "cooldown_seconds": self.cooldown_seconds,
                "total_opens": self.total_opens}
