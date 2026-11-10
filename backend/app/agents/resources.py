"""Resource-aware agent management (§10).

Agents are logical configurations sharing ONE model infrastructure (the
P-02 router). This module owns:
- effective per-agent budgets (template budget, agent override, factory
  ceilings — the tightest wins),
- host pressure evaluation from the P-01 SystemMonitor,
- the §10.4 backpressure ladder,
- the shared-inference concurrency gate (a counter around the single
  P-02 ModelRouter — there is never a per-agent provider instance).
"""
from __future__ import annotations

import asyncio

from ..database.models.core import Agent
from .constants import DEFAULT_RESOURCE_BUDGET
from .errors import ResourceLimitExceededError


class AgentResourceManager:
    def __init__(self, monitor=None):
        self._monitor = monitor
        self._inference_active = 0
        self._inference_lock = asyncio.Lock()
        # Monotonic counter proving Scenario J's "no duplicate model
        # initialization": the factory holds exactly ONE router reference,
        # injected once; this counter records how many times a router was
        # bound (expected: 1 per application).
        self.router_bindings = 0
        self._router = None

    def bind_router(self, router) -> None:
        self._router = router
        self.router_bindings += 1

    # --------------------------------------------------------------- budgets
    @staticmethod
    def effective_budget(agent: Agent, template_config: dict | None,
                         settings: dict) -> dict:
        budget = dict(DEFAULT_RESOURCE_BUDGET)
        if template_config:
            budget.update(template_config.get("resource_budget") or {})
        if agent.budget:
            budget.update(agent.budget)
        # Factory ceilings always win over template/agent figures.
        budget["max_concurrent_tasks"] = min(
            int(budget["max_concurrent_tasks"]), int(settings["max_concurrent_tasks_per_agent"]))
        budget["max_task_seconds"] = min(
            float(budget["max_task_seconds"]), float(settings["max_template_task_seconds"]))
        budget["memory_budget_mb"] = min(
            float(budget["memory_budget_mb"]), float(settings["max_template_memory_budget_mb"]))
        return budget

    # -------------------------------------------------------------- pressure
    def host_resources(self) -> dict:
        if self._monitor is None:
            return {"available": False}
        return {"available": True, **self._monitor.resources()}

    def blocking_enabled(self) -> bool:
        """Whether threshold violations may BLOCK work. Mirrors the P-01
        operational switch exactly (SystemMonitor.admission_block_reason
        honours Settings.block_nonessential_on_threshold: True in the
        production configuration, disabled in the test harness). Pressure
        is always REPORTED honestly; blocking follows the switch."""
        monitor = self._monitor
        settings = getattr(monitor, "settings", None) if monitor is not None else None
        if settings is None:
            return True
        return bool(getattr(settings, "block_nonessential_on_threshold", True))

    def pressure(self) -> dict:
        """Deterministic pressure evaluation. Level 0 = none; 1 = one
        threshold class violated (or queue near capacity); 2 = multiple
        classes violated. Feeds the §10.4 backpressure ladder."""
        if self._monitor is None:
            return {"level": 0, "violations": [], "queue": None,
                    "blocking_enabled": self.blocking_enabled()}
        violations = self._monitor.threshold_violations()
        level = 0
        if violations:
            level = 1 if len(violations) == 1 else 2
        queue = None
        if self._monitor.queue_stats is not None:
            queue = self._monitor.queue_stats.snapshot()
            capacity = queue.get("capacity") or 0
            depth = (queue.get("queued") or 0) + (queue.get("running") or 0)
            if capacity and depth >= 0.9 * capacity:
                level = max(level, 1)
        return {"level": level, "violations": violations, "queue": queue,
                "blocking_enabled": self.blocking_enabled()}

    def backpressure_actions(self, pressure_level: int) -> list[str]:
        """The §10.4 ladder, as data: what the factory does at each level.
        Critical/essential work is never blocked by the ladder."""
        if pressure_level <= 0:
            return []
        actions = [
            "stop_nonessential_agent_creation",
            "queue_low_priority_assignments",
            "report_resource_pressure_to_owner",
        ]
        if pressure_level >= 2:
            actions += [
                "reduce_effective_concurrency_to_minimum",
                "suspend_eligible_idle_agents",
            ]
        return actions

    def creation_blocked(self, *, essential: bool = False) -> str | None:
        """Reason string when creation must not proceed under pressure."""
        if essential:
            return None
        pressure = self.pressure()
        if not pressure.get("blocking_enabled", True):
            return None
        if pressure["level"] >= 1:
            names = ", ".join(v["resource"] for v in pressure["violations"]) or "queue saturation"
            return f"resource pressure level {pressure['level']} ({names})"
        return None

    # ---------------------------------------------------- shared inference
    @property
    def inference_active(self) -> int:
        return self._inference_active

    async def run_shared_inference(self, task_class: str, *, settings: dict):
        """Run ONE inference selection through the single shared P-02
        router, gated by max_concurrent_inference_requests. Returns the
        RouterDecision. Raises MODEL_PROVIDER_UNAVAILABLE when no router
        is bound, RESOURCE_LIMIT_EXCEEDED when the gate is full."""
        if self._router is None:
            from .errors import ModelProviderUnavailableError
            raise ModelProviderUnavailableError(
                "no shared model router is bound to the factory",
                details={"error_category": "MODEL_PROVIDER_UNAVAILABLE"})
        limit = int(settings["max_concurrent_inference_requests"])
        async with self._inference_lock:
            if self._inference_active >= limit:
                raise ResourceLimitExceededError(
                    f"shared inference concurrency limit reached ({limit}); "
                    "logical agents share one model infrastructure",
                    details={"error_category": "RESOURCE_LIMIT_EXCEEDED",
                             "limit": limit, "active": self._inference_active})
            self._inference_active += 1
        try:
            return await self._router.select(task_class)
        finally:
            async with self._inference_lock:
                self._inference_active -= 1
