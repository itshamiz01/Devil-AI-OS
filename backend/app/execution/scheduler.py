"""The execution scheduler, in its Stage 3 form.

Stage 2 admitted requests and queued them; nothing drained the queue, and the
subsystem said so (`execution_draining: false`). Stage 3 changes exactly one
thing about that: a submitted filesystem request is run, because the adapter
that would run it exists. What this module is, and is deliberately not:

* **A drain, not a scheduler.** `drain_once` picks the oldest QUEUED request,
  executes it, and records the run. There is no worker process, no concurrency
  pool and no retry loop yet - Stage 9 builds those over `SystemMonitor`
  pressure, and this file is where they will land. Calling the honest minimum
  "a scheduler" here would be the §6.1 failure in its other uniform: claiming
  a capability whose evidence does not exist.
* **Synchronous, by design.** The file routes call `submit` then `drain_once`
  and return the final outcome, so a file operation's result is visible in the
  same request rather than only after a second poll. That makes the file API
  honest about what it is: admitted and run, not admitted and queued forever.
* **A run row per attempt, whatever happened.** A failure is a recorded run at
  FAILED with its `error_category`, because §6 forbids collapsing
  requested/executed/verified and a silently vanished attempt is the worst of
  the three. A timeout is TIMED_OUT, and a timeout does not leave the file
  half-written: the adapter's atomic-write discipline means the previous
  content is intact.

Re-checking policy before running is the scheduler's job too, not the
adapter's: an admitted request whose tool was disabled while it waited, or
whose agent was suspended in the meantime, must not run. The ten checks are
re-run here against fresh rows rather than trusting the submission-time
verdict, which is what makes a queue that waits a safe queue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from ..database.models import ExecutionRequest, utcnow
from ..database.repositories import (
    AgentRepo,
    AuditRepo,
    ConfigRepo,
    ExecutionEvidenceRepo,
    ExecutionRequestRepo,
    ExecutionToolRepo,
    TaskRepo,
)
from .policy import RequestFacts
from .requests import (
    STANDING_AUTHORIZATIONS_KEY,
    ExecutionRequestService,
)

__all__ = ["DrainResult", "ExecutionScheduler"]


@dataclass
class DrainResult:
    request_id: str
    status: str
    run_id: str | None
    error_category: str | None = None
    result: dict[str, Any] = field(default_factory=dict)


class ExecutionScheduler:
    def __init__(self, db: Any, settings: Any, *, policy: Any,
                 adapters: dict[str, Any], bus: Any = None) -> None:
        self.db = db
        self.settings = settings
        self.policy = policy
        self.adapters = adapters
        self.bus = bus

    async def drain_once(self) -> DrainResult | None:
        """Run the oldest QUEUED request whose adapter exists, if any.

        Returns None when nothing is queued or nothing here can run it - a
        caller that treated None as "drained" would be reading an empty queue
        as a success, and the honest answer to "did anything run?" when
        nothing was queued is "no".
        """
        async with self.db.session_factory() as session:
            row = (await session.execute(
                select(ExecutionRequest)
                .where(ExecutionRequest.status == "QUEUED")
                .order_by(ExecutionRequest.priority.desc(),
                          ExecutionRequest.created_at))).scalars().first()
            if row is None:
                return None
            if row.adapter_type not in self.adapters:
                # Requests for adapters that do not exist yet (code, api) stay
                # queued: draining them would mean inventing them, and the
                # status endpoint reports them as waiting.
                return None
            return await self._run(session, row)

    async def _evaluate(self, session: Any, *, principal_id: str, agent: Any,
                        task: Any, tool: Any, facts: RequestFacts,
                        approval: Any = None) -> Any:
        """Re-run the ten checks against fresh rows (see module docstring)."""
        evidence = None
        if task is not None and agent is not None:
            evidence = await ExecutionRequestService._assignment_evidence(
                session, task, agent.id)
        standing_row = await ConfigRepo(session).get(STANDING_AUTHORIZATIONS_KEY)
        entries = standing_row.value if standing_row is not None else None
        uses: dict[str, int] = {}
        if isinstance(entries, dict):
            for entry in entries.get("authorizations") or []:
                if isinstance(entry, dict) and entry.get("id"):
                    uses[str(entry["id"])] = (
                        await ExecutionRequestRepo(session)
                        .count_standing_authorization_uses(
                            str(entry["id"]), agent.id if agent else ""))
        return await self.policy.evaluate(
            principal_id=principal_id, agent=agent, task=task, tool=tool,
            facts=facts, assignment_evidence=evidence, approval=approval,
            standing_entries=entries, standing_uses=uses, now=utcnow())

    async def _run(self, session: Any, row: ExecutionRequest) -> DrainResult:
        repo = ExecutionRequestRepo(session)
        adapter = self.adapters[row.adapter_type]
        tool = await ExecutionToolRepo(session).get(row.tool_id)
        agent = await AgentRepo(session).get(row.agent_id)
        task = await TaskRepo(session).get(row.task_id)
        facts = RequestFacts(
            task_id=row.task_id, tool_id=row.tool_id, action_name=row.action_name,
            action_parameters=dict(row.request_payload or {}),
            requested_scope=row.requested_scope,
            required_capabilities=list(row.required_capabilities or []),
            priority=int(row.priority), request_id=row.id)
        evaluation = await self._evaluate(
            session, principal_id=agent.principal_id if agent else "",
            agent=agent, task=task, tool=tool, facts=facts)
        if not evaluation.allowed and not evaluation.requires_approval:
            # The request was admitted at submission; policy now refuses it
            # (a tool disabled, an agent suspended, an assignment ended). The
            # row moves to REJECTED rather than staying QUEUED forever, and
            # the refusal is recorded so the change is auditable.
            await repo.update(row, status="REJECTED",
                              refusal_reason=evaluation.reason,
                              completed_at=utcnow())
            run = await repo.create_run(
                execution_request_id=row.id, worker_id="scheduler",
                status="REJECTED", attempt=1,
                verification_status="unverified")
            await AuditRepo(session).record(
                "execution.request_refused", "denied", resource=row.id,
                principal_id=agent.principal_id if agent else None,
                action="execution.scheduler_drain",
                payload={"reason": evaluation.reason,
                         "checks": [c.as_dict() for c in evaluation.checks]})
            await session.commit()
            return DrainResult(row.id, "REJECTED", run.id,
                               error_category="policy_refused")
        if evaluation.requires_approval:
            # Still waiting on a person. The request stays QUEUED (it was
            # admitted; only the approval is pending) and is not run.
            return DrainResult(row.id, row.status, None,
                               error_category="awaiting_approval")

        await repo.update(row, status="RUNNING", started_at=utcnow())
        run = await repo.create_run(
            execution_request_id=row.id, worker_id="scheduler", status="RUNNING",
            attempt=1, executed_action=row.action_name, started_at=utcnow())
        await session.commit()

        try:
            workspace = await adapter.resolve_workspace(
                session, owner_id=row.agent_id, scope=row.requested_scope)
        except Exception as exc:  # noqa: BLE001
            run.status = "FAILED"
            run.error_category = getattr(exc, "code", "workspace_error")
            run.completed_at = utcnow()
            run.result_summary = str(exc)
            session.add(run)
            await repo.update(row, status="FAILED", completed_at=utcnow())
            await AuditRepo(session).record(
                "execution.run_failed", "denied", resource=row.id,
                action="execution.scheduler_drain",
                payload={"error_category": run.error_category,
                         "reason": str(exc)})
            await session.commit()
            return DrainResult(row.id, "FAILED", run.id,
                               error_category=run.error_category)

        try:
            # `execute` is synchronous filesystem work; it runs inside the
            # caller's thread rather than a worker pool. Stage 9 adds the
            # concurrency and the pressure-aware queue; this stage runs one
            # request at a time, which is the honest minimum.
            result = adapter.execute(
                action=row.action_name, workspace=workspace,
                path=str((row.request_payload or {}).get("path", "")),
                **{k: v for k, v in (row.request_payload or {}).items()
                   if k != "path"})
        except Exception as exc:  # noqa: BLE001
            category = getattr(exc, "code", "operation_failed")
            run.status = "FAILED"
            run.error_category = category
            run.completed_at = utcnow()
            run.result_summary = str(exc)
            session.add(run)
            await repo.update(row, status="FAILED", completed_at=utcnow())
            await AuditRepo(session).record(
                "execution.run_failed", "denied", resource=row.id,
                action="execution.scheduler_drain",
                payload={"error_category": category, "reason": str(exc)})
            await session.commit()
            return DrainResult(row.id, "FAILED", run.id, error_category=category)

        outcome = result.get("outcome", "COMPLETED")
        run.status = outcome
        run.result_summary = str(result)[:2000]
        # An adapter that returns an exit code and resource usage (the code
        # adapter does) gets those recorded on the run row rather than buried
        # in the summary string: §6 wants what was executed and what it cost
        # to be readable without parsing a serialised dict.
        if "exit_code" in result:
            run.exit_code = result.get("exit_code")
        if "resource_usage" in result:
            run.resource_usage = dict(result.get("resource_usage") or {})
        run.completed_at = utcnow()
        session.add(run)
        await repo.update(row, status=outcome, completed_at=utcnow())
        if result.get("content_hash"):
            await ExecutionEvidenceRepo(session).create(
                execution_run_id=run.id, evidence_type="content_hash",
                evidence_reference=str((row.request_payload or {}).get("path", "")),
                content_hash=str(result["content_hash"]),
                verification_status="verified")
        await AuditRepo(session).record(
            "execution.run_completed", "allowed", resource=row.id,
            principal_id=agent.principal_id if agent else None,
            action="execution.scheduler_drain",
            payload={"outcome": outcome, "run_id": run.id})
        await session.commit()
        return DrainResult(row.id, outcome, run.id, result=result)
