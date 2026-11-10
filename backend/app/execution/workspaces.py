"""Managed workspaces (§9.1) — Execution Environment Manager.

Layout under the execution root (adapted from §9.1 to the repository):

    <root>/shared/            readable/writable by any authorized agent
    <root>/projects/          business/project work (business_ref scoped)
    <root>/businesses/        business/project work (business_ref scoped)
    <root>/agent_workspaces/<agent_id>/   one agent's private workspace
    <root>/temporary/         engine-internal (code runs); NOT agent-addressable
    <root>/quarantine/        reversible-deletion holding (§9.3)

Authorization rule (deterministic, checked in the policy layer AND again
in the filesystem adapter): an agent may address its own workspace and
``shared``; ``projects``/``businesses`` require the request to carry a
``business_ref``; ``temporary`` is internal-only; ``quarantine`` is
read/list for the owning agent and writable only as the destination of a
governed ``delete``.
"""
from __future__ import annotations

from pathlib import Path

from ..database.models.execution import ExecutionWorkspace
from ..database.repositories.execution import ExecutionWorkspaceRepository
from . import constants as C
from .errors import WorkspaceError


class WorkspaceManager:
    def __init__(self, session_factory, root: Path):
        self._session_factory = session_factory
        self.root = Path(root)

    # ------------------------------------------------------------------ seed
    def seed_workspaces(self) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        for kind in C.WORKSPACE_KINDS:
            (self.root / kind).mkdir(parents=True, exist_ok=True)
        session = self._session_factory()
        try:
            repo = ExecutionWorkspaceRepository(session)
            added = 0
            for kind in C.SYSTEM_WORKSPACES:
                if repo.get_by_name(kind) is None:
                    repo.add(ExecutionWorkspace(
                        name=kind, owner_type="system", owner_id=None, kind=kind,
                        root_path=str(self.root / kind),
                        permission_scope="managed", status="active"))
                    added += 1
            return added
        finally:
            session.close()

    def ensure_agent_workspace(self, agent_id: str) -> ExecutionWorkspace:
        name = f"agent:{agent_id}"
        session = self._session_factory()
        try:
            repo = ExecutionWorkspaceRepository(session)
            existing = repo.get_by_name(name)
            if existing is not None:
                return existing
            path = self.root / "agent_workspaces" / agent_id
            path.mkdir(parents=True, exist_ok=True)
            return repo.add(ExecutionWorkspace(
                name=name, owner_type="agent", owner_id=agent_id, kind="agent",
                root_path=str(path), permission_scope=f"agent:{agent_id}",
                status="active"))
        finally:
            session.close()

    # ------------------------------------------------------------------ read
    def get_workspace(self, name: str) -> ExecutionWorkspace:
        session = self._session_factory()
        try:
            workspace = ExecutionWorkspaceRepository(session).get_by_name(name)
            if workspace is None or workspace.status != "active":
                raise WorkspaceError(f"workspace '{name}' does not exist or is not active",
                                     details={"error_category": "WORKSPACE_NOT_FOUND"})
            return workspace
        finally:
            session.close()

    def list_workspaces(self) -> list[ExecutionWorkspace]:
        session = self._session_factory()
        try:
            return ExecutionWorkspaceRepository(session).list()
        finally:
            session.close()

    def quarantine_workspace(self) -> ExecutionWorkspace:
        return self.get_workspace("quarantine")

    def temporary_root(self) -> Path:
        path = self.root / "temporary"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ----------------------------------------------------------- authorization
    @staticmethod
    def is_authorized(workspace: ExecutionWorkspace, agent_id: str, *,
                      write: bool, business_ref: str | None = None,
                      internal: bool = False) -> bool:
        if internal:
            return True
        if workspace.kind == "agent":
            return workspace.owner_id == agent_id
        if workspace.kind == "shared":
            return True
        if workspace.kind in ("projects", "businesses"):
            if business_ref:
                return True
            return not write
        if workspace.kind == "quarantine":
            return not write
        if workspace.kind == "temporary":
            return False
        return False
