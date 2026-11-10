"""Workflow engine (§§15–16).

Workflow definitions are validated DATA — named steps referencing tool
actions, with per-step failure strategies and optional compensation
actions — never arbitrary code (§15.1). Runs are persistent: every step
writes a checkpoint (§16.1), every step submission carries an
idempotency key (§16.2), and restart recovery NEVER blindly repeats an
interrupted non-idempotent step (§16.4) — uncertain outcomes surface as
RECOVERY_REQUIRED for a human to reconcile.

Execution of steps goes through the exact same ExecutionService
submit/execute path as standalone requests: same policy, same
approvals, same audit. A workflow is orchestration, not a side door.
"""
from __future__ import annotations

from ..database.models.base import utcnow
from ..database.models.execution import WorkflowRun, WorkflowStepRun
from ..database.repositories.core import AgentRepository
from ..database.repositories.execution import (
    ExecutionRequestRepository,
    WorkflowDefinitionRepository,
    WorkflowRunRepository,
    WorkflowStepRunRepository,
)
from .constants import WORKFLOW_TRANSITIONS
from .errors import ApprovalRequiredError, WorkflowInvalidError, WorkflowStateError
from .schemas import ExecutionRequestIn

MAX_STEPS = 50
ON_FAILURE_STRATEGIES = ("stop", "continue", "retry")


def validate_definition(definition: dict) -> list[str]:
    """Structural validation of a workflow definition (data only)."""
    errors: list[str] = []
    if not isinstance(definition, dict):
        return ["definition must be an object"]
    steps = definition.get("steps")
    if not isinstance(steps, list) or not steps:
        return ["definition.steps must be a non-empty list"]
    if len(steps) > MAX_STEPS:
        errors.append(f"definition has {len(steps)} steps; the ceiling is {MAX_STEPS}")
    seen: set[str] = set()
    for index, step in enumerate(steps):
        where = f"steps[{index}]"
        if not isinstance(step, dict):
            errors.append(f"{where}: step must be an object")
            continue
        step_id = step.get("id")
        if not step_id or not isinstance(step_id, str):
            errors.append(f"{where}: step requires a string 'id'")
        elif step_id in seen:
            errors.append(f"{where}: duplicate step id '{step_id}'")
        else:
            seen.add(step_id)
        if not step.get("tool") or not step.get("action"):
            errors.append(f"{where}: step requires 'tool' and 'action'")
        if not isinstance(step.get("parameters", {}), dict):
            errors.append(f"{where}: 'parameters' must be an object")
        strategy = step.get("on_failure", "stop")
        if strategy not in ON_FAILURE_STRATEGIES:
            errors.append(f"{where}: on_failure must be one of {ON_FAILURE_STRATEGIES}")
        compensation = step.get("compensation")
        if compensation is not None:
            if not isinstance(compensation, dict) or not compensation.get("tool") \
                    or not compensation.get("action"):
                errors.append(f"{where}: compensation requires 'tool' and 'action'")
            elif not isinstance(compensation.get("parameters", {}), dict):
                errors.append(f"{where}: compensation.parameters must be an object")
    return errors


def _substitute(value, inputs: dict):
    """Replace ``{{input.key}}`` placeholders in string parameter values
    with workflow inputs (data substitution only — never code)."""
    if isinstance(value, str):
        for key, item in inputs.items():
            value = value.replace("{{input." + key + "}}", str(item))
        return value
    if isinstance(value, dict):
        return {k: _substitute(v, inputs) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, inputs) for v in value]
    return value


class WorkflowEngine:
    def __init__(self, session_factory, execution_service):
        self._session_factory = session_factory
        self._execution = execution_service

    # ------------------------------------------------------------- lifecycle
    def transition(self, run: WorkflowRun, target: str) -> None:
        allowed = WORKFLOW_TRANSITIONS.get(run.status, set())
        if target not in allowed:
            raise WorkflowStateError(
                f"workflow run cannot move {run.status} -> {target}",
                details={"from": run.status, "to": target})
        run.status = target

    def create_definition(self, principal, payload) -> object:
        errors = validate_definition(payload.definition)
        session = self._session_factory()
        try:
            repo = WorkflowDefinitionRepository(session)
            existing = repo.get_by_name_version(payload.name, payload.version)
            if existing is not None:
                raise WorkflowInvalidError(
                    f"workflow '{payload.name}' v{payload.version} already exists",
                    details={"definition_id": existing.id})
            from ..database.models.execution import WorkflowDefinition
            row = WorkflowDefinition(
                name=payload.name, version=payload.version,
                description=payload.description, definition=payload.definition,
                status="invalid" if errors else "valid",
                validation_errors=errors,
                created_by_type=principal.type.value, created_by_id=principal.id)
            repo.add(row)
            session.commit()
            session.refresh(row)
            return row
        finally:
            session.close()

    async def start_run(self, principal, definition_id: str, payload) -> WorkflowRun:
        session = self._session_factory()
        try:
            definitions = WorkflowDefinitionRepository(session)
            definition = definitions.get(definition_id)
            if definition is None:
                raise WorkflowInvalidError(f"workflow definition '{definition_id}' not found")
            if definition.status != "valid":
                raise WorkflowInvalidError(
                    "workflow definition is not valid: "
                    + "; ".join(definition.validation_errors or []))
            agent = AgentRepository(session).get(payload.agent_id)
            if agent is None:
                raise WorkflowInvalidError(f"agent '{payload.agent_id}' not found")
            checkpoint = {"completed_steps": [], "step_outputs": {},
                          "compensated_steps": [], "failed_steps": []}
            if getattr(payload, "business_ref", None):
                # P-06: carried in the checkpoint and propagated to step
                # requests (see _drive_step); absent for P-05-era runs.
                checkpoint["business_ref"] = payload.business_ref
            run = WorkflowRun(
                definition_id=definition.id, workflow_name=definition.name,
                workflow_version=definition.version,
                requesting_agent_id=payload.agent_id, task_id=payload.task_id,
                status="QUEUED", inputs=payload.inputs or {},
                checkpoint=checkpoint,
                submitted_by_type=principal.type.value, submitted_by_id=principal.id)
            WorkflowRunRepository(session).add(run)
            step_repo = WorkflowStepRunRepository(session)
            for step in definition.definition["steps"]:
                step_repo.add(WorkflowStepRun(workflow_run_id=run.id, step_id=step["id"],
                                              status="pending"))
            session.commit()
            session.refresh(run)
            run_id = run.id
        finally:
            session.close()
        return await self.drive(principal, run_id)

    # ----------------------------------------------------------------- drive
    async def drive(self, principal, run_id: str) -> WorkflowRun:
        """Advance a run until it completes, blocks (approval/human), or
        fails. Safe to call repeatedly (resume path)."""
        session = self._session_factory()
        try:
            run = WorkflowRunRepository(session).get(run_id)
            if run is None:
                raise WorkflowInvalidError(f"workflow run '{run_id}' not found")
            definition = WorkflowDefinitionRepository(session).get(run.definition_id)
            steps = definition.definition["steps"]
            if run.status in ("COMPLETED", "FAILED", "CANCELLED"):
                return run
            if run.status in ("PAUSED",):
                return run
            if run.status == "QUEUED":
                self.transition(run, "RUNNING")
                run.started_at = run.started_at or utcnow()
            elif run.status in ("AWAITING_APPROVAL", "AWAITING_HUMAN"):
                self.transition(run, "RUNNING")
            elif run.status != "RUNNING":
                raise WorkflowStateError(f"workflow run is {run.status} and cannot be driven")
            session.commit()
        finally:
            session.close()

        for step in steps:
            outcome = await self._drive_step(principal, run_id, step)
            if outcome != "completed":
                return self._get_run(run_id)
        session = self._session_factory()
        try:
            run = WorkflowRunRepository(session).get(run_id)
            self.transition(run, "COMPLETED")
            run.completed_at = utcnow()
            run.result = {"completed_steps": (run.checkpoint or {}).get("completed_steps", [])}
            session.commit()
            session.refresh(run)
            return run
        finally:
            session.close()

    async def _drive_step(self, principal, run_id: str, step: dict) -> str:
        session = self._session_factory()
        try:
            run = WorkflowRunRepository(session).get(run_id)
            step_repo = WorkflowStepRunRepository(session)
            step_run = step_repo.get_by_step(run_id, step["id"])
            inputs = run.inputs or {}
            run.current_step = step["id"]
            session.commit()
            request = None
            if step_run.execution_request_id:
                request = ExecutionRequestRepository(session).get(step_run.execution_request_id)
        finally:
            session.close()

        if request is None:
            run_snapshot = self._get_run(run_id)
            submitted = self._execution.submit(principal, ExecutionRequestIn(
                agent_id=run_snapshot.requesting_agent_id,
                tool=step["tool"], action=step["action"],
                parameters=_substitute(step.get("parameters", {}), inputs),
                task_id=run_snapshot.task_id,
                business_ref=(run_snapshot.checkpoint or {}).get("business_ref"),
                expected_outcome=step.get("expected_outcome", {}),
                idempotency_key=f"wf:{run_id}:{step['id']}",
            ))
            # Link the request to the workflow (fields exist on the model).
            self._execution.link_workflow(submitted.id, run_id, step["id"])
            session = self._session_factory()
            try:
                step_run = WorkflowStepRunRepository(session).get_by_step(run_id, step["id"])
                step_run.execution_request_id = submitted.id
                step_run.status = "running"
                step_run.started_at = utcnow()
                session.commit()
            finally:
                session.close()
            request = submitted

        if request.status in ("QUEUED", "AWAITING_APPROVAL"):
            try:
                request = await self._execution.execute(principal, request.id)
            except ApprovalRequiredError:
                # Still awaiting a decision: settle from the stored state
                # (the run returns to AWAITING_APPROVAL below).
                request = self._execution.get_request(request.id)

        return await self._settle_step(principal, run_id, step, request)

    async def _settle_step(self, principal, run_id: str, step: dict, request) -> str:
        status = request.status
        session = self._session_factory()
        try:
            run = WorkflowRunRepository(session).get(run_id)
            step_run = WorkflowStepRunRepository(session).get_by_step(run_id, step["id"])
            checkpoint = dict(run.checkpoint or {})
            if status in ("COMPLETED", "COMPLETED_WITH_WARNINGS"):
                step_run.status = "completed"
                step_run.completed_at = utcnow()
                step_run.output_ref = request.id
                completed = list(checkpoint.get("completed_steps", []))
                if step["id"] not in completed:
                    completed.append(step["id"])
                checkpoint["completed_steps"] = completed
                outputs = dict(checkpoint.get("step_outputs", {}))
                outputs[step["id"]] = request.id
                checkpoint["step_outputs"] = outputs
                run.checkpoint = checkpoint
                session.commit()
                return "completed"
            if status == "AWAITING_APPROVAL":
                step_run.status = "awaiting_approval"
                self.transition(run, "AWAITING_APPROVAL")
                session.commit()
                return "blocked"
            if status == "REQUIRES_HUMAN_ACTION":
                step_run.status = "awaiting_human"
                self.transition(run, "AWAITING_HUMAN")
                session.commit()
                return "blocked"
            # Failure family.
            step_run.status = "failed"
            step_run.error_details = {"status": status,
                                      "error_category": request.error_category,
                                      "summary": request.result_summary}
            failed = list(checkpoint.get("failed_steps", []))
            if step["id"] not in failed:
                failed.append(step["id"])
            checkpoint["failed_steps"] = failed
            run.checkpoint = checkpoint
            session.commit()
        finally:
            session.close()

        strategy = step.get("on_failure", "stop")
        if strategy == "continue":
            return "completed"  # recorded as failed in the checkpoint above
        if strategy == "retry":
            # Only ever for idempotent actions; the execution layer owns
            # attempt bookkeeping. One bounded retry per drive.
            fresh = self._execution.get_request(request.id)
            if fresh is not None and fresh.status in ("FAILED", "TIMED_OUT"):
                retried = await self._execution.execute(principal, request.id)
                return await self._settle_step(principal, run_id, step, retried)
        await self._fail_run(principal, run_id, step)
        return "failed"

    async def _fail_run(self, principal, run_id: str, failed_step: dict) -> None:
        """Mark the run FAILED and run compensation for completed steps
        that declared one (reverse order). Compensation goes through the
        normal execution path; if a compensation cannot run, the run is
        escalated to RECOVERY_REQUIRED instead of pretending (§16.3)."""
        session = self._session_factory()
        try:
            run = WorkflowRunRepository(session).get(run_id)
            definition = WorkflowDefinitionRepository(session).get(run.definition_id)
            checkpoint = dict(run.checkpoint or {})
            completed = list(checkpoint.get("completed_steps", []))
            steps_by_id = {s["id"]: s for s in definition.definition["steps"]}
            agent_id = run.requesting_agent_id
            inputs = run.inputs or {}
        finally:
            session.close()
        blocked = False
        for step_id in reversed(completed):
            compensation = steps_by_id[step_id].get("compensation")
            if not compensation:
                continue
            result = await self._execution.submit_and_execute(principal, ExecutionRequestIn(
                agent_id=agent_id, tool=compensation["tool"], action=compensation["action"],
                parameters=_substitute(compensation.get("parameters", {}), inputs),
                idempotency_key=f"wf:{run_id}:{step_id}:compensation"))
            session = self._session_factory()
            try:
                run = WorkflowRunRepository(session).get(run_id)
                checkpoint = dict(run.checkpoint or {})
                if result.status in ("COMPLETED", "COMPLETED_WITH_WARNINGS"):
                    done = list(checkpoint.get("compensated_steps", []))
                    done.append(step_id)
                    checkpoint["compensated_steps"] = done
                    step_run = WorkflowStepRunRepository(session).get_by_step(run_id, step_id)
                    if step_run is not None:
                        step_run.status = "compensated"
                else:
                    blocked = True
                    checkpoint.setdefault("compensation_blocked", []).append(
                        {"step": step_id, "status": result.status})
                run.checkpoint = checkpoint
                session.commit()
            finally:
                session.close()
        session = self._session_factory()
        try:
            run = WorkflowRunRepository(session).get(run_id)
            if blocked:
                self.transition(run, "RECOVERY_REQUIRED")
                run.result = {"reason": "a compensation action could not be executed; "
                                        "manual reconciliation required (not a rollback)"}
            else:
                self.transition(run, "FAILED")
                run.completed_at = utcnow()
                run.result = {"failed_step": failed_step["id"]}
            session.commit()
        finally:
            session.close()

    # --------------------------------------------------------------- control
    def pause(self, run_id: str) -> WorkflowRun:
        return self._control(run_id, "PAUSED")

    def cancel(self, run_id: str) -> WorkflowRun:
        return self._control(run_id, "CANCELLED")

    async def resume(self, principal, run_id: str) -> WorkflowRun:
        session = self._session_factory()
        try:
            run = WorkflowRunRepository(session).get(run_id)
            if run is None:
                raise WorkflowInvalidError(f"workflow run '{run_id}' not found")
            if run.status == "PAUSED":
                self.transition(run, "QUEUED")
                session.commit()
            elif run.status == "RECOVERY_REQUIRED":
                raise WorkflowStateError(
                    "run requires reconciliation; resolve the uncertain step before resuming")
        finally:
            session.close()
        return await self.drive(principal, run_id)

    def _control(self, run_id: str, target: str) -> WorkflowRun:
        session = self._session_factory()
        try:
            run = WorkflowRunRepository(session).get(run_id)
            if run is None:
                raise WorkflowInvalidError(f"workflow run '{run_id}' not found")
            self.transition(run, target)
            if target == "CANCELLED":
                run.completed_at = utcnow()
            session.commit()
            session.refresh(run)
            return run
        finally:
            session.close()

    def _get_run(self, run_id: str) -> WorkflowRun:
        session = self._session_factory()
        try:
            run = WorkflowRunRepository(session).get(run_id)
            if run is None:
                raise WorkflowInvalidError(f"workflow run '{run_id}' not found")
            session.expunge(run)
            return run
        finally:
            session.close()

    # -------------------------------------------------------------- recovery
    def recover_interrupted(self, idempotent_lookup) -> list[dict]:
        """§16.4: workflow runs left RUNNING by a restart. A step whose
        execution request ended in a terminal state settles normally on
        the next drive; a step whose request is non-terminal/interrupted
        is resumable ONLY if its action is idempotent — otherwise the
        run goes to RECOVERY_REQUIRED and nothing is repeated."""
        report = []
        session = self._session_factory()
        try:
            runs = WorkflowRunRepository(session).in_statuses(["RUNNING"])
            for run in runs:
                current = run.current_step
                step_run = None
                if current:
                    step_run = WorkflowStepRunRepository(session).get_by_step(run.id, current)
                request = None
                if step_run is not None and step_run.execution_request_id:
                    request = ExecutionRequestRepository(session).get(
                        step_run.execution_request_id)
                if request is not None and request.status in (
                        "ACCEPTED", "VALIDATING", "QUEUED", "RUNNING", "INTERRUPTED"):
                    if idempotent_lookup(request.tool_name, request.action_name):
                        run.status = "QUEUED"
                        report.append({"workflow_run_id": run.id, "action": "requeued",
                                       "reason": "interrupted step is idempotent; safe to resume"})
                    else:
                        run.status = "RECOVERY_REQUIRED"
                        checkpoint = dict(run.checkpoint or {})
                        checkpoint["recovery"] = {
                            "step": current, "request_id": request.id,
                            "reason": "interrupted during a non-idempotent step; "
                                      "outcome uncertain — reconcile manually, never auto-repeat"}
                        run.checkpoint = checkpoint
                        report.append({"workflow_run_id": run.id,
                                       "action": "recovery_required",
                                       "reason": "non-idempotent step interrupted"})
                else:
                    run.status = "QUEUED"
                    report.append({"workflow_run_id": run.id, "action": "requeued",
                                   "reason": "no in-flight step at restart"})
            session.commit()
            return report
        finally:
            session.close()
