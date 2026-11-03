"""Capability registry (P-02 §11.2).

A capability is something the system can *legitimately perform*. This registry
is the boundary between planning and execution: the planner may only propose
steps whose `capability_id` appears here, and every registered capability names
a real P-01 task handler.

§11.2 is explicit — "Do not advertise capabilities that do not have working
implementations." That is why the default registry is small. P-01 exposes exactly
three safe handlers (`system.noop`, `system.echo`, `system.wait`), so exactly
three families of executable work exist. Anything the intelligence engine can do
without executing a task (analysing, planning, scoring) is implemented as
deterministic Python and registered with `task_handler=None`, meaning it runs
in-process and never enters the task queue.

Registering a capability with no implementation is refused, not warned about.
"""

from __future__ import annotations

from threading import Lock

from .schemas import Capability, RiskLevel

#: The only handler names P-01 will execute. Mirrors `tasks/handlers.py`.
REAL_HANDLERS = frozenset({"system.noop", "system.echo", "system.wait"})


class UnknownCapabilityError(KeyError):
    def __init__(self, capability_id: str) -> None:
        self.capability_id = capability_id
        super().__init__(f"capability {capability_id!r} is not registered")


class CapabilityRegistry:
    """Registry of declared, implemented capabilities."""

    def __init__(self, capabilities: list[Capability] | None = None) -> None:
        self._capabilities: dict[str, Capability] = {}
        self._lock = Lock()
        for capability in capabilities or []:
            self.register(capability)

    def register(self, capability: Capability, *, replace: bool = False) -> None:
        """Register a capability, refusing unsupported handler names.

        A capability naming a handler outside `REAL_HANDLERS` would let the
        planner propose work the Core OS cannot execute — or worse, work that
        only appears safe because its handler was never checked.
        """
        if capability.task_handler is not None and capability.task_handler not in REAL_HANDLERS:
            raise ValueError(
                f"capability {capability.capability_id!r} names handler "
                f"{capability.task_handler!r}, which is not a registered P-01 handler"
            )
        with self._lock:
            if capability.capability_id in self._capabilities and not replace:
                raise ValueError(
                    f"capability {capability.capability_id!r} is already registered; "
                    "pass replace=True to update it deliberately"
                )
            self._capabilities[capability.capability_id] = capability

    def unregister(self, capability_id: str) -> None:
        with self._lock:
            self._capabilities.pop(capability_id, None)

    def get(self, capability_id: str) -> Capability:
        with self._lock:
            try:
                return self._capabilities[capability_id].model_copy(deep=True)
            except KeyError:
                raise UnknownCapabilityError(capability_id) from None

    def has(self, capability_id: str) -> bool:
        with self._lock:
            return capability_id in self._capabilities

    def all(self) -> list[Capability]:
        with self._lock:
            return [c.model_copy(deep=True) for c in self._capabilities.values()]

    def available(self) -> list[Capability]:
        return [c for c in self.all() if c.available]

    def executable(self) -> list[Capability]:
        """Capabilities that dispatch a real task handler."""
        return [c for c in self.available() if c.task_handler is not None]

    def in_process(self) -> list[Capability]:
        """Capabilities implemented as deterministic in-process code."""
        return [c for c in self.available() if c.task_handler is None]

    def requiring_permission(self, permission_code: str) -> list[Capability]:
        return [c for c in self.all() if permission_code in c.required_permissions]

    def max_risk(self, capability_ids: list[str]) -> RiskLevel:
        """Highest risk among a set of capabilities.

        Used by the planner so a plan's risk is never lower than the riskiest
        step it contains — a plan cannot look safe by averaging.
        """
        from .schemas import RISK_RANK

        worst = RiskLevel.LOW
        for capability_id in capability_ids:
            if not self.has(capability_id):
                continue
            risk = self.get(capability_id).risk
            if RISK_RANK[risk] > RISK_RANK[worst]:
                worst = risk
        return worst


def default_capabilities() -> CapabilityRegistry:
    """The capabilities P-02 can honestly claim.

    Each entry maps to code that exists in this repository. Nothing here is
    aspirational: `analyze.text`, `plan.generate` and `compute.deterministic`
    are deterministic Python in this package, and the `task.*` entries name the
    three real P-01 handlers.

    Deliberately absent: web browsing, file writing, sending email, executing
    shell commands, financial operations. Those belong to P-05/P-07 and
    registering them here would advertise capability that does not exist.
    """
    return CapabilityRegistry([
        Capability(
            capability_id="analyze.text",
            description="Deterministically analyse supplied text: classify it, extract stated constraints and assess risk.",
            input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
            output_schema={"type": "object", "properties": {"analysis": {"type": "object"}}},
            required_permissions=[],
            risk=RiskLevel.LOW,
            supported_task_categories=["analysis", "research"],
        ),
        Capability(
            capability_id="plan.generate",
            description="Generate and validate a structured plan from a mission using deterministic decomposition.",
            input_schema={"type": "object", "properties": {"mission_id": {"type": "string"}}, "required": ["mission_id"]},
            output_schema={"type": "object", "properties": {"plan": {"type": "object"}}},
            required_permissions=[],
            risk=RiskLevel.LOW,
            supported_task_categories=["planning"],
        ),
        Capability(
            capability_id="compute.deterministic",
            description="Perform arithmetic and comparison in deterministic code. Financial and risk mathematics never goes through a model.",
            input_schema={"type": "object", "properties": {"expression": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"result": {"type": "number"}}},
            required_permissions=[],
            risk=RiskLevel.LOW,
            supported_task_categories=["analysis"],
        ),
        Capability(
            capability_id="evaluate.decision",
            description="Score decision alternatives transparently and classify their risk.",
            input_schema={"type": "object", "properties": {"decision_id": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"scores": {"type": "object"}}},
            required_permissions=[],
            risk=RiskLevel.LOW,
            supported_task_categories=["analysis", "planning"],
        ),
        Capability(
            capability_id="task.echo",
            description="Execute the registered system.echo handler: returns its validated payload. Safe, side-effect free.",
            input_schema={"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]},
            output_schema={"type": "object"},
            required_permissions=["tasks.create"],
            risk=RiskLevel.LOW,
            supported_task_categories=["execution"],
            task_handler="system.echo",
        ),
        Capability(
            capability_id="task.noop",
            description="Execute the registered system.noop handler. Essential; used to verify the execution path end to end.",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object"},
            required_permissions=["tasks.create"],
            risk=RiskLevel.LOW,
            supported_task_categories=["execution"],
            task_handler="system.noop",
        ),
        Capability(
            capability_id="task.wait",
            description="Execute the registered system.wait handler: waits a bounded number of seconds.",
            input_schema={"type": "object", "properties": {"seconds": {"type": "number"}}, "required": ["seconds"]},
            output_schema={"type": "object"},
            required_permissions=["tasks.create"],
            risk=RiskLevel.LOW,
            supported_task_categories=["execution"],
            task_handler="system.wait",
        ),
    ])


__all__ = [
    "CapabilityRegistry",
    "REAL_HANDLERS",
    "UnknownCapabilityError",
    "default_capabilities",
]
