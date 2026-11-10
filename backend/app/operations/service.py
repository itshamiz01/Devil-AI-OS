"""OperationsService — the P-12 Autonomous Operations Engine facade.

Composition, not replacement (audit §1/§4): workflows are decomposed
deterministically, authorized through the P-10 PermissionBroker,
approved through P-01 approvals, budgeted through P-07, executed
through the P-01 TaskManager / P-05 ExecutionService, verified
independently, learned from through P-09 — and every transition is
recorded. This service owns only P-12's coordination state.

The §22 pipeline is the ONLY execution path: there is deliberately
no method here that dispatches a step without passing validation →
policy/decision → broker authorization → approval (when required)
first. ``execute_step_direct`` does not exist; the security test
suite asserts the pipeline's stages fire in order and that raw
instruction text is rejected at validation.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json

from sqlalchemy.orm import Session

from ..core.config import Settings
from ..core.exceptions import (
    InvalidStateTransitionError, NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.base import utcnow
from ..database.models.core import AuditEvent
from ..database.models.operations import (
    AutonomousWorkflow, OperationsApprovalLink, OperationsAssignment,
    OperationsAutonomyPolicy, OperationsDeadLetter, OperationsDecision,
    OperationsRecoveryRecord, OperationsReport, OperationsTrigger,
    WorkflowCheckpoint, WorkflowEvent, WorkflowExecution, WorkflowTask,
    WorkflowVersion,
)
from ..database.repositories.core import AuditRepository, ConfigRepository
from ..database.repositories.operations import (
    ApprovalLinkRepository, AssignmentRepository, AutonomyPolicyRepository,
    DeadLetterRepository, DecisionRepository, RecoveryRecordRepository,
    ReportRepository, TriggerRepository, WorkflowCheckpointRepository,
    WorkflowEventRepository, WorkflowExecutionRepository,
    WorkflowRepository, WorkflowTaskRepository, WorkflowVersionRepository,
)
from ..events.events import Event, EventType
from ..permissions.models import Principal, PrincipalType
from . import autonomy as autonomy_mod
from . import constants as C
from . import decisions as decisions_mod
from . import planner as planner_mod
from . import recovery as recovery_mod
from . import scheduling as scheduling_mod
from . import verification as verification_mod
from .state_machine import (
    validate_task_transition, validate_workflow_transition,
)

SYSTEM_PRINCIPAL = Principal(PrincipalType.SYSTEM, "operations-engine")


def _actor(principal: Principal | None) -> str:
    if principal is None:
        return "system:operations-engine"
    return f"{principal.type.value}:{principal.id}"


class OperationsService:
    def __init__(self, session_factory, *, settings: Settings, bus,
                 approvals, tasks, agents, execution, business,
                 financial, survival, memory, security, monitor=None):
        self._session_factory = session_factory
        self._settings = settings
        self._bus = bus
        self._approvals = approvals
        self._tasks = tasks
        self._agents = agents
        self._execution = execution
        self._business = business
        self._financial = financial
        self._survival = survival
        self._memory = memory
        self._security = security
        self._monitor = monitor
        self._breakers: dict[str, recovery_mod.CircuitBreaker] = {}
        self._loop_task: asyncio.Task | None = None
        self._stopped = asyncio.Event()
        self._seed_settings()
        self._subscribe_triggers()

    # ------------------------------------------------------------ settings
    def _seed_settings(self) -> None:
        session = self._session_factory()
        try:
            repo = ConfigRepository(session)
            if repo.get(C.SETTINGS_KEY) is None:
                repo.set(C.SETTINGS_KEY, json.dumps(C.DEFAULT_SETTINGS),
                         "operations settings (owner-governed: concurrency, "
                         "autonomy defaults, recovery thresholds)")
        finally:
            session.close()

    def get_settings(self) -> dict:
        session = self._session_factory()
        try:
            row = ConfigRepository(session).get(C.SETTINGS_KEY)
            raw = row.value if row is not None else None
        finally:
            session.close()
        merged = dict(C.DEFAULT_SETTINGS)
        if raw:
            try:
                merged.update(json.loads(raw))
            except ValueError:
                pass
        return merged

    def update_settings(self, principal: Principal, patch: dict) -> dict:
        if principal.type != PrincipalType.OWNER:
            raise PermissionDeniedError(
                "operations settings are owner-governed")
        current = self.get_settings()
        allowed = set(C.DEFAULT_SETTINGS)
        for key, value in (patch or {}).items():
            if key not in allowed or key == "version":
                continue
            if key == "tick_interval_seconds" and float(value) < 5:
                raise ValidationError(
                    "tick_interval_seconds must be at least 5")
            if key == "default_autonomy_level" and not 0 <= int(value) <= 4:
                raise ValidationError(
                    "default_autonomy_level must be 0..4")
            if key.startswith("max_") and int(value) < 1:
                raise ValidationError(f"{key} must be at least 1")
            if key in ("circuit_breaker_threshold", "default_max_retries") \
                    and int(value) < 0:
                raise ValidationError(f"{key} must be at least 0")
            current[key] = value
        current["version"] = int(current.get("version", 1)) + 1
        session = self._session_factory()
        try:
            ConfigRepository(session).set(
                C.SETTINGS_KEY, json.dumps(current),
                "operations settings (owner-governed)")
        finally:
            session.close()
        self._audit(principal, "operations.settings_updated", "settings",
                    C.SETTINGS_KEY, "allow", "owner updated operations settings",
                    {"version": current["version"]})
        return current

    # ------------------------------------------------------------ audit/events
    def _audit(self, principal, action, resource_type, resource_id,
               decision, reason, details=None) -> None:
        session = self._session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value if principal else "system",
                actor_id=principal.id if principal else "operations-engine",
                action=action, target_type=resource_type,
                target_id=str(resource_id) if resource_id else None,
                decision=decision, reason=reason,
                details=details or {}, created_at=utcnow()))
        except Exception:
            session.rollback()
        finally:
            session.close()

    def _record_event(self, workflow_id: str, event_type: str, *,
                      task_id: str | None = None, actor: str = "system",
                      payload: dict | None = None,
                      correlation_id: str | None = None,
                      bus_type: EventType | None = None,
                      severity: str = "info") -> None:
        session = self._session_factory()
        try:
            WorkflowEventRepository(session).add(WorkflowEvent(
                workflow_id=workflow_id, task_id=task_id,
                event_type=event_type, actor=actor, payload=payload or {},
                correlation_id=correlation_id))
        finally:
            session.close()
        if bus_type is not None and self._bus is not None:
            self._bus.publish_sync_safe(Event(
                event_type=bus_type, source="operations",
                payload={"workflow_id": workflow_id, "task_id": task_id,
                         **(payload or {})},
                correlation_id=correlation_id, severity=severity))

    def _transition_workflow(self, session: Session, workflow: AutonomousWorkflow,
                             target: str) -> None:
        validate_workflow_transition(workflow.status, target)
        workflow.status = target

    def _transition_task(self, session: Session, task: WorkflowTask,
                         target: str) -> None:
        validate_task_transition(task.status, target)
        task.status = target

    # ------------------------------------------------------------ views
    def workflow_view(self, row: AutonomousWorkflow) -> dict:
        return {
            "id": row.id, "name": row.name, "business_id": row.business_id,
            "objective": row.objective, "description": row.description,
            "origin": row.origin, "trigger_id": row.trigger_id,
            "priority": row.priority, "priority_class": row.priority_class,
            "autonomy_level": row.autonomy_level,
            "execution_policy": row.execution_policy or {},
            "budget_id": row.budget_id, "deadline": _iso(row.deadline),
            "success_conditions": row.success_conditions or {},
            "failure_conditions": row.failure_conditions or {},
            "verification_policy": row.verification_policy or {},
            "status": row.status, "current_version": row.current_version,
            "definition": row.definition or {},
            "created_by": f"{row.created_by_type}:{row.created_by_id}",
            "idempotency_key": row.idempotency_key,
            "started_at": _iso(row.started_at),
            "completed_at": _iso(row.completed_at),
            "verified_outcome": row.verified_outcome,
            "failure_reason": row.failure_reason,
            "learning_record_id": row.learning_record_id,
            "created_at": _iso(row.created_at), "updated_at": _iso(row.updated_at),
        }

    def task_view(self, row: WorkflowTask) -> dict:
        return {
            "id": row.id, "workflow_id": row.workflow_id,
            "step_key": row.step_key, "name": row.name,
            "objective": row.objective, "description": row.description,
            "kind": row.kind, "action_class": row.action_class,
            "substrate": row.substrate or {}, "depends_on": row.depends_on or [],
            "assigned_agent_id": row.assigned_agent_id,
            "required_capabilities": row.required_capabilities or [],
            "priority": row.priority, "deadline": _iso(row.deadline),
            "budget_ref": row.budget_ref or {},
            "input_data": row.input_data or {},
            "expected_output": row.expected_output or {},
            "acceptance_criteria": row.acceptance_criteria or {},
            "verification_method": row.verification_method,
            "retry_policy": row.retry_policy or {},
            "status": row.status, "attempts": row.attempts,
            "idempotency_key": row.idempotency_key,
            "substrate_ref": row.substrate_ref, "result": row.result,
            "verification_status": row.verification_status,
            "verification_detail": row.verification_detail or {},
            "error": row.error,
            "started_at": _iso(row.started_at),
            "completed_at": _iso(row.completed_at),
            "next_attempt_at": _iso(row.next_attempt_at),
        }

    # ------------------------------------------------------------ access guard
    def _assert_business_access(self, principal: Principal,
                                business_id: str | None) -> None:
        """Agents act only inside their own business (P-10 broker
        gate 3 mirrors this for step authorization; creation and
        reads enforce it here too — §14 isolation)."""
        if business_id is None:
            return
        if principal.type == PrincipalType.AGENT:
            session = self._session_factory()
            try:
                from ..database.models.core import Agent as AgentRow
                row = session.get(AgentRow, principal.id)
            finally:
                session.close()
            if row is None or row.business_ref != business_id:
                raise PermissionDeniedError(
                    "agent is scoped to a different business",
                    details={"business_id": business_id})
        elif principal.type == PrincipalType.EXTERNAL:
            raise PermissionDeniedError("external principals have no business access")

    def _get_workflow(self, session: Session, workflow_id: str) -> AutonomousWorkflow:
        row = WorkflowRepository(session).get(workflow_id)
        if row is None:
            raise NotFoundError(f"workflow {workflow_id} not found")
        return row

    # ------------------------------------------------------------ workflows CRUD
    def create_workflow(self, principal: Principal, data: dict) -> dict:
        """Create a workflow in DRAFT from a structured definition or
        a deterministic template. Free-text instructions are refused:
        a definition must carry validated steps (§22 stage 1–2)."""
        business_id = data.get("business_id")
        self._assert_business_access(principal, business_id)
        if business_id is not None:
            self._business.get_business(business_id)  # must exist

        definition = data.get("definition")
        if definition is None and data.get("template"):
            definition = planner_mod.decompose(
                data["template"], data.get("objective", ""))
        if definition is None:
            raise ValidationError(
                "a workflow requires a structured 'definition' (or a "
                "'template'); free-text instructions are never executed")
        if isinstance(definition, dict) and definition.get("instructions") \
                and not definition.get("steps"):
            raise ValidationError(
                "raw instruction text cannot become a workflow; submit "
                "structured steps (LLM output is validated the same way)")
        steps = planner_mod.validate_definition(definition)

        idem = data.get("idempotency_key")
        session = self._session_factory()
        try:
            repo = WorkflowRepository(session)
            if idem:
                existing = repo.get_by_idempotency_key(idem)
                if existing is not None:
                    return self.workflow_view(existing)
            row = AutonomousWorkflow(
                name=str(data.get("name") or "Untitled workflow")[:300],
                business_id=business_id,
                objective=str(data.get("objective")
                              or definition.get("objective") or ""),
                description=data.get("description"),
                origin=data.get("origin") or (
                    "owner" if principal.type == PrincipalType.OWNER
                    else principal.type.value),
                trigger_id=data.get("trigger_id"),
                priority=int(data.get("priority", 5)),
                priority_class=int(data.get("priority_class",
                                            data.get("priority", 5))),
                autonomy_level=int(data.get("autonomy_level", 1)),
                execution_policy=dict(data.get("execution_policy") or {}),
                budget_id=data.get("budget_id"),
                deadline=_parse_dt(data.get("deadline")),
                success_conditions=dict(data.get("success_conditions") or {}),
                failure_conditions=dict(data.get("failure_conditions") or {}),
                verification_policy=dict(data.get("verification_policy") or {}),
                status="DRAFT",
                definition=definition,
                created_by_type=principal.type.value,
                created_by_id=principal.id,
                idempotency_key=idem,
                correlation_id=data.get("correlation_id"))
            repo.add(row)
            WorkflowVersionRepository(session).add(WorkflowVersion(
                workflow_id=row.id, version=1, definition=definition,
                change_reason="created",
                created_by=_actor(principal)))
            self._materialise_tasks(session, row, steps)
            session.expunge(row)
            view = self.workflow_view(row)
        finally:
            session.close()
        self._record_event(view["id"], "workflow.created",
                           actor=_actor(principal),
                           payload={"origin": view["origin"]},
                           bus_type=EventType.OPERATIONS_WORKFLOW_CREATED)
        self._audit(principal, "operations.workflow_created", "workflow",
                    view["id"], "allow", "workflow created in DRAFT",
                    {"business_id": business_id})
        return view

    def _materialise_tasks(self, session: Session,
                           workflow: AutonomousWorkflow,
                           steps: list[dict]) -> None:
        repo = WorkflowTaskRepository(session)
        for step in steps:
            repo.add(WorkflowTask(
                workflow_id=workflow.id, step_key=step["step_key"],
                name=step["name"], objective=step["objective"],
                description=step.get("description"), kind=step["kind"],
                action_class=step["action_class"],
                substrate=step["substrate"], depends_on=step["depends_on"],
                assigned_agent_id=step.get("assigned_agent_id"),
                required_capabilities=step["required_capabilities"],
                priority=step["priority"],
                estimated_effort=step["estimated_effort"],
                budget_ref=step["budget_ref"],
                permission_requirements=step["permission_requirements"],
                input_data=step["input_data"],
                expected_output=step["expected_output"],
                acceptance_criteria=step["acceptance_criteria"],
                verification_method=step["verification_method"],
                retry_policy=step["retry_policy"], status="PENDING",
                idempotency_key=f"wf:{workflow.id}:{step['step_key']}"))

    def get_workflow(self, principal: Principal, workflow_id: str) -> dict:
        session = self._session_factory()
        try:
            row = self._get_workflow(session, workflow_id)
            self._assert_business_access(principal, row.business_id)
            view = self.workflow_view(row)
            view["tasks"] = [self.task_view(t) for t in
                             WorkflowTaskRepository(session)
                             .list_for_workflow(workflow_id)]
            checkpoint = WorkflowCheckpointRepository(
                session).get_for_workflow(workflow_id)
            view["checkpoints"] = [
                {"id": c.id, "execution_id": c.execution_id,
                 "completed_steps": c.completed_steps or [],
                 "state": c.state or {},
                 "created_at": _iso(c.created_at)}
                for c in ([checkpoint] if checkpoint else [])]
            events = WorkflowEventRepository(session).list_for_workflow(
                workflow_id, limit=100)
            view["history"] = [
                {"id": e.id, "event_type": e.event_type, "actor": e.actor,
                 "task_id": e.task_id, "payload": e.payload or {},
                 "created_at": _iso(e.created_at)}
                for e in events]
            return view
        finally:
            session.close()

    def list_workflows(self, principal: Principal, *, business_id=None,
                       status=None, origin=None, limit=50, offset=0) -> dict:
        if principal.type == PrincipalType.AGENT and business_id is not None:
            self._assert_business_access(principal, business_id)
        session = self._session_factory()
        try:
            rows, total = WorkflowRepository(session).list(
                business_id=business_id, status=status, origin=origin,
                limit=limit, offset=offset)
            if principal.type == PrincipalType.AGENT:
                rows = [r for r in rows
                        if self._agent_business(principal.id) == r.business_id
                        or r.business_id is None]
            return {"items": [self.workflow_view(r) for r in rows],
                    "total": total}
        finally:
            session.close()

    def _agent_business(self, agent_id: str) -> str | None:
        session = self._session_factory()
        try:
            from ..database.models.core import Agent as AgentRow
            row = session.get(AgentRow, agent_id)
            return row.business_ref if row else None
        finally:
            session.close()

    def workflow_history(self, principal: Principal, workflow_id: str,
                         limit: int = 100) -> dict:
        session = self._session_factory()
        try:
            row = self._get_workflow(session, workflow_id)
            self._assert_business_access(principal, row.business_id)
            events = WorkflowEventRepository(session).list_for_workflow(
                workflow_id, limit=limit)
            executions = WorkflowExecutionRepository(session).list_for_workflow(
                workflow_id)
            return {
                "workflow_id": workflow_id,
                "events": [{"id": e.id, "event_type": e.event_type,
                            "task_id": e.task_id, "actor": e.actor,
                            "payload": e.payload or {},
                            "created_at": _iso(e.created_at)}
                           for e in events],
                "executions": [{"id": x.id, "attempt_number": x.attempt_number,
                                "trigger_source": x.trigger_source,
                                "status": x.status,
                                "started_at": _iso(x.started_at),
                                "finished_at": _iso(x.finished_at),
                                "detail": x.detail or {}}
                               for x in executions],
            }
        finally:
            session.close()

    # ------------------------------------------------------------ validation (§10)
    def validate_workflow(self, principal: Principal, workflow_id: str) -> dict:
        """§22 stage 2/3 for the whole workflow: definition integrity,
        budget reference, capability availability, deadline sanity.
        DRAFT → READY on success; failures are recorded and the
        workflow returns to DRAFT with reasons."""
        session = self._session_factory()
        try:
            row = self._get_workflow(session, workflow_id)
            self._assert_business_access(principal, row.business_id)
            if row.status not in ("DRAFT", "BLOCKED"):
                raise InvalidStateTransitionError(
                    f"workflow in {row.status} cannot be validated")
            self._transition_workflow(session, row, "VALIDATING")
            WorkflowRepository(session).save(row)
            workflow_id_ = row.id
            business_id = row.business_id
            definition = row.definition or {}
            budget_id = row.budget_id
        finally:
            session.close()

        problems: list[str] = []
        try:
            steps = planner_mod.validate_definition(definition)
        except ValidationError as exc:
            steps = []
            problems.append(f"definition invalid: {exc.message}")
        if budget_id:
            try:
                budget = self._financial.budgets.get_budget(budget_id)
                if budget.business_id not in (None, business_id):
                    problems.append("budget belongs to a different business")
                if budget.status != "active":
                    problems.append(f"budget status is {budget.status}")
            except NotFoundError:
                problems.append("referenced P-07 budget does not exist")
        for step in steps:
            if step["kind"] == "task_handler":
                handler = step["substrate"].get("handler")
                if not self._tasks.registry.has(handler):
                    problems.append(
                        f"step {step['step_key']}: handler '{handler}' is "
                        "not in the P-01 registry")
            for cap in step["required_capabilities"]:
                if not self._capability_known(cap):
                    problems.append(
                        f"step {step['step_key']}: capability '{cap}' is "
                        "not in the P-04 catalogue")
        session = self._session_factory()
        try:
            row = self._get_workflow(session, workflow_id_)
            if problems:
                self._transition_workflow(session, row, "DRAFT")
                row.failure_reason = "; ".join(problems)
            else:
                not_before = _not_before(row.execution_policy)
                if not_before > utcnow():
                    self._transition_workflow(session, row, "READY")
                    self._transition_workflow(session, row, "SCHEDULED")
                else:
                    self._transition_workflow(session, row, "READY")
                row.failure_reason = None
            WorkflowRepository(session).save(row)
            session.expunge(row)
            view = self.workflow_view(row)
        finally:
            session.close()
        self._record_event(workflow_id_, "workflow.validated",
                           actor=_actor(principal),
                           payload={"problems": problems},
                           bus_type=EventType.OPERATIONS_WORKFLOW_VALIDATED)
        self._record_decision(
            principal, workflow_id=workflow_id_, business_id=business_id,
            category="EXECUTE" if not problems else "REJECT",
            subject="workflow validation",
            rationale="validation passed" if not problems
            else "; ".join(problems),
            evidence={"problems": problems}, policy_checks={},
            authorization_result={})
        if problems:
            raise ValidationError("workflow validation failed",
                                  details={"problems": problems})
        return view

    def _capability_known(self, capability_id: str) -> bool:
        try:
            catalogue = self._agents.capabilities.list_catalogue()
        except Exception:
            return False
        return any(c.name == capability_id for c in catalogue)

    # ------------------------------------------------------------ lifecycle controls
    def pause_workflow(self, principal: Principal, workflow_id: str) -> dict:
        return self._control(principal, workflow_id, "PAUSED",
                             "operations.workflow_paused")

    def cancel_workflow(self, principal: Principal, workflow_id: str) -> dict:
        return self._control(principal, workflow_id, "CANCELLED",
                             "operations.workflow_cancelled")

    def _control(self, principal: Principal, workflow_id: str,
                 target: str, audit_action: str) -> dict:
        session = self._session_factory()
        try:
            row = self._get_workflow(session, workflow_id)
            self._assert_business_access(principal, row.business_id)
            if principal.type == PrincipalType.AGENT \
                    and row.created_by_id != principal.id:
                # Agents control only their own workflows (§14:
                # authority over another agent's work is not implied
                # by business scope).
                raise PermissionDeniedError(
                    "agents may control only workflows they created")
            self._transition_workflow(session, row, target)
            if target == "CANCELLED":
                for task in WorkflowTaskRepository(session).list_for_workflow(
                        workflow_id):
                    if task.status in ("PENDING", "READY", "BLOCKED",
                                       "RECOVERY_PENDING",
                                       "WAITING_FOR_APPROVAL"):
                        self._transition_task(session, task, "CANCELLED")
                        WorkflowTaskRepository(session).save(task)
            WorkflowRepository(session).save(row)
            session.expunge(row)
            view = self.workflow_view(row)
        finally:
            session.close()
        self._record_event(workflow_id, f"workflow.{target.lower()}",
                           actor=_actor(principal),
                           bus_type=EventType.OPERATIONS_WORKFLOW_PAUSED
                           if target == "PAUSED" else None)
        self._audit(principal, audit_action, "workflow", workflow_id,
                    "allow", f"workflow moved to {target}")
        return view

    async def resume_workflow(self, principal: Principal,
                              workflow_id: str) -> dict:
        """Resume a PAUSED/BLOCKED/RECOVERY_PENDING workflow and drive
        it. Resuming re-runs the pipeline — authorization is never
        inherited from before the interruption."""
        session = self._session_factory()
        try:
            row = self._get_workflow(session, workflow_id)
            self._assert_business_access(principal, row.business_id)
            if row.status not in ("PAUSED", "BLOCKED", "RECOVERY_PENDING",
                                  "READY", "SCHEDULED"):
                raise InvalidStateTransitionError(
                    f"workflow in {row.status} cannot be resumed")
        finally:
            session.close()
        return await self.drive_workflow(workflow_id, principal,
                                         trigger_source="resume")

    # ------------------------------------------------------------ autonomy policies
    def set_autonomy_policy(self, principal: Principal, data: dict) -> dict:
        """Owner-only (§4.5 + Article 0 posture): agents can never
        raise — or set — autonomy policy."""
        if principal.type != PrincipalType.OWNER:
            raise PermissionDeniedError(
                "autonomy policies are set by the owner only; agents "
                "cannot modify the rules that govern them")
        scope_type = data.get("scope_type")
        if scope_type not in ("global", "business", "agent",
                              "agent_business", "workflow"):
            raise ValidationError(f"unknown scope_type '{scope_type}'")
        level = int(data.get("level", data.get("max_level", 1)))
        if level < 0 or level > 4:
            raise ValidationError("autonomy level must be 0..4")
        scope_ref = str(data.get("scope_ref") or "")
        agent_ref = data.get("agent_ref")
        if scope_type == "agent_business" and not agent_ref:
            raise ValidationError("agent_business scope requires agent_ref")
        session = self._session_factory()
        try:
            repo = AutonomyPolicyRepository(session)
            row = repo.find(scope_type, scope_ref, agent_ref)
            if row is None:
                row = OperationsAutonomyPolicy(
                    scope_type=scope_type, scope_ref=scope_ref,
                    agent_ref=agent_ref, level=level,
                    action_caps=dict(data.get("action_caps") or {}),
                    set_by=_actor(principal), reason=data.get("reason"))
                repo.add(row)
            else:
                row.level = level
                row.action_caps = dict(data.get("action_caps") or {})
                row.set_by = _actor(principal)
                row.reason = data.get("reason")
                repo.save(row)
            session.expunge(row)
            view = {"id": row.id, "scope_type": row.scope_type,
                    "scope_ref": row.scope_ref, "agent_ref": row.agent_ref,
                    "level": row.level,
                    "level_name": C.AUTONOMY_LEVELS[row.level],
                    "action_caps": row.action_caps or {},
                    "set_by": row.set_by, "reason": row.reason}
        finally:
            session.close()
        self._audit(principal, "operations.autonomy_policy_set",
                    "autonomy_policy", view["id"], "allow",
                    f"{scope_type} policy set to level {level}",
                    {"scope_ref": scope_ref, "agent_ref": agent_ref})
        return view

    def list_autonomy_policies(self, principal: Principal) -> dict:
        session = self._session_factory()
        try:
            rows = AutonomyPolicyRepository(session).all_rows()
            return {"items": [
                {"id": r.id, "scope_type": r.scope_type,
                 "scope_ref": r.scope_ref, "agent_ref": r.agent_ref,
                 "level": r.level, "level_name": C.AUTONOMY_LEVELS[r.level],
                 "action_caps": r.action_caps or {}, "set_by": r.set_by,
                 "reason": r.reason} for r in rows]}
        finally:
            session.close()

    def resolve_autonomy(self, *, business_id, agent_id, workflow_id,
                         workflow_declared_level, action_class,
                         declared_by_owner: bool = False) -> dict:
        session = self._session_factory()
        try:
            rows = AutonomyPolicyRepository(session).all_rows()
            policies = [{"scope_type": r.scope_type,
                         "scope_ref": r.scope_ref,
                         "agent_ref": r.agent_ref, "level": r.level,
                         "action_caps": r.action_caps or {}}
                        for r in rows]
        finally:
            session.close()
        security_mode = self._security.emergency.current_mode()
        return autonomy_mod.resolve_autonomy(
            policies, business_id=business_id, agent_id=agent_id,
            workflow_id=workflow_id,
            workflow_declared_level=workflow_declared_level,
            action_class=action_class,
            default_level=int(self.get_settings()["default_autonomy_level"]),
            constitution_mode=self._settings.mode,
            security_mode=security_mode,
            declared_by_owner=declared_by_owner)

    # ------------------------------------------------------------ decisions
    def _record_decision(self, principal, *, workflow_id=None, task_id=None,
                         business_id=None, category, subject, rationale,
                         evidence, policy_checks, authorization_result,
                         confidence="medium", approval_required=False) -> str:
        session = self._session_factory()
        try:
            row = DecisionRepository(session).add(OperationsDecision(
                workflow_id=workflow_id, task_id=task_id,
                business_id=business_id, category=category,
                subject=subject[:300], rationale=rationale,
                evidence=evidence or {}, policy_checks=policy_checks or {},
                authorization_result=authorization_result or {},
                confidence=confidence, approval_required=approval_required,
                decided_by=_actor(principal)))
            return row.id
        finally:
            session.close()

    def list_decisions(self, principal: Principal, *, workflow_id=None,
                       business_id=None, limit=100) -> dict:
        session = self._session_factory()
        try:
            rows = DecisionRepository(session).list(
                workflow_id=workflow_id, business_id=business_id,
                limit=limit)
            return {"items": [
                {"id": r.id, "workflow_id": r.workflow_id,
                 "task_id": r.task_id, "business_id": r.business_id,
                 "category": r.category, "subject": r.subject,
                 "rationale": r.rationale, "evidence": r.evidence or {},
                 "policy_checks": r.policy_checks or {},
                 "authorization_result": r.authorization_result or {},
                 "confidence": r.confidence,
                 "approval_required": r.approval_required,
                 "decided_by": r.decided_by,
                 "created_at": _iso(r.created_at)} for r in rows]}
        finally:
            session.close()

    # ------------------------------------------------------------ start / drive
    async def start_workflow(self, principal: Principal,
                             workflow_id: str) -> dict:
        """Owner/API entry: READY (or SCHEDULED) → drive. Agent
        callers are scoped to their business; the per-step pipeline
        still gates every action."""
        session = self._session_factory()
        try:
            row = self._get_workflow(session, workflow_id)
            self._assert_business_access(principal, row.business_id)
            if row.status not in ("READY", "SCHEDULED"):
                raise InvalidStateTransitionError(
                    f"workflow in {row.status} cannot be started "
                    "(validate it first)")
        finally:
            session.close()
        return await self.drive_workflow(workflow_id, principal,
                                         trigger_source="start")

    async def drive_workflow(self, workflow_id: str, principal: Principal,
                             *, trigger_source: str = "drive") -> dict:
        """Run the workflow until it completes, blocks, waits for an
        approval, pauses, or fails. Safe to call repeatedly: completed
        steps are never re-executed (checkpoint + substrate
        idempotency keys), and a workflow already being driven is not
        re-entered."""
        if not hasattr(self, "_driving"):
            self._driving = set()
        if workflow_id in self._driving:
            return self.get_workflow(principal, workflow_id)
        self._driving.add(workflow_id)
        try:
            return await self._drive_inner(workflow_id, principal,
                                           trigger_source)
        finally:
            self._driving.discard(workflow_id)

    async def _drive_inner(self, workflow_id: str, principal: Principal,
                           trigger_source: str) -> dict:
        session = self._session_factory()
        try:
            row = self._get_workflow(session, workflow_id)
            if row.status in C.TERMINAL_WORKFLOW_STATES:
                session.expunge(row)
                return self.workflow_view(row)
            if row.status == "DRAFT":
                raise InvalidStateTransitionError("workflow must be validated before it runs")
            if row.status == "VALIDATING":
                raise InvalidStateTransitionError("workflow validation is in progress")
            if row.status != "RUNNING":
                self._transition_workflow(session, row, "RUNNING")
            if row.started_at is None:
                row.started_at = utcnow()
            WorkflowRepository(session).save(row)
            attempt = len(WorkflowExecutionRepository(session)
                          .list_for_workflow(workflow_id)) + 1
            execution = WorkflowExecutionRepository(session).add(
                WorkflowExecution(
                    workflow_id=workflow_id, attempt_number=attempt,
                    trigger_source=trigger_source, status="running",
                    started_at=utcnow()))
            execution_id = execution.id
        finally:
            session.close()
        self._record_event(workflow_id, "workflow.started",
                           actor=_actor(principal),
                           payload={"trigger_source": trigger_source},
                           bus_type=EventType.OPERATIONS_WORKFLOW_STARTED)

        outcome = "running"
        last_signature: tuple | None = None
        waves = 0
        while True:
            waves += 1
            self._promote_due_retries(workflow_id)
            session = self._session_factory()
            try:
                tasks = WorkflowTaskRepository(session).list_for_workflow(
                    workflow_id)
                task_dicts = [{"step_key": t.step_key, "status": t.status,
                               "priority": t.priority,
                               "depends_on": t.depends_on or []}
                              for t in tasks]
            finally:
                session.close()
            if all(t["status"] in C.TERMINAL_TASK_STATES for t in task_dicts):
                outcome = "terminal"
                break
            ready = planner_mod.ready_steps(task_dicts)
            ready = [t for t in ready if self._task_due(workflow_id,
                                                        t["step_key"])]
            if not ready:
                if any(t["status"] in ("FAILED", "DEAD_LETTER")
                       for t in task_dicts):
                    # A terminal failure strands its dependents: they
                    # can never become ready. Skip them so the
                    # workflow can settle as FAILED (§5 failure path).
                    self._skip_stranded(workflow_id)
                    outcome = "terminal"
                    break
                outcome = self._blocked_outcome(workflow_id)
                break
            settings = self.get_settings()
            limit = max(1, int(settings["max_concurrent_tasks_global"]))
            wave = ready[:limit]
            results = await asyncio.gather(*[
                self._run_step(workflow_id, t["step_key"], principal)
                for t in wave], return_exceptions=True)
            for step, res in zip(wave, results):
                if isinstance(res, Exception):
                    self._audit(principal, "operations.drive_step_error",
                                "workflow", workflow_id, "deny",
                                f"step pipeline raised: {res}")
                    # A pipeline exception must never stall the
                    # workflow silently: the step fails through the
                    # normal recovery path (retry/dead-letter rules
                    # apply) with the exception on record.
                    try:
                        session = self._session_factory()
                        try:
                            row = WorkflowTaskRepository(
                                session).get_by_step(workflow_id,
                                                     step["step_key"])
                            fresh = self.task_view(row) if row else None
                        finally:
                            session.close()
                        if fresh and fresh["status"] not in (
                                "COMPLETED", "FAILED", "DEAD_LETTER",
                                "CANCELLED", "SKIPPED"):
                            self._fail_task(
                                workflow_id, fresh, "system_error",
                                {"code": type(res).__name__,
                                 "message": str(res)}, principal)
                    except Exception:
                        pass
            self._save_checkpoint(workflow_id, execution_id)
            if "paused" in results:
                outcome = "paused"
                break
            if "approval" in results:
                outcome = "approval"
                break
            # No-progress guard: if a full wave changed no task state
            # (e.g. a step pipeline keeps raising), stop driving —
            # an engine must never spin against its own substrates.
            session = self._session_factory()
            try:
                signature = tuple(sorted(
                    (t.step_key, t.status) for t in
                    WorkflowTaskRepository(session).list_for_workflow(
                        workflow_id)))
            finally:
                session.close()
            if signature == last_signature or waves > 500:
                outcome = self._blocked_outcome(workflow_id)
                break
            last_signature = signature

        return self._settle_workflow(workflow_id, principal, execution_id,
                                     outcome)

    def _promote_due_retries(self, workflow_id: str) -> None:
        """RECOVERY_PENDING tasks whose backoff has elapsed become
        READY again — with authorization re-checked by the pipeline
        on the new attempt (§13: retries are new pipeline passes)."""
        session = self._session_factory()
        try:
            repo = WorkflowTaskRepository(session)
            for task in repo.list_for_workflow(workflow_id):
                if task.status != "RECOVERY_PENDING":
                    continue
                due = task.next_attempt_at
                if due is not None and due.tzinfo is None:
                    due = due.replace(tzinfo=dt.timezone.utc)
                if due is None or due <= utcnow():
                    self._transition_task(session, task, "READY")
                    repo.save(task)
        finally:
            session.close()

    def _skip_stranded(self, workflow_id: str) -> None:
        session = self._session_factory()
        try:
            repo = WorkflowTaskRepository(session)
            for task in repo.list_for_workflow(workflow_id):
                if task.status in ("PENDING", "READY", "BLOCKED"):
                    self._transition_task(session, task, "SKIPPED")
                    task.error = {"code": "dependency_failed",
                                  "message": "a dependency failed; "
                                             "step skipped"}
                    repo.save(task)
        finally:
            session.close()

    def _task_due(self, workflow_id: str, step_key: str) -> bool:
        session = self._session_factory()
        try:
            task = WorkflowTaskRepository(session).get_by_step(
                workflow_id, step_key)
            if task is None:
                return False
            if (task.error or {}).get("code") == "deferred":
                return True  # explicit drives re-check deferrals
            if task.next_attempt_at is not None:
                due = task.next_attempt_at
                if due.tzinfo is None:
                    due = due.replace(tzinfo=dt.timezone.utc)
                return due <= utcnow()
            return True
        finally:
            session.close()

    def _blocked_outcome(self, workflow_id: str) -> str:
        session = self._session_factory()
        try:
            tasks = WorkflowTaskRepository(session).list_for_workflow(
                workflow_id)
            statuses = {t.status for t in tasks}
        finally:
            session.close()
        if "WAITING_FOR_APPROVAL" in statuses:
            return "approval"
        if "RECOVERY_PENDING" in statuses:
            return "recovery"
        if "BLOCKED" in statuses:
            return "blocked"
        return "running"

    def _settle_workflow(self, workflow_id: str, principal: Principal,
                         execution_id: str, outcome: str) -> dict:
        session = self._session_factory()
        try:
            row = self._get_workflow(session, workflow_id)
            tasks = WorkflowTaskRepository(session).list_for_workflow(
                workflow_id)
            statuses = {t.status for t in tasks}
            execution = WorkflowExecutionRepository(session).get(execution_id)
            if all(t.status in C.TERMINAL_TASK_STATES for t in tasks):
                failed = [t for t in tasks
                          if t.status in ("FAILED", "DEAD_LETTER")]
                if failed:
                    self._transition_workflow(session, row, "FAILED")
                    row.failure_reason = (
                        "steps failed: "
                        + ", ".join(t.step_key for t in failed))
                    row.verified_outcome = "failed"
                    execution.status = "failed"
                else:
                    # §22: completion requires the VERIFYING pass —
                    # every completed step independently verified.
                    self._transition_workflow(session, row, "VERIFYING")
                    unverified = [t for t in tasks
                                  if t.status == "COMPLETED"
                                  and t.verification_status != "verified"]
                    if unverified:
                        self._transition_workflow(session, row, "FAILED")
                        row.failure_reason = (
                            "verification incomplete for: "
                            + ", ".join(t.step_key for t in unverified))
                        row.verified_outcome = "unverified"
                        execution.status = "failed"
                    else:
                        self._transition_workflow(session, row, "COMPLETED")
                        row.verified_outcome = "verified"
                        execution.status = "completed"
                row.completed_at = utcnow()
            elif outcome == "approval":
                self._transition_workflow(session, row, "WAITING_FOR_APPROVAL")
                execution.status = "waiting_for_approval"
            elif outcome == "paused":
                if row.status == "RUNNING":
                    self._transition_workflow(session, row, "PAUSED")
                execution.status = "paused"
            elif outcome == "recovery":
                self._transition_workflow(session, row, "RECOVERY_PENDING")
                execution.status = "recovery_pending"
            elif outcome == "blocked":
                self._transition_workflow(session, row, "BLOCKED")
                execution.status = "blocked"
            else:
                execution.status = "running"
            execution.finished_at = utcnow()
            WorkflowExecutionRepository(session).save(execution)
            WorkflowRepository(session).save(row)
            final_status = row.status
            session.expunge(row)
            view = self.workflow_view(row)
        finally:
            session.close()
        if final_status == "COMPLETED":
            self._record_event(
                workflow_id, "workflow.completed", actor=_actor(principal),
                bus_type=EventType.OPERATIONS_WORKFLOW_COMPLETED)
            view["learning_record_id"] = self._record_learning(
                principal, workflow_id)
        elif final_status == "FAILED":
            self._record_event(
                workflow_id, "workflow.failed", actor=_actor(principal),
                payload={"reason": view.get("failure_reason")},
                bus_type=EventType.OPERATIONS_WORKFLOW_FAILED,
                severity="error")
        return view

    def _save_checkpoint(self, workflow_id: str, execution_id: str) -> None:
        session = self._session_factory()
        try:
            tasks = WorkflowTaskRepository(session).list_for_workflow(
                workflow_id)
            completed = [{"step_key": t.step_key,
                          "idempotency_key": t.idempotency_key,
                          "substrate_ref": t.substrate_ref}
                         for t in tasks if t.status == "COMPLETED"]
            repo = WorkflowCheckpointRepository(session)
            row = repo.get_for_workflow(workflow_id)
            state = {"completed_steps": [c["step_key"] for c in completed],
                     "task_statuses": {t.step_key: t.status for t in tasks}}
            if row is None:
                repo.add(WorkflowCheckpoint(
                    workflow_id=workflow_id, execution_id=execution_id,
                    state=state, completed_steps=completed))
            else:
                row.execution_id = execution_id
                row.state = state
                row.completed_steps = completed
                repo.save(row)
        finally:
            session.close()

    # ------------------------------------------------------------ agent selection (§7)
    def select_agent(self, workflow: dict, task: dict,
                     *, exclude: set[str] | None = None) -> dict | None:
        """Capability- and business-scoped selection with recorded
        evidence. Candidates must: belong to the workflow's business
        (when it has one), hold every required capability, be active,
        and be under the per-agent concurrency cap. Ranking is
        deterministic: fewest running tasks, then best health, then
        agent id (stable)."""
        from ..database.models.core import Agent as AgentRow
        exclude = exclude or set()
        required = task.get("required_capabilities") or []
        business_id = workflow.get("business_id")
        settings = self.get_settings()
        session = self._session_factory()
        try:
            from sqlalchemy import select
            stmt = select(AgentRow).where(AgentRow.status == "active")
            candidates = list(session.scalars(stmt))
        finally:
            session.close()
        evaluated = []
        for agent in candidates:
            reasons = []
            if agent.id in exclude:
                reasons.append("excluded (previous assignee failed)")
            if business_id is not None and agent.business_ref != business_id:
                reasons.append("different business scope")
            granted = set(self._agents.capabilities
                          .granted_capability_names(agent.id))
            missing = [c for c in required if c not in granted]
            if missing:
                reasons.append(f"missing capabilities: {missing}")
            running = self._running_tasks_for_agent(agent.id)
            if running >= int(settings["max_concurrent_tasks_per_agent"]):
                reasons.append("at concurrency limit")
            health = {}
            try:
                health = self._agents.latest_health(agent.id) or {}
            except Exception:
                health = {}
            evaluated.append({"agent_id": agent.id, "eligible": not reasons,
                              "reasons": reasons, "running": running,
                              "health": health.get("status", "unknown"),
                              "granted": sorted(granted)})
        eligible = [e for e in evaluated if e["eligible"]]
        if not eligible:
            return None
        eligible.sort(key=lambda e: (e["running"],
                                     0 if e["health"] in ("healthy", "ok")
                                     else 1, e["agent_id"]))
        chosen = eligible[0]
        return {"agent_id": chosen["agent_id"],
                "reason": ("capability match on "
                           f"{required or 'no specific capability'}; "
                           f"business scope ok; load {chosen['running']}; "
                           f"health {chosen['health']}"),
                "evidence": {"candidates": evaluated,
                             "required_capabilities": required,
                             "business_id": business_id}}

    def _running_tasks_for_agent(self, agent_id: str) -> int:
        session = self._session_factory()
        try:
            return WorkflowTaskRepository(session).count_running(
                agent_id=agent_id)
        finally:
            session.close()

    def _assign_task(self, workflow_id: str, task_id: str, agent_id: str,
                     selection: dict, *, previous: str | None = None) -> None:
        session = self._session_factory()
        try:
            repo = AssignmentRepository(session)
            active = repo.active_for_task(task_id)
            if active is not None:
                active.status = "released"
                repo.save(active)
            repo.add(OperationsAssignment(
                workflow_id=workflow_id, task_id=task_id,
                agent_id=agent_id, previous_agent_id=previous,
                selection_reason=selection.get("reason", ""),
                selection_evidence=selection.get("evidence", {}),
                status="assigned"))
            task = WorkflowTaskRepository(session).get(task_id)
            task.assigned_agent_id = agent_id
            WorkflowTaskRepository(session).save(task)
        finally:
            session.close()

    def reassign_task(self, principal: Principal, workflow_id: str,
                      task_id: str, agent_id: str) -> dict:
        """Owner reassignment (§7): recorded with a handoff package —
        completed work, verified outputs, remaining steps, known
        issues — so the receiving agent never restarts blindly."""
        session = self._session_factory()
        try:
            row = self._get_workflow(session, workflow_id)
            self._assert_business_access(principal, row.business_id)
            task = WorkflowTaskRepository(session).get(task_id)
            if task is None or task.workflow_id != workflow_id:
                raise NotFoundError("workflow task not found")
            previous = task.assigned_agent_id
            tasks = WorkflowTaskRepository(session).list_for_workflow(
                workflow_id)
            handoff = {
                "completed_steps": [t.step_key for t in tasks
                                    if t.status == "COMPLETED"],
                "verified_outputs": {t.step_key: t.result for t in tasks
                                     if t.status == "COMPLETED"
                                     and t.verification_status == "verified"},
                "remaining_steps": [t.step_key for t in tasks
                                    if t.status not in
                                    C.TERMINAL_TASK_STATES],
                "known_issues": [t.error for t in tasks if t.error],
                "transferred_by": _actor(principal),
            }
        finally:
            session.close()
        agent = self._agents.get_agent(agent_id)  # must exist
        if row.business_id is not None and agent.business_ref != row.business_id:
            raise PermissionDeniedError(
                "cannot assign an agent from a different business")
        self._assign_task(workflow_id, task_id, agent_id,
                          {"reason": "owner reassignment",
                           "evidence": {"handoff": handoff}},
                          previous=previous)
        session = self._session_factory()
        try:
            repo = AssignmentRepository(session)
            record = repo.active_for_task(task_id)
            if record is not None:
                record.handoff = handoff
                repo.save(record)
        finally:
            session.close()
        self._record_recovery(workflow_id, task_id, "agent_failure",
                              "reassign", 1, "succeeded",
                              {"from": previous, "to": agent_id})
        return self.get_workflow(principal, workflow_id)

    # ------------------------------------------------------------ the pipeline (§22)
    async def _run_step(self, workflow_id: str, step_key: str,
                        principal: Principal) -> str:
        """Execute ONE workflow step through the full §22 pipeline.
        Returns an outcome token for the drive loop."""
        session = self._session_factory()
        try:
            workflow = self._get_workflow(session, workflow_id)
            task = WorkflowTaskRepository(session).get_by_step(
                workflow_id, step_key)
            if task is None or task.status in C.TERMINAL_TASK_STATES:
                return "skipped"
            if task.status == "WAITING_FOR_APPROVAL":
                return "approval"
            wf = self.workflow_view(workflow)
            tk = self.task_view(task)
        finally:
            session.close()

        # -- assignment (§7) -------------------------------------------
        needs_agent = bool(tk["required_capabilities"]) \
            or tk["kind"] == "execution"
        if needs_agent and not tk["assigned_agent_id"]:
            selection = self.select_agent(wf, tk)
            if selection is None:
                self._record_decision(
                    principal, workflow_id=workflow_id, task_id=tk["id"],
                    business_id=wf["business_id"], category="DEFER",
                    subject=f"assign agent for {step_key}",
                    rationale="no eligible agent (capability/business/"
                              "capacity) is available",
                    evidence={}, policy_checks={}, authorization_result={})
                self._set_task_status(workflow_id, tk["id"], "BLOCKED",
                                      error={"code": "no_eligible_agent",
                                             "message": "no eligible agent available"})
                return "blocked"
            self._assign_task(workflow_id, tk["id"], selection["agent_id"],
                              selection)
            tk["assigned_agent_id"] = selection["agent_id"]
        agent_id = tk["assigned_agent_id"]
        if agent_id and wf["business_id"]:
            agent_business = self._agent_business(agent_id)
            if agent_business != wf["business_id"]:
                self._record_decision(
                    principal, workflow_id=workflow_id, task_id=tk["id"],
                    business_id=wf["business_id"], category="REJECT",
                    subject=f"isolation check for {step_key}",
                    rationale="assigned agent belongs to a different "
                              "business; cross-business execution denied",
                    evidence={"agent_business": agent_business},
                    policy_checks={}, authorization_result={})
                self._set_task_status(
                    workflow_id, tk["id"], "BLOCKED",
                    error={"code": "cross_business_agent",
                           "message": "agent scoped to another business"})
                return "blocked"
        if agent_id and needs_agent and not self._agent_available(agent_id):
            # §7/Scenario 6: an assignee that became unavailable mid-
            # workflow is replaced when a healthy eligible agent
            # exists — the workflow never continues blindly on a dead
            # assignee, and never silently drops the step either.
            selection = self.select_agent(wf, tk, exclude={agent_id})
            if selection is not None:
                self._assign_task(workflow_id, tk["id"],
                                  selection["agent_id"], selection,
                                  previous=agent_id)
                self._record_recovery(
                    workflow_id, tk["id"], "agent_failure", "reassign",
                    tk["attempts"], "succeeded",
                    {"from": agent_id, "to": selection["agent_id"],
                     "reason": "assignee unavailable"})
                agent_id = selection["agent_id"]
                tk["assigned_agent_id"] = agent_id

        acting = Principal(PrincipalType.AGENT, agent_id) if agent_id \
            else SYSTEM_PRINCIPAL

        # -- budget pre-check (§10): P-07 decides ----------------------
        spend = await self._spend_gate(wf, tk, acting, principal)
        if spend["outcome"] == "blocked":
            self._record_decision(
                principal, workflow_id=workflow_id, task_id=tk["id"],
                business_id=wf["business_id"], category="REJECT",
                subject=f"budget gate for {step_key}",
                rationale=spend["reason"], evidence=spend,
                policy_checks={"budget": "blocked"},
                authorization_result={})
            self._record_event(workflow_id, "workflow.budget_blocked",
                               task_id=tk["id"], payload=spend,
                               bus_type=EventType.OPERATIONS_BUDGET_BLOCKED,
                               severity="error")
            self._fail_task(workflow_id, tk, "budget_failure",
                            {"code": "budget_blocked",
                             "message": spend["reason"]}, principal)
            return "failed"
        if spend["outcome"] == "approval":
            self._record_decision(
                principal, workflow_id=workflow_id, task_id=tk["id"],
                business_id=wf["business_id"], category="REQUEST_APPROVAL",
                subject=f"spend approval for {step_key}",
                rationale=spend.get("reason", "spend held by P-07"),
                evidence=spend, policy_checks={"budget": "held"},
                authorization_result={}, approval_required=True)
            return "approval"  # task already parked by the gate

        # -- autonomy + decision (§4/§12) -------------------------------
        autonomy = self.resolve_autonomy(
            business_id=wf["business_id"], agent_id=agent_id,
            workflow_id=workflow_id,
            workflow_declared_level=wf["autonomy_level"],
            action_class=tk["action_class"],
            declared_by_owner=wf["created_by"].startswith("owner"))
        budget_ctx = {"status": spend["outcome"]}
        if spend.get("utilisation_pct") is not None:
            budget_ctx["utilisation_pct"] = spend["utilisation_pct"]
        ctx = {
            "security_mode": self._security.emergency.current_mode(),
            "financial_suspended":
                self._security.emergency.financial_suspended(),
            "step_is_financial": tk["action_class"].startswith("financial.")
            or bool(tk["budget_ref"].get("requires_spend")),
            "business_paused": bool(wf["business_id"])
            and self._survival.is_paused(wf["business_id"]),
            "conflict_with": self._conflict_ref(wf, workflow_id),
            "budget": budget_ctx,
            "inputs_complete": not tk["input_data"].get("missing_inputs"),
            "agent_required": needs_agent,
            "agent_available": True if not needs_agent else
            self._agent_available(agent_id),
            "agent_healthy": self._agent_healthy(agent_id) if agent_id
            else None,
            "overloaded": self._system_overloaded(),
            "autonomy": autonomy,
        }
        decision = decisions_mod.decide_step(ctx)
        # A held P-07 spend already produced REQUEST_APPROVAL handling
        # in the gate; the decision record below is the step's own.
        self._record_decision(
            principal, workflow_id=workflow_id, task_id=tk["id"],
            business_id=wf["business_id"], category=decision["category"],
            subject=f"execute step {step_key}",
            rationale=decision["rationale"],
            evidence={"autonomy": autonomy, "spend": spend},
            policy_checks=decision["policy_checks"],
            authorization_result={},
            approval_required=decision["approval_required"])
        category = decision["category"]
        if category == "REJECT":
            self._fail_task(workflow_id, tk, "policy_violation",
                            {"code": "decision_reject",
                             "message": decision["rationale"]}, principal)
            return "failed"
        if category == "PAUSE":
            return "paused"
        if category == "DEFER":
            self._defer_task(workflow_id, tk["id"], seconds=30)
            return "deferred"
        if category == "RESEARCH_MORE":
            self._set_task_status(
                workflow_id, tk["id"], "BLOCKED",
                error={"code": "missing_input",
                       "message": decision["rationale"]})
            return "blocked"
        if category in ("REQUEST_APPROVAL", "ESCALATE"):
            # An already-approved, hash-bound approval for this exact
            # step satisfies the requirement — the pipeline proceeds
            # to the broker, which re-verifies the binding itself.
            if not self._approved_link_for_task(workflow_id, tk["id"]):
                self._request_step_approval(wf, tk, acting, principal,
                                            decision["rationale"])
                return "approval"

        # -- authorization (§22 stage 4): the P-10 broker --------------
        approval_id = self._approved_link_for_task(workflow_id, tk["id"])
        broker_result = self._security.broker.authorize(
            acting, permission=C.ACTION_PERMISSIONS[tk["action_class"]],
            action=tk["action_class"],
            resource=f"workflow:{workflow_id}/task:{step_key}",
            business_ref=wf["business_id"], task_id=None,
            parameters=self._step_parameters(tk),
            approval_id=approval_id)
        if not broker_result.get("allowed"):
            failed_gates = {g.get("gate") for g in
                            broker_result.get("gates", [])
                            if not g.get("passed")}
            approval_curable = bool(failed_gates & {
                "capability_or_approval", "owner_approval"})
            if approval_curable and not approval_id:
                self._request_step_approval(
                    wf, tk, acting, principal,
                    broker_result.get("reason", "approval required"))
                return "approval"
            self._record_decision(
                principal, workflow_id=workflow_id, task_id=tk["id"],
                business_id=wf["business_id"], category="REJECT",
                subject=f"authorization for {step_key}",
                rationale=broker_result.get("reason", "denied by broker"),
                evidence={"broker": broker_result}, policy_checks={},
                authorization_result=broker_result)
            self._fail_task(workflow_id, tk, "permission_failure",
                            {"code": "broker_denied",
                             "message": broker_result.get("reason", "")},
                            principal)
            return "failed"
        if approval_id:
            self._consume_link(workflow_id, tk["id"])

        # -- execution (§22 stage 6): substrates only ------------------
        return await self._execute_step(wf, tk, acting, principal)

    def _step_parameters(self, tk: dict) -> dict:
        """The exact parameter set an approval binds to: substrate +
        input data. Reconstructed identically at verification time
        from the stored task row, so drift is impossible without
        changing the row (which changes the hash and fails closed)."""
        return {"substrate": tk["substrate"], "input_data": tk["input_data"],
                "action_class": tk["action_class"], "kind": tk["kind"]}

    def _conflict_ref(self, wf: dict, workflow_id: str) -> str | None:
        """§11 conflict rule: two workflows may not modify the same
        shared resource at once. A workflow declares its resource in
        execution_policy.resource_ref; if another workflow for the
        same business with the same ref is RUNNING/VERIFYING, the
        newcomer defers (the incumbent keeps precedence)."""
        resource = (wf["execution_policy"] or {}).get("resource_ref")
        if not resource or not wf["business_id"]:
            return None
        session = self._session_factory()
        try:
            rows, _ = WorkflowRepository(session).list(
                business_id=wf["business_id"], limit=200)
            for other in rows:
                if other.id == workflow_id:
                    continue
                if other.status not in ("RUNNING", "VERIFYING"):
                    continue
                if (other.execution_policy or {}).get("resource_ref") \
                        == resource:
                    return f"{resource} (workflow {other.id})"
            return None
        finally:
            session.close()

    def _agent_available(self, agent_id: str | None) -> bool:
        if not agent_id:
            return False
        try:
            agent = self._agents.get_agent(agent_id)
            return agent.status == "active"
        except Exception:
            return False

    def _agent_healthy(self, agent_id: str) -> bool | None:
        try:
            health = self._agents.latest_health(agent_id) or {}
        except Exception:
            return None
        status = health.get("status")
        if status is None:
            return None
        return status not in ("unhealthy", "critical", "failed")

    def _system_overloaded(self) -> bool:
        # Pressure is always measured honestly, but whether it may
        # DEFER work follows the same operational switch the rest of
        # the system honours (Settings.block_nonessential_on_
        # threshold — True in production, disabled in the test
        # harness so host load on a shared VM cannot gate tests;
        # mirrors app/agents/resources.py::blocking_enabled).
        settings = getattr(self._monitor, "settings", None) \
            if self._monitor is not None else None
        if settings is not None and not getattr(
                settings, "block_nonessential_on_threshold", True):
            return False
        if self._monitor is None:
            return False
        try:
            resources = self._monitor.resources() or {}
        except Exception:
            return False
        cpu = resources.get("cpu_percent") or 0
        mem = resources.get("memory_percent") or 0
        return cpu >= 95 or mem >= 95

    def _defer_task(self, workflow_id: str, task_id: str, *, seconds: int):
        session = self._session_factory()
        try:
            repo = WorkflowTaskRepository(session)
            task = repo.get(task_id)
            task.next_attempt_at = utcnow() + dt.timedelta(seconds=seconds)
            # Marked as deferred: an explicit drive re-checks the
            # condition immediately (the decision engine re-defers
            # if it still holds); the timestamp paces background
            # ticks.
            task.error = {"code": "deferred",
                          "message": "deferred by the decision engine"}
            repo.save(task)
        finally:
            session.close()

    def _set_task_status(self, workflow_id: str, task_id: str, status: str,
                         *, error: dict | None = None):
        session = self._session_factory()
        try:
            task = WorkflowTaskRepository(session).get(task_id)
            if task is not None and task.status != status:
                self._transition_task(session, task, status)
                if error is not None:
                    task.error = error
                WorkflowTaskRepository(session).save(task)
        finally:
            session.close()

    # ------------------------------------------------------------ budget gate (§10)
    async def _spend_gate(self, wf: dict, tk: dict, acting: Principal,
                          principal: Principal) -> dict:
        """All spend flows through P-07's BudgetService.request_spend
        — the only place a spend decision exists. P-12 stores the
        request id and outcome, never an amount column."""
        from ..financial.money import Money
        budget_ref = tk["budget_ref"] or {}
        budget_id = budget_ref.get("budget_id") or wf["budget_id"]
        outcome: dict = {"outcome": "none", "budget_id": budget_id}
        if budget_id:
            try:
                util = self._financial.budgets.budget_utilisation(budget_id)
                limit = util.get("limit_minor") or 0
                used = util.get("utilised_minor")
                if used is None:
                    used = util.get("used_minor") or 0
                if limit:
                    outcome["utilisation_pct"] = round(100 * used / limit, 2)
            except Exception:
                pass
        if not budget_ref.get("requires_spend"):
            return outcome
        if not wf["business_id"]:
            return {"outcome": "blocked", "budget_id": budget_id,
                    "reason": "spend step on a workflow with no business"}
        # Idempotency: a previously decided spend is never re-requested.
        prior = (tk.get("result") or {}).get("spend")
        if prior and prior.get("spend_request_id"):
            try:
                current = self._financial.budgets.get_request(
                    prior["spend_request_id"])
                if str(current["status"]).startswith("authorised"):
                    outcome.update({"outcome": "ok",
                                    "spend_request_id": current["id"],
                                    "spend_status": current["status"]})
                    return outcome
                if current["status"] == "held_for_owner":
                    outcome.update({"outcome": "approval",
                                    "spend_request_id": current["id"],
                                    "reason": "spend still held for owner"})
                    return outcome
            except Exception:
                pass
        amount_minor = tk["input_data"].get("spend_amount_minor")
        if not isinstance(amount_minor, int) or amount_minor <= 0:
            return {"outcome": "blocked", "budget_id": budget_id,
                    "reason": "spend step lacks a positive integer "
                              "spend_amount_minor in input_data"}
        currency = tk["input_data"].get("currency")
        if not currency and budget_id:
            try:
                currency = self._financial.budgets.get_budget(budget_id).currency
            except Exception:
                currency = None
        currency = currency or "INR"
        result = self._financial.budgets.request_spend(
            acting, wf["business_id"], {
                "amount": Money(amount_minor, currency),
                "kind": budget_ref.get("spend_kind", "expense"),
                "category": budget_ref.get("category", "operations"),
                "budget_id": budget_id,
                "purpose": f"workflow '{wf['name']}' step {tk['step_key']}",
                "agent_id": tk["assigned_agent_id"],
                "task_id": tk["id"]})
        status = result["status"]
        self._store_task_result(tk["id"], {"spend": {
            "spend_request_id": result["id"], "spend_status": status,
            "decision_reason": result.get("decision_reason")}})
        if status == "blocked_level3":
            return {"outcome": "blocked", "budget_id": budget_id,
                    "spend_request_id": result["id"],
                    "reason": result.get("decision_reason")
                    or "Level 3 spend structurally blocked by P-07"}
        if status == "held_for_owner":
            self._request_spend_approval(wf, tk, acting, result)
            return {"outcome": "approval", "budget_id": budget_id,
                    "spend_request_id": result["id"],
                    "reason": result.get("decision_reason")
                    or "held for owner by P-07"}
        outcome.update({"outcome": "ok", "spend_request_id": result["id"],
                        "spend_status": status})
        return outcome

    def _store_task_result(self, task_id: str, patch: dict) -> None:
        session = self._session_factory()
        try:
            task = WorkflowTaskRepository(session).get(task_id)
            merged = dict(task.result or {})
            merged.update(patch)
            task.result = merged
            WorkflowTaskRepository(session).save(task)
        finally:
            session.close()

    # ------------------------------------------------------------ approvals (§22 stage 5)
    def _request_step_approval(self, wf: dict, tk: dict, acting: Principal,
                               principal: Principal, reason: str) -> None:
        """Create (or reuse) the P-01 approval binding this exact step
        execution: action = the step's action class, resource = the
        workflow/task, parameters = the step parameters. The workflow
        parks; nothing executes until the owner decides and the
        binding verifies."""
        session = self._session_factory()
        try:
            repo = ApprovalLinkRepository(session)
            for link in repo.list_for_workflow(wf["id"]):
                if link.task_id == tk["id"] and link.purpose == "task_step" \
                        and link.status == "pending":
                    return  # already waiting on an identical request
        finally:
            session.close()
        from ..security.policy import classify_action
        risk = classify_action(tk["action_class"])
        approval = self._approvals.create(
            acting, action=tk["action_class"],
            resource=f"workflow:{wf['id']}/task:{tk['step_key']}",
            risk_classification=f"risk_{risk}",
            reason=f"P-12 step approval: {reason}",
            requested_permissions=[], parameters=self._step_parameters(tk),
            expires_at=utcnow() + dt.timedelta(hours=24))
        session = self._session_factory()
        try:
            ApprovalLinkRepository(session).add(OperationsApprovalLink(
                workflow_id=wf["id"], task_id=tk["id"],
                approval_id=approval.id, purpose="task_step",
                action=tk["action_class"],
                parameters_hash=approval.parameters_hash, status="pending"))
        finally:
            session.close()
        self._set_task_status(wf["id"], tk["id"], "WAITING_FOR_APPROVAL")
        self._record_event(wf["id"], "workflow.approval_required",
                           task_id=tk["id"], actor=_actor(principal),
                           payload={"approval_id": approval.id,
                                    "action": tk["action_class"]},
                           bus_type=EventType.OPERATIONS_APPROVAL_REQUIRED,
                           severity="warning")

    def _request_spend_approval(self, wf: dict, tk: dict,
                                acting: Principal, spend_result: dict) -> None:
        """The P-01 approval P-07's approve_spend will verify:
        action 'financial.spend_approve', resource = business,
        parameters = the exact spend identity."""
        session = self._session_factory()
        try:
            for link in ApprovalLinkRepository(session).list_for_workflow(
                    wf["id"]):
                if link.purpose == "spend" and link.status == "pending" \
                        and link.task_id == tk["id"]:
                    return
        finally:
            session.close()
        parameters = {"spending_request_id": spend_result["id"],
                      "amount_minor": spend_result["amount_minor"],
                      "currency": spend_result["currency"]}
        approval = self._approvals.create(
            acting, action="financial.spend_approve",
            resource=wf["business_id"], risk_classification="risk_2",
            reason="P-12 workflow spend held for owner by P-07: "
                   + (spend_result.get("decision_reason") or ""),
            requested_permissions=["request_financial_operations"],
            parameters=parameters,
            expires_at=utcnow() + dt.timedelta(hours=24))
        session = self._session_factory()
        try:
            ApprovalLinkRepository(session).add(OperationsApprovalLink(
                workflow_id=wf["id"], task_id=tk["id"],
                approval_id=approval.id, purpose="spend",
                action="financial.spend_approve",
                parameters_hash=approval.parameters_hash, status="pending"))
        finally:
            session.close()
        self._set_task_status(wf["id"], tk["id"], "WAITING_FOR_APPROVAL")
        self._record_event(wf["id"], "workflow.approval_required",
                           task_id=tk["id"],
                           payload={"approval_id": approval.id,
                                    "purpose": "spend",
                                    "spend_request_id": spend_result["id"]},
                           bus_type=EventType.OPERATIONS_APPROVAL_REQUIRED,
                           severity="warning")

    def _approved_link_for_task(self, workflow_id: str,
                                task_id: str) -> str | None:
        session = self._session_factory()
        try:
            for link in ApprovalLinkRepository(session).list_for_workflow(
                    workflow_id):
                if link.task_id == task_id and link.purpose == "task_step" \
                        and link.status == "approved":
                    return link.approval_id
            return None
        finally:
            session.close()

    def _consume_link(self, workflow_id: str, task_id: str) -> None:
        session = self._session_factory()
        try:
            repo = ApprovalLinkRepository(session)
            for link in repo.list_for_workflow(workflow_id):
                if link.task_id == task_id and link.status == "approved":
                    link.status = "consumed"
                    repo.save(link)
        finally:
            session.close()

    async def check_approvals(self, principal: Principal) -> dict:
        """Resolve pending approval links against the P-01 store.
        Approved task steps are released and their workflows driven;
        approved spends are completed through P-07's approve_spend
        (owner only — it enforces that itself); rejections and
        expiries fail the waiting step. Parameter drift fails closed:
        ApprovalService.verify_binding must pass before anything is
        released."""
        resolved: list[dict] = []
        drive_ids: set[str] = set()
        session = self._session_factory()
        try:
            links = ApprovalLinkRepository(session).pending()
            link_views = [(link.id, link.workflow_id, link.task_id,
                           link.approval_id, link.purpose, link.action)
                          for link in links]
        finally:
            session.close()
        for link_id, workflow_id, task_id, approval_id, purpose, action \
                in link_views:
            try:
                approval = self._approvals.get(approval_id)
            except NotFoundError:
                self._set_link_status(link_id, "cancelled")
                continue
            if approval.status == "pending":
                continue
            if approval.status in ("rejected", "expired", "cancelled"):
                self._set_link_status(link_id, approval.status)
                if task_id:
                    self._fail_task_by_id(
                        workflow_id, task_id,
                        "approval_timeout" if approval.status == "expired"
                        else "permission_failure",
                        {"code": f"approval_{approval.status}",
                         "message": f"approval {approval.status} by owner "
                                    "decision or expiry"}, principal)
                resolved.append({"link_id": link_id,
                                 "outcome": approval.status})
                continue
            # approved — verify the binding before releasing anything.
            session = self._session_factory()
            try:
                task = WorkflowTaskRepository(session).get(task_id) \
                    if task_id else None
                tk = self.task_view(task) if task else None
            finally:
                session.close()
            if purpose == "task_step" and tk is not None:
                ok = self._approvals.verify_binding(
                    approval, action,
                    f"workflow:{workflow_id}/task:{tk['step_key']}",
                    self._step_parameters(tk))
                if not ok:
                    self._set_link_status(link_id, "drift_rejected")
                    self._fail_task_by_id(
                        workflow_id, task_id, "policy_violation",
                        {"code": "approval_drift",
                         "message": "approval parameters no longer match "
                                    "the step; failing closed"}, principal)
                    resolved.append({"link_id": link_id,
                                     "outcome": "drift_rejected"})
                    continue
                self._set_link_status(link_id, "approved")
                self._set_task_status(workflow_id, task_id, "READY")
                drive_ids.add(workflow_id)
                resolved.append({"link_id": link_id, "outcome": "approved"})
            elif purpose == "execution":
                # P-05 verifies its own approval binding when the
                # request executes; P-12 only mirrors the outcome and
                # releases the step back into the pipeline.
                self._set_link_status(link_id, "consumed")
                if task_id:
                    self._set_task_status(workflow_id, task_id, "READY")
                drive_ids.add(workflow_id)
                resolved.append({"link_id": link_id,
                                 "outcome": "execution_approved"})
            elif purpose == "spend":
                spend_id = (approval.parameters or {}).get(
                    "spending_request_id")
                try:
                    self._financial.budgets.approve_spend(
                        principal, spend_id, approval_id)
                    self._set_link_status(link_id, "consumed")
                    if task_id:
                        self._set_task_status(workflow_id, task_id, "READY")
                    drive_ids.add(workflow_id)
                    resolved.append({"link_id": link_id,
                                     "outcome": "spend_approved"})
                except Exception as exc:
                    resolved.append({"link_id": link_id,
                                     "outcome": f"spend_approve_failed: {exc}"})
        for workflow_id in drive_ids:
            session = self._session_factory()
            try:
                row = WorkflowRepository(session).get(workflow_id)
                status = row.status if row else None
            finally:
                session.close()
            if status in ("WAITING_FOR_APPROVAL", "BLOCKED",
                          "RECOVERY_PENDING", "PAUSED"):
                await self.drive_workflow(workflow_id, principal,
                                          trigger_source="approval")
        return {"resolved": resolved, "driven": sorted(drive_ids)}

    def _set_link_status(self, link_id: str, status: str) -> None:
        session = self._session_factory()
        try:
            repo = ApprovalLinkRepository(session)
            link = repo.get(link_id)
            if link is not None:
                link.status = status
                repo.save(link)
        finally:
            session.close()

    # ------------------------------------------------------------ execution (§22 stage 6-7)
    async def _execute_step(self, wf: dict, tk: dict, acting: Principal,
                            principal: Principal) -> str:
        session = self._session_factory()
        try:
            task = WorkflowTaskRepository(session).get(tk["id"])
            self._transition_task(session, task, "RUNNING")
            task.attempts += 1
            task.started_at = utcnow()
            task.next_attempt_at = None
            WorkflowTaskRepository(session).save(task)
        finally:
            session.close()
        # The attempt has begun (RUNNING) before the breaker gate so
        # a breaker refusal travels the normal failure path.
        target = self._breaker_target(tk)
        breaker = self._breaker_for(target)
        if not breaker.allow():
            return self._fail_task(
                wf["id"], tk, "external_service_unavailable",
                {"code": "circuit_open",
                 "message": f"circuit breaker open for {target}"},
                principal)
        self._record_event(wf["id"], "workflow.task_started",
                           task_id=tk["id"],
                           bus_type=EventType.OPERATIONS_TASK_STARTED)

        substrate_status: str | None = None
        result: dict | None = None
        error: dict | None = None
        try:
            if tk["kind"] == "task_handler":
                substrate_status, result = await self._run_task_handler(
                    wf, tk, acting)
            elif tk["kind"] == "execution":
                substrate_status, result = await self._run_execution_tool(
                    wf, tk, acting)
            else:
                substrate_status, result = self._run_internal(wf, tk)
        except Exception as exc:  # substrate raised — classify below
            error = {"code": type(exc).__name__, "message": str(exc)}

        if substrate_status == "awaiting_approval":
            # P-05 parked its own request on its own P-01 approval.
            # Link it (reference only) and park the step with it.
            approval_id = (result or {}).get("approval_id")
            if approval_id:
                session = self._session_factory()
                try:
                    repo = ApprovalLinkRepository(session)
                    if not any(link.approval_id == approval_id
                               for link in repo.list_for_workflow(wf["id"])):
                        approval = self._approvals.get(approval_id)
                        repo.add(OperationsApprovalLink(
                            workflow_id=wf["id"], task_id=tk["id"],
                            approval_id=approval_id, purpose="execution",
                            action=approval.action,
                            parameters_hash=approval.parameters_hash,
                            status="pending"))
                finally:
                    session.close()
            self._set_task_status(wf["id"], tk["id"], "WAITING_FOR_APPROVAL")
            return "approval"

        if error is not None or substrate_status in ("failed", "cancelled",
                                                     "error"):
            transition = breaker.record_failure()
            if transition:
                self._record_recovery(wf["id"], tk["id"],
                                      "external_service_unavailable",
                                      "circuit_breaker", tk["attempts"],
                                      "breaker_opened", {"target": target})
            category = recovery_mod.classify_failure(
                error=error or (result or {}).get("error"),
                substrate_status=substrate_status)
            return self._fail_task(wf["id"], tk, category,
                                   error or {"code": "substrate_failed",
                                             "message": f"substrate status "
                                                        f"{substrate_status}"},
                                   principal)
        breaker.record_success()

        # Independent verification — the executor's claim is checked,
        # never trusted (§22 stage 7, Scenario 12).
        self._set_task_status(wf["id"], tk["id"], "VERIFYING")
        verdict = verification_mod.evaluate(
            tk["acceptance_criteria"], substrate_status=substrate_status,
            result=result)
        session = self._session_factory()
        try:
            task = WorkflowTaskRepository(session).get(tk["id"])
            task.result = {**(task.result or {}), "output": result}
            task.verification_status = verdict["status"]
            task.verification_detail = verdict
            task.error = None  # clear any defer/failure marker
            task.completed_at = utcnow()
            if verdict["status"] == "verified":
                self._transition_task(session, task, "COMPLETED")
            WorkflowTaskRepository(session).save(task)
            task_status = task.status
        finally:
            session.close()
        if verdict["status"] == "verified":
            self._record_event(wf["id"], "workflow.task_completed",
                               task_id=tk["id"],
                               bus_type=EventType.OPERATIONS_TASK_COMPLETED)
            return "completed"
        return self._fail_task(
            wf["id"], tk, "invalid_output",
            {"code": "verification_failed",
             "message": verdict["reason"],
             "verification": verdict}, principal)

    def _breaker_target(self, tk: dict) -> str:
        if tk["kind"] == "task_handler":
            return f"handler:{tk['substrate'].get('handler')}"
        if tk["kind"] == "execution":
            return f"tool:{tk['substrate'].get('tool')}"
        return f"runner:{tk['substrate'].get('runner')}"

    def _breaker_for(self, target: str) -> recovery_mod.CircuitBreaker:
        if target not in self._breakers:
            settings = self.get_settings()
            self._breakers[target] = recovery_mod.CircuitBreaker(
                target,
                threshold=int(settings["circuit_breaker_threshold"]),
                cooldown_seconds=float(
                    settings["circuit_breaker_cooldown_seconds"]))
        return self._breakers[target]

    async def _run_task_handler(self, wf: dict, tk: dict,
                                acting: Principal) -> tuple[str, dict]:
        """Dispatch into the P-01 queue. The task idempotency key
        makes a resumed workflow reuse the original P-01 task instead
        of executing twice (Scenario 9)."""
        submitted = await self._tasks.submit(
            acting, name=f"P-12 {wf['name']}: {tk['step_key']}",
            handler_name=tk["substrate"]["handler"],
            payload=tk["substrate"].get("payload") or {},
            category="operations",
            priority=max(1, min(10, tk["priority"])),
            assigned_agent_id=tk["assigned_agent_id"],
            idempotency_key=tk["idempotency_key"],
            correlation_id=wf["id"])
        self._store_substrate_ref(tk["id"], submitted.id)
        deadline = utcnow() + dt.timedelta(seconds=120)
        while utcnow() < deadline:
            row = self._tasks.get(submitted.id)
            if row.status in ("completed", "failed", "cancelled"):
                result = dict(row.result or {})
                if row.status != "completed" and row.error:
                    result = {**result, "error": row.error}
                return row.status, result
            await asyncio.sleep(0.05)
        return "failed", {"error": {"code": "timeout",
                                    "message": "task did not settle "
                                               "within 120s"}}

    async def _run_execution_tool(self, wf: dict, tk: dict,
                                  acting: Principal) -> tuple[str, dict]:
        """Dispatch into P-05 (its own policy/approval/verification
        stack applies unchanged). If P-05 parks the request at
        AWAITING_APPROVAL, the step parks with it — linked to P-05's
        own P-01 approval — and resumes through P-05's execute once
        that approval lands."""
        from ..execution.schemas import ExecutionRequestIn
        parameters = dict(tk["substrate"].get("parameters") or {})
        if tk["substrate"]["tool"] in ("filesystem", "documents") \
                and "workspace" not in parameters:
            # P-05's adapters operate inside managed workspaces; the
            # acting agent's own workspace is the default scope.
            parameters["workspace"] = \
                f"agent:{tk['assigned_agent_id']}"
        payload = ExecutionRequestIn(
            agent_id=tk["assigned_agent_id"],
            tool=tk["substrate"]["tool"], action=tk["substrate"]["action"],
            parameters=parameters,
            business_ref=wf["business_id"],
            idempotency_key=tk["idempotency_key"],
            expected_outcome=tk["expected_output"] or {})
        request = self._execution.submit(acting, payload)
        self._store_substrate_ref(tk["id"], request.id)
        try:
            self._execution.link_workflow(request.id, wf["id"], tk["id"])
        except Exception:
            pass
        if request.status == "AWAITING_APPROVAL":
            approval_id = request.approval_id
            if approval_id:
                try:
                    approval = self._approvals.get(approval_id)
                except Exception:
                    approval = None
                if approval is not None and approval.status == "approved":
                    request = await self._execution.execute(acting,
                                                            request.id)
                else:
                    return "awaiting_approval", {
                        "approval_id": approval_id,
                        "execution_request_id": request.id}
        elif request.status == "QUEUED":
            request = await self._execution.execute(acting, request.id)
        result = request.verified_outcome or request.executed_action or {}
        return str(request.status).lower(), result

    def _run_internal(self, wf: dict, tk: dict) -> tuple[str, dict]:
        """Deterministic internal runners over real workflow data."""
        runner = tk["substrate"].get("runner")
        session = self._session_factory()
        try:
            tasks = WorkflowTaskRepository(session).list_for_workflow(wf["id"])
            deps = {t.step_key: (t.result or {}) for t in tasks
                    if t.step_key in (tk["depends_on"] or [])
                    and t.status == "COMPLETED"}
        finally:
            session.close()
        if runner == "summarize_inputs":
            parts = [f"{k}: {json.dumps(v, default=str)[:400]}"
                     for k, v in sorted(deps.items())]
            return "completed", {
                "summary": " | ".join(parts) or "no completed inputs",
                "inputs": len(deps),
                "source_steps": sorted(deps)}
        if runner == "record_note":
            note = tk["input_data"].get("note") or tk["objective"] \
                or "maintenance note recorded"
            return "completed", {"note": note, "recorded_at": _iso(utcnow())}
        if runner == "compose_report":
            report = self._generate_report(
                SYSTEM_PRINCIPAL, "business" if wf["business_id"] else "daily",
                business_id=wf["business_id"])
            return "completed", {"report": report["id"],
                                 "report_kind": report["kind"]}
        return "failed", {"error": f"unknown internal runner {runner}"}

    def _store_substrate_ref(self, task_id: str, ref: str) -> None:
        session = self._session_factory()
        try:
            task = WorkflowTaskRepository(session).get(task_id)
            task.substrate_ref = ref
            WorkflowTaskRepository(session).save(task)
        finally:
            session.close()

    # ------------------------------------------------------------ failure / recovery (§13)
    def _fail_task(self, workflow_id: str, tk: dict, category: str,
                   error: dict, principal: Principal) -> str:
        return self._fail_task_by_id(workflow_id, tk["id"], category,
                                     error, principal)

    def _fail_task_by_id(self, workflow_id: str, task_id: str,
                         category: str, error: dict,
                         principal: Principal) -> str:
        session = self._session_factory()
        try:
            task = WorkflowTaskRepository(session).get(task_id)
            if task is None or task.status in C.TERMINAL_TASK_STATES:
                return "skipped"
            tk = self.task_view(task)
        finally:
            session.close()
        settings = self.get_settings()
        max_retries = int((tk["retry_policy"] or {}).get(
            "max_retries", settings["default_max_retries"]))
        if category == "agent_failure":
            selection = self.select_agent(
                {"business_id": tk.get("business_id")}, tk,
                exclude={tk["assigned_agent_id"]} - {None}) \
                if tk["assigned_agent_id"] else None
            # select_agent needs the workflow business; fetch it.
            if selection is None and tk["assigned_agent_id"]:
                session = self._session_factory()
                try:
                    wf_row = WorkflowRepository(session).get(workflow_id)
                    business_id = wf_row.business_id if wf_row else None
                finally:
                    session.close()
                selection = self.select_agent(
                    {"business_id": business_id}, tk,
                    exclude={tk["assigned_agent_id"]})
            if selection is not None:
                self._assign_task(workflow_id, task_id,
                                  selection["agent_id"], selection,
                                  previous=tk["assigned_agent_id"])
                self._set_task_status(workflow_id, task_id, "READY")
                self._record_recovery(workflow_id, task_id, category,
                                      "reassign", tk["attempts"],
                                      "succeeded",
                                      {"to": selection["agent_id"]})
                return "reassigned"
        if recovery_mod.retry_eligible(category, tk["attempts"], max_retries):
            delay = recovery_mod.retry_delay(
                tk["attempts"], float(settings["retry_base_delay_seconds"]),
                float(settings["retry_max_delay_seconds"]))
            session = self._session_factory()
            try:
                task = WorkflowTaskRepository(session).get(task_id)
                if task.status != "RECOVERY_PENDING":
                    self._transition_task(session, task, "RECOVERY_PENDING")
                task.error = {**error, "failure_category": category}
                task.next_attempt_at = utcnow() + dt.timedelta(seconds=delay)
                WorkflowTaskRepository(session).save(task)
            finally:
                session.close()
            self._record_recovery(workflow_id, task_id, category, "retry",
                                  tk["attempts"], "scheduled",
                                  {"delay_seconds": round(delay, 3)})
            self._record_event(workflow_id, "workflow.recovery_attempted",
                               task_id=task_id,
                               payload={"category": category,
                                        "action": "retry"},
                               bus_type=EventType.OPERATIONS_RECOVERY_ATTEMPTED)
            return "recovery"
        if category in C.NON_RETRYABLE_CATEGORIES or \
                category in ("invalid_output", "approval_timeout",
                             "missing_input", "data_conflict"):
            self._set_task_status(workflow_id, task_id, "FAILED",
                                  error={**error,
                                         "failure_category": category})
            self._record_recovery(workflow_id, task_id, category,
                                  "escalate", tk["attempts"], "failed",
                                  {"terminal": "FAILED"})
            self._record_event(workflow_id, "workflow.task_failed",
                               task_id=task_id, payload={"category": category},
                               bus_type=EventType.OPERATIONS_TASK_FAILED,
                               severity="error")
            return "failed"
        # Retries exhausted or unknown failure: dead-letter with the
        # full context for owner investigation (§13).
        session = self._session_factory()
        try:
            task = WorkflowTaskRepository(session).get(task_id)
            if task.status in ("RUNNING", "VERIFYING"):
                self._transition_task(session, task, "RECOVERY_PENDING")
            if task.status != "DEAD_LETTER":
                self._transition_task(session, task, "DEAD_LETTER")
            task.error = {**error, "failure_category": category}
            WorkflowTaskRepository(session).save(task)
            if DeadLetterRepository(session).for_task(task_id) is None:
                DeadLetterRepository(session).add(OperationsDeadLetter(
                    workflow_id=workflow_id, task_id=task_id,
                    failure_category=category,
                    reason=str(error.get("message") or error),
                    context={"task": tk, "error": error,
                             "attempts": tk["attempts"]}))
        finally:
            session.close()
        self._record_recovery(workflow_id, task_id, category, "dead_letter",
                              tk["attempts"], "dead_lettered", {})
        self._record_event(workflow_id, "workflow.task_dead_lettered",
                           task_id=task_id, payload={"category": category},
                           bus_type=EventType.OPERATIONS_TASK_DEAD_LETTERED,
                           severity="error")
        return "dead_letter"

    def _record_recovery(self, workflow_id: str, task_id: str | None,
                         category: str, action: str, attempt: int,
                         outcome: str, detail: dict) -> None:
        session = self._session_factory()
        try:
            RecoveryRecordRepository(session).add(OperationsRecoveryRecord(
                workflow_id=workflow_id, task_id=task_id,
                failure_category=category, action=action, attempt=attempt,
                outcome=outcome, detail=detail or {}))
        finally:
            session.close()

    # ------------------------------------------------------------ learning (§17)
    def _record_learning(self, principal: Principal, workflow_id: str):
        """Only VERIFIED completions teach P-09. Confidence stays
        mechanically capped by P-09's own rules; P-12 proposes, P-09's
        LearningService disposes. A learning failure never fails the
        workflow. Returns the learning record id (or None)."""
        session = self._session_factory()
        try:
            row = self._get_workflow(session, workflow_id)
            if row.verified_outcome != "verified" \
                    or row.learning_record_id:
                return row.learning_record_id
            tasks = WorkflowTaskRepository(session).list_for_workflow(
                workflow_id)
            wf = self.workflow_view(row)
        finally:
            session.close()
        try:
            record = self._memory.learning.analyze(SYSTEM_PRINCIPAL, {
                "lesson": (f"Workflow '{wf['name']}' completed with all "
                           f"{len(tasks)} steps independently verified."),
                "expected_outcome": wf["objective"] or "workflow completion",
                "actual_outcome": "completed; every step verified",
                "source_type": "workflow",
                "source_ref": workflow_id,
                "business_id": wf["business_id"],
                "confidence": "MODERATE",
                "metrics": {"steps": len(tasks), "origin": wf["origin"]},
            })
            record_id = record.get("id") if isinstance(record, dict) \
                else getattr(record, "id", None)
        except Exception as exc:
            self._audit(principal, "operations.learning_failed", "workflow",
                        workflow_id, "deny",
                        f"P-09 learning record refused: {exc}")
            return None
        session = self._session_factory()
        try:
            row = WorkflowRepository(session).get(workflow_id)
            row.learning_record_id = record_id
            WorkflowRepository(session).save(row)
        finally:
            session.close()
        return record_id

    # ------------------------------------------------------------ triggers (§8)
    def create_trigger(self, principal: Principal, data: dict) -> dict:
        trigger_type = data.get("trigger_type")
        if trigger_type not in C.TRIGGER_TYPES:
            raise ValidationError(f"unknown trigger_type '{trigger_type}'")
        business_id = data.get("business_id")
        self._assert_business_access(principal, business_id)
        template = data.get("workflow_template") or {}
        if not isinstance(template, dict) or not template:
            raise ValidationError(
                "a trigger requires a workflow_template (the create "
                "payload used when it fires)")
        schedule = data.get("schedule") or {}
        next_fire = None
        if trigger_type == "time":
            scheduling_mod.validate_schedule(schedule)
            next_fire = scheduling_mod.next_fire(schedule, utcnow(), None)
        elif trigger_type == "event":
            if not data.get("event_type"):
                raise ValidationError("an event trigger requires event_type")
        elif trigger_type == "threshold":
            threshold = data.get("threshold") or {}
            if threshold.get("metric") not in (
                    "budget_utilisation_pct", "dead_letter_count",
                    "failed_workflows"):
                raise ValidationError(
                    "threshold metric must be one of "
                    "budget_utilisation_pct|dead_letter_count|failed_workflows")
            if threshold.get("comparator") not in ("gt", "gte", "lt",
                                                   "lte", "eq"):
                raise ValidationError("threshold comparator invalid")
        session = self._session_factory()
        try:
            row = TriggerRepository(session).add(OperationsTrigger(
                name=str(data.get("name") or "trigger")[:300],
                trigger_type=trigger_type, business_id=business_id,
                workflow_template=template, schedule=schedule,
                event_type=data.get("event_type"),
                threshold=data.get("threshold") or {},
                status="active", next_fire_at=next_fire,
                created_by_type=principal.type.value,
                created_by_id=principal.id))
            session.expunge(row)
            return self.trigger_view(row)
        finally:
            session.close()

    def trigger_view(self, row: OperationsTrigger) -> dict:
        return {"id": row.id, "name": row.name,
                "trigger_type": row.trigger_type,
                "business_id": row.business_id,
                "workflow_template": row.workflow_template or {},
                "schedule": row.schedule or {},
                "event_type": row.event_type,
                "threshold": row.threshold or {}, "status": row.status,
                "next_fire_at": _iso(row.next_fire_at),
                "last_fire_at": _iso(row.last_fire_at),
                "fire_count": row.fire_count,
                "missed_count": row.missed_count,
                "created_by": f"{row.created_by_type}:{row.created_by_id}"}

    def list_triggers(self, principal: Principal, *, status=None) -> dict:
        session = self._session_factory()
        try:
            rows, total = TriggerRepository(session).list(status=status)
            return {"items": [self.trigger_view(r) for r in rows],
                    "total": total}
        finally:
            session.close()

    def set_trigger_status(self, principal: Principal, trigger_id: str,
                           status: str) -> dict:
        if status not in ("active", "paused", "cancelled"):
            raise ValidationError(f"unknown trigger status '{status}'")
        session = self._session_factory()
        try:
            repo = TriggerRepository(session)
            row = repo.get(trigger_id)
            if row is None:
                raise NotFoundError(f"trigger {trigger_id} not found")
            self._assert_business_access(principal, row.business_id)
            row.status = status
            if status == "active" and row.trigger_type == "time":
                row.next_fire_at = scheduling_mod.next_fire(
                    row.schedule or {}, utcnow(), row.last_fire_at)
            repo.save(row)
            session.expunge(row)
            return self.trigger_view(row)
        finally:
            session.close()

    async def _fire_trigger(self, trigger_row: OperationsTrigger,
                            *, origin: str, fire_key: str | None) -> dict:
        """Instantiate the trigger's workflow. Owner/system triggers
        validate + drive; agent-proposed triggers create DRAFTs only
        (§8: agent proposals pass validation + authorization before
        anything executes — they never self-execute)."""
        template = dict(trigger_row.workflow_template or {})
        template.setdefault("business_id", trigger_row.business_id)
        template["origin"] = origin
        template["trigger_id"] = trigger_row.id
        if fire_key:
            template["idempotency_key"] = fire_key
        creator = Principal(
            PrincipalType(trigger_row.created_by_type)
            if trigger_row.created_by_type in ("owner", "agent", "service")
            else PrincipalType.SYSTEM, trigger_row.created_by_id)
        workflow = self.create_workflow(creator, template)
        if trigger_row.created_by_type == "agent":
            self._record_decision(
                creator, workflow_id=workflow["id"],
                business_id=workflow["business_id"], category="DEFER",
                subject="agent-proposed trigger fired",
                rationale="agent-proposed work is created as a draft "
                          "only; owner validation and the step pipeline "
                          "stand between proposal and execution",
                evidence={"trigger_id": trigger_row.id},
                policy_checks={}, authorization_result={})
            return {"workflow_id": workflow["id"], "driven": False}
        self.validate_workflow(creator, workflow["id"])
        view = await self.drive_workflow(workflow["id"], creator,
                                         trigger_source=f"trigger:{origin}")
        return {"workflow_id": workflow["id"], "driven": True,
                "status": view["status"]}

    def _subscribe_triggers(self) -> None:
        if self._bus is None:
            return

        async def _on_event(event: Event) -> None:
            # Operations' own events never retrigger (feedback guard);
            # domain events from other engines do.
            if event.source == "operations":
                return
            matches = []
            session = self._session_factory()
            try:
                rows, _ = TriggerRepository(session).list(status="active")
                matches = [r for r in rows
                           if r.trigger_type == "event"
                           and r.event_type == event.event_type.value]
                for row in matches:
                    session.expunge(row)
            finally:
                session.close()
            for row in matches:
                try:
                    await self._fire_trigger(
                        row, origin="event",
                        fire_key=f"event:{row.id}:{event.event_id}")
                    self._mark_fired(row.id, missed=0)
                except Exception:
                    pass

        self._bus.subscribe("*", _on_event)

    def _mark_fired(self, trigger_id: str, *, missed: int) -> None:
        session = self._session_factory()
        try:
            repo = TriggerRepository(session)
            row = repo.get(trigger_id)
            if row is None:
                return
            row.last_fire_at = utcnow()
            row.fire_count += 1
            row.missed_count += missed
            if row.trigger_type == "time":
                row.next_fire_at = scheduling_mod.next_fire(
                    row.schedule or {}, utcnow(), row.last_fire_at)
                if (row.schedule or {}).get("kind") == "once":
                    row.status = "cancelled"  # one-shot spent
            repo.save(row)
        finally:
            session.close()

    # ------------------------------------------------------------ scheduler loop
    async def tick(self) -> dict:
        """One scheduler pass: approval resolution, due triggers,
        threshold evaluation, scheduled starts, recovery resumes.
        Called by the background loop and directly by tests."""
        summary = {"approvals": None, "fired": [], "started": [],
                   "resumed": []}
        summary["approvals"] = await self.check_approvals(SYSTEM_PRINCIPAL)
        now = utcnow()
        session = self._session_factory()
        try:
            rows, _ = TriggerRepository(session).list(status="active")
            due = []
            for row in rows:
                session.expunge(row)
                if row.trigger_type == "time" and row.next_fire_at:
                    nxt = row.next_fire_at
                    if nxt.tzinfo is None:
                        nxt = nxt.replace(tzinfo=dt.timezone.utc)
                    if nxt <= now:
                        due.append(row)
                elif row.trigger_type == "threshold":
                    due.append(row)
        finally:
            session.close()
        for row in due:
            try:
                if row.trigger_type == "time":
                    instant, missed = scheduling_mod.pending_instant(
                        row.schedule or {}, now, row.last_fire_at,
                        row.next_fire_at)
                    if instant is None:
                        continue
                    key = scheduling_mod.fire_key(row.id, instant)
                    if row.last_fire_key == key:
                        continue
                    result = await self._fire_trigger(
                        row, origin="schedule", fire_key=key)
                    session = self._session_factory()
                    try:
                        fresh = TriggerRepository(session).get(row.id)
                        fresh.last_fire_key = key
                        TriggerRepository(session).save(fresh)
                    finally:
                        session.close()
                    self._mark_fired(row.id, missed=missed)
                    summary["fired"].append(
                        {"trigger_id": row.id, **result})
                else:
                    if await self._threshold_met(row):
                        result = await self._fire_trigger(
                            row, origin="threshold", fire_key=None)
                        self._mark_fired(row.id, missed=0)
                        summary["fired"].append(
                            {"trigger_id": row.id, **result})
            except Exception as exc:
                summary["fired"].append(
                    {"trigger_id": row.id, "error": str(exc)})
        # SCHEDULED workflows whose not_before has arrived.
        session = self._session_factory()
        try:
            rows, _ = WorkflowRepository(session).list(status="SCHEDULED",
                                                       limit=50)
            scheduled_ids = [r.id for r in rows
                             if _not_before(r.execution_policy) <= now]
            recovery_rows, _ = WorkflowRepository(session).list(
                status="RECOVERY_PENDING", limit=50)
            recovery_ids = [r.id for r in recovery_rows]
            # RUNNING workflows with deferred steps (e.g. a load
            # deferral whose pressure has since cleared) are re-driven
            # too — a deferral is a pause, not a stall.
            running_rows, _ = WorkflowRepository(session).list(
                status="RUNNING", limit=50)
            recovery_ids += [r.id for r in running_rows
                             if r.id not in recovery_ids]
        finally:
            session.close()
        for workflow_id in scheduled_ids:
            await self.drive_workflow(workflow_id, SYSTEM_PRINCIPAL,
                                      trigger_source="schedule")
            summary["started"].append(workflow_id)
        for workflow_id in recovery_ids:
            await self.drive_workflow(workflow_id, SYSTEM_PRINCIPAL,
                                      trigger_source="recovery")
            summary["resumed"].append(workflow_id)
        return summary

    async def _threshold_met(self, row: OperationsTrigger) -> bool:
        threshold = row.threshold or {}
        cooldown = float(threshold.get("cooldown_seconds", 3600))
        if row.last_fire_at is not None:
            last = row.last_fire_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=dt.timezone.utc)
            if (utcnow() - last).total_seconds() < cooldown:
                return False
        metric = threshold.get("metric")
        value: float | None = None
        if metric == "budget_utilisation_pct":
            budget_id = threshold.get("budget_id")
            if not budget_id:
                return False
            try:
                util = self._financial.budgets.budget_utilisation(budget_id)
                limit = util.get("limit_minor") or 0
                used = util.get("utilised_minor") or util.get("used_minor") or 0
                value = (100.0 * used / limit) if limit else 0.0
            except Exception:
                return False
        elif metric == "dead_letter_count":
            session = self._session_factory()
            try:
                _, total = DeadLetterRepository(session).list(status="open")
                value = float(total)
            finally:
                session.close()
        elif metric == "failed_workflows":
            session = self._session_factory()
            try:
                counts = WorkflowRepository(session).count_by_status()
                value = float(counts.get("FAILED", 0))
            finally:
                session.close()
        if value is None:
            return False
        target = float(threshold.get("value", 0))
        comparator = threshold.get("comparator", "gt")
        return {"gt": value > target, "gte": value >= target,
                "lt": value < target, "lte": value <= target,
                "eq": value == target}[comparator]

    async def start_loop(self) -> None:
        self._loop_task = asyncio.current_task()
        self._stopped.clear()
        interval = float(self.get_settings()["tick_interval_seconds"])
        while not self._stopped.is_set():
            try:
                await self.tick()
            except Exception:
                pass  # the loop must survive a bad pass; ticks are audited
            try:
                await asyncio.wait_for(self._stopped.wait(),
                                       timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def stop_loop(self) -> None:
        self._stopped.set()
        self._loop_task = None

    def recover_interrupted(self) -> int:
        """Startup recovery (§13): workflows left RUNNING/VERIFYING
        by a process death are moved to RECOVERY_PENDING — never
        blindly re-executed. Their completed steps are protected by
        checkpoints + substrate idempotency keys on resume."""
        session = self._session_factory()
        count = 0
        try:
            repo = WorkflowRepository(session)
            for status in ("RUNNING", "VERIFYING"):
                rows, _ = repo.list(status=status, limit=200)
                for row in rows:
                    self._transition_workflow(session, row,
                                              "RECOVERY_PENDING")
                    row.failure_reason = (
                        "interrupted by process restart; awaiting "
                        "checked resume")
                    repo.save(row)
                    count += 1
        finally:
            session.close()
        return count

    # ------------------------------------------------------------ emergency (§15)
    async def emergency_stop(self, principal: Principal, scope: str,
                             ref: str | None = None,
                             reason: str = "") -> dict:
        """Scoped stops composed over the existing machinery: P-10
        modes for global/financial, P-08 pause for a business, P-04
        stop for agents, P-05 stop for external execution, and P-12's
        own workflow pauses. P-12 builds no parallel emergency
        system."""
        if scope not in C.STOP_SCOPES:
            raise ValidationError(f"unknown stop scope '{scope}'")
        result: dict = {"scope": scope, "ref": ref, "actions": []}
        if scope == "global":
            self._security.emergency.set_mode(
                principal, "emergency_stop", reason or "P-12 global stop")
            result["actions"].append("p10_mode=emergency_stop")
            session = self._session_factory()
            try:
                rows, _ = WorkflowRepository(session).list(limit=200)
                targets = [r.id for r in rows
                           if r.status in ("RUNNING", "READY", "SCHEDULED",
                                           "VERIFYING", "RECOVERY_PENDING")]
            finally:
                session.close()
            for workflow_id in targets:
                try:
                    self.pause_workflow(principal, workflow_id)
                    result["actions"].append(f"paused:{workflow_id}")
                except Exception:
                    pass
        elif scope == "business":
            if not ref:
                raise ValidationError("a business stop requires ref=business_id")
            self._survival.pause_business(principal, ref,
                                          reason or "P-12 business stop")
            result["actions"].append("p08_business_paused")
            session = self._session_factory()
            try:
                rows, _ = WorkflowRepository(session).list(
                    business_id=ref, limit=200)
                targets = [r.id for r in rows
                           if r.status in ("RUNNING", "READY", "SCHEDULED",
                                           "VERIFYING", "RECOVERY_PENDING")]
            finally:
                session.close()
            for workflow_id in targets:
                try:
                    self.pause_workflow(principal, workflow_id)
                    result["actions"].append(f"paused:{workflow_id}")
                except Exception:
                    pass
        elif scope == "agent":
            if not ref:
                raise ValidationError("an agent stop requires ref=agent_id")
            await self._agents.emergency_stop(
                principal=principal, scope="agent", agent_id=ref,
                reason=reason or "P-12 agent stop")
            result["actions"].append("p04_agent_stopped")
        elif scope == "workflow":
            if not ref:
                raise ValidationError("a workflow stop requires ref=workflow_id")
            self.pause_workflow(principal, ref)
            result["actions"].append("workflow_paused")
        elif scope == "external":
            await self._execution.emergency_stop(principal)
            result["actions"].append("p05_execution_stopped")
        elif scope == "financial":
            self._security.emergency.set_financial_suspension(
                principal, True, reason or "P-12 financial stop")
            result["actions"].append("p10_financial_suspended")
        self._record_decision(
            principal, business_id=ref if scope == "business" else None,
            category="PAUSE", subject=f"emergency stop ({scope})",
            rationale=reason or f"{scope} emergency stop engaged",
            evidence=result, policy_checks={},
            authorization_result={"by": _actor(principal)})
        self._audit(principal, "operations.emergency_stop", "emergency",
                    f"{scope}:{ref}", "allow",
                    reason or f"{scope} stop", result)
        if self._bus is not None:
            self._bus.publish_sync_safe(Event(
                event_type=EventType.OPERATIONS_EMERGENCY_STOP,
                source="operations",
                payload={"scope": scope, "ref": ref}, severity="critical"))
        return result

    async def emergency_resume(self, principal: Principal, scope: str,
                               ref: str | None = None) -> dict:
        """Restart requires explicit owner authorization — enforced
        here AND by each underlying service. Resuming a scope lifts
        its stop; paused workflows are NOT auto-restarted (each is a
        deliberate owner resume after integrity revalidation)."""
        if principal.type != PrincipalType.OWNER:
            raise PermissionDeniedError(
                "restarting after an emergency stop requires explicit "
                "owner authorization")
        result: dict = {"scope": scope, "ref": ref, "actions": []}
        if scope == "global":
            self._security.emergency.set_mode(
                principal, "normal", "owner restart after P-12 stop")
            result["actions"].append("p10_mode=normal")
        elif scope == "business":
            self._survival.resume_business(principal, ref)
            result["actions"].append("p08_business_resumed")
        elif scope == "agent":
            result["actions"].append(
                "agent resumes are deliberate per-agent acts in P-04; "
                "no bulk resume performed")
        elif scope == "workflow":
            if not ref:
                raise ValidationError("a workflow resume requires ref")
            view = await self.resume_workflow(principal, ref)
            result["actions"].append(f"workflow_resumed:{view['status']}")
        elif scope == "external":
            self._execution.emergency_resume(principal)
            result["actions"].append("p05_execution_resumed")
        elif scope == "financial":
            self._security.emergency.set_financial_suspension(
                principal, False, "owner restart after P-12 stop")
            result["actions"].append("p10_financial_unsuspended")
        else:
            raise ValidationError(f"unknown resume scope '{scope}'")
        self._audit(principal, "operations.emergency_resume", "emergency",
                    f"{scope}:{ref}", "allow", "owner-authorized restart",
                    result)
        return result

    def safety_status(self, principal: Principal) -> dict:
        session = self._session_factory()
        try:
            counts = WorkflowRepository(session).count_by_status()
            _, dead_open = DeadLetterRepository(session).list(status="open")
            pending_links = len(ApprovalLinkRepository(session).pending())
        finally:
            session.close()
        return {
            "security_mode": self._security.emergency.current_mode(),
            "financial_suspended":
                self._security.emergency.financial_suspended(),
            "constitution_mode": self._settings.mode,
            "workflow_counts": counts,
            "paused_workflows": counts.get("PAUSED", 0),
            "open_dead_letters": dead_open,
            "pending_approvals": pending_links,
            "circuit_breakers": [b.view() for b in
                                 self._breakers.values()],
            "emergency_scopes": list(C.STOP_SCOPES),
            "restart_rule": "owner authorization required; workflows "
                            "resume individually after revalidation",
        }

    # ------------------------------------------------------------ observability (§18)
    def overview(self, principal: Principal) -> dict:
        session = self._session_factory()
        try:
            wf_counts = WorkflowRepository(session).count_by_status()
            task_counts = WorkflowTaskRepository(session).count_by_status()
            decision_counts = DecisionRepository(session).count_by_category()
            _, dead_open = DeadLetterRepository(session).list(status="open")
            pending_links = len(ApprovalLinkRepository(session).pending())
            triggers, _ = TriggerRepository(session).list(status="active")
            rows, _ = WorkflowRepository(session).list(limit=500)
            durations = [
                (r.completed_at - r.started_at).total_seconds()
                for r in rows
                if r.started_at and r.completed_at
                and r.status == "COMPLETED"]
            completed = wf_counts.get("COMPLETED", 0)
            failed = wf_counts.get("FAILED", 0)
        finally:
            session.close()
        terminal = completed + failed
        resources = None
        if self._monitor is not None:
            try:
                resources = self._monitor.resources()
            except Exception:
                resources = None
        settings = self.get_settings()
        return {
            "workflows": wf_counts,
            "tasks": task_counts,
            "completion_rate_pct": (round(100 * completed / terminal, 2)
                                    if terminal else None),
            "failure_rate_pct": (round(100 * failed / terminal, 2)
                                 if terminal else None),
            "avg_workflow_duration_seconds": (
                round(sum(durations) / len(durations), 2) if durations
                else None),
            "decisions": decision_counts,
            "pending_approvals": pending_links,
            "open_dead_letters": dead_open,
            "engine": {
                "running": self._loop_task is not None
                and not self._loop_task.done(),
                "tick_interval_seconds":
                    settings["tick_interval_seconds"],
            },
            "active_triggers": len(triggers),
            "resources": resources,
            "limits": {
                "max_concurrent_workflows":
                    settings["max_concurrent_workflows"],
                "max_concurrent_tasks_global":
                    settings["max_concurrent_tasks_global"],
                "max_concurrent_tasks_per_business":
                    settings["max_concurrent_tasks_per_business"],
                "max_concurrent_tasks_per_agent":
                    settings["max_concurrent_tasks_per_agent"],
                "low_resource_mode": settings["low_resource_mode"],
            },
            "gpu": "unavailable (target hardware is CPU-only; no GPU "
                   "telemetry exists in this system)",
            "autonomy_default_level": settings["default_autonomy_level"],
            "constitution_mode": self._settings.mode,
            "security_mode": self._security.emergency.current_mode(),
        }

    def business_operations(self, principal: Principal,
                            business_id: str) -> dict:
        self._assert_business_access(principal, business_id)
        business = self._business.get_business(business_id)
        session = self._session_factory()
        try:
            repo = WorkflowRepository(session)
            rows, total = repo.list(business_id=business_id, limit=200)
            by_status: dict[str, int] = {}
            for row in rows:
                by_status[row.status] = by_status.get(row.status, 0) + 1
            decisions = DecisionRepository(session).list(
                business_id=business_id, limit=20)
        finally:
            session.close()
        financial_summary = None
        try:
            financial_summary = self._financial.business_summary(business_id)
        except Exception:
            financial_summary = None
        return {
            "business_id": business_id,
            "business_status": business.get("status"),
            "paused": self._survival.is_paused(business_id),
            "workflows_total": total, "workflows_by_status": by_status,
            "recent_decisions": [
                {"id": d.id, "category": d.category,
                 "subject": d.subject, "created_at": _iso(d.created_at)}
                for d in decisions],
            "financial_summary": financial_summary,
            "financial_source": "P-07 (sole financial authority)",
        }

    def agent_operations(self, principal: Principal) -> dict:
        session = self._session_factory()
        try:
            assignments = session.query(OperationsAssignment).all()
            tasks = session.query(WorkflowTask).filter(
                WorkflowTask.assigned_agent_id.is_not(None)).all()
        finally:
            session.close()
        per_agent: dict[str, dict] = {}
        for task in tasks:
            entry = per_agent.setdefault(task.assigned_agent_id, {
                "agent_id": task.assigned_agent_id, "assigned_tasks": 0,
                "completed": 0, "failed": 0, "running": 0})
            entry["assigned_tasks"] += 1
            if task.status == "COMPLETED":
                entry["completed"] += 1
            elif task.status in ("FAILED", "DEAD_LETTER"):
                entry["failed"] += 1
            elif task.status in ("RUNNING", "VERIFYING"):
                entry["running"] += 1
        for entry in per_agent.values():
            decided = entry["completed"] + entry["failed"]
            entry["success_rate_pct"] = (
                round(100 * entry["completed"] / decided, 2) if decided
                else None)
            try:
                entry["health"] = (self._agents.latest_health(
                    entry["agent_id"]) or {}).get("status", "unknown")
            except Exception:
                entry["health"] = "unknown"
        return {"items": sorted(per_agent.values(),
                                key=lambda e: e["agent_id"]),
                "assignments_recorded": len(assignments)}

    def recovery_center(self, principal: Principal) -> dict:
        session = self._session_factory()
        try:
            dead, dead_total = DeadLetterRepository(session).list(limit=100)
            records = RecoveryRecordRepository(session).list(limit=100)
            checkpoints = session.query(WorkflowCheckpoint).count()
        finally:
            session.close()
        return {
            "dead_letters": [
                {"id": d.id, "workflow_id": d.workflow_id,
                 "task_id": d.task_id,
                 "failure_category": d.failure_category,
                 "reason": d.reason, "status": d.status,
                 "context": d.context or {},
                 "created_at": _iso(d.created_at)} for d in dead],
            "dead_letter_total": dead_total,
            "recovery_records": [
                {"id": r.id, "workflow_id": r.workflow_id,
                 "task_id": r.task_id,
                 "failure_category": r.failure_category,
                 "action": r.action, "attempt": r.attempt,
                 "outcome": r.outcome, "detail": r.detail or {},
                 "created_at": _iso(r.created_at)} for r in records],
            "circuit_breakers": [b.view() for b in
                                 self._breakers.values()],
            "checkpoints": checkpoints,
        }

    def resolve_dead_letter(self, principal: Principal, dead_id: str,
                            resolution: str) -> dict:
        if principal.type != PrincipalType.OWNER:
            raise PermissionDeniedError(
                "dead-letter resolution is an owner act")
        session = self._session_factory()
        try:
            repo = DeadLetterRepository(session)
            row = repo.get(dead_id)
            if row is None:
                raise NotFoundError("dead letter not found")
            row.status = "resolved"
            row.resolution = resolution
            repo.save(row)
            session.expunge(row)
            return {"id": row.id, "status": row.status,
                    "resolution": row.resolution}
        finally:
            session.close()

    def approvals_center(self, principal: Principal) -> dict:
        """P-12's view over the single P-01 approval store: links with
        their approval state. Decisions are made in the existing
        approval surfaces (P-01 API / P-11 Approval Center)."""
        session = self._session_factory()
        try:
            all_links = session.query(OperationsApprovalLink).order_by(
                OperationsApprovalLink.created_at.desc()).limit(100).all()
            links = [{"id": link.id, "workflow_id": link.workflow_id,
                      "task_id": link.task_id,
                      "approval_id": link.approval_id,
                      "purpose": link.purpose, "action": link.action,
                      "parameters_hash": link.parameters_hash,
                      "status": link.status} for link in all_links]
        finally:
            session.close()
        enriched = []
        for link in links:
            try:
                approval = self._approvals.get(link["approval_id"])
                link = {**link, "approval_status": approval.status,
                        "requested_by":
                            f"{approval.requesting_principal_type}:"
                            f"{approval.requesting_principal_id}",
                        "reason": approval.reason}
            except Exception:
                link = {**link, "approval_status": "unknown"}
            enriched.append(link)
        return {"items": enriched,
                "note": "Approvals live in the P-01 store; this view "
                        "links P-12 work to them. Decide approvals via "
                        "the approvals API or the Command Center inbox."}

    # ------------------------------------------------------------ reports (§19 I)
    def _generate_report(self, principal: Principal, kind: str,
                         *, business_id: str | None = None) -> dict:
        if kind not in C.REPORT_KINDS:
            raise ValidationError(f"unknown report kind '{kind}'")
        overview = self.overview(principal)
        payload: dict = {"kind": kind, "generated_from": "live records",
                         "overview": overview}
        if kind == "failure":
            payload["recovery"] = self.recovery_center(principal)
        elif kind == "resource":
            payload["breakers"] = [b.view() for b in self._breakers.values()]
        elif kind == "agent":
            payload["agents"] = self.agent_operations(principal)
        elif kind == "business":
            if business_id:
                payload["business"] = self.business_operations(
                    principal, business_id)
        session = self._session_factory()
        try:
            row = ReportRepository(session).add(OperationsReport(
                kind=kind, business_id=business_id, payload=payload,
                period_end=utcnow(), generated_by=_actor(principal)))
            session.expunge(row)
            return {"id": row.id, "kind": row.kind,
                    "business_id": row.business_id, "payload": row.payload,
                    "generated_by": row.generated_by,
                    "created_at": _iso(row.created_at)}
        finally:
            session.close()

    def generate_report(self, principal: Principal, kind: str,
                        *, business_id: str | None = None) -> dict:
        return self._generate_report(principal, kind,
                                     business_id=business_id)

    def list_reports(self, principal: Principal, *, kind=None) -> dict:
        session = self._session_factory()
        try:
            rows, total = ReportRepository(session).list(kind=kind)
            return {"items": [
                {"id": r.id, "kind": r.kind, "business_id": r.business_id,
                 "generated_by": r.generated_by,
                 "created_at": _iso(r.created_at)} for r in rows],
                "total": total}
        finally:
            session.close()

    def get_report(self, principal: Principal, report_id: str) -> dict:
        session = self._session_factory()
        try:
            row = ReportRepository(session).get(report_id)
            if row is None:
                raise NotFoundError("report not found")
            session.expunge(row)
            return {"id": row.id, "kind": row.kind,
                    "business_id": row.business_id, "payload": row.payload,
                    "generated_by": row.generated_by,
                    "created_at": _iso(row.created_at)}
        finally:
            session.close()

    def engine_status(self) -> dict:
        session = self._session_factory()
        try:
            counts = WorkflowRepository(session).count_by_status()
        finally:
            session.close()
        return {"engine": "p12-autonomous-operations",
                "workflow_counts": counts,
                "settings": self.get_settings(),
                "constitution_mode": self._settings.mode,
                "security_mode": self._security.emergency.current_mode(),
                "pipeline": "proposal -> validation -> policy -> broker "
                            "authorization -> approval (if required) -> "
                            "P-05/P-01 execution -> independent "
                            "verification -> audit",
                "llm": "no real LLM in staging; deterministic templates "
                       "(operations-template-v1) and P-02 plan import only"}


def _not_before(execution_policy: dict | None) -> dt.datetime:
    raw = (execution_policy or {}).get("not_before")
    if not raw:
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    parsed = _parse_dt(raw)
    return parsed or dt.datetime.min.replace(tzinfo=dt.timezone.utc)

def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_dt(value):
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed
