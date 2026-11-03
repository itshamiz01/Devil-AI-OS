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
        emergency = await s.emergency.state()
        ready = s.lifecycle.state in {LifecycleState.READY, LifecycleState.DEGRADED} and db_ok and s.tasks.accepting
        # An active emergency stop means reduced functionality, not outage: the
        # process is up and owner-control paths still work, so readiness stays
        # true while status reports degraded.
        status = "ok" if ready and not pressure and not emergency["active"] else ("degraded" if ready else "unavailable")
        return {
            "status": status,
            "ready": ready,
            "lifecycle": s.lifecycle.state.value,
            "checks": {
                "database": db_ok,
                "task_manager": s.tasks.accepting,
                "resource_pressure": pressure,
                "emergency_stop_active": emergency["active"],
            },
            "emergency": emergency,
            "tasks": tasks,
        }
