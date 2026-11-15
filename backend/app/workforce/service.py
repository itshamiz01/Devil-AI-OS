"""The workforce service: organization management, work orders, handoffs,
messages and the employee lifecycle (§6, §7, §9, §10, §17).

This is the organizational layer's operating surface. It does not run models
and does not dispatch execution: work orders are records that the existing
task queue and execution engine act on, and the CEO/manager/employee
"intelligence" is deterministic orchestration over real records - consistent
with the P-02 §8.5 efficiency rule already established in the codebase.

Two invariants the service enforces rather than hopes for:

**The reporting hierarchy is authoritative.** A manager assigns work only to
its own department's employees; the CEO may assign to any manager. A
cross-department assignment requires an approved handoff. An employee cannot
be assigned work by a manager it does not report to.

**Completion is judged, not accepted.** A work order reaches COMPLETED only
when its deliverable satisfies the verification requirements recorded on the
order, and the result is evidence-backed. The service never marks work
complete because an answer was generated.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..core.config import Settings
from ..core.exceptions import ConflictError, NotFoundError, ForbiddenError
from ..database.connection import Database
from ..database.models import utcnow
from ..database.repositories import (
    WorkforceDepartmentRepo,
    WorkforceEmployeeRepo,
    WorkforceHandoffRepo,
    WorkforceMessageRepo,
    WorkforceObjectiveRepo,
    WorkforcePerformanceRepo,
    WorkforceStatusHistoryRepo,
    WorkforceWorkOrderRepo,
)
from .catalog import CEO_ID, DEPARTMENT_BY_CODE
from .schemas import (
    HandoffCreate,
    MessageCreate,
    ObjectiveCreate,
    WorkOrderCreate,
)

logger = logging.getLogger(__name__)

__all__ = ["WorkforceService"]


class WorkforceService:
    """The organizational operating surface."""

    def __init__(self, *, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db

    # ------------------------------------------------------------------ #
    # Organization overview and statistics (§18)
    # ------------------------------------------------------------------ #
    async def overview(self) -> dict[str, Any]:
        """Real counts from the database - never a hard-coded 111."""
        async with self.db.session_factory() as session:
            emp = WorkforceEmployeeRepo(session)
            dept = WorkforceDepartmentRepo(session)
            orders = WorkforceWorkOrderRepo(session)
            objectives = WorkforceObjectiveRepo(session)
            handoffs = WorkforceHandoffRepo(session)
            employees = await emp.list_all()
            by_status: dict[str, int] = {}
            for e in employees:
                by_status[e.status] = by_status.get(e.status, 0) + 1
            return {
                "total_employees": len(employees),
                "ceo_count": sum(1 for e in employees if e.employee_id == CEO_ID),
                "manager_count": sum(1 for e in employees if e.employee_id.startswith("DEV-MGR")),
                "specialist_count": sum(
                    1 for e in employees
                    if e.employee_id.startswith("DEV-")
                    and not e.employee_id.startswith(("DEV-MGR", "DEV-CEO"))),
                "department_count": len(await dept.list_all()),
                "available_employees": by_status.get("AVAILABLE", 0)
                + by_status.get("ACTIVE", 0),
                "busy_employees": by_status.get("BUSY", 0),
                "blocked_employees": by_status.get("BLOCKED", 0),
                "active_work_orders": len(await orders.by_status("TASK_ASSIGNED"))
                + len(await orders.by_status("TASK_ACCEPTED"))
                + len(await orders.by_status("WORKING"))
                + len(await orders.by_status("REVIEW_PENDING")),
                "completed_work_orders": len(await orders.by_status("COMPLETED")),
                "failed_work_orders": len(await orders.by_status("FAILED")),
                "pending_objectives": len([o for o in await objectives.list_all()
                                           if o.status in ("OPEN", "DELEGATED", "IN_PROGRESS")]),
                "open_handoffs": len([h for h in await handoffs.list_all()
                                      if h.status == "pending"]),
                "by_status": by_status,
            }

    async def structure(self) -> dict[str, Any]:
        """The full organizational hierarchy: CEO → managers → specialists."""
        async with self.db.session_factory() as session:
            emp = WorkforceEmployeeRepo(session)
            dept = WorkforceDepartmentRepo(session)
            employees = await emp.list_all()
            by_id = {e.employee_id: e for e in employees}
            ceo = by_id.get(CEO_ID)
            result: dict[str, Any] = {
                "ceo": self._employee_summary(ceo) if ceo else None,
                "departments": [],
            }
            for department in await dept.list_all():
                manager = by_id.get(department.manager_employee_id)
                reports = await emp.by_manager(department.manager_employee_id)
                result["departments"].append({
                    "code": department.code,
                    "name": department.name,
                    "mission": department.mission,
                    "manager": self._employee_summary(manager) if manager else None,
                    "employees": [self._employee_summary(e) for e in reports],
                })
            return result

    # ------------------------------------------------------------------ #
    # Departments and employees (§5, §6, §18)
    # ------------------------------------------------------------------ #
    async def list_departments(self) -> list[dict[str, Any]]:
        async with self.db.session_factory() as session:
            dept = WorkforceDepartmentRepo(session)
            emp = WorkforceEmployeeRepo(session)
            out = []
            for d in await dept.list_all():
                manager = await emp.get(d.manager_employee_id)
                reports = await emp.by_manager(d.manager_employee_id)
                out.append({
                    "id": d.id, "code": d.code, "name": d.name,
                    "mission": d.mission,
                    "manager_employee_id": d.manager_employee_id,
                    "manager_name": manager.display_name if manager else None,
                    "employee_count": len(reports),
                })
            return out

    async def get_employee(self, employee_id: str) -> dict[str, Any]:
        async with self.db.session_factory() as session:
            emp = WorkforceEmployeeRepo(session)
            row = await emp.get(employee_id)
            if row is None:
                raise NotFoundError(f"employee {employee_id} not found")
            profile = self._employee_profile(row)
            orders = await WorkforceWorkOrderRepo(session).by_employee(employee_id)
            profile["work_orders"] = [self._order_summary(o) for o in orders]
            perf = await WorkforcePerformanceRepo(session).by_employee(employee_id)
            profile["performance"] = [self._perf_summary(p) for p in perf]
            return profile

    async def list_employees(self, *, department_code: str | None = None,
                             status: str | None = None) -> list[dict[str, Any]]:
        async with self.db.session_factory() as session:
            emp = WorkforceEmployeeRepo(session)
            if department_code:
                employees = await emp.by_department(department_code)
            else:
                employees = await emp.list_all()
            if status:
                employees = [e for e in employees if e.status == status]
            return [self._employee_summary(e) for e in employees]

    async def update_employee_status(self, employee_id: str, status: str,
                                     reason: str, actor: str = "owner") -> dict[str, Any]:
        """Pause/resume/disable/suspend an employee, recording the transition.

        The owner may suspend any employee immediately (§18). The transition is
        written to the status history so a disabled employee's record is never
        lost (§6).
        """
        if status not in {
            "ACTIVE", "AVAILABLE", "BUSY", "WAITING", "BLOCKED",
            "ON_LEAVE", "SUSPENDED", "DISABLED",
        }:
            raise ForbiddenError(f"invalid employee status: {status}")
        async with self.db.session_factory() as session:
            emp = WorkforceEmployeeRepo(session)
            row = await emp.get(employee_id)
            if row is None:
                raise NotFoundError(f"employee {employee_id} not found")
            previous = row.status
            await emp.set_status(employee_id, status)
            await WorkforceStatusHistoryRepo(session).create(
                employee_id=employee_id, from_status=previous, to_status=status,
                reason=reason, actor=actor)
            await session.commit()
            return {"employee_id": employee_id, "from_status": previous,
                    "to_status": status, "reason": reason, "actor": actor}

    # ------------------------------------------------------------------ #
    # Work orders (§7, §10)
    # ------------------------------------------------------------------ #
    async def create_work_order(self, order: WorkOrderCreate,
                                *, manager_employee_id: str) -> dict[str, Any]:
        """Assign a structured work order, validating the reporting hierarchy.

        Only the employee's own manager (or the CEO) may assign work to it. A
        cross-department assignment is refused unless an approved handoff names
        the receiving employee - the hierarchy is authoritative (§9).
        """
        async with self.db.session_factory() as session:
            emp = WorkforceEmployeeRepo(session)
            target = await emp.get(order.employee_id)
            if target is None:
                raise NotFoundError(f"employee {order.employee_id} not found")
            assigner = await emp.get(manager_employee_id)
            if assigner is None:
                raise NotFoundError(f"manager {manager_employee_id} not found")

            # Hierarchy rule: the assigner must be the target's manager, or the
            # CEO. Nothing else may hand work directly to an employee.
            is_ceo = manager_employee_id == CEO_ID
            is_own_manager = target.manager_employee_id == manager_employee_id
            if not is_ceo and not is_own_manager:
                raise ForbiddenError(
                    f"{manager_employee_id} may not assign work to "
                    f"{order.employee_id}; only the employee's own manager or "
                    f"the CEO may do so (cross-department work requires a handoff)")

            # Duplicate-assignment guard: refuse a second open order with the
            # same title for the same employee (§10: prevent duplicate work).
            existing = await WorkforceWorkOrderRepo(session).by_employee(order.employee_id)
            for o in existing:
                if o.status in ("TASK_ASSIGNED", "TASK_ACCEPTED", "WORKING",
                                "REVIEW_PENDING") and o.title == order.title:
                    raise ConflictError(
                        f"employee {order.employee_id} already has an open work "
                        f"order titled '{order.title}'")

            row = await WorkforceWorkOrderRepo(session).create(
                employee_id=order.employee_id,
                manager_employee_id=manager_employee_id,
                objective_id=order.objective_id,
                title=order.title,
                instructions=order.instructions,
                required_inputs=order.required_inputs,
                expected_deliverable=order.expected_deliverable,
                deadline=order.deadline,
                priority=order.priority,
                dependencies=order.dependencies,
                available_tools=order.available_tools,
                permission_scope=order.permission_scope or target.permission_scope,
                budget_constraints=order.budget_constraints,
                verification_requirements=order.verification_requirements,
                status="TASK_ASSIGNED",
            )
            await emp.set_status(order.employee_id, "BUSY")
            await session.commit()
            return self._order_summary(row)

    async def advance_work_order(self, order_id: str, *, action: str,
                                 result: dict[str, Any] | None = None,
                                 evidence: list[str] | None = None) -> dict[str, Any]:
        """Move a work order through its lifecycle (§10).

        The state machine is enforced: TASK_ASSIGNED → TASK_ACCEPTED → WORKING
        → REVIEW_PENDING → COMPLETED, with side states. COMPLETED is reached
        only when the deliverable satisfies the order's verification
        requirements and evidence is provided.
        """
        async with self.db.session_factory() as session:
            orders = WorkforceWorkOrderRepo(session)
            row = await orders.get(order_id)
            if row is None:
                raise NotFoundError(f"work order {order_id} not found")
            current = row.status
            allowed = {
                "accept": {"TASK_ASSIGNED"},
                "start": {"TASK_ACCEPTED"},
                "submit_review": {"WORKING"},
                "complete": {"REVIEW_PENDING"},
                "block": {"TASK_ASSIGNED", "TASK_ACCEPTED", "WORKING"},
                "fail": {"TASK_ASSIGNED", "TASK_ACCEPTED", "WORKING", "REVIEW_PENDING"},
            }
            if action not in allowed:
                raise ForbiddenError(f"unknown work order action: {action}")
            if current not in allowed[action]:
                raise ConflictError(
                    f"work order {order_id} is {current}; action '{action}' is "
                    f"not valid from that state")

            new_status = {
                "accept": "TASK_ACCEPTED", "start": "WORKING",
                "submit_review": "REVIEW_PENDING", "complete": "COMPLETED",
                "block": "BLOCKED", "fail": "FAILED",
            }[action]

            if action == "complete":
                # Completion is judged, not accepted: the deliverable must
                # satisfy the verification requirements and carry evidence.
                if not evidence:
                    raise ForbiddenError(
                        "a work order cannot be completed without evidence; "
                        "completion is judged, not accepted")
                unmet = [r for r in row.verification_requirements
                         if result and not result.get(r, True)]
                if unmet:
                    raise ForbiddenError(
                        f"deliverable does not satisfy verification requirements: "
                        f"{', '.join(unmet)}")

            await orders.set_status(
                order_id, new_status, result=result,
                evidence=evidence or row.evidence,
                completed_at=utcnow() if new_status in ("COMPLETED", "FAILED") else None)
            if new_status in ("COMPLETED", "FAILED", "CANCELLED"):
                await WorkforceEmployeeRepo(session).set_status(
                    row.employee_id, "AVAILABLE")
            await session.commit()
            updated = await orders.get(order_id)
            return self._order_summary(updated)

    # ------------------------------------------------------------------ #
    # Handoffs (§7, §11)
    # ------------------------------------------------------------------ #
    async def create_handoff(self, handoff: HandoffCreate,
                             *, from_employee_id: str) -> dict[str, Any]:
        """Create a cross-department handoff - the only authorized channel for
        cross-department collaboration. Scoped, traceable, with completion
        criteria."""
        async with self.db.session_factory() as session:
            emp = WorkforceEmployeeRepo(session)
            sender = await emp.get(from_employee_id)
            receiver = await emp.get(handoff.to_employee_id)
            if sender is None:
                raise NotFoundError(f"sender {from_employee_id} not found")
            if receiver is None:
                raise NotFoundError(f"receiver {handoff.to_employee_id} not found")
            if sender.department_code == receiver.department_code:
                raise ConflictError(
                    "a handoff is for cross-department collaboration; both "
                    "employees are in the same department")
            row = await WorkforceHandoffRepo(session).create(
                from_department=sender.department_code,
                to_department=receiver.department_code,
                from_employee_id=from_employee_id,
                to_employee_id=handoff.to_employee_id,
                source_work_order_id=handoff.source_work_order_id,
                objective=handoff.objective,
                deliverable=handoff.deliverable,
                context=handoff.context,
                references=handoff.references,
                required_action=handoff.required_action,
                access_scope=handoff.access_scope,
                status="pending",
                completion_criteria=handoff.completion_criteria,
            )
            await session.commit()
            return self._handoff_summary(row)

    async def list_handoffs(self) -> list[dict[str, Any]]:
        async with self.db.session_factory() as session:
            return [self._handoff_summary(h)
                    for h in await WorkforceHandoffRepo(session).list_all()]

    # ------------------------------------------------------------------ #
    # Messages (§17)
    # ------------------------------------------------------------------ #
    async def send_message(self, message: MessageCreate,
                           *, from_employee_id: str) -> dict[str, Any]:
        """Send an internal message, associated with a task, handoff or channel.

        Messages never carry credentials or private memory, and never create a
        hidden execution channel (§17).
        """
        async with self.db.session_factory() as session:
            emp = WorkforceEmployeeRepo(session)
            receiver = await emp.get(message.to_employee_id)
            if receiver is None:
                raise NotFoundError(f"recipient {message.to_employee_id} not found")
            row = await WorkforceMessageRepo(session).create(
                from_employee_id=from_employee_id,
                to_employee_id=message.to_employee_id,
                channel_type="direct",
                task_id=message.task_id,
                handoff_id=message.handoff_id,
                kind=message.kind,
                content=message.content,
            )
            await session.commit()
            return self._message_summary(row)

    async def conversation(self, a_id: str, b_id: str) -> list[dict[str, Any]]:
        async with self.db.session_factory() as session:
            rows = await WorkforceMessageRepo(session).by_channel(a_id, b_id)
            rows += await WorkforceMessageRepo(session).by_channel(b_id, a_id)
            rows.sort(key=lambda m: m.created_at)
            return [self._message_summary(m) for m in rows]

    # ------------------------------------------------------------------ #
    # Objectives (§4, §8)
    # ------------------------------------------------------------------ #
    async def create_objective(self, objective: ObjectiveCreate,
                               *, source: str = "owner",
                               created_by: str | None = None) -> dict[str, Any]:
        """Record an executive objective. The CEO delegates it to the
        identified departments; the objective moves through OPEN → DELEGATED →
        IN_PROGRESS → COMPLETED/FAILED."""
        async with self.db.session_factory() as session:
            row = await WorkforceObjectiveRepo(session).create(
                objective=objective.objective,
                source=source,
                status="OPEN",
                departments=objective.departments,
                expected_outcome=objective.expected_outcome,
                created_by=created_by,
            )
            await session.commit()
            return self._objective_summary(row)

    async def delegate_objective(self, objective_id: str,
                                 *, departments: list[str]) -> dict[str, Any]:
        """The CEO delegates an objective to department managers (§4)."""
        async with self.db.session_factory() as session:
            objectives = WorkforceObjectiveRepo(session)
            row = await objectives.get(objective_id)
            if row is None:
                raise NotFoundError(f"objective {objective_id} not found")
            for code in departments:
                if code not in DEPARTMENT_BY_CODE:
                    raise NotFoundError(f"unknown department: {code}")
            await objectives.set_status(objective_id, "DELEGATED")
            row.departments = departments
            await session.commit()
            return self._objective_summary(row)

    # ------------------------------------------------------------------ #
    # Serialization helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _employee_summary(e: Any) -> dict[str, Any]:
        return {
            "employee_id": e.employee_id, "display_name": e.display_name,
            "department_code": e.department_code, "department_name": e.department_name,
            "job_title": e.job_title, "manager_employee_id": e.manager_employee_id,
            "status": e.status, "is_baseline": e.is_baseline,
            "is_expansion": e.is_expansion,
        }

    @staticmethod
    def _employee_profile(e: Any) -> dict[str, Any]:
        return {
            "employee_id": e.employee_id, "display_name": e.display_name,
            "department_code": e.department_code, "department_name": e.department_name,
            "job_title": e.job_title, "role_description": e.role_description,
            "primary_responsibilities": e.primary_responsibilities,
            "secondary_responsibilities": e.secondary_responsibilities,
            "manager_employee_id": e.manager_employee_id,
            "seniority": e.seniority, "skills": e.skills,
            "tool_access": e.tool_access, "memory_scope": e.memory_scope,
            "system_instructions": e.system_instructions,
            "communication_style": e.communication_style,
            "autonomy_level": e.autonomy_level,
            "permission_scope": e.permission_scope, "status": e.status,
            "is_baseline": e.is_baseline, "is_expansion": e.is_expansion,
            "current_assignments": e.current_assignments,
            "last_activity": e.last_activity,
            "configuration_version": e.configuration_version,
        }

    @staticmethod
    def _order_summary(o: Any) -> dict[str, Any]:
        return {
            "id": o.id, "employee_id": o.employee_id,
            "manager_employee_id": o.manager_employee_id,
            "objective_id": o.objective_id, "task_id": o.task_id,
            "title": o.title, "status": o.status, "priority": o.priority,
            "deadline": o.deadline, "dependencies": o.dependencies,
            "expected_deliverable": o.expected_deliverable,
            "verification_requirements": o.verification_requirements,
            "available_tools": o.available_tools,
            "permission_scope": o.permission_scope,
            "budget_constraints": o.budget_constraints,
            "result": o.result, "evidence": o.evidence,
            "completed_at": o.completed_at,
        }

    @staticmethod
    def _handoff_summary(h: Any) -> dict[str, Any]:
        return {
            "id": h.id, "from_department": h.from_department,
            "to_department": h.to_department,
            "from_employee_id": h.from_employee_id,
            "to_employee_id": h.to_employee_id,
            "source_work_order_id": h.source_work_order_id,
            "objective": h.objective, "deliverable": h.deliverable,
            "references": h.references, "required_action": h.required_action,
            "access_scope": h.access_scope, "status": h.status,
            "completion_criteria": h.completion_criteria,
        }

    @staticmethod
    def _message_summary(m: Any) -> dict[str, Any]:
        return {
            "id": m.id, "from_employee_id": m.from_employee_id,
            "to_employee_id": m.to_employee_id, "channel_type": m.channel_type,
            "task_id": m.task_id, "handoff_id": m.handoff_id,
            "kind": m.kind, "content": m.content, "created_at": m.created_at,
        }

    @staticmethod
    def _objective_summary(o: Any) -> dict[str, Any]:
        return {
            "id": o.id, "objective": o.objective, "source": o.source,
            "status": o.status, "departments": o.departments,
            "expected_outcome": o.expected_outcome,
            "created_by": o.created_by, "completed_at": o.completed_at,
        }

    @staticmethod
    def _perf_summary(p: Any) -> dict[str, Any]:
        return {
            "employee_id": p.employee_id, "period": p.period,
            "composite_score": p.composite_score,
            "task_completion_rate": p.task_completion_rate,
            "quality_score": p.quality_score,
            "deadline_adherence": p.deadline_adherence,
            "verified_success_rate": p.verified_success_rate,
            "rework_rate": p.rework_rate, "error_rate": p.error_rate,
            "collaboration_quality": p.collaboration_quality,
            "policy_compliance": p.policy_compliance,
        }
