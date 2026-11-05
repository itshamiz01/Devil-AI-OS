"""The tool registry (§7): what tools exist, what they may do, and whether
they are currently allowed to.

A tool is registered by declaring itself - its adapter, its actions, the
capabilities it requires, its risk class. Registration is not availability.
§7's rule is that a tool must not become AVAILABLE until its configuration and
health checks pass, so registration lands at REGISTERED and only
:meth:`ToolRegistry.validate_tool` can move it, through VALIDATING, to
AVAILABLE. The validator's checks are deterministic and small on purpose: is
the adapter one this environment can run at all, does the tool declare any
actions, is its risk class one the execution system may route at all, does a
sensitive tool actually require the approval its risk demands, and - for code
tools - has somebody stated what isolation was verified (§30 rule 22). Real
adapter health probing arrives with the adapters (Stages 3-4) and reports
through the same `health_status` these checks write.

Two further disciplines, both inherited from P-04's capability catalog:

* **The registry is code-seeded for what cannot run.** Browser and desktop
  tools are registered DISABLED at startup with the reason recorded, so the
  registry answers "is there a browser tool?" with "yes, and here is why it
  cannot run" instead of "no", which would invite somebody to register one.
* **Discovery is a narrowed view.** `ToolView` carries descriptions, actions,
  contracts, capabilities and risk - never `configuration_reference`, which is
  where a secret's address would live if one ever did. §7 forbids exposing
  internal configuration through discovery, so the column exists on the row
  and is absent from the view, deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.config import Settings
from ..core.exceptions import ConflictError, NotFoundError
from ..database.repositories import AuditRepo, ExecutionToolRepo
from .schemas import (
    ADAPTERS_UNSUPPORTED_HERE,
    ADAPTER_TYPES,
    TOOL_STATE_TRANSITIONS,
    ToolRegistrationInput,
    ToolView,
)

__all__ = [
    "REGISTRY_ACTION",
    "BUILTIN_TOOLS",
    "ToolNotFoundError",
    "ToolRegistrationError",
    "ToolTransitionError",
    "ToolValidationResult",
    "ToolRegistry",
]

#: Permission code every registry write is audited against.
REGISTRY_ACTION = "execution.admin"

VALIDATION_CHECKS = (
    "adapter_supported",
    "actions_declared",
    "risk_permitted",
    "approval_consistency",
    "isolation_declared",
)


class ToolNotFoundError(NotFoundError):
    code = "execution_tool_not_found"


class ToolRegistrationError(ConflictError):
    code = "tool_registration_conflict"


class ToolTransitionError(ConflictError):
    code = "tool_transition_invalid"


@dataclass
class ToolValidationResult:
    tool_id: str
    available: bool
    status: str
    checks: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"tool_id": self.tool_id, "available": self.available,
                "status": self.status, "checks": list(self.checks)}


#: Tools registered at startup in DISABLED, because the honest answer to "can
#: this system drive a browser?" is "the registry knows what that would take,
#: and this environment cannot do it" (§30's closing rule). They carry the risk
#: and approval levels the real tools will carry, so policy behaviour against
#: them is already correct when an adapter does arrive.
BUILTIN_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "browser.session",
        "description": "Drive a controlled browser session: navigate, inspect, "
                       "interact and capture evidence on approved domains.",
        "category": "browser",
        "adapter_type": "browser",
        "version": "1.0.0",
        "supported_actions": ["navigate", "inspect", "interact", "screenshot"],
        "capability_requirements": ["browser.control"],
        "risk_level": 2,
        "required_approval_level": 2,
        "supported_platforms": ["windows"],
    },
    {
        "name": "desktop.window",
        "description": "Inspect and interact with approved application windows "
                       "through Windows UI Automation.",
        "category": "desktop",
        "adapter_type": "desktop",
        "version": "1.0.0",
        "supported_actions": ["inspect", "screenshot", "action"],
        "capability_requirements": [],
        "risk_level": 2,
        "required_approval_level": 2,
        "supported_platforms": ["windows"],
    },
)


class ToolRegistry:
    def __init__(self, db: Any, settings: Settings, *, bus: Any = None) -> None:
        self.db = db
        self.settings = settings
        self.bus = bus

    # ------------------------------------------------------------------ #
    # Registration and lifecycle
    # ------------------------------------------------------------------ #
    async def register(self, definition: ToolRegistrationInput, *,
                       actor: str | None = None,
                       correlation_id: str | None = None) -> ToolView:
        """Record a tool declaration. The tool is REGISTERED, not available:
        availability is validation's to grant, and conflating the two is how a
        registry ends up routing work to tools nobody has checked."""
        if definition.adapter_type not in ADAPTER_TYPES:
            raise ToolRegistrationError(
                f"'{definition.adapter_type}' is not an adapter type; the engine "
                f"has {', '.join(ADAPTER_TYPES)}")
        async with self.db.session_factory() as session:
            repo = ExecutionToolRepo(session)
            existing = await repo.by_name_version(definition.name, definition.version)
            if existing is not None:
                raise ToolRegistrationError(
                    f"tool '{definition.name}' version {definition.version} is "
                    f"already registered as {existing.id}; register a new version "
                    "rather than redefining one that requests may already name")
            row = await repo.create(
                name=definition.name, description=definition.description,
                category=definition.category, adapter_type=definition.adapter_type,
                version=definition.version,
                supported_actions=list(definition.supported_actions),
                input_schema=dict(definition.input_schema),
                output_schema=dict(definition.output_schema),
                capability_requirements=list(definition.capability_requirements),
                risk_level=int(definition.risk_level),
                required_approval_level=int(definition.required_approval_level),
                supported_platforms=list(definition.supported_platforms),
                resource_requirements=dict(definition.resource_requirements),
                timeout_default_seconds=int(definition.timeout_default_seconds),
                retry_eligible=bool(definition.retry_eligible),
                idempotent=bool(definition.idempotent), status="REGISTERED",
                health_status="unknown",
                configuration_reference=definition.configuration_reference,
                isolation_strength=definition.isolation_strength)
            tool_id = row.id
            await AuditRepo(session).record(
                "execution.tool_registered", "allowed", resource=tool_id,
                principal_id=actor, action=REGISTRY_ACTION,
                correlation_id=correlation_id,
                payload={"name": definition.name, "version": definition.version,
                         "adapter_type": definition.adapter_type,
                         "risk_level": definition.risk_level, "actor": actor})
            await session.commit()
            view = ToolView.from_row(row)
        await self._emit("ExecutionToolRegistered",
                         {"tool_id": tool_id, "name": definition.name,
                          "adapter_type": definition.adapter_type,
                          "status": "REGISTERED"}, correlation_id)
        return view

    async def validate_tool(self, tool_id: str, *, actor: str | None = None,
                            correlation_id: str | None = None) -> ToolValidationResult:
        """Run the health and configuration gates. AVAILABLE only if all pass.

        A failed validation disables the tool with the failures recorded, rather
        than leaving it REGISTERED: a tool that was checked and found wanting is
        a different fact from a tool nobody has checked yet, and the registry
        should say which one it is holding.
        """
        async with self.db.session_factory() as session:
            repo = ExecutionToolRepo(session)
            row = await repo.get(tool_id)
            if row is None:
                raise ToolNotFoundError(f"tool {tool_id} is not registered")
            self._assert_transition(row.status, "VALIDATING")
            previous = row.status
            checks: list[dict[str, Any]] = []

            def check(name: str, passed: bool, detail: str) -> None:
                checks.append({"name": name, "passed": passed, "detail": detail})

            unsupported = ADAPTERS_UNSUPPORTED_HERE.get(row.adapter_type)
            check(VALIDATION_CHECKS[0], unsupported is None,
                  f"the {row.adapter_type} adapter can run in this environment"
                  if unsupported is None else
                  f"the {row.adapter_type} adapter is unsupported here: {unsupported}")
            check(VALIDATION_CHECKS[1], bool(row.supported_actions),
                  f"declares {len(row.supported_actions or [])} action(s)"
                  if row.supported_actions else
                  "declares no actions; a tool that does nothing cannot be "
                  "available, because a request routed to it could only fail")
            check(VALIDATION_CHECKS[2], int(row.risk_level) <= 2,
                  f"risk class {row.risk_level} may be routed"
                  if int(row.risk_level) <= 2 else
                  "a Risk 3 tool can never be available: prohibited operations "
                  "are rejected by policy before a tool is consulted (§8)")
            check(VALIDATION_CHECKS[3],
                  int(row.risk_level) < 2 or int(row.required_approval_level) >= 2,
                  "a sensitive tool requires owner approval"
                  if int(row.risk_level) >= 2 else
                  f"risk class {row.risk_level} needs no approval consistency")
            if row.adapter_type == "code":
                check(VALIDATION_CHECKS[4], bool(row.isolation_strength),
                      f"isolation declared: {row.isolation_strength}"
                      if row.isolation_strength else
                      "no isolation strength is declared; §30 rule 22 forbids "
                      "claiming sandbox security that was not verified, and an "
                      "undeclared strength is an unverified one")
            else:
                check(VALIDATION_CHECKS[4], True,
                      "the tool runs no untrusted code, so no isolation claim "
                      "is required")

            failures = [c for c in checks if not c["passed"]]
            available = not failures
            if available:
                status, health = "AVAILABLE", "healthy"
                detail = "all validation checks passed"
                changes: dict[str, Any] = {"status": status, "health_status": health,
                                           "health_detail": detail,
                                           "disabled_reason": None}
            else:
                status, health = "DISABLED", "unhealthy"
                detail = "; ".join(f"{c['name']}: {c['detail']}" for c in failures)
                changes = {"status": status, "health_status": health,
                           "health_detail": detail,
                           "disabled_reason": f"validation failed: {detail}"}
            await repo.update(row, **changes)
            await AuditRepo(session).record(
                "execution.tool_validated", "allowed" if available else "denied",
                resource=tool_id, principal_id=actor, action=REGISTRY_ACTION,
                correlation_id=correlation_id,
                payload={"from": previous, "to": status, "available": available,
                         "checks": checks, "actor": actor})
            await session.commit()
        await self._emit("ExecutionToolStateChanged",
                         {"tool_id": tool_id, "from": previous, "to": status,
                          "reason": detail}, correlation_id)
        return ToolValidationResult(tool_id, available, status, checks)

    async def disable_tool(self, tool_id: str, *, reason: str = "",
                           actor: str | None = None,
                           correlation_id: str | None = None) -> ToolView:
        """Take a tool out of routing. Reachable from any state except REMOVED:
        turning something off must never be blocked by where it happens to be."""
        async with self.db.session_factory() as session:
            repo = ExecutionToolRepo(session)
            row = await repo.get(tool_id)
            if row is None:
                raise ToolNotFoundError(f"tool {tool_id} is not registered")
            self._assert_transition(row.status, "DISABLED")
            previous = row.status
            detail = reason or "disabled by an administrator"
            await repo.update(row, status="DISABLED", disabled_reason=detail)
            await AuditRepo(session).record(
                "execution.tool_disabled", "allowed", resource=tool_id,
                principal_id=actor, action=REGISTRY_ACTION,
                correlation_id=correlation_id,
                payload={"from": previous, "to": "DISABLED", "reason": detail,
                         "actor": actor})
            await session.commit()
            view = ToolView.from_row(row)
        await self._emit("ExecutionToolStateChanged",
                         {"tool_id": tool_id, "from": previous, "to": "DISABLED",
                          "reason": detail}, correlation_id)
        return view

    @staticmethod
    def _assert_transition(current: str, target: str) -> None:
        allowed = TOOL_STATE_TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            raise ToolTransitionError(
                f"a tool that is '{current}' cannot become '{target}'; "
                + ("it is terminal" if not allowed
                   else f"only {', '.join(sorted(allowed))} follow it"))

    # ------------------------------------------------------------------ #
    # Startup seeding and reads
    # ------------------------------------------------------------------ #
    async def reconcile_builtin_tools(self) -> dict[str, list[str]]:
        """Register the tools this environment cannot run, as DISABLED.

        Additive only, like the capability catalog reconciliation: an existing
        row is left exactly as it is, so an owner who disabled something by
        hand does not find it re-registered by a restart.
        """
        created, existing = [], []
        async with self.db.session_factory() as session:
            repo = ExecutionToolRepo(session)
            for definition in BUILTIN_TOOLS:
                if await repo.by_name_version(definition["name"], definition["version"]):
                    existing.append(definition["name"])
                    continue
                reason = ADAPTERS_UNSUPPORTED_HERE[definition["adapter_type"]]
                await repo.create(
                    **definition, status="DISABLED", health_status="unsupported",
                    health_detail=reason, disabled_reason=reason)
                created.append(definition["name"])
            await session.commit()
        return {"created": created, "existing": existing}

    async def get_tool(self, tool_id: str) -> ToolView:
        async with self.db.session_factory() as session:
            row = await ExecutionToolRepo(session).get(tool_id)
            if row is None:
                raise ToolNotFoundError(f"tool {tool_id} is not registered")
            return ToolView.from_row(row)

    async def list_tools(self, *, status: str | None = None,
                         adapter_type: str | None = None, limit: int = 100,
                         offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        async with self.db.session_factory() as session:
            repo = ExecutionToolRepo(session)
            rows = await repo.list_all(status=status, adapter_type=adapter_type,
                                       limit=limit, offset=offset)
            total = await repo.count(status=status, adapter_type=adapter_type)
            return [ToolView.from_row(r).model_dump(mode="json") for r in rows], total

    async def status(self) -> dict[str, Any]:
        async with self.db.session_factory() as session:
            by_status = await ExecutionToolRepo(session).count_by_status()
        return {
            "tools_by_status": by_status,
            "routable": sum(by_status.get(s, 0) for s in ("AVAILABLE", "DEGRADED")),
            "unsupported_adapters": dict(ADAPTERS_UNSUPPORTED_HERE),
        }

    async def _emit(self, event_type: str, payload: dict[str, Any],
                    correlation_id: str | None) -> None:
        if self.bus is None:
            return
        await self.bus.publish_new(event_type, "execution_tools", payload,
                                   correlation_id=correlation_id)
