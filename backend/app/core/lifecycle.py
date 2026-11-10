"""Application lifecycle states (P-01 §4)."""
from __future__ import annotations

import enum


class AppState(str, enum.Enum):
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class LifecycleManager:
    """Tracks the application state; transitions are explicit and validated."""

    _TRANSITIONS: dict[AppState, set[AppState]] = {
        AppState.STARTING: {AppState.READY, AppState.DEGRADED, AppState.FAILED, AppState.STOPPING},
        AppState.READY: {AppState.DEGRADED, AppState.STOPPING, AppState.FAILED},
        AppState.DEGRADED: {AppState.READY, AppState.STOPPING, AppState.FAILED},
        AppState.STOPPING: {AppState.STOPPED, AppState.FAILED},
        AppState.STOPPED: {AppState.STARTING},
        AppState.FAILED: {AppState.STARTING, AppState.STOPPING},
    }

    def __init__(self) -> None:
        self._state = AppState.STOPPED
        self.degraded_reasons: list[str] = []

    @property
    def state(self) -> AppState:
        return self._state

    def transition(self, target: AppState, reason: str | None = None) -> AppState:
        if target == self._state:
            return self._state
        allowed = self._TRANSITIONS.get(self._state, set())
        if target not in allowed:
            raise ValueError(f"Invalid lifecycle transition {self._state} -> {target}")
        self._state = target
        if target == AppState.DEGRADED and reason:
            self.degraded_reasons.append(reason)
        if target == AppState.READY:
            self.degraded_reasons.clear()
        return self._state

    @property
    def is_ready(self) -> bool:
        return self._state in (AppState.READY, AppState.DEGRADED)
