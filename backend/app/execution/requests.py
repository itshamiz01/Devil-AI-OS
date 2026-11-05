"""The execution request manager (§5A, §6): steps 3-9 of the §4 lifecycle.

An agent submits a request; this module validates it, has policy classify and
gate it, opens the approval a sensitive request needs, and leaves it QUEUED.
Nothing here executes anything - adapters are Stages 3-7 and the scheduler is
its own component, so a QUEUED request at the end of Stage 2 is an honest
state: *admitted and waiting*, in a system that does not yet run work. The
subsystem status says exactly that rather than implying a queue that drains.

Five decisions shape the module.

**Identity comes from the principal, never the payload.** The request model
has no agent field. The agent is resolved from the authenticated principal
(`agents.principal_id`), so an agent cannot submit as another agent by naming
it (§21: "Do not trust client-supplied agent identity").

**A structural failure is an exception; a policy failure is a REJECTED row.**
Asking for a tool or task that does not exist is a malformed request - there
is nothing to record it against - so it raises, like an assignment request
for a missing task. A well-formed request that policy refuses *is* recorded,
at REJECTED with the reason, because §6.1 has REJECTED as an outcome and an
owner auditing "what did agents try to do?" needs those rows. The route turns
that row into a 409 carrying the evaluation, so the refusal cannot be read
past, while the row remains.

**Approvals are the central service's, bound by hash.** A Risk 2 request that
policy cannot clear opens an approval in `approvals` (action
`execution.execute`, resource this request's id, payload hash over tool,
action, parameters and scope) and waits at AWAITING_APPROVAL. When the owner
decides, the agent retries; policy re-runs and `verify_binding` proves the
request being admitted is the request that was approved - not a similar one
the agent substituted afterwards.

**The approval opens outside the request's transaction.** Submission commits
the request row first, then creates the approval, then records the reference
in a short second transaction. Creating it inside the submission's session
deadlocks on SQLite: the request's uncommitted write holds the writer lock
the approval's own session needs for its insert. The intermediate state - a
request at AWAITING_APPROVAL without a reference yet - is visible only
between two commits in the same call, and retry tolerates it by opening the
approval then instead (see `retry`).

**Idempotency returns the original.** Repeating a submission with the same
key returns the existing request, whatever state it reached, rather than
admitting the work twice (§16.2). The unique constraint named in the schema
is what makes that safe under a race; this module handles the ordinary path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from ..core.config import Settings
from ..core.exceptions import ConflictError, ForbiddenError, NotFoundError
from ..database.models import utcnow
from ..database.repositories import (
    AgentAssignmentRepo,
    AgentRepo,
    ApprovalRepo,
    AuditRepo,
    ConfigRepo,
    ExecutionRequestRepo,
    ExecutionToolRepo,
    TaskRepo,
)
from ..agents.schemas import IN_FLIGHT_ASSIGNMENT_STATUSES
from ..permissions.models import ApprovalCreateRequest
from .policy import (
    APPROVAL_ACTION,
    POLICY_CHECKS,
    ExecutionPolicy,
    PolicyEvaluation,
    RequestFacts,
    binding_parameters,
    classify_risk,
)
from .registry import ToolNotFoundError
from .schemas import (
    APPROVAL_RISK_BY_CLASS,
    EXECUTION_OUTCOMES,
    OUTCOME_TRANSITIONS,
    TERMINAL_OUTCOMES,
    ExecutionRequestInput,
    ExecutionRequestView,
)

__all__ = [
    "REQUEST_ACTION",
    "STANDING_AUTHORIZATIONS_KEY",
    "ExecutionRequestNotFoundError",
    "ExecutionTaskNotFoundError",
    "ExecutionIdentityError",
    "ExecutionRefusedError",
    "ExecutionTransitionError",
    "SubmissionResult",
    "ExecutionRequestService",
]

#: Permission code every request write is audited against.
REQUEST_ACTION = "execution.submit"

#: `system_configurations` key holding §17 standing authorizations:
#: `{"authorizations": [{id, agent_id, tool_id, action_name, scope, max_uses,
#: expires_at, revoked}]}`. Configuration, not a table, because the plan puts
#: standing authorizations in `system_configurations` with explicit scope,
#: limit, expiry and revocation fields - each entry carries all four.
STANDING_AUTHORIZATIONS_KEY = "execution.standing_authorizations"

#: How long an admitted request stays admissible. Nothing sweeps expired
#: requests in this stage (recovery is Stage 8's), so the timestamp is
#: recorded and reported; inventing a sweep here would hide that gap.
REQUEST_EXPIRY_HOURS = 24

#: States `retry` may re-evaluate from: waiting on a person, or interrupted.
RETRYABLE_OUTCOMES = frozenset({"AWAITING_APPROVAL", "REQUIRES_HUMAN_ACTION", "INTERRUPTED"})


class ExecutionRequestNotFoundError(NotFoundError):
    code = "execution_request_not_found"


class ExecutionTaskNotFoundError(NotFoundError):
    code = "execution_task_not_found"


class ExecutionIdentityError(ForbiddenError):
    """The caller is not an agent principal, or not this request's agent."""

    code = "execution_identity_required"


class ExecutionRefusedError(ConflictError):
    """Policy refused, and the body says which check. The request row exists at
    REJECTED; this refusal is the HTTP shape of that row, not its replacement."""

    code = "execution_refused"


class ExecutionTransitionError(ConflictError):
    code = "execution_transition_invalid"


@dataclass
class SubmissionResult:
    request_id: str | None
    status: str
    evaluation: PolicyEvaluation | None
    view: ExecutionRequestView

    def as_dict(self) -> dict[str, Any]:
        body = self.view.model_dump(mode="json")
        if self.evaluation is not None:
            body["evaluation"] = self.evaluation.as_dict()
        return body


class ExecutionRequestService:
    def __init__(self, db: Any, settings: Settings, *, policy: ExecutionPolicy,
                 approvals: Any = None, bus: Any = None) -> None:
        self.db = db
        self.settings = settings
        self.policy = policy
        self.approvals = approvals
        self.bus = bus

    # ------------------------------------------------------------------ #
    # Submission (§4 steps 3-9)
    # ------------------------------------------------------------------ #
    async def submit(self, principal_id: str, payload: ExecutionRequestInput, *,
                     correlation_id: str | None = None) -> SubmissionResult:
        async with self.db.session_factory() as session:
            repo = ExecutionRequestRepo(session)
            agent = await AgentRepo(session).by_principal(principal_id)
            if agent is None:
                await AuditRepo(session).record(
                    "execution.request_refused", "denied", principal_id=principal_id,
                    resource=payload.tool_id, action=REQUEST_ACTION,
                    correlation_id=correlation_id,
                    payload={"reason": "no agent is bound to the authenticated "
                                       "principal", "tool_id": payload.tool_id,
                             "action_name": payload.action_name})
                await session.commit()
                raise ExecutionIdentityError(
                    "no agent is bound to the authenticated principal; execution "
                    "requests are submitted by agents, with the agent's identity "
                    "taken from the principal rather than the payload")
            if payload.idempotency_key:
                existing = await repo.by_idempotency_key(payload.idempotency_key)
                if existing is not None:
                    if existing.agent_id != agent.id:
                        raise ExecutionIdentityError(
                            "this idempotency key belongs to another agent's "
                            "request; keys are not transferable between agents")
                    return SubmissionResult(
                        existing.id, existing.status, PolicyEvaluation(
                            existing.status == "QUEUED", int(existing.risk_level),
                            "the original request for this idempotency key is "
                            "returned rather than the work being admitted twice"),
                        ExecutionRequestView.from_row(existing))
            tool = await ExecutionToolRepo(session).get(payload.tool_id)
            if tool is None:
                raise ToolNotFoundError(f"tool {payload.tool_id} is not registered")
            task = await TaskRepo(session).get(payload.task_id)
            if task is None:
                raise ExecutionTaskNotFoundError(
                    f"task {payload.task_id} does not exist")

            risk = classify_risk(int(tool.risk_level), payload.action_name)
            row = await repo.create(
                task_id=task.id, agent_id=agent.id, tool_id=tool.id,
                adapter_type=tool.adapter_type, action_name=payload.action_name,
                request_payload=dict(payload.action_parameters),
                input_references=list(payload.input_references),
                requested_scope=payload.requested_scope,
                required_capabilities=list(payload.required_capabilities),
                risk_level=risk, status="ACCEPTED", priority=int(payload.priority),
                timeout_seconds=int(payload.timeout_seconds),
                retry_policy=payload.retry_policy.model_dump(),
                expected_output_schema=dict(payload.expected_output_schema),
                idempotency_key=payload.idempotency_key,
                business_id=payload.business_id,
                expires_at=utcnow() + timedelta(hours=REQUEST_EXPIRY_HOURS))
            request_id = row.id
            facts = RequestFacts(
                task_id=task.id, tool_id=tool.id, action_name=payload.action_name,
                action_parameters=dict(payload.action_parameters),
                requested_scope=payload.requested_scope,
                required_capabilities=list(payload.required_capabilities),
                priority=int(payload.priority), request_id=request_id)
            evaluation = await self._evaluate(session, principal_id=principal_id,
                                              agent=agent, task=task, tool=tool,
                                              facts=facts)
            status = await self._apply(session, repo, row, evaluation, facts=facts,
                                       agent=agent, correlation_id=correlation_id)
            agent_principal_id, agent_name = agent.principal_id, agent.name
            await session.commit()

        if status == "AWAITING_APPROVAL":
            await self._open_approval(request_id, facts, risk,
                                      agent_principal_id=agent_principal_id,
                                      agent_name=agent_name,
                                      correlation_id=correlation_id)
        view = await self.get(request_id)
        await self._emit_for(status, correlation_id)
        return SubmissionResult(request_id, status, evaluation, view)

    async def retry(self, request_id: str, principal_id: str, *,
                    correlation_id: str | None = None) -> SubmissionResult:
        """Re-run policy for a request waiting on a person.

        This is how an approved request proceeds: the owner decides in the
        central approval queue, and the agent's retry is what re-asks policy
        with the bound approval in hand. Re-evaluating everything, rather than
        trusting that only the approval state changed, means a capability
        revoked in the meantime is caught here too. If submission left the
        request without an approval (the approval service was unavailable),
        retry is where one gets opened.
        """
        async with self.db.session_factory() as session:
            repo = ExecutionRequestRepo(session)
            row = await repo.get(request_id)
            if row is None:
                raise ExecutionRequestNotFoundError(
                    f"execution request {request_id} does not exist")
            agent = await AgentRepo(session).get(row.agent_id)
            if agent is None or agent.principal_id != principal_id:
                raise ExecutionIdentityError(
                    "only the agent that submitted a request may retry it")
            if row.status not in RETRYABLE_OUTCOMES:
                raise ExecutionTransitionError(
                    f"a request that is '{row.status}' cannot be retried; only "
                    f"{', '.join(sorted(RETRYABLE_OUTCOMES))} may be re-evaluated")
            tool = await ExecutionToolRepo(session).get(row.tool_id)
            task = await TaskRepo(session).get(row.task_id)
            facts = RequestFacts(
                task_id=row.task_id, tool_id=row.tool_id, action_name=row.action_name,
                action_parameters=dict(row.request_payload or {}),
                requested_scope=row.requested_scope,
                required_capabilities=list(row.required_capabilities or []),
                priority=int(row.priority), request_id=row.id)
            approval = None
            if row.approval_reference:
                approval = await ApprovalRepo(session).get(row.approval_reference)
            evaluation = await self._evaluate(
                session, principal_id=principal_id, agent=agent, task=task,
                tool=tool, facts=facts, approval=approval)
            had_reference = bool(row.approval_reference)
            risk = int(row.risk_level)
            status = await self._apply(session, repo, row, evaluation, facts=facts,
                                       agent=agent, correlation_id=correlation_id)
            agent_principal_id, agent_name = agent.principal_id, agent.name
            await session.commit()

        if status == "AWAITING_APPROVAL" and not had_reference:
            await self._open_approval(request_id, facts, risk,
                                      agent_principal_id=agent_principal_id,
                                      agent_name=agent_name,
                                      correlation_id=correlation_id)
        view = await self.get(request_id)
        await self._emit_for(status, correlation_id, retried=True)
        return SubmissionResult(request_id, status, evaluation, view)

    async def _open_approval(self, request_id: str, facts: RequestFacts, risk: int,
                             *, agent_principal_id: str, agent_name: str,
                             correlation_id: str | None) -> None:
        """Open the central approval for a waiting request and bind its id.

        Runs outside any request transaction (the module docstring explains
        why). A failure here leaves the request at AWAITING_APPROVAL without a
        reference - visible in the row, recoverable by retry - rather than
        leaving the submission half-committed.
        """
        if self.approvals is None:
            return
        approval = await self.approvals.create(
            agent_principal_id,
            ApprovalCreateRequest(
                action=APPROVAL_ACTION, resource=request_id,
                risk=APPROVAL_RISK_BY_CLASS[risk],
                reason=(f"Risk {risk} execution requested by agent "
                        f"'{agent_name}': {facts.action_name} on tool "
                        f"{facts.tool_id} at scope "
                        f"'{facts.requested_scope or '(none)'}'"),
                requested_permissions=list(facts.required_capabilities),
                parameters=binding_parameters(facts)),
            correlation_id=correlation_id)
        async with self.db.session_factory() as session:
            repo = ExecutionRequestRepo(session)
            row = await repo.get(request_id)
            if row is not None and row.status == "AWAITING_APPROVAL":
                await repo.update(row, approval_reference=approval.id)
                await AuditRepo(session).record(
                    "execution.approval_opened", "allowed", resource=request_id,
                    principal_id=agent_principal_id, action=REQUEST_ACTION,
                    correlation_id=correlation_id,
                    payload={"approval_reference": approval.id,
                             "risk_level": risk, "action": APPROVAL_ACTION})
                await session.commit()

    async def _evaluate(self, session: Any, *, principal_id: str, agent: Any,
                        task: Any, tool: Any, facts: RequestFacts,
                        approval: Any = None) -> PolicyEvaluation:
        evidence = None
        if task is not None and agent is not None:
            evidence = await self._assignment_evidence(session, task, agent.id)
        standing_row = await ConfigRepo(session).get(STANDING_AUTHORIZATIONS_KEY)
        entries = standing_row.value if standing_row is not None else None
        uses: dict[str, int] = {}
        if isinstance(entries, dict):
            repo = ExecutionRequestRepo(session)
            for entry in entries.get("authorizations") or []:
                if isinstance(entry, dict) and entry.get("id"):
                    uses[str(entry["id"])] = await repo.count_standing_authorization_uses(
                        str(entry["id"]), agent.id if agent else "")
        return await self.policy.evaluate(
            principal_id=principal_id, agent=agent, task=task, tool=tool,
            facts=facts, assignment_evidence=evidence, approval=approval,
            standing_entries=entries, standing_uses=uses, now=utcnow())

    async def _apply(self, session: Any, repo: ExecutionRequestRepo, row: Any,
                     evaluation: PolicyEvaluation, *, facts: RequestFacts,
                     agent: Any, correlation_id: str | None) -> str:
        """Write the evaluation's outcome onto the request row, and audit it."""
        if evaluation.allowed:
            # ACCEPTED passes through VALIDATING: the graph has no direct edge,
            # because a request is validated before it is anything else (§4
            # step 4 precedes steps 5-9). Retried requests are already past it.
            if row.status == "ACCEPTED":
                await self._set_status(session, repo, row, "VALIDATING")
            await self._set_status(session, repo, row, "QUEUED")
            if evaluation.standing_authorization_id:
                await repo.update(
                    row, standing_authorization_id=evaluation.standing_authorization_id)
            await AuditRepo(session).record(
                "execution.request_queued", "allowed", resource=row.id,
                principal_id=agent.principal_id, action=REQUEST_ACTION,
                correlation_id=correlation_id,
                payload={"agent_id": agent.id, "task_id": row.task_id,
                         "tool_id": row.tool_id, "action_name": row.action_name,
                         "risk_level": evaluation.risk,
                         "standing_authorization_id":
                             evaluation.standing_authorization_id,
                         "checks": [c.as_dict() for c in evaluation.checks]})
            return "QUEUED"
        if evaluation.requires_approval:
            if row.status == "ACCEPTED":
                await self._set_status(session, repo, row, "VALIDATING")
            if row.status == "VALIDATING":
                await self._set_status(session, repo, row, "AWAITING_APPROVAL")
            # A request already waiting on a person (AWAITING_APPROVAL,
            # REQUIRES_HUMAN_ACTION, INTERRUPTED) stays where it waits; the
            # graph gives those states no edge to AWAITING_APPROVAL, and does
            # not need one.
            await AuditRepo(session).record(
                "execution.request_awaiting_approval", "allowed", resource=row.id,
                principal_id=agent.principal_id, action=REQUEST_ACTION,
                correlation_id=correlation_id,
                payload={"agent_id": agent.id, "task_id": row.task_id,
                         "tool_id": row.tool_id, "action_name": row.action_name,
                         "risk_level": evaluation.risk,
                         "approval_reference": row.approval_reference,
                         "approvals_available": self.approvals is not None,
                         "checks": [c.as_dict() for c in evaluation.checks]})
            return "AWAITING_APPROVAL"
        await self._set_status(session, repo, row, "REJECTED")
        await repo.update(row, refusal_reason=evaluation.reason,
                          completed_at=utcnow())
        await AuditRepo(session).record(
            "execution.request_refused", "denied", resource=row.id,
            principal_id=agent.principal_id, action=REQUEST_ACTION,
            correlation_id=correlation_id,
            payload={"agent_id": agent.id, "task_id": row.task_id,
                     "tool_id": row.tool_id, "action_name": row.action_name,
                     "risk_level": evaluation.risk, "reason": evaluation.reason,
                     "checks": [c.as_dict() for c in evaluation.checks]})
        return "REJECTED"

    async def _emit_for(self, status: str, correlation_id: str | None, *,
                        retried: bool = False) -> None:
        if self.bus is None:
            return
        event = {"QUEUED": "ExecutionRequested", "AWAITING_APPROVAL": "ExecutionStateChanged",
                 "REJECTED": "ExecutionRefused"}.get(status)
        if event:
            await self.bus.publish_new(event, "execution_requests",
                                       {"status": status, "retried": retried},
                                       correlation_id=correlation_id)

    @staticmethod
    async def _assignment_evidence(session: Any, task: Any, agent_id: str) -> str | None:
        """Why this agent holding this task is a fact, or None (§8.1 check 3).

        Two sources, because the ledger and the task's own pointer are both
        live records: the Stage-6 ledger row while it is in flight, or
        `tasks.assigned_agent_id`. Either must name *this* agent.
        """
        if getattr(task, "assigned_agent_id", None) == agent_id:
            return "the task's assignment pointer names this agent"
        row = await AgentAssignmentRepo(session).for_task(task.id)
        if (row is not None and row.agent_id == agent_id
                and row.status in IN_FLIGHT_ASSIGNMENT_STATUSES):
            return f"assignment {row.id} ({row.status}) names this agent"
        return None

    # ------------------------------------------------------------------ #
    # Lifecycle and reads
    # ------------------------------------------------------------------ #
    async def cancel(self, request_id: str, principal_id: str, *,
                     reason: str = "", correlation_id: str | None = None,
                     ) -> ExecutionRequestView:
        """Withdraw a request that has not finished. A running execution's
        cancellation belongs to the scheduler; here only the admitted states
        can be cancelled, and a terminal request refuses, because rewriting a
        finished outcome would falsify the record."""
        async with self.db.session_factory() as session:
            repo = ExecutionRequestRepo(session)
            row = await repo.get(request_id)
            if row is None:
                raise ExecutionRequestNotFoundError(
                    f"execution request {request_id} does not exist")
            agent = await AgentRepo(session).get(row.agent_id)
            if agent is None or agent.principal_id != principal_id:
                raise ExecutionIdentityError(
                    "only the agent that submitted a request may cancel it")
            # Captured before the update, for the reason the assignment ledger
            # documents: reading it afterwards would record a transition that
            # did not happen.
            previous = row.status
            await self._set_status(session, repo, row, "CANCELLED")
            await repo.update(row, completed_at=utcnow())
            await AuditRepo(session).record(
                "execution.request_cancelled", "allowed", resource=request_id,
                principal_id=principal_id, action=REQUEST_ACTION,
                correlation_id=correlation_id,
                payload={"agent_id": row.agent_id, "from": previous,
                         "to": "CANCELLED", "reason": reason or "cancelled by "
                                 "the requesting agent"})
            await session.commit()
            view = ExecutionRequestView.from_row(row)
        if self.bus is not None:
            await self.bus.publish_new("ExecutionStateChanged", "execution_requests",
                                       {"request_id": request_id, "from": previous,
                                        "to": "CANCELLED"},
                                       correlation_id=correlation_id)
        return view

    async def _set_status(self, session: Any, repo: ExecutionRequestRepo,
                          row: Any, target: str) -> None:
        allowed = OUTCOME_TRANSITIONS.get(row.status, frozenset())
        if target not in allowed:
            raise ExecutionTransitionError(
                f"an execution request that is '{row.status}' cannot become "
                f"'{target}'; "
                + ("it is terminal" if row.status in TERMINAL_OUTCOMES
                   else f"only {', '.join(sorted(allowed))} follow it"))
        await repo.update(row, status=target)

    async def get(self, request_id: str) -> ExecutionRequestView:
        async with self.db.session_factory() as session:
            row = await ExecutionRequestRepo(session).get(request_id)
            if row is None:
                raise ExecutionRequestNotFoundError(
                    f"execution request {request_id} does not exist")
            return ExecutionRequestView.from_row(row)

    async def list_requests(self, *, status: str | None = None,
                            agent_id: str | None = None, tool_id: str | None = None,
                            limit: int = 100, offset: int = 0,
                            ) -> tuple[list[dict[str, Any]], int]:
        async with self.db.session_factory() as session:
            repo = ExecutionRequestRepo(session)
            rows = await repo.list_all(status=status, agent_id=agent_id,
                                       tool_id=tool_id, limit=limit, offset=offset)
            total = await repo.count(status=status, agent_id=agent_id, tool_id=tool_id)
            return ([ExecutionRequestView.from_row(r).model_dump(mode="json")
                     for r in rows], total)

    async def status(self) -> dict[str, Any]:
        """What the request manager holds, with this stage's gap stated."""
        async with self.db.session_factory() as session:
            by_status = await ExecutionRequestRepo(session).count_by_status()
        return {
            "requests_by_status": by_status,
            "outcomes": list(EXECUTION_OUTCOMES),
            "policy_checks": list(POLICY_CHECKS),
            # Stage 2 admits and queues; nothing drains the queue until the
            # adapters (Stages 3-4) and scheduler exist. Reported rather than
            # left to be inferred from a healthy-looking QUEUED count.
            "execution_draining": False,
        }
