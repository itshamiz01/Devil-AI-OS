"""Assembly for the P-05 execution subsystem.

Mirrors :mod:`app.agents.subsystem`: ``build_execution`` constructs the
subsystem from validated settings and performs no I/O, and ``initialize``
reconciles what is code-defined and reports what the tables already hold.

Stage 3 assembles four components - the policy engine, the tool registry, the
request manager and the scheduler - and the scheduler holds one adapter: the
filesystem one. Its status says plainly what is not here yet: code, api,
document and data adapters do not exist, so requests routed to them stay
queued, and browser and desktop tools are registered disabled because this
environment cannot drive either. Reporting the absent parts is not
decoration: a caller that believed code execution existed would otherwise
discover otherwise from a failed request.

The capability authority and the approval service arrive from the subsystems
that own them (P-04 and P-01). Built without them, policy still evaluates and
fails closed on the checks that need them - a request requiring a capability
is refused for unverifiable authority rather than admitted on trust.
"""

from __future__ import annotations

from typing import Any

from ..core.config import Settings
from ..database.connection import Database
from ..database.repositories import ExecutionRequestRepo, ExecutionToolRepo
from ..events.bus import EventBus
from .adapters_fs import FilesystemAdapter
from .adapters_code import CodeAdapter
from .policy import ExecutionPolicy
from .registry import BUILTIN_CODE_TOOLS, BUILTIN_FS_TOOLS, ToolRegistry
from .requests import ExecutionRequestService
from .scheduler import ExecutionScheduler

__all__ = ["ExecutionServices", "build_execution", "initialize"]


class ExecutionServices:
    """The P-05 subsystem as the rest of the application sees it."""

    def __init__(self, *, settings: Settings, db: Database, bus: EventBus | None,
                 policy: ExecutionPolicy, registry: ToolRegistry,
                 requests: ExecutionRequestService,
                 scheduler: ExecutionScheduler | None = None,
                 notes: tuple[str, ...] = ()) -> None:
        self.settings = settings
        self.db = db
        self.bus = bus
        self.policy = policy
        self.registry = registry
        self.requests = requests
        self.scheduler = scheduler
        self.notes = list(notes)

    def status(self) -> dict[str, Any]:
        """What is assembled, and what is deliberately not yet."""
        return {
            "enabled": True,
            "stage": "P-05 Stage 4 (execution core + filesystem and code adapters)",
            "policy": True,
            "tool_registry": True,
            "request_manager": True,
            "adapters": {
                "filesystem": True,
                "code": True,
                "api": False,
                "document": False,
                "data": False,
                "browser": "disabled: unsupported in this environment",
                "desktop": "disabled: unsupported in this environment",
            },
            "scheduler": True,
            "workflows": False,
            "notes": tuple(self.notes),
        }


def build_execution(settings: Settings, db: Database, bus: EventBus | None = None,
                    *, capabilities: Any = None, approvals: Any = None,
                    monitor: Any = None, emergency: Any = None) -> ExecutionServices:
    """Assemble the subsystem. Construction performs no I/O.

    The keyword collaborators are optional for the reason the agent subsystem
    gives: the engine assembled without the capability authority still
    evaluates correctly and refuses what it cannot verify, so tests and
    degraded deployments do not silently lose a gate.
    """
    policy = ExecutionPolicy(db, settings, capabilities=capabilities,
                             approvals=approvals, monitor=monitor,
                             emergency=emergency)
    registry = ToolRegistry(db, settings, bus=bus)
    requests = ExecutionRequestService(db, settings, policy=policy,
                                       approvals=approvals, bus=bus)
    adapters = {"filesystem": FilesystemAdapter(db, settings, bus=bus),
                "code": CodeAdapter(db, settings, bus=bus)}
    scheduler = ExecutionScheduler(db, settings, policy=policy,
                                   adapters=adapters, bus=bus)
    notes = [
        "Stage 4 runs filesystem and code requests: submitted requests are "
        "policy-checked, then drained by the scheduler, which executes them "
        "and records the run. Requests for adapters that do not exist yet "
        "(api, document, data) stay queued until Stages 5-7 land them",
        "risk is computed by the policy engine from the tool and the action; "
        "a request cannot declare its own risk class, and a prohibited action "
        "is refused with no approval path",
        "Risk 2 work opens an approval in the central approvals table, bound "
        "by a hash of tool, action, parameters and scope; execution approvals "
        "are not a second queue",
        "browser and desktop tools are registered DISABLED at startup with "
        "the reason recorded: this environment has no browser binary, no "
        "display and no Windows UI Automation",
        "the execution capability entries in the P-04 catalog (filesystem.read, "
        "filesystem.write) are enabled by Stage 3 because the filesystem "
        "adapter that exercises them exists, and code.execute is enabled by "
        "Stage 4 because the code adapter exists; execution.tool, "
        "external.network and browser.control remain disabled until their "
        "adapters land, so capability checks refuse them honestly rather than "
        "admitting work nobody can perform",
        "the code adapter runs a single allow-listed interpreter inside the "
        "agent's workspace under a wall-clock timeout with capped output, and "
        "self-labels its isolation as 'subprocess-with-timeout (weak)': no OS "
        "sandbox is verifiable here (§30 rule 22), so the code tool is Risk 2 "
        "and requires owner approval on every run, and that human gate is the "
        "control standing in for the isolation this environment cannot provide",
        "external execution is locked off by the P-01 settings validator "
        "(AUTONOMUS_EXTERNAL_EXECUTION_ENABLED cannot be enabled), so api and "
        "browser adapters fail policy in this build by construction",
    ]
    return ExecutionServices(settings=settings, db=db, bus=bus, policy=policy,
                             registry=registry, requests=requests,
                             scheduler=scheduler, notes=tuple(notes))


async def initialize(services: ExecutionServices) -> dict[str, Any]:
    """Reconcile the code-defined tools and report what persisted.

    Recovery restores *definitions* - the browser and desktop tools exist in
    the registry, disabled, with their reasons - and writes no request, opens
    no approval and resumes nothing. A request that was QUEUED when the
    process stopped is still QUEUED, because nothing here may decide on its
    own that work should start.
    """
    reconciled = await services.registry.reconcile_builtin_tools()
    fs_reconciled = await services.registry.reconcile_builtin_tools(BUILTIN_FS_TOOLS)
    await services.registry.validate_builtin_fs_tools()
    code_reconciled = await services.registry.reconcile_builtin_tools(BUILTIN_CODE_TOOLS)
    await services.registry.validate_builtin_code_tools()
    async with services.db.session_factory() as session:
        tools = await ExecutionToolRepo(session).count()
        requests = await ExecutionRequestRepo(session).count()
        by_status = await ExecutionRequestRepo(session).count_by_status()
    return {
        "tools": tools,
        "builtin_created": reconciled["created"],
        "builtin_existing": reconciled["existing"],
        "fs_tools_created": fs_reconciled["created"],
        "fs_tools_existing": fs_reconciled["existing"],
        "code_tools_created": code_reconciled["created"],
        "code_tools_existing": code_reconciled["existing"],
        "requests": requests,
        "requests_queued": by_status.get("QUEUED", 0),
        "requests_awaiting_approval": by_status.get("AWAITING_APPROVAL", 0),
    }
