"""P-05 Stage 4: the code execution adapter, end to end.

The code adapter runs one allow-listed interpreter inside a managed workspace
under a wall-clock timeout, with capped output and a minimal environment. The
tests here exercise the adapter both directly (constructing it and calling
`execute`, which is what the scheduler does) and through the request path (a
Risk-2 code run held for owner approval, and a run that a standing
authorization carries through to execution).

The tests create real subprocesses under `tmp_path` - a real `python -c` that
prints, sleeps, exits non-zero, or tries to name a disallowed interpreter - so
each test is a distinct behaviour rather than a mock that could pass vacuously.
"""

import asyncio
import types
import uuid

from app.agents.capabilities import CapabilityService
from app.core.application import seed_core_data
from app.database.connection import Database
from app.database.models import (
    Agent,
    AgentPermission,
    ExecutionTool,
    Principal,
    Task,
)
from app.database.repositories import (
    AgentCapabilityRepo,
    ConfigRepo,
    ExecutionRequestRepo,
)
from app.execution.adapters_code import (
    ISOLATION_STRENGTH,
    CodeAdapter,
    InterpreterNotAllowedError,
)
from app.execution.requests import STANDING_AUTHORIZATIONS_KEY
from app.execution.schemas import ExecutionRequestInput
from app.execution.subsystem import build_execution, initialize
from app.monitoring.system_monitor import SystemMonitor
from app.permissions.approvals import ApprovalService
from sqlalchemy import select


class _Bus:
    def __init__(self):
        self.events = []

    async def publish_new(self, event_type, source, payload=None, **kwargs):
        self.events.append((event_type, payload or {}))


def _settings(tmp_path):
    from app.core.config import Settings
    settings = Settings()
    settings.execution_workspace_root = tmp_path / "workspaces"
    settings.execution_code_timeout_seconds = 5
    return settings


def _fake_workspace(root):
    """A workspace-like object, as the scheduler's `resolve_workspace` returns."""
    return types.SimpleNamespace(root_path=str(root), id="ws")


# --------------------------------------------------------------------------- #
# Adapter-level: the interpreter, the timeout, the output, the environment
# --------------------------------------------------------------------------- #
def test_a_run_executes_the_program_and_returns_stdout(tmp_path):
    adapter = CodeAdapter(None, _settings(tmp_path))
    result = adapter.execute(action="run", workspace=_fake_workspace(tmp_path),
                             code="print('hello from subprocess')")
    assert result["outcome"] == "COMPLETED"
    assert result["exit_code"] == 0
    assert "hello from subprocess" in result["stdout"]
    assert result["isolation_strength"] == ISOLATION_STRENGTH


def test_the_run_gets_a_controlled_environment_not_the_engines(tmp_path):
    """A code run must not read the engine's secrets from its environment."""
    import os
    adapter = CodeAdapter(None, _settings(tmp_path))
    # Set a secret in the engine's environment; the child must not see it.
    os.environ["SUPERSECRET_API_KEY"] = "engine-secret-value"
    try:
        result = adapter.execute(
            action="run", workspace=_fake_workspace(tmp_path),
            code="import os; print(os.environ.get('SUPERSECRET_API_KEY', 'ABSENT'))")
        assert "ABSENT" in result["stdout"]
        assert "engine-secret-value" not in result["stdout"]
    finally:
        os.environ.pop("SUPERSECRET_API_KEY", None)


def test_a_non_zero_exit_is_a_failed_run_not_an_adapter_error(tmp_path):
    adapter = CodeAdapter(None, _settings(tmp_path))
    result = adapter.execute(
        action="run", workspace=_fake_workspace(tmp_path),
        code="import sys; print('boom'); sys.exit(3)")
    assert result["outcome"] == "FAILED"
    assert result["exit_code"] == 3
    assert result["error_category"] == "nonzero_exit"


def test_a_timeout_kills_the_run(tmp_path):
    settings = _settings(tmp_path)
    settings.execution_code_timeout_seconds = 1
    adapter = CodeAdapter(None, settings)
    result = adapter.execute(
        action="run", workspace=_fake_workspace(tmp_path),
        code="import time; time.sleep(30)")
    assert result["outcome"] == "TIMED_OUT"
    assert result["error_category"] == "timeout"


def test_output_is_capped_and_flagged(tmp_path):
    settings = _settings(tmp_path)
    settings.execution_code_output_cap_bytes = 1024
    adapter = CodeAdapter(None, settings)
    result = adapter.execute(
        action="run", workspace=_fake_workspace(tmp_path),
        code="print('x' * 50000)")
    assert result["outcome"] == "COMPLETED_WITH_WARNINGS"
    assert result["truncated"] is True
    # The cap is honoured: the captured stdout is bounded, not the full output.
    assert len(result["stdout"]) < 50000


def test_a_disallowed_interpreter_is_refused(tmp_path):
    adapter = CodeAdapter(None, _settings(tmp_path))
    try:
        adapter.execute(action="run", workspace=_fake_workspace(tmp_path),
                        code="print(1)", interpreter="/bin/sh")
    except InterpreterNotAllowedError as exc:
        assert exc.code == "interpreter_not_allowed"
        return
    raise AssertionError("a disallowed interpreter must be refused, not run")


def test_the_allow_listed_interpreter_is_the_engine_by_default(tmp_path):
    import sys
    adapter = CodeAdapter(None, _settings(tmp_path))
    allowed = adapter._allowed_interpreter(None)
    assert allowed == sys.executable
    # Requesting the allow-listed interpreter by basename is honoured.
    assert adapter._allowed_interpreter("python") == sys.executable


# --------------------------------------------------------------------------- #
# Request path: the Risk-2 approval gate and a standing authorization
# --------------------------------------------------------------------------- #
async def _code_tool_id(db):
    async with db.session_factory() as session:
        row = (await session.execute(
            select(ExecutionTool).where(ExecutionTool.name == "code.execute")
        )).scalars().first()
    return row.id if row else None


def _world_with_grants(settings, body, *, workspace):
    """Boot, create the world, grant code.execute, run body.

    A plain ``def`` that calls ``asyncio.run`` internally - like the filesystem
    test's harness. Marking it ``async def`` and calling it without ``await``
    makes the three tests that use it pass vacuously (the coroutine is never
    run); that trap was hit once already in Stage 3 and must not recur.
    """
    async def go():
        db = Database(settings)
        try:
            await db.initialize()
            await seed_core_data(db, settings)
            bus = _Bus()
            approvals = ApprovalService(db, bus)
            capabilities = CapabilityService(db, settings)
            await capabilities.reconcile_catalog()
            execution = build_execution(
                settings, db, bus, capabilities=capabilities,
                approvals=approvals, monitor=SystemMonitor(settings))
            await initialize(execution)
            async with db.session_factory() as session:
                owner = (await session.execute(
                    select(Principal).where(Principal.kind == "owner")
                )).scalars().first()
                if owner is None:
                    owner = Principal(kind="owner", name="owner")
                    session.add(owner)
                    await session.flush()
                session.add(owner)
                await session.flush()
                principal = Principal(
                    kind="agent", name=f"agent-{uuid.uuid4().hex[:8]}")
                session.add(principal)
                await session.flush()
                agent = Agent(
                    principal_id=principal.id,
                    name=f"worker-{principal.id[:8]}", role="research")
                session.add(agent)
                await session.flush()
                task = Task(name="job", handler="test.handler",
                            status="QUEUED", creator_id=owner.id,
                            assigned_agent_id=agent.id)
                session.add(task)
                await session.flush()
                world = {"agent_id": agent.id, "principal_id": principal.id,
                         "task_id": task.id, "owner_id": owner.id}
                # Grant the code.execute capability to the agent, scoped.
                capability = await AgentCapabilityRepo(
                    session).by_key("code.execute")
                session.add(AgentPermission(
                    agent_id=agent.id, capability_id=capability.id,
                    scope="reports", status="active"))
                await session.commit()
            return await body(db, execution, bus, world)
        finally:
            await db.dispose()

    return asyncio.run(go())


async def _submit(execution, principal_id, task_id, tool_id, params,
                  scope="reports"):
    return await execution.requests.submit(
        principal_id,
        ExecutionRequestInput(task_id=task_id, tool_id=tool_id,
                               action_name="run", action_parameters=params,
                               requested_scope=scope))


def test_a_code_run_without_authorization_waits_for_the_owner(tmp_path):
    """§30 rule 22: weak-isolated untrusted code does not run without approval."""
    async def body(db, execution, bus, world):
        tool_id = await _code_tool_id(db)
        result = await _submit(execution, world["principal_id"],
                               world["task_id"], tool_id,
                               {"code": "print('hi')"})
        # Risk 2 with no standing authorization: held, not run.
        assert result.status == "AWAITING_APPROVAL"
        # The scheduler does not execute an approval-pending run.
        drained = await execution.scheduler.drain_once()
        assert drained is None or drained.status == "AWAITING_APPROVAL"
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)


def test_a_standing_authorization_carries_a_code_run_through_to_execution(tmp_path):
    """With a standing authorization, the Risk-2 run is admitted and runs."""
    async def body(db, execution, bus, world):
        tool_id = await _code_tool_id(db)
        async with db.session_factory() as session:
            await ConfigRepo(session).set(STANDING_AUTHORIZATIONS_KEY, {
                "authorizations": [{
                    "id": "sa-code-1", "agent_id": world["agent_id"],
                    "tool_id": tool_id, "action_name": "run",
                    "scope": "reports", "max_uses": 5, "revoked": False,
                    "expires_at": "2999-01-01T00:00:00+00:00"}]})
            await session.commit()
        result = await _submit(execution, world["principal_id"],
                               world["task_id"], tool_id,
                               {"code": "print('ran under authorization')"})
        assert result.status == "QUEUED"
        drained = await execution.scheduler.drain_once()
        assert drained.status == "COMPLETED"
        assert "ran under authorization" in drained.result["stdout"]
        # The run is recorded with its exit code and the weak isolation label.
        async with db.session_factory() as session:
            runs = await ExecutionRequestRepo(session).runs_for(
                drained.request_id)
        assert runs
        assert runs[0].exit_code == 0
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)


def test_the_code_tool_is_registered_and_available(tmp_path):
    """The code tool is seeded, validated, and reports its isolation."""
    async def body(db, execution, bus, world):
        tool_id = await _code_tool_id(db)
        assert tool_id is not None
        view = await execution.registry.get_tool(tool_id)
        assert view.status == "AVAILABLE"
        assert view.isolation_strength == ISOLATION_STRENGTH
        assert "run" in view.supported_actions
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)
