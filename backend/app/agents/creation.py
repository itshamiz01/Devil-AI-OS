"""Execution of creation decisions (P-04 Stage 4).

`factory.py` decides; this module acts. The split is not cosmetic. A decision is
a pure function of database state and configuration, which makes it testable
without a single write, while execution mints identities, opens approval gates
and moves money-adjacent state — and every one of those needs its own
transaction, audit record and event.

Three rules shape what is here.

**The request is recorded before it is executed.** A decision that fails halfway
must still be on the ledger; otherwise the system has no record that it was ever
asked, and a later audit cannot distinguish "refused" from "never happened".

**An approval gate is never bypassed, and is never self-served.** Gated
creations open an approval at risk ``high``, which engages the existing
self-approval block in `ApprovalService`: the principal that asked for an agent
cannot be the principal that authorizes it. When the owner grants it, the request
is *re-evaluated* rather than executed on the strength of the earlier decision,
because the registry may have filled while the approval was pending. Approval is
authority to create, not a guarantee that creation is still possible.

**The one crash window is resolved by refusal.** If the process dies between
recording a gated request and creating its approval, the ledger holds a request
awaiting approval with no approval id. `sweep_expired` closes such a request; it
never creates the agent, because an ungated creation is exactly what the gate
exists to prevent.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from ..core.config import Settings
from ..core.exceptions import ConflictError
from ..database.connection import Database
from ..database.models import AgentConfigurationHistory
from ..database.repositories import (
    AgentCreationRequestRepo,
    AgentRepo,
    AgentTemplateRepo,
    AuditRepo,
    PrincipalRepo,
)
from ..permissions.models import ApprovalCreateRequest
from .factory import CREATION_APPROVAL_ACTION, AgentFactory, Check, Evaluation
from .lifecycle import AgentStatus, transition
from .schemas import CreationDecision, CreationRequestInput

__all__ = ["CreationEngine", "register_factory_approval_subscribers"]


class CreationEngine:
    """Records decisions and carries out the ones that have an execution path."""

    def __init__(self, db: Database, factory: AgentFactory, settings: Settings,
                 approvals: Any = None, bus: Any = None, permissions: Any = None) -> None:
        self.db = db
        self.factory = factory
        self.settings = settings
        self.approvals = approvals
        self.bus = bus
        self.permissions = permissions

    # ------------------------------------------------------------------ #
    # Entry points
    # ------------------------------------------------------------------ #
    async def create(self, request: CreationRequestInput, *, actor_id: str | None = None,
                     correlation_id: str | None = None) -> Evaluation:
        """Evaluate, record the decision, and carry it out."""
        if request.idempotency_key:
            existing = await self._by_idempotency_key(request.idempotency_key)
            if existing is not None:
                return self._replay(existing)

        evaluation = await self.factory.evaluate(request)
        await self._resolve_gate(evaluation, actor_id)
        evaluation.request_id = await self._record_request(request, evaluation)
        evaluation.recorded = True

        if evaluation.decision is CreationDecision.CREATE_AGENT:
            await self._execute_create(request, evaluation, actor_id, correlation_id)
        elif evaluation.decision is CreationDecision.REQUEST_OWNER_APPROVAL:
            await self._execute_approval(request, evaluation, actor_id, correlation_id)
        elif evaluation.decision is CreationDecision.REUSE_EXISTING:
            await self._finish(evaluation.request_id, evaluation.decision,
                               evaluation.reason, completed=True)
        else:  # QUEUE stays open; REJECT is terminal
            await self._finish(evaluation.request_id, evaluation.decision,
                               evaluation.reason,
                               completed=evaluation.decision is CreationDecision.REJECT)

        await self._emit_for(evaluation, correlation_id)
        return evaluation

    async def drain_queue(self, *, actor_id: str | None = None, limit: int = 50,
                          correlation_id: str | None = None) -> dict[str, Any]:
        """Re-evaluate queued requests, oldest first.

        Owner-invoked, never scheduled: autonomous scheduling is P-12, so nothing
        here runs on a timer. Requests are re-evaluated from scratch because the
        facts that produced QUEUE may have changed in either direction.
        """
        swept = await self.sweep_expired(correlation_id=correlation_id)
        outcomes: list[dict[str, Any]] = []
        async with self.db.session_factory() as session:
            queued = await AgentCreationRequestRepo(session).queued(limit)
            pending = [(r.id, r.requested_role, r.justification,
                        list(r.requested_capabilities or []), r.requested_template_id,
                        r.business_id, dict(r.resource_estimate or {})) for r in queued]
        for (rid, role, justification, capabilities, template_id, business_id,
             estimate) in pending:
            request = self._input_from_row(role, justification, capabilities, template_id,
                                           business_id, estimate)
            evaluation = await self.factory.evaluate(request)
            evaluation.request_id = rid
            evaluation.recorded = True
            if evaluation.decision is CreationDecision.CREATE_AGENT:
                await self._execute_create(request, evaluation, actor_id, correlation_id,
                                           request_id=rid)
            else:
                await self._finish(rid, evaluation.decision, evaluation.reason,
                                   completed=evaluation.decision
                                   is not CreationDecision.QUEUE)
            await self._emit_for(evaluation, correlation_id)
            outcomes.append(evaluation.as_dict())
        return {"swept": swept, "considered": len(pending), "outcomes": outcomes}

    async def on_approval_granted(self, event: Any) -> None:
        await self._apply_approval_decision(event.payload.get("approval_id"),
                                            event.correlation_id, granted=True)

    async def on_approval_rejected(self, event: Any) -> None:
        await self._apply_approval_decision(event.payload.get("approval_id"),
                                            event.correlation_id, granted=False)

    async def sweep_expired(self, correlation_id: str | None = None) -> dict[str, int]:
        """Close requests whose approval can no longer authorize anything."""
        expired = 0
        orphaned = 0
        async with self.db.session_factory() as session:
            pending = await AgentCreationRequestRepo(session).list(
                200, 0, approval_status="pending")
            targets = [(r.id, r.approval_id) for r in pending]
        for rid, approval_id in targets:
            if approval_id is None:
                await self._finish(rid, CreationDecision.REJECT,
                                   "the approval record was never created, so the request "
                                   "cannot be authorized; it was closed rather than "
                                   "executed", approval_status="expired", completed=True)
                orphaned += 1
                continue
            approval = await self.approvals.get(approval_id) if self.approvals else None
            if approval is not None and approval.status in ("expired", "rejected"):
                await self._finish(rid, CreationDecision.REQUEST_OWNER_APPROVAL,
                                   f"the approval {approval.status} before a decision was "
                                   "recorded", approval_status=approval.status,
                                   completed=True)
                expired += 1
        if expired or orphaned:
            await self._emit("AgentCreationRejected", {
                "swept_expired": expired, "swept_orphaned": orphaned}, correlation_id)
        return {"expired": expired, "orphaned": orphaned}

    # ------------------------------------------------------------------ #
    # Approval completion
    # ------------------------------------------------------------------ #
    async def _apply_approval_decision(self, approval_id: str | None,
                                       correlation_id: str | None, *, granted: bool) -> None:
        if not approval_id:
            return
        async with self.db.session_factory() as session:
            row = await AgentCreationRequestRepo(session).by_approval(approval_id)
            if row is None or row.approval_status != "pending":
                return
            snapshot = (row.id, row.requested_role, row.justification,
                        list(row.requested_capabilities or []), row.requested_template_id,
                        row.business_id, dict(row.resource_estimate or {}))
        rid, role, justification, capabilities, template_id, business_id, estimate = snapshot
        if not granted:
            await self._finish(rid, CreationDecision.REQUEST_OWNER_APPROVAL,
                               "the owner rejected the creation request",
                               approval_status="rejected", completed=True)
            await self._emit("AgentCreationRejected", {
                "request_id": rid, "approval_id": approval_id,
                "decision": CreationDecision.REQUEST_OWNER_APPROVAL.value,
                "reason": "the owner rejected the creation request"}, correlation_id)
            return

        request = self._input_from_row(role, justification, capabilities, template_id,
                                       business_id, estimate)
        evaluation = await self.factory.evaluate(request)
        evaluation.request_id = rid
        evaluation.recorded = True
        evaluation.approval_id = approval_id
        if evaluation.decision in (CreationDecision.CREATE_AGENT,
                                   CreationDecision.REQUEST_OWNER_APPROVAL):
            # A re-evaluation that asks for owner approval again is asking for the
            # approval that has just been granted. Treating that as "still gated"
            # would leave the request open forever with a granted approval attached
            # to it, so the gate counts as satisfied here and only here. Every
            # other decision - QUEUE, REJECT, REUSE_EXISTING - still stands, which
            # is what keeps a grant from overriding a ceiling reached meanwhile.
            if evaluation.decision is CreationDecision.REQUEST_OWNER_APPROVAL:
                evaluation.checks.append(Check(
                    "approval_gate_satisfied", True,
                    f"approval {approval_id} was granted by the owner, which is the "
                    "authorization this gate asks for"))
                evaluation.decision = CreationDecision.CREATE_AGENT
            await self._execute_create(request, evaluation, None, correlation_id,
                                       request_id=rid, approval_id=approval_id)
        elif evaluation.decision is CreationDecision.REUSE_EXISTING:
            await self._finish(rid, evaluation.decision, evaluation.reason,
                               approval_status="granted", completed=True)
        else:
            await self._finish(rid, evaluation.decision,
                               f"approval was granted but re-evaluation decided "
                               f"{evaluation.decision.value}: {evaluation.reason}",
                               approval_status="granted",
                               completed=evaluation.decision is CreationDecision.REJECT)
        await self._emit_for(evaluation, correlation_id, approval_id=approval_id)

    # ------------------------------------------------------------------ #
    # Execution paths
    # ------------------------------------------------------------------ #
    async def _execute_create(self, request: CreationRequestInput, evaluation: Evaluation,
                              actor_id: str | None, correlation_id: str | None,
                              *, request_id: str | None = None,
                              approval_id: str | None = None) -> None:
        """Mint the identity: one principal, one agent, one configuration snapshot.

        ``agents.principal_id`` is unique, so an agent *is* a principal and both
        rows are written in one transaction. The lifecycle is walked rather than
        assigned — PROPOSED -> INITIALIZING -> ACTIVE through the same
        ``transition`` the rest of the system uses — so an agent cannot appear in
        a state the graph does not permit.

        No health check is claimed here. Bringing the agent to ACTIVE means its
        identity, registry row and configuration snapshot exist; nothing has yet
        observed it doing work, which is what Stage 8's health states are for.
        """
        rid = request_id or evaluation.request_id
        configuration = await self._stored_configuration(evaluation.template_id,
                                                         evaluation.template_version)
        name = request.agent_name or self.factory.generated_name(request.requested_role)
        async with self.db.session_factory() as session:
            agents = AgentRepo(session)
            principal_id = None
            agent = None
            last_error: Exception | None = None
            for attempt in range(3):
                candidate = name if attempt == 0 else f"{name}-{uuid4().hex[:6]}"
                try:
                    principal = await PrincipalRepo(session).create("agent", candidate)
                    agent = await agents.create(
                        principal_id=principal.id, name=candidate,
                        role=request.requested_role, status=AgentStatus.PROPOSED.value,
                        metadata_json={
                            "template_id": evaluation.template_id,
                            "template_version": evaluation.template_version,
                            "template_name": configuration.get("_template_name"),
                            "created_from_request": rid,
                            "configuration_fingerprint": configuration.get("_fingerprint"),
                            "essential_claim": request.essential,
                        },
                        template_id=evaluation.template_id,
                        template_version=evaluation.template_version,
                        configuration_version=1,
                        parent_agent_id=request.parent_agent_id,
                        business_id=request.business_id)
                    principal_id = principal.id
                    break
                except IntegrityError as exc:
                    await session.rollback()
                    last_error = exc
            if agent is None or principal_id is None:
                raise ConflictError(
                    "an agent or principal with that name already exists",
                    {"name": name, "error": str(last_error)})

            walked = []
            for target in (AgentStatus.INITIALIZING, AgentStatus.ACTIVE):
                transition(agent.status, target.value)
                await agents.set_status(agent.id, target.value)
                agent.status = target.value
                walked.append(target.value)

            session.add(AgentConfigurationHistory(
                agent_id=agent.id, configuration_version=1,
                configuration_snapshot={k: v for k, v in configuration.items()
                                        if not k.startswith("_")},
                change_reason=(f"created from template {evaluation.template_id} version "
                               f"{evaluation.template_version}"),
                changed_by=actor_id, approval_id=approval_id))
            await session.flush()

            await AgentCreationRequestRepo(session).set_decision(
                rid, decision=CreationDecision.CREATE_AGENT.value,
                reason=evaluation.reason,
                approval_status=("granted" if approval_id else "not_required"),
                approval_id=approval_id, completed=True)
            await AuditRepo(session).record(
                "agent.created", "allowed", principal_id=actor_id, resource=agent.id,
                action=CREATION_APPROVAL_ACTION, correlation_id=correlation_id,
                payload={"template_id": evaluation.template_id,
                         "template_version": evaluation.template_version,
                         "request_id": rid, "approval_id": approval_id,
                         "principal_id": principal_id, "status": agent.status,
                         "lifecycle_walked": walked})
            await session.commit()
        evaluation.agent_id = agent.id
        evaluation.approval_id = approval_id

    async def _resolve_gate(self, evaluation: Evaluation, actor_id: str | None) -> None:
        """Do not open an approval that nobody could answer.

        A gated creation records its requester on the approval, and risk ``high``
        means the requester cannot decide it. When the requester *is* the owner —
        the only principal that holds ``approvals.decide`` — the approval would be
        unanswerable by anyone, which is a deadlock, not a control. The owner
        asking for an agent is the owner deciding about it, so the request is its
        own authorization and no approval is opened.

        When any other principal asks, the gate stands exactly as designed and the
        self-approval block bites. The test is a permission question answered by
        the authoritative engine, read-only, so this cannot disagree with what the
        approval endpoints enforce.
        """
        if evaluation.decision is not CreationDecision.REQUEST_OWNER_APPROVAL:
            return
        if not actor_id or self.permissions is None:
            return
        if not await self.permissions.is_granted(actor_id, "approvals.decide"):
            return
        detail = ("the requesting principal holds approvals.decide, so its request is "
                  "its own authorization; opening an approval only that principal could "
                  "decide would be unanswerable rather than safe")
        evaluation.checks.append(Check("requester_holds_deciding_authority", True, detail))
        evaluation.decision = CreationDecision.CREATE_AGENT
        evaluation.reason = (f"{evaluation.reason} - resolved without an approval because "
                             f"{detail}")

    async def _execute_approval(self, request: CreationRequestInput,
                                evaluation: Evaluation, actor_id: str | None,
                                correlation_id: str | None) -> None:
        """Open the approval gate, or refuse if there is nothing to open it with."""
        if self.approvals is None:
            evaluation.decision = CreationDecision.REJECT
            evaluation.reason = ("owner approval is required but no approval service is "
                                 "available; the request was refused rather than created "
                                 "ungated")
            await self._finish(evaluation.request_id, CreationDecision.REJECT,
                               evaluation.reason, completed=True)
            return
        approval = await self.approvals.create(
            actor_id or "system",
            ApprovalCreateRequest(
                action=CREATION_APPROVAL_ACTION,
                resource=evaluation.request_id or "",
                risk="high",
                reason=request.justification[:2000],
                requested_permissions=[],
                parameters={"requested_role": request.requested_role,
                            "template_id": evaluation.template_id,
                            "template_version": evaluation.template_version,
                            "requested_capabilities": list(request.requested_capabilities),
                            "essential": request.essential}),
            correlation_id)
        await self._finish(evaluation.request_id, CreationDecision.REQUEST_OWNER_APPROVAL,
                           evaluation.reason, approval_status="pending",
                           approval_id=approval.id)
        evaluation.approval_id = approval.id

    async def _record_request(self, request: CreationRequestInput,
                              evaluation: Evaluation) -> str:
        async with self.db.session_factory() as session:
            repo = AgentCreationRequestRepo(session)
            row = await repo.create(
                requested_role=request.requested_role, justification=request.justification,
                requested_capabilities=list(request.requested_capabilities),
                resource_estimate={"essential": request.essential,
                                   "allow_reuse": request.allow_reuse,
                                   **dict(request.resource_estimate)},
                # The resolved template only. ``requested_template_id`` is a
                # foreign key, so writing back a caller-supplied id that resolved
                # to nothing would fail the constraint and turn a recorded
                # refusal into a 500 — and even without the constraint it would
                # put a template that does not exist on the ledger. What the
                # caller asked for is preserved in the reason text and in the
                # audit record below, which have no such constraint.
                requested_template_id=evaluation.template_id,
                business_id=request.business_id,
                idempotency_key=request.idempotency_key)
            await repo.set_decision(row.id, decision=evaluation.decision.value,
                                    reason=evaluation.reason)
            await AuditRepo(session).record(
                "agent.creation_decided", "allowed", resource=row.id,
                action=CREATION_APPROVAL_ACTION,
                payload={"decision": evaluation.decision.value,
                         "reason": evaluation.reason,
                         "template_id": evaluation.template_id,
                         "requested_template_id": request.template_id,
                         "essential": request.essential})
            await session.commit()
            return row.id

    async def _finish(self, request_id: str | None, decision: CreationDecision,
                      reason: str, *, approval_status: str | None = None,
                      approval_id: str | None = None, completed: bool = False) -> None:
        if not request_id:
            return
        async with self.db.session_factory() as session:
            await AgentCreationRequestRepo(session).set_decision(
                request_id, decision=decision.value, reason=reason,
                approval_status=approval_status, approval_id=approval_id,
                completed=completed)
            await session.commit()

    async def _stored_configuration(self, template_id: str | None,
                                    version: int | None) -> dict[str, Any]:
        if not template_id or version is None:
            return {}
        async with self.db.session_factory() as session:
            repo = AgentTemplateRepo(session)
            template = await repo.get(template_id)
            row = await repo.get_version(template_id, version)
        configuration = dict(row.configuration_json or {}) if row else {}
        configuration["_template_name"] = template.name if template else None
        configuration["_fingerprint"] = ((row.validation_details_json or {})
                                         .get("configuration_fingerprint") if row else None)
        return configuration

    async def _by_idempotency_key(self, key: str) -> Any:
        async with self.db.session_factory() as session:
            return await AgentCreationRequestRepo(session).by_idempotency_key(key)

    def _replay(self, row: Any) -> Evaluation:
        """Answer a repeated key from the ledger instead of deciding twice."""
        evaluation = Evaluation(
            CreationDecision(row.decision) if row.decision else CreationDecision.REJECT,
            row.decision_reason or "")
        evaluation.request_id = row.id
        evaluation.template_id = row.requested_template_id
        evaluation.approval_id = row.approval_id
        evaluation.replayed = True
        evaluation.recorded = True
        evaluation.checks = [Check(
            "idempotency_key", True,
            f"request {row.id} was already decided {row.decision}; the recorded outcome is "
            "replayed and nothing new was created")]
        return evaluation

    def _input_from_row(self, role: str, justification: str, capabilities: list[str],
                        template_id: str | None, business_id: str | None,
                        estimate: dict[str, Any]) -> CreationRequestInput:
        """Rebuild the original request from its stored row.

        ``essential`` and ``allow_reuse`` are restored rather than left to their
        defaults: a drained request that silently became reusable would answer
        REUSE_EXISTING instead of creating what was asked for, and one that lost
        an essentiality claim would queue again under pressure. Re-evaluating a
        *different* request is not re-evaluating the request.
        """
        stored = dict(estimate or {})
        payload = {k: v for k, v in stored.items() if k not in ("essential", "allow_reuse")}
        return CreationRequestInput(
            requested_role=role, justification=justification,
            requested_capabilities=capabilities, template_id=template_id,
            business_id=business_id, resource_estimate=payload,
            essential=bool(stored.get("essential", False)),
            allow_reuse=bool(stored.get("allow_reuse", True)))

    # ------------------------------------------------------------------ #
    # Events
    # ------------------------------------------------------------------ #
    async def _emit_for(self, evaluation: Evaluation, correlation_id: str | None,
                        approval_id: str | None = None) -> None:
        payload = {
            "request_id": evaluation.request_id,
            "decision": evaluation.decision.value,
            "reason": evaluation.reason,
            "template_id": evaluation.template_id,
            "template_version": evaluation.template_version,
            "agent_id": evaluation.agent_id,
            "approval_id": approval_id or evaluation.approval_id,
        }
        await self._emit("AgentCreationRequested", payload, correlation_id)
        # REUSE_EXISTING deliberately has no second event: reusing an agent
        # creates nothing, and emitting a creation event for it would inflate
        # every downstream count of agents that were made.
        event = {
            CreationDecision.CREATE_AGENT: "AgentCreated",
            CreationDecision.QUEUE: "AgentCreationQueued",
            CreationDecision.REQUEST_OWNER_APPROVAL: "AgentCreationApprovalRequested",
            CreationDecision.REJECT: "AgentCreationRejected",
        }.get(evaluation.decision)
        if event:
            await self._emit(event, payload, correlation_id)

    async def _emit(self, event_type: str, payload: dict[str, Any],
                    correlation_id: str | None) -> None:
        if self.bus is None:
            return
        await self.bus.publish_new(event_type, "agent_factory", payload,
                                   correlation_id=correlation_id)


def register_factory_approval_subscribers(bus: Any, engine: CreationEngine) -> None:
    """Route approval outcomes back into pending creation requests.

    Kept out of `register_default_subscribers` for the same reason as the task
    equivalent: it needs a service that does not exist when the bus is first
    attached, and wiring it early would mean holding a half-built engine.
    """
    bus.subscribe("ApprovalGranted", engine.on_approval_granted)
    bus.subscribe("ApprovalRejected", engine.on_approval_rejected)
