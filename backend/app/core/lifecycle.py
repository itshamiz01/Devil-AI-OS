from __future__ import annotations

import time
from enum import Enum


class LifecycleState(str, Enum):
    STARTING = "STARTING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class Lifecycle:
    def __init__(self):
        self.state = LifecycleState.STOPPED
        self.started_at: float | None = None
        self.error: str | None = None

    def set(self, state: LifecycleState, error: str | None = None) -> None:
        self.state = state
        self.error = error
        if state in {LifecycleState.READY, LifecycleState.DEGRADED} and self.started_at is None:
            self.started_at = time.monotonic()

    def uptime_seconds(self) -> float:
        return 0.0 if self.started_at is None else round(time.monotonic() - self.started_at, 3)
