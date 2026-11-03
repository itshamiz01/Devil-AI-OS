from __future__ import annotations

from .lifecycle import LifecycleState


class HealthService:
    def __init__(self, services):
        self.services = services

    async def ready(self) -> bool:
        s = self.services
        return s.lifecycle.state in {LifecycleState.READY, LifecycleState.DEGRADED} and await s.db.health() and s.tasks.accepting

    async def detailed(self) -> dict:
        s = self.services
        db_ok = await s.db.health()
        pressure = s.monitor.resource_pressure()
        tasks = await s.tasks.health()
        ready = s.lifecycle.state in {LifecycleState.READY, LifecycleState.DEGRADED} and db_ok and s.tasks.accepting
        status = "ok" if ready and not pressure else ("degraded" if ready else "unavailable")
        return {
            "status": status,
            "ready": ready,
            "lifecycle": s.lifecycle.state.value,
            "checks": {"database": db_ok, "task_manager": s.tasks.accepting, "resource_pressure": pressure},
            "tasks": tasks,
        }
