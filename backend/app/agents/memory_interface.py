"""Scoped agent memory interface (§15) — the P-09 seam.

P-04 does NOT build a memory engine. This interface defines how an agent
requests memory, enforces scoping, and serves ONLY the two scopes backed
by data P-04 legitimately owns:

- ``agent_configuration_history``: the requesting agent's OWN §13 history.
- ``previous_task_references``: the requesting agent's OWN assignments
  (references and outcomes — not other agents' work).

The remaining scopes (approved contextual memory, business context,
approved lessons/evaluations) return an explicit UNAVAILABLE result:
P-09 owns them. An agent can never read another agent's scopes through
this interface; owner/system principals may read any agent's two served
scopes for oversight.
"""
from __future__ import annotations

from typing import Protocol

from ..core.exceptions import PermissionDeniedError
from ..database.repositories.agents import AssignmentRepository, ConfigHistoryRepository
from ..permissions.models import Principal, PrincipalType

SERVED_SCOPES = ("agent_configuration_history", "previous_task_references")
DEFERRED_SCOPES = ("approved_contextual_memory", "business_context",
                   "approved_lessons_or_evaluations")
ALL_SCOPES = SERVED_SCOPES + DEFERRED_SCOPES


class AgentMemoryInterface(Protocol):
    """The contract P-09 will implement in full. P-04 ships
    :class:`P04MemoryInterface`, which serves SERVED_SCOPES and reports
    DEFERRED_SCOPES as unavailable."""

    def read(self, *, requester: Principal, agent_id: str, scope: str,
             limit: int = 20) -> dict: ...


class P04MemoryInterface:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def read(self, *, requester: Principal, agent_id: str, scope: str,
             limit: int = 20) -> dict:
        if scope not in ALL_SCOPES:
            return {"scope": scope, "status": "unavailable", "items": [],
                    "note": f"unknown memory scope '{scope}'"}
        if requester.type is PrincipalType.AGENT and requester.id != agent_id:
            raise PermissionDeniedError(
                "an agent may only read its OWN memory scopes",
                details={"error_category": "CAPABILITY_NOT_AUTHORIZED", "scope": scope})
        if scope in DEFERRED_SCOPES:
            return {"scope": scope, "status": "unavailable", "items": [],
                    "note": "scope is owned by P-09 (Memory and Continuous Learning), "
                            "which is not built; P-04 does not simulate it"}
        session = self._session_factory()
        try:
            if scope == "agent_configuration_history":
                rows = ConfigHistoryRepository(session).for_agent(agent_id)
                items = [{"configuration_version": r.configuration_version,
                          "change_reason": r.change_reason,
                          "changed_by": r.changed_by_id,
                          "created_at": r.created_at.isoformat() if r.created_at else None}
                         for r in rows[-limit:]]
            else:  # previous_task_references
                rows, _ = AssignmentRepository(session).for_agent(agent_id, limit=limit, offset=0)
                items = [{"assignment_id": r.id, "task_id": r.task_id,
                          "objective": r.objective, "status": r.status,
                          "business_ref": r.business_ref} for r in rows]
            return {"scope": scope, "status": "ok", "items": items,
                    "note": "scoped to this agent only"}
        finally:
            session.close()
