"""Master orchestrator (P-02 §11).

Coordinates missions, plans and tasks. It creates no agents (that is P-04) and
executes nothing itself: every unit of work goes through the P-01
`TaskManager.submit`, which is the only path into execution.

Two invariants:

* **Never bypass the task manager** (§11.3). There is no code path here that
  starts a thread, a subprocess or a background coroutine to do plan work.
* **Progress is measured, not narrated** (§11.4). Percentages come from persisted
  task states read back from the database. A model is never asked how far along a
  mission is, and could not answer truthfully if it were.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from ..database.connection import Database
from ..database.models import Task
from ..database.repositories import AuditRepo
from ..tasks.manager import TaskManager
from ..tasks.models import TaskSubmitRequest
from .autonomy import AutonomyController
from .capabilities import CapabilityRegistry, UnknownCapabilityError
from .planning import DependencyResolver, Planner, Replanner
from .schemas import (
    RISK_RANK,
    Capability,
    Mission,
    MissionProgress,
    MissionState,
    Plan,
    PlanStatus,
    PlanStep,
    RiskLevel,
    StepStatus,
    validate_mission_transition,
)

#: Task status strings as persisted by P-01.
TASK_TERMINAL = frozenset({"COMPLETED", "FAILED", "CANCELLED"})
TASK_ACTIVE = frozenset({"RUNNING"})
TASK_PENDING = frozenset({"CREATED", "VALIDATING", "QUEUED", "RETRY_PENDING"})
TASK_BLOCKED_STATES = frozenset({"PAUSED", "WAITING_FOR_APPROVAL"})

AUDIT_DISPATCH = "intelligence.task_dispatched"
AUDIT_BLOCKED = "intelligence.dispatch_blocked"
AUDIT_FAILURE = "intelligence.task_failure"
AUDIT_PROGRESS = "intelligence.progress_updated"


class DispatchRefusedError(RuntimeError):
    """Raised when the orchestrator may not submit work."""

    def __init__(self, reason: str, *, step_id: str | None = None) -> None:
        self.reason = reason
        self.step_id = step_id
        super().__init__(reason)


@dataclass
class DispatchPolicy:
    """Limits the orchestrator imposes on itself (§16, §18)."""

    #: Maximum tasks in flight for one mission. Bounded so a large plan cannot
    #: saturate the P-01 queue and starve owner-initiated work.
    max_concurrent_per_mission: int = 2
    default_priority: int = 5
    default_timeout_seconds: float = 30.0
    #: Risk at or above which a step must carry an approval gate.
    approval_required_at: RiskLevel = RiskLevel.HIGH
    #: In-process capabilities are resolved by code and never queued.
    dispatch_in_process_capabilities: bool = True


@dataclass
class DispatchRecord:
    """What was submitted, so dispatch is auditable (§11.3)."""

    mission_id: str
    plan_id: str
    step_id: str
    capability_id: str
    task_id: str | None
    handler: str | None
    idempotency_key: str
    correlation_id: str | None
    in_process: bool
    refused_reason: str | None = None
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FailureAssessment:
    """§11.5 — what a task failure means for the mission."""

    step_id: str
    task_id: str
    task_status: str
    error_details: dict[str, Any]
    recoverable: bool
    retry_permitted: bool
    affected_dependents: list[str]
    replan_recommended: bool
    reason: str


class TaskDispatcher:
    """Turns plan steps into P-01 task submissions."""

    def __init__(
        self,
        tasks: TaskManager,
        capabilities: CapabilityRegistry,
        *,
        autonomy: AutonomyController,
        policy: DispatchPolicy | None = None,
    ) -> None:
        self.tasks = tasks
        self.capabilities = capabilities
        self.autonomy = autonomy
        self.policy = policy or DispatchPolicy()
        self.records: list[DispatchRecord] = []

    def build_request(
        self,
        step: PlanStep,
        capability: Capability,
        *,
        mission: Mission,
        plan: Plan,
        correlation_id: str | None = None,
    ) -> tuple[TaskSubmitRequest, str, str | None]:
        """Construct the submission, carrying full provenance (§11.3).

        `TaskSubmitRequest` has a fixed shape, so mission/plan/step identity
        travels in `description` and in the idempotency key rather than in extra
        fields the Core OS would ignore. The idempotency key is the important
        part: `plan:step` makes a re-dispatch after restart collide with the
        original task instead of running the work twice (§9.3).
        """
        if capability.task_handler is None:
            raise DispatchRefusedError(
                f"capability {capability.capability_id!r} is in-process and cannot be dispatched as a task",
                step_id=step.step_id,
            )
        idempotency_key = f"{plan.plan_id}:{step.step_id}"[:128]
        provenance = (
            f"mission={mission.mission_id} plan={plan.plan_id} v{plan.version} "
            f"step={step.step_id} capability={capability.capability_id} "
            f"expected={step.expected_output or 'unspecified'}"
        )
        request = TaskSubmitRequest(
            name=step.title[:200],
            description=provenance[:2000],
            handler=capability.task_handler,
            payload=self._payload_for(capability, step, mission=mission),
            priority=self.policy.default_priority,
            timeout_seconds=self.policy.default_timeout_seconds,
            idempotency_key=idempotency_key,
            approval_required=(
                plan.approval_required
                or RISK_RANK[capability.risk] >= RISK_RANK[self.policy.approval_required_at]
            ),
        )
        return request, idempotency_key, correlation_id

    def _payload_for(self, capability: Capability, step: PlanStep, *, mission: Mission) -> dict[str, Any]:
        """Build a payload the handler's own schema will accept.

        Payloads are validated by P-01 against the handler schema, so sending an
        arbitrary structure would be rejected before queueing. Each handler gets
        exactly what it declares.
        """
        handler = capability.task_handler
        if handler == "system.echo":
            # The echoed message carries the step intent, never a secret: §11
            # forbids sensitive values in ordinary task data.
            return {"message": f"{step.title} | mission={mission.mission_id} | step={step.step_id}"}
        if handler == "system.wait":
            bounded = min(5.0, max(0.1, (step.estimated_duration_seconds or 1.0)))
            return {"seconds": bounded}
        return {}

    async def dispatch(
        self,
        step: PlanStep,
        *,
        mission: Mission,
        plan: Plan,
        principal_id: str,
        correlation_id: str | None = None,
        db: Database | None = None,
    ) -> DispatchRecord:
        """Submit one step, or refuse and record why.

        Refusals are audited rather than raised silently: a plan that cannot be
        dispatched must leave a trace explaining why (§11.5).
        """
        capability_id = step.capability_id
        if capability_id is None:
            return await self._refuse(step, mission, plan, "step names no capability", db=db, principal_id=principal_id)

        try:
            capability = self.capabilities.get(capability_id)
        except UnknownCapabilityError:
            return await self._refuse(
                step, mission, plan, f"capability {capability_id!r} is not registered",
                db=db, principal_id=principal_id,
            )

        if not capability.available:
            return await self._refuse(
                step, mission, plan, f"capability {capability_id!r} is not available",
                db=db, principal_id=principal_id,
            )

        # §15: at advisory level the engine may plan but must not execute.
        if not self.autonomy.may_submit_tasks():
            return await self._refuse(
                step, mission, plan,
                f"autonomy level {self.autonomy.level.value} is advisory and may not submit execution tasks",
                db=db, principal_id=principal_id,
            )

        # In-process capabilities are resolved by deterministic code, not queued.
        if capability.task_handler is None:
            record = DispatchRecord(
                mission_id=mission.mission_id, plan_id=plan.plan_id, step_id=step.step_id,
                capability_id=capability_id, task_id=None, handler=None,
                idempotency_key=f"{plan.plan_id}:{step.step_id}"[:128],
                correlation_id=correlation_id, in_process=True,
            )
            self.records.append(record)
            return record

        request, idempotency_key, corr = self.build_request(
            step, capability, mission=mission, plan=plan, correlation_id=correlation_id
        )

        task = await self.tasks.submit(principal_id, request, correlation_id=corr)
        record = DispatchRecord(
            mission_id=mission.mission_id, plan_id=plan.plan_id, step_id=step.step_id,
            capability_id=capability_id, task_id=task.id, handler=capability.task_handler,
            idempotency_key=idempotency_key, correlation_id=corr, in_process=False,
        )
        self.records.append(record)

        if db is not None:
            async with db.session_factory() as session:
                await AuditRepo(session).record(
                    AUDIT_DISPATCH, "allowed", principal_id=principal_id,
                    resource=mission.mission_id, action="dispatch",
                    correlation_id=corr,
                    payload={
                        "plan_id": plan.plan_id, "step_id": step.step_id,
                        "task_id": task.id, "capability": capability_id,
                        "handler": capability.task_handler,
                        "idempotency_key": idempotency_key,
                    },
                )
                await session.commit()
        return record

    async def _refuse(
        self, step: PlanStep, mission: Mission, plan: Plan, reason: str,
        *, db: Database | None, principal_id: str,
    ) -> DispatchRecord:
        record = DispatchRecord(
            mission_id=mission.mission_id, plan_id=plan.plan_id, step_id=step.step_id,
            capability_id=step.capability_id or "", task_id=None, handler=None,
            idempotency_key=f"{plan.plan_id}:{step.step_id}"[:128],
            correlation_id=None, in_process=False, refused_reason=reason,
        )
        self.records.append(record)
        if db is not None:
            async with db.session_factory() as session:
                await AuditRepo(session).record(
                    AUDIT_BLOCKED, "denied", principal_id=principal_id,
                    resource=mission.mission_id, action="dispatch",
                    payload={"plan_id": plan.plan_id, "step_id": step.step_id, "reason": reason},
                )
                await session.commit()
        return record

    def in_flight_for_mission(self, mission_id: str) -> int:
        return sum(
            1 for r in self.records
            if r.mission_id == mission_id and r.task_id is not None and r.refused_reason is None
        )


class ProgressMonitor:
    """Derives mission progress from persisted task states (§11.4)."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.resolver = DependencyResolver()

    async def task_states(self, task_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Read real task rows. Returns only tasks that exist."""
        if not task_ids:
            return {}
        async with self.db.session_factory() as session:
            rows = (
                await session.execute(select(Task).where(Task.id.in_(task_ids)))
            ).scalars().all()
        return {
            row.id: {
                "status": row.status,
                "error_details": row.error_details or {},
                "result": row.result or {},
                "retry_count": row.retry_count,
                "essential": row.essential,
            }
            for row in rows
        }

    def apply_task_states(self, plan: Plan, states: dict[str, dict[str, Any]]) -> Plan:
        """Project task states onto plan steps.

        A step whose task row is missing is marked BLOCKED, not COMPLETED: an
        absent task is not a finished one, and §11.5 forbids silently treating a
        failed or missing mission as complete.
        """
        updated: list[PlanStep] = []
        for step in plan.steps:
            if step.status in {StepStatus.COMPLETED, StepStatus.CANCELLED, StepStatus.SKIPPED}:
                updated.append(step)
                continue
            if step.task_id is None:
                updated.append(step)
                continue
            state = states.get(step.task_id)
            if state is None:
                updated.append(step.model_copy(update={"status": StepStatus.BLOCKED}))
                continue
            updated.append(step.model_copy(update={"status": _map_task_status(state["status"])}))

        new_plan = plan.model_copy(update={"steps": updated})
        # Dependencies gate readiness: a step whose ancestor failed is blocked.
        blocked = set(self.resolver.blocked_by_failure(updated))
        final: list[PlanStep] = []
        for step in new_plan.steps:
            if step.step_id in blocked and step.status not in {StepStatus.COMPLETED, StepStatus.CANCELLED}:
                final.append(step.model_copy(update={"status": StepStatus.BLOCKED}))
            else:
                final.append(step)
        return new_plan.model_copy(update={"steps": final})

    def progress(self, mission: Mission, plan: Plan | None) -> MissionProgress:
        """Compute percentages from step states alone."""
        if plan is None:
            return MissionProgress(
                mission_id=mission.mission_id, state=mission.state, incomplete_data=True
            )
        steps = plan.steps
        total = len(steps)
        completed = sum(1 for s in steps if s.status == StepStatus.COMPLETED)
        failed = sum(1 for s in steps if s.status == StepStatus.FAILED)
        blocked = sum(1 for s in steps if s.status == StepStatus.BLOCKED)
        active = sum(1 for s in steps if s.status in {StepStatus.RUNNING, StepStatus.DISPATCHED})
        pending = sum(1 for s in steps if s.status in {StepStatus.PENDING, StepStatus.READY})
        awaiting = sum(1 for s in steps if s.status == StepStatus.AWAITING_APPROVAL)
        percent = round(100.0 * completed / total, 2) if total else 0.0
        return MissionProgress(
            mission_id=mission.mission_id,
            state=mission.state,
            total_steps=total,
            completed=completed,
            active=active,
            pending=pending,
            failed=failed,
            blocked=blocked,
            awaiting_approval=awaiting,
            percent_complete=percent,
            incomplete_data=total == 0,
        )


def _map_task_status(status: str) -> StepStatus:
    """Map a P-01 task status onto a plan step status."""
    mapping = {
        "COMPLETED": StepStatus.COMPLETED,
        "FAILED": StepStatus.FAILED,
        "CANCELLED": StepStatus.CANCELLED,
        "RUNNING": StepStatus.RUNNING,
        "QUEUED": StepStatus.DISPATCHED,
        "RETRY_PENDING": StepStatus.PENDING,
        "CREATED": StepStatus.PENDING,
        "VALIDATING": StepStatus.PENDING,
        "PAUSED": StepStatus.BLOCKED,
        "WAITING_FOR_APPROVAL": StepStatus.AWAITING_APPROVAL,
    }
    return mapping.get(status, StepStatus.BLOCKED)


class Orchestrator:
    """Coordinates a mission from validated plan to terminal state (§11.1)."""

    def __init__(
        self,
        db: Database,
        tasks: TaskManager,
        capabilities: CapabilityRegistry,
        *,
        autonomy: AutonomyController,
        planner: Planner | None = None,
        policy: DispatchPolicy | None = None,
    ) -> None:
        self.db = db
        self.tasks = tasks
        self.capabilities = capabilities
        self.autonomy = autonomy
        self.planner = planner or Planner(capabilities)
        self.replanner = Replanner(self.planner)
        self.policy = policy or DispatchPolicy()
        self.dispatcher = TaskDispatcher(tasks, capabilities, autonomy=autonomy, policy=self.policy)
        self.monitor = ProgressMonitor(db)
        self.resolver = DependencyResolver()

    async def execute_plan(
        self,
        mission: Mission,
        plan: Plan,
        *,
        principal_id: str,
        correlation_id: str | None = None,
    ) -> tuple[Plan, list[DispatchRecord]]:
        """Dispatch every step that is currently ready, respecting concurrency.

        Only steps whose dependencies have completed are dispatched (§9.3), and
        the per-mission concurrency cap is enforced here rather than left to the
        queue, so one mission cannot monopolise execution (§18).
        """
        if plan.status not in {PlanStatus.VALIDATED, PlanStatus.ACTIVE}:
            raise DispatchRefusedError(
                f"plan {plan.plan_id} is {plan.status.value}; only a VALIDATED or ACTIVE plan may be dispatched"
            )

        records: list[DispatchRecord] = []
        in_flight = self.dispatcher.in_flight_for_mission(mission.mission_id)

        for step in self.resolver.ready_steps(plan.steps):
            if in_flight >= self.policy.max_concurrent_per_mission:
                break
            if step.status in {StepStatus.COMPLETED, StepStatus.CANCELLED, StepStatus.SKIPPED}:
                continue
            record = await self.dispatcher.dispatch(
                step, mission=mission, plan=plan, principal_id=principal_id,
                correlation_id=correlation_id, db=self.db,
            )
            records.append(record)
            if record.task_id is not None:
                in_flight += 1

        updated = plan.model_copy(update={"status": PlanStatus.ACTIVE})
        for record in records:
            if record.task_id is None:
                continue
            updated_steps = [
                s.model_copy(update={"status": StepStatus.DISPATCHED, "task_id": record.task_id})
                if s.step_id == record.step_id else s
                for s in updated.steps
            ]
            updated = updated.model_copy(update={"steps": updated_steps})
        return updated, records

    async def refresh(self, mission: Mission, plan: Plan) -> tuple[Plan, MissionProgress]:
        """Re-read task states and recompute progress (§11.4)."""
        task_ids = [s.task_id for s in plan.steps if s.task_id]
        states = await self.monitor.task_states(task_ids)
        updated = self.monitor.apply_task_states(plan, states)
        return updated, self.monitor.progress(mission, updated)

    async def assess_failure(self, step: PlanStep, plan: Plan) -> FailureAssessment:
        """Work out what a failed step means (§11.5).

        Retry permission is decided from the *task's* recorded state and the
        autonomy level, never from the orchestrator's preference: §7 of P-01
        already classifies which errors are retryable, and Level 1 may not retry
        autonomously.
        """
        state: dict[str, Any] = {}
        if step.task_id:
            states = await self.monitor.task_states([step.task_id])
            state = states.get(step.task_id, {})
        status = str(state.get("status", "FAILED"))
        errors = dict(state.get("error_details") or {})
        retries_used = int(state.get("retry_count") or 0)

        # Resolve dependents against a projection of the plan in which *this*
        # step has failed. The caller may not have refreshed the plan yet, and
        # reading dependents from stale step states would under-report the blast
        # radius of the failure being assessed.
        projected = [
            s.model_copy(update={"status": StepStatus.FAILED}) if s.step_id == step.step_id else s
            for s in plan.steps
        ]
        dependents = self.resolver.blocked_by_failure(projected)
        # A code in P-01's non-retryable set means retrying cannot help.
        non_retryable = {"VALIDATION_ERROR", "PERMISSION_DENIED", "APPROVAL_REJECTED",
                         "APPROVAL_EXPIRED", "APPROVAL_BINDING_MISMATCH", "SECURITY_VIOLATION"}
        code = str(errors.get("code", ""))
        recoverable = status == "FAILED" and code not in non_retryable
        retry_permitted = recoverable and self.autonomy.may_retry_autonomously()

        reason = (
            f"task {step.task_id} ended {status}"
            + (f" with code {code}" if code else "")
            + (f"; {retries_used} retry(ies) already used" if retries_used else "")
        )
        return FailureAssessment(
            step_id=step.step_id,
            task_id=step.task_id or "",
            task_status=status,
            error_details=errors,
            recoverable=recoverable,
            retry_permitted=retry_permitted,
            affected_dependents=[d for d in dependents if d != step.step_id],
            replan_recommended=bool(dependents) and not retry_permitted,
            reason=reason,
        )

    def completion_state(self, plan: Plan, mission: Mission) -> MissionState:
        """Decide the mission's terminal state from real step states.

        §11.5: a mission with any failed or blocked step is never COMPLETED. This
        is the guard against a failed mission being silently marked successful.
        """
        steps = plan.steps
        if not steps:
            return MissionState.BLOCKED
        if any(s.status == StepStatus.FAILED for s in steps):
            return MissionState.FAILED
        if any(s.status == StepStatus.BLOCKED for s in steps):
            return MissionState.BLOCKED
        if all(s.status in {StepStatus.COMPLETED, StepStatus.SKIPPED, StepStatus.CANCELLED} for s in steps):
            # Cancelled steps mean the mission did not actually finish its work.
            if any(s.status == StepStatus.CANCELLED for s in steps):
                return MissionState.CANCELLED
            return MissionState.COMPLETED
        if any(s.status in {StepStatus.RUNNING, StepStatus.DISPATCHED} for s in steps):
            return MissionState.EXECUTING
        return MissionState.EXECUTING

    def transition_mission(self, mission: Mission, target: MissionState, *, reason: str) -> Mission:
        """Validate and apply a mission state change, recording the reason."""
        validate_mission_transition(mission.state, target)
        return mission.model_copy(update={"state": target})

    async def audit_progress(self, mission: Mission, progress: MissionProgress, *, principal_id: str) -> None:
        async with self.db.session_factory() as session:
            await AuditRepo(session).record(
                AUDIT_PROGRESS, "allowed", principal_id=principal_id,
                resource=mission.mission_id, action="progress",
                payload={
                    "percent_complete": progress.percent_complete,
                    "completed": progress.completed,
                    "failed": progress.failed,
                    "blocked": progress.blocked,
                    "total_steps": progress.total_steps,
                    "state": progress.state.value,
                },
            )
            await session.commit()


__all__ = [
    "AUDIT_BLOCKED",
    "AUDIT_DISPATCH",
    "AUDIT_FAILURE",
    "AUDIT_PROGRESS",
    "DispatchPolicy",
    "DispatchRecord",
    "DispatchRefusedError",
    "FailureAssessment",
    "Orchestrator",
    "ProgressMonitor",
    "TaskDispatcher",
]
