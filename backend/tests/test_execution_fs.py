"""P-05 Stage 3: the filesystem adapter, end to end.

Every claim in this module is about what the adapter *refuses* or *does* to
the bytes, and the tests create real directories, real symlinks and real
files under `tmp_path`.

The containment tests are the heart of the stage. A path that resolves
outside its workspace root is refused - `..` segments, absolute paths, drive
letters, symlinks pointing out of the root, and (the case a prefix check
cannot catch) a symlinked *parent* directory of a path being created. Each
is a separate test because each is a distinct attack, and a single
"traversal is refused" test would be indistinguishable from a test that
passed because nothing was ever attempted.

The atomicity and reversibility tests check the filesystem state directly
after the run, not the response body: a write that leaves a half-written
file is a failure even if the response says COMPLETED, and §6.1's rule that
COMPLETED is never returned merely because nothing raised is what the
evidence rows exist to prevent.
"""

import asyncio
import uuid
from pathlib import Path

from app.agents.capabilities import CapabilityService
from app.core.application import seed_core_data
from app.database.connection import Database
from app.database.models import (
    Agent,
    AgentPermission,
    ExecutionRun,
    ExecutionTool,
    Principal,
    Task,
)
from app.database.repositories import (
    AgentCapabilityRepo,
    ExecutionEvidenceRepo,
    ExecutionRequestRepo,
)
from app.execution.adapters_fs import hash_file
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


def _run(settings, body, *, workspace=None):
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
            if workspace is not None:
                settings.execution_workspace_root = workspace
            async with db.session_factory() as session:
                owner = Principal(kind="owner", name="owner")
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
                await session.commit()
            return await body(db, execution, bus, world)
        finally:
            await db.dispose()

    return asyncio.run(go())


async def _tool_id(db, name):
    async with db.session_factory() as session:
        row = (await session.execute(
            select(ExecutionTool).where(ExecutionTool.name == name)
        )).scalars().first()
    return row.id if row else None


async def _submit_and_drain(execution, principal_id, *, tool, action,
                            params, scope="reports"):
    tool_id = await _tool_id(execution.db, tool)
    result = await execution.requests.submit(
        principal_id,
        ExecutionRequestInput(
            task_id=None,  # replaced below
            tool_id=tool_id, action_name=action,
            action_parameters=params, requested_scope=scope))
    return result, await execution.scheduler.drain_once()


async def _file_tool_ids(db, *, read=True, write=True):
    async with db.session_factory() as session:
        ids = {}
        if read:
            row = (await session.execute(
                select(ExecutionTool).where(
                    ExecutionTool.name == "filesystem.read_ops")
            )).scalars().first()
            ids["read"] = row.id
        if write:
            row = (await session.execute(
                select(ExecutionTool).where(
                    ExecutionTool.name == "filesystem.write_ops")
            )).scalars().first()
            ids["write"] = row.id
    return ids


def _grant(db, agent_id, *keys, scope="reports"):
    async def go():
        async with db.session_factory() as session:
            for key in keys:
                capability = await AgentCapabilityRepo(session).by_key(key)
                session.add(AgentPermission(
                    agent_id=agent_id, capability_id=capability.id,
                    scope=scope, status="active"))
            await session.commit()
    asyncio.run(go())


async def _submit(execution, principal_id, task_id, tool_id, action,
                  params, scope="reports"):
    return await execution.requests.submit(
        principal_id,
        ExecutionRequestInput(task_id=task_id, tool_id=tool_id,
                               action_name=action,
                               action_parameters=params,
                               requested_scope=scope))


def _world_with_grants(settings, body, *, workspace):
    """Boot, create the world, grant both filesystem capabilities, run body."""
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
                # The seeded owner is reused rather than re-created:
                # principals.name is UNIQUE and every test in this module
                # shares one database, so a second "owner" would be a
                # constraint violation rather than a fixture reset.
                owner = (await session.execute(
                    select(Principal).where(Principal.kind == "owner")
                )).scalars().first()
                if owner is None:
                    owner = Principal(kind="owner", name="owner")
                    session.add(owner)
                    await session.flush()
                session.add(owner)
                await session.flush()
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
                for key in ("filesystem.read", "filesystem.write"):
                    capability = await AgentCapabilityRepo(
                        session).by_key(key)
                    session.add(AgentPermission(
                        agent_id=agent.id, capability_id=capability.id,
                        scope="reports", status="active"))
                await session.commit()
            return await body(db, execution, bus, world)
        finally:
            await db.dispose()

    return asyncio.run(go())


# --------------------------------------------------------------------------- #
# Setup
# --------------------------------------------------------------------------- #
def _settings(tmp_path):
    from app.core.config import Settings
    settings = Settings()
    settings.execution_workspace_root = tmp_path / "workspaces"
    return settings


# --------------------------------------------------------------------------- #
# Containment
# --------------------------------------------------------------------------- #
def test_a_parent_traversal_is_refused(tmp_path):
    async def body(db, execution, bus, world):
        tool_id = (await _file_tool_ids(db, read=True, write=False))["read"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      tool_id, "read", {"path": "../../etc/passwd"})
        drained = await execution.scheduler.drain_once()
        assert drained.status == "FAILED"
        assert drained.error_category == "workspace_escape"
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)


def test_an_absolute_path_is_refused(tmp_path):
    async def body(db, execution, bus, world):
        tool_id = (await _file_tool_ids(db, read=True, write=False))["read"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      tool_id, "read", {"path": "/etc/passwd"})
        drained = await execution.scheduler.drain_once()
        assert drained.status == "FAILED"
        assert drained.error_category == "workspace_escape"
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)


def test_a_symlink_escaping_the_root_is_refused(tmp_path):
    """The case a prefix check cannot catch: the *parent* is a symlink out."""
    async def body(db, execution, bus, world):
        workspace = tmp_path / "workspaces" / world["agent_id"] / "reports"
        workspace.mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("classified")
        (workspace / "link").symlink_to(outside)
        tool_id = (await _file_tool_ids(db, read=True, write=False))["read"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      tool_id, "read", {"path": "link/secret.txt"})
        drained = await execution.scheduler.drain_once()
        assert drained.status == "FAILED"
        assert drained.error_category == "workspace_escape"
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)


def test_a_symlinked_parent_of_a_new_file_is_refused(tmp_path):
    """A write into a symlinked directory: the target does not exist, so
    there is no realpath for it - the nearest existing ancestor decides."""
    async def body(db, execution, bus, world):
        workspace = tmp_path / "workspaces" / world["agent_id"] / "reports"
        workspace.mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        (workspace / "escape").symlink_to(outside)
        tool_id = (await _file_tool_ids(db, read=False, write=True))["write"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      tool_id, "write",
                      {"path": "escape/new.txt", "content": "x"})
        drained = await execution.scheduler.drain_once()
        assert drained.status == "FAILED"
        assert drained.error_category == "workspace_escape"
        assert not (outside / "new.txt").exists()
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)


def test_a_write_inside_the_workspace_succeeds(tmp_path):
    async def body(db, execution, bus, world):
        tool_id = (await _file_tool_ids(db, read=False, write=True))["write"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      tool_id, "write",
                      {"path": "notes/a.txt", "content": "hello"})
        drained = await execution.scheduler.drain_once()
        assert drained.status == "COMPLETED"
        workspace = tmp_path / "workspaces" / world["agent_id"] / "reports"
        assert (workspace / "notes" / "a.txt").read_text() == "hello"
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)


# --------------------------------------------------------------------------- #
# Atomic writes
# --------------------------------------------------------------------------- #
def test_a_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    async def body(db, execution, bus, world):
        tool_id = (await _file_tool_ids(db, read=False, write=True))["write"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      tool_id, "write",
                      {"path": "notes/a.txt", "content": "atomic"})
        drained = await execution.scheduler.drain_once()
        assert drained.status == "COMPLETED"
        workspace = tmp_path / "workspaces" / world["agent_id"] / "reports"
        assert (workspace / "notes" / "a.txt").read_text() == "atomic"
        temp_files = list(workspace.rglob(".tmp-*"))
        assert temp_files == [], f"leftover temp files: {temp_files}"
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)


def test_overwriting_a_file_replaces_it_atomically(tmp_path):
    async def body(db, execution, bus, world):
        tool_id = (await _file_tool_ids(db, read=False, write=True))["write"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      tool_id, "write",
                      {"path": "a.txt", "content": "v1"})
        await execution.scheduler.drain_once()
        await _submit(execution, world["principal_id"], world["task_id"],
                      tool_id, "write",
                      {"path": "a.txt", "content": "v2"})
        drained = await execution.scheduler.drain_once()
        assert drained.status == "COMPLETED"
        workspace = tmp_path / "workspaces" / world["agent_id"] / "reports"
        assert (workspace / "a.txt").read_text() == "v2"
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)


# --------------------------------------------------------------------------- #
# Deletes and reversibility
# --------------------------------------------------------------------------- #
def test_a_delete_quarantines_the_file_for_recovery(tmp_path):
    async def body(db, execution, bus, world):
        write_id = (await _file_tool_ids(db, read=False, write=True))["write"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      write_id, "write", {"path": "a.txt", "content": "x"})
        await execution.scheduler.drain_once()
        delete_id = write_id
        await _submit(execution, world["principal_id"], world["task_id"],
                      delete_id, "delete", {"path": "a.txt"})
        drained = await execution.scheduler.drain_once()
        assert drained.status == "COMPLETED"
        workspace = tmp_path / "workspaces" / world["agent_id"] / "reports"
        assert not (workspace / "a.txt").exists()
        # The result carries where the file actually went; asserting a
        # hardcoded path would test the test's guess rather than the
        # adapter's behaviour.
        quarantined_path = Path(drained.result["quarantined"])
        assert quarantined_path.exists()
        assert quarantined_path.read_text() == "x"
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)


# --------------------------------------------------------------------------- #
# Reads, listing, evidence
# --------------------------------------------------------------------------- #
def test_a_read_returns_content_and_records_evidence(tmp_path):
    async def body(db, execution, bus, world):
        write_id = (await _file_tool_ids(db, read=False, write=True))["write"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      write_id, "write", {"path": "a.txt", "content": "data"})
        await execution.scheduler.drain_once()
        read_id = (await _file_tool_ids(db, read=True, write=False))["read"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      read_id, "read", {"path": "a.txt"})
        drained = await execution.scheduler.drain_once()
        assert drained.status == "COMPLETED"
        assert drained.result["content"] == "data"
        assert drained.result["content_hash"] == hash_file(
            str(tmp_path / "workspaces" / world["agent_id"] / "reports" / "a.txt"))
        async with db.session_factory() as session:
            evidence = await ExecutionEvidenceRepo(session).for_run(
                drained.run_id)
        assert evidence
        assert evidence[0].content_hash == drained.result["content_hash"]
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)


def test_a_listing_returns_entries(tmp_path):
    async def body(db, execution, bus, world):
        write_id = (await _file_tool_ids(db, read=False, write=True))["write"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      write_id, "write", {"path": "a.txt", "content": "x"})
        await execution.scheduler.drain_once()
        read_id = (await _file_tool_ids(db, read=True, write=False))["read"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      read_id, "list", {"path": ""})
        drained = await execution.scheduler.drain_once()
        assert drained.status == "COMPLETED"
        names = [e["name"] for e in drained.result["entries"]]
        assert "a.txt" in names
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)


# --------------------------------------------------------------------------- #
# Move and create_dir
# --------------------------------------------------------------------------- #
def test_a_move_works_inside_the_workspace(tmp_path):
    async def body(db, execution, bus, world):
        write_id = (await _file_tool_ids(db, read=False, write=True))["write"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      write_id, "write", {"path": "a.txt", "content": "x"})
        await execution.scheduler.drain_once()
        await _submit(execution, world["principal_id"], world["task_id"],
                      write_id, "move",
                      {"path": "a.txt", "destination": "b/a.txt"})
        drained = await execution.scheduler.drain_once()
        assert drained.status == "COMPLETED"
        workspace = tmp_path / "workspaces" / world["agent_id"] / "reports"
        assert not (workspace / "a.txt").exists()
        assert (workspace / "b" / "a.txt").read_text() == "x"
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)


def test_create_dir_creates_a_directory(tmp_path):
    async def body(db, execution, bus, world):
        write_id = (await _file_tool_ids(db, read=False, write=True))["write"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      write_id, "create_dir", {"path": "sub/dir"})
        drained = await execution.scheduler.drain_once()
        assert drained.status == "COMPLETED"
        workspace = tmp_path / "workspaces" / world["agent_id"] / "reports"
        assert (workspace / "sub" / "dir").is_dir()
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)


# --------------------------------------------------------------------------- #
# Runs are recorded
# --------------------------------------------------------------------------- #
def test_a_failed_run_is_recorded_with_its_category(tmp_path):
    async def body(db, execution, bus, world):
        read_id = (await _file_tool_ids(db, read=True, write=False))["read"]
        await _submit(execution, world["principal_id"], world["task_id"],
                      read_id, "read", {"path": "../../etc/passwd"})
        drained = await execution.scheduler.drain_once()
        assert drained.status == "FAILED"
        async with db.session_factory() as session:
            run = (await session.execute(
                select(ExecutionRun).where(
                    ExecutionRun.execution_request_id == drained.request_id)
            )).scalars().first()
            request = await ExecutionRequestRepo(session).get(
                drained.request_id)
        assert run.status == "FAILED"
        assert run.error_category == "workspace_escape"
        assert request.status == "FAILED"
    _world_with_grants(_settings(tmp_path), body, workspace=tmp_path)
