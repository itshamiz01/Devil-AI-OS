"""Workforce service: seed, profiles, orchestration, KPI read model.

Design rules (Master Prompt v1.0, non-negotiables §29):
- Employees ARE P-01 ``agents`` rows. No duplicate registry.
- Work orders ARE P-01 tasks (submitted with ``requires_approval=True``
  so they park in WAITING_FOR_APPROVAL and cannot auto-execute) plus a
  P-04 ``agent_assignments`` contract row. A task is released to the
  queue ONLY after the employee's manager accepts the deliverable —
  and the handler it then runs is the existing ``core.noop``: the task
  execution records the reviewed deliverable, it does not perform the
  employee's work. Completion is never fabricated: an assignment is
  'completed' only by a manager's recorded acceptance.
- Restricted work (publishing, payments, external sends, deletions…)
  is NEVER dispatched: it creates a P-01 Approval requested by the CEO
  agent and stays parked. ``ApprovalService.decide`` structurally
  requires the ``approve_actions`` authority, which agent principals
  (CEO and managers included) do not hold — the CEO cannot bypass it.
- KPI scores are computed from ``agent_metrics`` / assignment outcomes
  only. Components with no data are excluded and weights renormalized;
  employees with no verified outcomes report ``no_data``.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

from sqlalchemy import func, select

from ..core.exceptions import (
    InvalidStateTransitionError, NotFoundError, PermissionDeniedError,
    ValidationError,
)
from ..database.models.agents import AgentAssignment, AgentMetric
from ..database.models.base import utcnow
from ..database.models.core import Agent, AuditEvent
from ..database.models.memory import AgentHandoff
from ..database.models.workforce import (
    WorkforceDeliverable, WorkforceDepartment, WorkforceObjective,
    WorkforceProfile,
)
from ..permissions.models import Principal, PrincipalType
from .definition import CEO, DEPARTMENTS, KPI_WEIGHTS, employee_code, iter_employees

RESTRICTED_KEYWORDS = (
    "publish", "payment", "pay ", "transfer", "spend", "purchase", "buy ",
    "send email", "send an email", "email to", "post publicly", "delete",
    "destroy", "wire", "invoice customer", "charge", "refund", "withdraw",
    "trade execution", "place order",
)

WORKFORCE_STATUSES = {"ACTIVE", "AVAILABLE", "BUSY", "WAITING", "BLOCKED",
                      "ON_LEAVE", "SUSPENDED", "DISABLED"}


def _is_restricted(text: str) -> bool:
    low = f" {text.lower()} "
    return any(k in low for k in RESTRICTED_KEYWORDS)


def _instructions_for(level: str, title: str, dept_name: str | None,
                      manager_title: str | None, responsibilities: list[str],
                      tools: list[str]) -> str:
    """Role-specific system instructions generated from THIS employee's
    actual responsibilities (§6) — never one generic prompt ×111."""
    resp = "; ".join(responsibilities)
    if level == "ceo":
        head = ("You are DEV-CEO-001, Chief Executive Officer of the Devil "
                "AI OS workforce. You report to the human owner, who has "
                "final authority.")
    elif level == "manager":
        head = (f"You are the {title} of the {dept_name} department in the "
                "Devil AI OS workforce. You report to DEV-CEO-001.")
    else:
        head = (f"You are the {title} in the {dept_name} department of the "
                f"Devil AI OS workforce. You report to the {manager_title}.")
    return (
        f"{head} Your responsibilities: {resp}. "
        f"Approved tool scope (declaration only — a grant still requires "
        f"the P-04 factory path): {', '.join(tools) if tools else 'none'}. "
        "Accept work only through organizational work orders. Submit "
        "deliverables in the §10 standard (objective, work performed, "
        "result, evidence, limitations, verification status). Never "
        "modify your own permissions, never bypass P-10 policy or P-07 "
        "financial authority, never store credentials in memory, and "
        "escalate blockers and restricted actions to your manager.")


class WorkforceService:
    def __init__(self, session_factory, tasks, approvals, permissions,
                 security_mode_getter=None):
        self._session_factory = session_factory
        self._tasks = tasks
        self._approvals = approvals
        self._permissions = permissions
        # Callable returning the P-10 security mode; when it reports
        # 'emergency_stop', new work-order dispatch is refused (§21).
        self._security_mode_getter = security_mode_getter

    def _assert_not_emergency_stopped(self) -> None:
        if self._security_mode_getter is not None:
            try:
                mode = self._security_mode_getter()
            except Exception:
                mode = None  # unreadable mode: P-10 itself fails closed
            if mode == "emergency_stop":
                raise InvalidStateTransitionError(
                    "global emergency stop is active (P-10 mode="
                    "emergency_stop): new workforce work orders are "
                    "suspended until the owner resumes")

    # ------------------------------------------------------------ helpers
    def _audit(self, session, actor: Principal, action: str, target_type: str,
               target_id: str, decision: str = "allow", details: dict | None = None):
        session.add(AuditEvent(
            actor_type=actor.type.value, actor_id=actor.id, action=action,
            target_type=target_type, target_id=target_id, decision=decision,
            details=details or {}))
        session.commit()

    @staticmethod
    def _require_owner_or_system(principal: Principal, action: str) -> None:
        if principal.type not in (PrincipalType.OWNER, PrincipalType.SYSTEM):
            raise PermissionDeniedError(
                f"{action} requires the owner (or system) principal; "
                f"'{principal.type.value}' principals cannot perform it — "
                "in particular, no employee or manager may perform it for "
                "itself")

    def _profile_by_code(self, session, code: str) -> WorkforceProfile:
        row = session.scalar(
            select(WorkforceProfile).where(WorkforceProfile.employee_code == code))
        if row is None:
            raise NotFoundError(f"employee {code} not found")
        return row

    def _agent(self, session, agent_id: str) -> Agent:
        agent = session.get(Agent, agent_id)
        if agent is None:
            raise NotFoundError(f"agent {agent_id} not found")
        return agent

    # ---------------------------------------------------------------- seed
    def seed_workforce(self, actor: Principal) -> dict:
        """Idempotent: employees are keyed by the unique employee_code.
        Re-running creates ZERO new agents/profiles/departments."""
        self._require_owner_or_system(actor, "workforce.seed")
        session = self._session_factory()
        created = {"departments": 0, "agents": 0, "profiles": 0}
        try:
            existing_codes = set(session.scalars(
                select(WorkforceProfile.employee_code)).all())
            dept_rows: dict[str, WorkforceDepartment] = {}
            for i, dept in enumerate(DEPARTMENTS):
                row = session.scalar(select(WorkforceDepartment).where(
                    WorkforceDepartment.code == dept["code"]))
                if row is None:
                    row = WorkforceDepartment(
                        code=dept["code"], name=dept["name"],
                        mission=dept["mission"], sort_order=i + 1)
                    session.add(row)
                    session.commit()
                    created["departments"] += 1
                dept_rows[dept["code"]] = row

            def ensure_employee(code: str, level: str, title: str,
                                dept_row, parent_agent_id, role_desc: str,
                                primary: list, secondary: list, skills: list,
                                tools: list, seniority: str, autonomy: str,
                                style: str, manager_title: str | None = None) -> str:
                if code in existing_codes:
                    prof = session.scalar(select(WorkforceProfile).where(
                        WorkforceProfile.employee_code == code))
                    return prof.agent_id
                agent = Agent(
                    name=title, role=title, parent_agent_id=parent_agent_id,
                    objective=role_desc, status="active",
                    agent_type=f"workforce_{level}",
                    description=role_desc,
                    security_classification="internal",
                    created_by_type=actor.type.value, created_by_id=actor.id)
                session.add(agent)
                session.commit()
                created["agents"] += 1
                memory_scope = {
                    "identity": True, "role_instructions": True,
                    "department": dept_row.code if dept_row else "executive",
                    "business_context": "assigned_only",
                    "shared": "approved_handoffs_only",
                    "credentials": "never",
                }
                profile = WorkforceProfile(
                    agent_id=agent.id, employee_code=code, level=level,
                    department_id=dept_row.id if dept_row else None,
                    display_name=title, job_title=title,
                    role_description=role_desc,
                    primary_responsibilities=primary,
                    secondary_responsibilities=secondary,
                    seniority=seniority, skills=skills, tool_access=tools,
                    memory_scope=memory_scope,
                    system_instructions=_instructions_for(
                        level, title,
                        dept_row.name if dept_row else "Executive Office",
                        manager_title, primary, tools),
                    communication_style=style, autonomy_level=autonomy,
                    permission_scope={
                        "capability_declarations": tools,
                        "grants": "factory_governed_only",
                        "financial_execution": "none",
                        "self_permission_change": "prohibited",
                    },
                    workforce_status="ACTIVE" if level == "ceo" else "AVAILABLE",
                    kpi_weights=dict(KPI_WEIGHTS), config_version=1)
                session.add(profile)
                session.commit()
                created["profiles"] += 1
                existing_codes.add(code)
                return agent.id

            ceo_agent_id = ensure_employee(
                CEO["employee_code"], "ceo", CEO["job_title"], None, None,
                CEO["role_description"], CEO["primary_responsibilities"],
                CEO["secondary_responsibilities"], CEO["skills"],
                CEO["tool_access"], CEO["seniority"], CEO["autonomy_level"],
                CEO["communication_style"])

            for dept in DEPARTMENTS:
                dept_row = dept_rows[dept["code"]]
                mgr_agent_id = ensure_employee(
                    dept["manager_code"], "manager", dept["manager_title"],
                    dept_row, ceo_agent_id, dept["manager_duty"],
                    ["Create departmental execution plans",
                     "Break objectives into employee work orders",
                     "Assign tasks according to employee skills",
                     "Manage employee workload", "Monitor task progress",
                     "Review employee deliverables", "Verify work quality",
                     "Resolve departmental blockers",
                     "Coordinate with other managers", "Report to the CEO",
                     "Maintain departmental performance"],
                    ["Recommend process improvements",
                     "Recommend agent suspension for investigation"],
                    ["department leadership", "planning", "quality review"],
                    ["internal_reasoning", "internal_database_read",
                     "internal_database_write", "memory_read"],
                    "department_head", "supervised",
                    "Structured departmental reporting: status, completed, "
                    "active, delayed, failed, risks, recommendations.",
                    manager_title="Chief Executive Officer")
                if dept_row.manager_agent_id != mgr_agent_id:
                    dept_row.manager_agent_id = mgr_agent_id
                    session.add(dept_row)
                    session.commit()
                for dept_e, global_number, emp in iter_employees():
                    if dept_e["code"] != dept["code"]:
                        continue
                    title, responsibilities, skills, tools = emp
                    ensure_employee(
                        employee_code(dept, global_number), "employee", title,
                        dept_row, mgr_agent_id,
                        f"{title} in the {dept['name']} department. "
                        f"Department mission: {dept['mission']}",
                        responsibilities,
                        ["Report progress, blockers and evidence to the "
                         "manager through the work-order system",
                         "Collaborate cross-department only through "
                         "approved handoffs"],
                        skills, tools, "specialist", "supervised",
                        "Concise, evidence-linked deliverables in the §10 "
                        "output standard.",
                        manager_title=dept["manager_title"])
            self._audit(session, actor, "workforce.seed", "organization",
                        "devil-ai-os", details=created)
            total = session.scalar(select(func.count()).select_from(
                WorkforceProfile)) or 0
            return {**created, "total_profiles": total}
        finally:
            session.close()

    # ---------------------------------------------------------------- reads
    def overview(self) -> dict:
        session = self._session_factory()
        try:
            def count(level=None, status=None):
                stmt = select(func.count()).select_from(WorkforceProfile)
                if level:
                    stmt = stmt.where(WorkforceProfile.level == level)
                if status:
                    stmt = stmt.where(WorkforceProfile.workforce_status == status)
                return session.scalar(stmt) or 0
            dept_count = session.scalar(select(func.count()).select_from(
                WorkforceDepartment)) or 0
            wo_total = session.scalar(select(func.count()).select_from(
                AgentAssignment)) or 0
            return {
                "total_employees": count(),
                "ceo": count("ceo"), "managers": count("manager"),
                "employees": count("employee"), "departments": dept_count,
                "available": count(status="AVAILABLE"),
                "busy": count(status="BUSY"),
                "blocked": count(status="BLOCKED"),
                "suspended": count(status="SUSPENDED"),
                "disabled": count(status="DISABLED"),
                "work_orders_total": wo_total,
            }
        finally:
            session.close()

    def list_departments(self) -> list[dict]:
        session = self._session_factory()
        try:
            rows = session.scalars(select(WorkforceDepartment).order_by(
                WorkforceDepartment.sort_order)).all()
            out = []
            for row in rows:
                members = session.scalars(select(WorkforceProfile).where(
                    WorkforceProfile.department_id == row.id,
                    WorkforceProfile.level == "employee")).all()
                mgr = session.scalar(select(WorkforceProfile).where(
                    WorkforceProfile.department_id == row.id,
                    WorkforceProfile.level == "manager"))
                out.append({
                    "code": row.code, "name": row.name, "mission": row.mission,
                    "manager_code": mgr.employee_code if mgr else None,
                    "manager_title": mgr.job_title if mgr else None,
                    "employee_count": len(members)})
            return out
        finally:
            session.close()

    def _profile_dict(self, session, prof: WorkforceProfile) -> dict:
        agent = self._agent(session, prof.agent_id)
        dept = session.get(WorkforceDepartment, prof.department_id) \
            if prof.department_id else None
        manager_code = None
        if agent.parent_agent_id:
            mgr = session.scalar(select(WorkforceProfile).where(
                WorkforceProfile.agent_id == agent.parent_agent_id))
            manager_code = mgr.employee_code if mgr else None
        return {
            "employee_code": prof.employee_code, "agent_id": prof.agent_id,
            "level": prof.level, "display_name": prof.display_name,
            "job_title": prof.job_title,
            "department_code": dept.code if dept else None,
            "department_name": dept.name if dept else "Executive Office",
            "manager_code": manager_code,
            "role_description": prof.role_description,
            "primary_responsibilities": prof.primary_responsibilities,
            "secondary_responsibilities": prof.secondary_responsibilities,
            "seniority": prof.seniority, "skills": prof.skills,
            "tool_access": prof.tool_access, "memory_scope": prof.memory_scope,
            "system_instructions": prof.system_instructions,
            "communication_style": prof.communication_style,
            "autonomy_level": prof.autonomy_level,
            "permission_scope": prof.permission_scope,
            "workforce_status": prof.workforce_status,
            "agent_status": agent.status, "kpi_weights": prof.kpi_weights,
            "config_version": prof.config_version,
            "created_at": prof.created_at.isoformat() if prof.created_at else None,
        }

    def list_employees(self, *, level=None, department_code=None,
                       status=None, limit=200, offset=0):
        session = self._session_factory()
        try:
            stmt = select(WorkforceProfile)
            count_stmt = select(func.count()).select_from(WorkforceProfile)
            if level:
                stmt = stmt.where(WorkforceProfile.level == level)
                count_stmt = count_stmt.where(WorkforceProfile.level == level)
            if status:
                stmt = stmt.where(WorkforceProfile.workforce_status == status)
                count_stmt = count_stmt.where(
                    WorkforceProfile.workforce_status == status)
            if department_code:
                dept = session.scalar(select(WorkforceDepartment).where(
                    WorkforceDepartment.code == department_code))
                if dept is None:
                    raise NotFoundError(f"department {department_code} not found")
                stmt = stmt.where(WorkforceProfile.department_id == dept.id)
                count_stmt = count_stmt.where(
                    WorkforceProfile.department_id == dept.id)
            total = session.scalar(count_stmt) or 0
            rows = session.scalars(stmt.order_by(
                WorkforceProfile.employee_code).limit(limit).offset(offset)).all()
            return [self._profile_dict(session, r) for r in rows], total
        finally:
            session.close()

    def get_employee(self, code: str) -> dict:
        session = self._session_factory()
        try:
            prof = self._profile_by_code(session, code)
            data = self._profile_dict(session, prof)
            assignments = session.scalars(select(AgentAssignment).where(
                AgentAssignment.agent_id == prof.agent_id).order_by(
                AgentAssignment.created_at.desc()).limit(50)).all()
            data["assignments"] = [{
                "id": a.id, "objective": a.objective, "status": a.status,
                "task_id": a.task_id,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            } for a in assignments]
            data["performance"] = self._performance(session, prof)
            return data
        finally:
            session.close()

    # ------------------------------------------------------- status control
    def set_employee_status(self, principal: Principal, code: str,
                            action: str) -> dict:
        """pause / resume / disable / enable an employee (§18 controls).

        Owner-only. An employee or manager principal attempting this —
        including on itself — is refused: no employee may alter its own
        lifecycle or permissions (§29 rules 7–8). Disabled employees are
        suspended at the agent layer (reversible, blocks assignment via
        the factory's ASSIGNABLE_STATES) and their full history —
        profile, assignments, metrics, audit — is preserved.
        """
        self._require_owner_or_system(principal, f"workforce.{action}")
        transitions = {
            # action: (from workforce statuses, to workforce, to agent)
            "pause": ({"ACTIVE", "AVAILABLE", "BUSY", "WAITING"}, "SUSPENDED", "suspended"),
            "resume": ({"SUSPENDED"}, "AVAILABLE", "active"),
            "disable": ({"ACTIVE", "AVAILABLE", "BUSY", "WAITING", "SUSPENDED", "BLOCKED"}, "DISABLED", "suspended"),
            "enable": ({"DISABLED"}, "AVAILABLE", "active"),
            "block": ({"ACTIVE", "AVAILABLE", "BUSY", "WAITING"}, "BLOCKED", None),
            "unblock": ({"BLOCKED"}, "AVAILABLE", None),
        }
        if action not in transitions:
            raise ValidationError(f"unknown employee action '{action}'")
        allowed_from, to_wf, to_agent = transitions[action]
        session = self._session_factory()
        try:
            prof = self._profile_by_code(session, code)
            if prof.workforce_status not in allowed_from:
                raise InvalidStateTransitionError(
                    f"cannot {action} employee in status {prof.workforce_status}")
            agent = self._agent(session, prof.agent_id)
            if to_agent and agent.status != to_agent:
                from ..agents.lifecycle import validate_transition
                if not validate_transition(agent.status, to_agent):
                    raise InvalidStateTransitionError(
                        f"agent lifecycle forbids {agent.status} -> {to_agent}")
                agent.status = to_agent
                session.add(agent)
            prof.workforce_status = to_wf
            session.add(prof)
            session.commit()
            self._audit(session, principal, f"workforce.{action}", "agent",
                        prof.agent_id, details={"employee_code": code,
                                                "workforce_status": to_wf})
            return self._profile_dict(session, prof)
        finally:
            session.close()

    # ------------------------------------------------------------- objectives
    def submit_objective(self, principal: Principal, *, title: str,
                         description: str,
                         department_codes: list[str] | None = None) -> dict:
        """CEO objective intake (§4 cycle steps 1–6). Produces a PLAN.
        A plan is not authorization: nothing is dispatched by this call,
        and restricted content is flagged for the approval path (§19)."""
        self._require_owner_or_system(principal, "workforce.objective.submit")
        session = self._session_factory()
        try:
            ceo = self._profile_by_code(session, "DEV-CEO-001")
            depts = session.scalars(select(WorkforceDepartment).order_by(
                WorkforceDepartment.sort_order)).all()
            dept_by_code = {d.code: d for d in depts}
            chosen: list[WorkforceDepartment] = []
            if department_codes:
                for code in department_codes:
                    if code not in dept_by_code:
                        raise NotFoundError(f"department {code} not found")
                    chosen.append(dept_by_code[code])
            else:
                text = f"{title} {description}".lower()
                for d in depts:
                    hay = f"{d.name} {d.mission}".lower()
                    tokens = {w for w in re.split(r"[^a-z]+", hay) if len(w) > 4}
                    if tokens & {w for w in re.split(r"[^a-z]+", text) if len(w) > 4}:
                        chosen.append(d)
                if not chosen:
                    chosen = list(depts)  # portfolio-wide objective
            restricted = _is_restricted(f"{title} {description}")
            plan = []
            for d in chosen:
                mgr = session.scalar(select(WorkforceProfile).where(
                    WorkforceProfile.department_id == d.id,
                    WorkforceProfile.level == "manager"))
                plan.append({
                    "department_code": d.code, "department_name": d.name,
                    "manager_code": mgr.employee_code if mgr else None,
                    "goal": (f"Contribute the {d.name} department's part of "
                             f"the objective '{title}': {description}"),
                    "requires_approval": restricted,
                    "rationale": ("explicit department selection"
                                  if department_codes else
                                  "keyword/department-mission match"),
                })
            obj = WorkforceObjective(
                title=title, description=description,
                submitted_by_type=principal.type.value,
                submitted_by_id=principal.id, ceo_agent_id=ceo.agent_id,
                status="plan_ready", plan=plan,
                restricted_actions=([{"kind": "objective_content",
                                      "note": "objective text contains "
                                              "restricted action language; "
                                              "affected work orders require "
                                              "owner approval before "
                                              "dispatch"}]
                                     if restricted else []))
            session.add(obj)
            session.commit()
            self._audit(session, principal, "workforce.objective.submit",
                        "workforce_objective", obj.id,
                        details={"departments": [p["department_code"] for p in plan],
                                 "restricted": restricted})
            return self._objective_dict(session, obj)
        finally:
            session.close()

    def _objective_dict(self, session, obj: WorkforceObjective) -> dict:
        return {
            "id": obj.id, "title": obj.title, "description": obj.description,
            "status": obj.status, "plan": obj.plan,
            "restricted_actions": obj.restricted_actions,
            "consolidated_report": obj.consolidated_report,
            "submitted_by": {"type": obj.submitted_by_type, "id": obj.submitted_by_id},
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
        }

    def get_objective(self, objective_id: str) -> dict:
        session = self._session_factory()
        try:
            obj = session.get(WorkforceObjective, objective_id)
            if obj is None:
                raise NotFoundError(f"objective {objective_id} not found")
            return self._objective_dict(session, obj)
        finally:
            session.close()

    def list_objectives(self, limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            total = session.scalar(select(func.count()).select_from(
                WorkforceObjective)) or 0
            rows = session.scalars(select(WorkforceObjective).order_by(
                WorkforceObjective.created_at.desc()).limit(limit).offset(offset)).all()
            return [self._objective_dict(session, r) for r in rows], total
        finally:
            session.close()

    # --------------------------------------------------------------- dispatch
    async def dispatch_work_order(self, principal: Principal, *,
                                  objective_id: str, employee_code: str,
                                  objective: str, instructions: str = "",
                                  expected_deliverable: str = "",
                                  priority: int = 5,
                                  deadline: dt.datetime | None = None,
                                  restricted: bool = False) -> dict:
        """Manager breaks a departmental goal into a work order (§7).

        The caller must be the employee's own manager, the CEO, or the
        owner/system. Cross-department assignment by a manager is
        refused — collaboration happens through handoffs (§7/§11).
        Restricted work orders are NOT dispatched: a P-01 approval is
        created (requested by the CEO agent) and the order stays parked
        until an owner-authority decision exists.
        """
        self._assert_not_emergency_stopped()
        session = self._session_factory()
        try:
            obj = session.get(WorkforceObjective, objective_id)
            if obj is None:
                raise NotFoundError(f"objective {objective_id} not found")
            if obj.status not in ("plan_ready", "dispatched", "in_progress"):
                raise InvalidStateTransitionError(
                    f"objective in status '{obj.status}' cannot take work orders")
            prof = self._profile_by_code(session, employee_code)
            if prof.level != "employee":
                raise ValidationError("work orders go to specialized employees")
            employee = self._agent(session, prof.agent_id)
            manager = self._agent(session, employee.parent_agent_id)
            ceo = self._profile_by_code(session, "DEV-CEO-001")
            allowed_ids = {manager.id, ceo.agent_id}
            if principal.type in (PrincipalType.OWNER, PrincipalType.SYSTEM):
                pass
            elif principal.type is PrincipalType.AGENT and principal.id in allowed_ids:
                pass
            else:
                raise PermissionDeniedError(
                    "only the employee's manager, the CEO, or the owner may "
                    "dispatch a work order to this employee")
            if prof.workforce_status in ("SUSPENDED", "DISABLED", "ON_LEAVE", "BLOCKED"):
                raise InvalidStateTransitionError(
                    f"employee {employee_code} is {prof.workforce_status} "
                    "and cannot receive work orders")
            dept = session.get(WorkforceDepartment, prof.department_id)
            plan_codes = {p["department_code"] for p in obj.plan}
            if dept and dept.code not in plan_codes:
                raise ValidationError(
                    f"department {dept.code} is not part of this objective's plan")
            is_restricted = restricted or _is_restricted(objective) or \
                _is_restricted(instructions)
            if is_restricted:
                approval = self._approvals.create(
                    Principal(PrincipalType.AGENT, ceo.agent_id),
                    action="workforce.restricted_work_order",
                    resource=f"workforce_objective:{objective_id}",
                    reason=(f"Restricted work order for {employee_code}: "
                            f"{objective}"),
                    risk_classification="high",
                    requested_permissions=["workforce.restricted_work_order"],
                    parameters={"employee_code": employee_code,
                                "objective": objective})
                actions = list(obj.restricted_actions or [])
                actions.append({
                    "kind": "work_order", "employee_code": employee_code,
                    "objective": objective, "approval_id": approval.id,
                    "status": "pending_owner_approval"})
                obj.restricted_actions = actions
                session.add(obj)
                session.commit()
                self._audit(session, principal, "workforce.work_order.escalated",
                            "workforce_objective", objective_id,
                            decision="escalated",
                            details={"employee_code": employee_code,
                                     "approval_id": approval.id})
                return {"status": "escalated_to_owner_approval",
                        "approval_id": approval.id,
                        "employee_code": employee_code,
                        "objective_id": objective_id}
            manager_principal = Principal(PrincipalType.AGENT, manager.id)
            idem = "wf-" + hashlib.sha256(
                f"{objective_id}:{employee_code}:{objective}".encode()
            ).hexdigest()[:40]
            task = await self._tasks.submit(
                manager_principal,
                name=f"[{employee_code}] {objective}"[:300],
                handler_name="core.noop",
                payload={}, description=objective, category="workforce_work_order",
                priority=priority, assigned_agent_id=employee.id,
                requires_approval=True, idempotency_key=idem)
            assignment = AgentAssignment(
                agent_id=employee.id, task_id=task.id,
                objective=objective,
                input_refs=[{"instructions": instructions,
                             "objective_id": objective_id,
                             "department_code": dept.code if dept else None}],
                required_capabilities=[], priority=priority, deadline=deadline,
                expected_output={"required_fields": [],
                                 "deliverable": expected_deliverable},
                quality_requirements={"review": "manager",
                                      "standard": "prompt §10 output standard"},
                assigned_by_type=manager_principal.type.value,
                assigned_by_id=manager_principal.id,
                status="assigned", idempotency_key=idem)
            session.add(assignment)
            session.commit()
            obj.status = "dispatched"
            session.add(obj)
            session.commit()
            self._audit(session, principal, "workforce.work_order.dispatch",
                        "agent", employee.id,
                        details={"assignment_id": assignment.id,
                                 "task_id": task.id,
                                 "objective_id": objective_id})
            return {"status": "assigned", "assignment_id": assignment.id,
                    "task_id": task.id, "employee_code": employee_code,
                    "objective_id": objective_id,
                    "task_status": task.status}
        finally:
            session.close()

    # ------------------------------------------------------- work-order cycle
    def _assignment(self, session, assignment_id: str) -> AgentAssignment:
        row = session.get(AgentAssignment, assignment_id)
        if row is None:
            raise NotFoundError(f"assignment {assignment_id} not found")
        return row

    def _require_employee_actor(self, principal: Principal, employee_agent_id: str,
                                manager_agent_id: str | None = None) -> None:
        if principal.type in (PrincipalType.OWNER, PrincipalType.SYSTEM):
            return
        if principal.type is PrincipalType.AGENT and principal.id == employee_agent_id:
            return
        if manager_agent_id and principal.type is PrincipalType.AGENT \
                and principal.id == manager_agent_id:
            return
        raise PermissionDeniedError(
            "only the assigned employee (or the owner) may perform this step")

    def accept_work_order(self, principal: Principal, assignment_id: str) -> dict:
        session = self._session_factory()
        try:
            row = self._assignment(session, assignment_id)
            employee = self._agent(session, row.agent_id)
            self._require_employee_actor(principal, row.agent_id)
            if row.status != "assigned":
                raise InvalidStateTransitionError(
                    f"assignment in status '{row.status}' cannot be accepted")
            row.status = "running"
            row.started_at = utcnow()
            session.add(row)
            prof = session.scalar(select(WorkforceProfile).where(
                WorkforceProfile.agent_id == row.agent_id))
            if prof:
                prof.workforce_status = "BUSY"
                session.add(prof)
            session.commit()
            return {"assignment_id": row.id, "status": row.status,
                    "employee_code": prof.employee_code if prof else None}
        finally:
            session.close()

    def submit_deliverable(self, principal: Principal, assignment_id: str, *,
                           work_performed: str, result: str,
                           evidence: list | None = None,
                           limitations: str = "",
                           outstanding_issues: str = "") -> dict:
        """Employee submits a §10-standard deliverable. Submission is a
        self-report — it becomes a verified result ONLY on manager
        acceptance (§10: an employee must not report a task completed
        merely because it generated an answer)."""
        session = self._session_factory()
        try:
            row = self._assignment(session, assignment_id)
            self._require_employee_actor(principal, row.agent_id)
            if row.status != "running":
                raise InvalidStateTransitionError(
                    f"assignment in status '{row.status}' cannot take a "
                    "deliverable (accept the work order first)")
            version = (session.scalar(select(func.count()).select_from(
                WorkforceDeliverable).where(
                    WorkforceDeliverable.assignment_id == row.id)) or 0) + 1
            deliverable = WorkforceDeliverable(
                assignment_id=row.id, task_id=row.task_id,
                employee_agent_id=row.agent_id, version=version,
                objective=row.objective, work_performed=work_performed,
                result=result, evidence=evidence or [],
                limitations=limitations, outstanding_issues=outstanding_issues,
                verification_status="self_reported", review_status="submitted")
            session.add(deliverable)
            row.status = "review_pending"
            session.add(row)
            prof = session.scalar(select(WorkforceProfile).where(
                WorkforceProfile.agent_id == row.agent_id))
            if prof:
                prof.workforce_status = "WAITING"
                session.add(prof)
            session.commit()
            return {"deliverable_id": deliverable.id,
                    "assignment_id": row.id, "version": version,
                    "review_status": "submitted",
                    "verification_status": "self_reported"}
        finally:
            session.close()

    def review_deliverable(self, principal: Principal, deliverable_id: str, *,
                           accept: bool, quality_score: float | None = None,
                           notes: str | None = None) -> dict:
        """Manager review (§9/§10). Only the employee's own manager (or
        the owner/system) may review. Acceptance is the moment a result
        becomes verified: metrics are recorded and the parked P-01 task
        is released to the queue. Rework returns the assignment to the
        employee — never a silent failure."""
        session = self._session_factory()
        try:
            deliverable = session.get(WorkforceDeliverable, deliverable_id)
            if deliverable is None:
                raise NotFoundError(f"deliverable {deliverable_id} not found")
            if deliverable.review_status != "submitted":
                raise InvalidStateTransitionError(
                    f"deliverable already reviewed ({deliverable.review_status})")
            row = self._assignment(session, deliverable.assignment_id)
            employee = self._agent(session, row.agent_id)
            manager_id = employee.parent_agent_id
            if principal.type in (PrincipalType.OWNER, PrincipalType.SYSTEM):
                pass
            elif principal.type is PrincipalType.AGENT and principal.id == manager_id:
                pass
            else:
                raise PermissionDeniedError(
                    "only the employee's manager (or the owner) may review "
                    "this deliverable")
            prof = session.scalar(select(WorkforceProfile).where(
                WorkforceProfile.agent_id == row.agent_id))
            deliverable.reviewed_by_agent_id = manager_id
            deliverable.review_notes = notes
            if accept:
                deliverable.review_status = "accepted"
                deliverable.verification_status = "manager_verified"
                deliverable.quality_score = quality_score
                on_time = None
                if row.deadline is not None:
                    from ..database.models.base import as_utc
                    on_time = as_utc(deliverable.created_at) <= as_utc(row.deadline)
                deliverable.on_time = on_time
                row.status = "completed"
                row.completed_at = utcnow()
                row.result_summary = deliverable.result[:500]
                self._record_metric(session, row.agent_id, "tasks_completed", 1)
                self._record_metric(session, row.agent_id, "verified_success", 1)
                if quality_score is not None:
                    self._record_metric(session, row.agent_id, "quality_score",
                                        float(quality_score))
                if on_time is not None:
                    self._record_metric(session, row.agent_id,
                                        "deadline_adherence", 1.0 if on_time else 0.0)
                if prof:
                    prof.workforce_status = "AVAILABLE"
                    session.add(prof)
                session.add(deliverable)
                session.add(row)
                session.commit()
                # Release the parked task: it now executes core.noop,
                # recording the reviewed deliverable in the task engine.
                if row.task_id:
                    self._tasks.approve_task(row.task_id)
                outcome = "accepted"
            else:
                deliverable.review_status = "rework_requested"
                row.status = "running"
                if prof:
                    prof.workforce_status = "BUSY"
                    session.add(prof)
                session.add(deliverable)
                session.add(row)
                session.commit()
                outcome = "rework_requested"
            self._audit(session, principal, "workforce.deliverable.review",
                        "agent_assignment", row.id, decision=outcome,
                        details={"deliverable_id": deliverable.id,
                                 "quality_score": quality_score})
            return {"deliverable_id": deliverable.id, "outcome": outcome,
                    "assignment_id": row.id, "assignment_status": row.status}
        finally:
            session.close()

    @staticmethod
    def _record_metric(session, agent_id: str, name: str, value: float) -> None:
        session.add(AgentMetric(
            agent_id=agent_id, metric_name=name, metric_value=float(value),
            measurement_type="measured", recorded_at=utcnow(),
            details={"source": "workforce"}))
        session.commit()

    # --------------------------------------------------------------- handoffs
    def create_handoff(self, principal: Principal, *, from_code: str,
                       to_code: str, objective: str, task_ref: str = "",
                       work_completed: str = "",
                       next_actions: list | None = None) -> dict:
        """Cross-department collaboration ONLY through a P-09 handoff
        record (§7/§11). Direct cross-department assignment is refused
        in dispatch_work_order."""
        session = self._session_factory()
        try:
            src = self._profile_by_code(session, from_code)
            dst = self._profile_by_code(session, to_code)
            if principal.type is PrincipalType.AGENT \
                    and principal.id not in (src.agent_id, dst.agent_id):
                # a manager of either side may also hand off
                src_agent = self._agent(session, src.agent_id)
                dst_agent = self._agent(session, dst.agent_id)
                if principal.id not in (src_agent.parent_agent_id,
                                        dst_agent.parent_agent_id):
                    raise PermissionDeniedError(
                        "handoffs may be created by the sending/receiving "
                        "employee, their managers, or the owner")
            row = AgentHandoff(
                from_agent_id=src.agent_id, to_agent_id=dst.agent_id,
                task_ref=task_ref, objective=objective,
                work_completed=work_completed, current_status="HANDED_OFF",
                next_actions=next_actions or [],
                created_by=f"{principal.type.value}:{principal.id}")
            session.add(row)
            session.commit()
            self._audit(session, principal, "workforce.handoff", "agent",
                        dst.agent_id, details={"from": from_code, "to": to_code,
                                               "handoff_id": row.id})
            return {"handoff_id": row.id, "from": from_code, "to": to_code,
                    "objective": objective}
        finally:
            session.close()

    # ------------------------------------------------------------- performance
    def _performance(self, session, prof: WorkforceProfile) -> dict:
        metrics = session.scalars(select(AgentMetric).where(
            AgentMetric.agent_id == prof.agent_id,
            AgentMetric.measurement_type == "measured")).all()
        by_name: dict[str, list[float]] = {}
        for m in metrics:
            if m.metric_value is not None:
                by_name.setdefault(m.metric_name, []).append(m.metric_value)

        def mean(name):
            vals = by_name.get(name)
            return (sum(vals) / len(vals)) if vals else None

        completed = len([a for a in session.scalars(select(AgentAssignment).where(
            AgentAssignment.agent_id == prof.agent_id)).all()
            if a.status == "completed"])
        terminal_failed = len([a for a in session.scalars(select(AgentAssignment).where(
            AgentAssignment.agent_id == prof.agent_id)).all()
            if a.status in ("failed", "output_invalid", "cancelled")])
        components: dict[str, float | None] = {
            "quality": mean("quality_score"),
            "verified_success": (
                100.0 * sum(by_name.get("verified_success", [])) /
                max(1, int(sum(by_name.get("tasks_completed", [])) +
                           sum(by_name.get("tasks_failed", [])))))
            if by_name.get("tasks_completed") else None,
            "deadline_adherence": (mean("deadline_adherence") * 100.0
                                   if mean("deadline_adherence") is not None else None),
            "reliability": (100.0 * completed / (completed + terminal_failed)
                            if (completed + terminal_failed) > 0 else None),
            "resource_efficiency": mean("resource_efficiency"),
            "collaboration": mean("collaboration_score"),
            "policy_compliance": mean("policy_compliance"),
        }
        weights = prof.kpi_weights or KPI_WEIGHTS
        present = {k: v for k, v in components.items() if v is not None}
        if not present:
            return {"data_status": "no_data", "score": None,
                    "components": components,
                    "note": "no verified outcomes recorded yet — no score "
                            "is fabricated (§14)"}
        total_weight = sum(weights.get(k, 0) for k in present)
        score = sum(present[k] * weights.get(k, 0) for k in present) / total_weight \
            if total_weight else None
        return {"data_status": "measured", "score": round(score, 2) if score is not None else None,
                "components": components,
                "weights_used": {k: weights.get(k, 0) for k in present},
                "weights_renormalized_over": sorted(present)}

    def employee_performance(self, code: str) -> dict:
        session = self._session_factory()
        try:
            prof = self._profile_by_code(session, code)
            return {"employee_code": code, **self._performance(session, prof)}
        finally:
            session.close()

    def department_performance(self, department_code: str) -> dict:
        session = self._session_factory()
        try:
            dept = session.scalar(select(WorkforceDepartment).where(
                WorkforceDepartment.code == department_code))
            if dept is None:
                raise NotFoundError(f"department {department_code} not found")
            members = session.scalars(select(WorkforceProfile).where(
                WorkforceProfile.department_id == dept.id)).all()
            perfs = [self._performance(session, m) for m in members]
            scored = [p["score"] for p in perfs if p["score"] is not None]
            return {
                "department_code": department_code,
                "members": len(members),
                "members_with_data": len(scored),
                "department_score": round(sum(scored) / len(scored), 2) if scored else None,
                "data_status": "measured" if scored else "no_data",
            }
        finally:
            session.close()

    # ------------------------------------------------------------ consolidate
    def consolidate_objective(self, principal: Principal, objective_id: str) -> dict:
        """CEO-level consolidated report (§4/§8): assembled ONLY from
        recorded assignments and reviewed deliverables."""
        session = self._session_factory()
        try:
            obj = session.get(WorkforceObjective, objective_id)
            if obj is None:
                raise NotFoundError(f"objective {objective_id} not found")
            ceo = self._profile_by_code(session, "DEV-CEO-001")
            if principal.type in (PrincipalType.OWNER, PrincipalType.SYSTEM):
                pass
            elif principal.type is PrincipalType.AGENT and principal.id == ceo.agent_id:
                pass
            else:
                raise PermissionDeniedError(
                    "consolidation is a CEO (or owner) function")
            assignments = session.scalars(select(AgentAssignment)).all()
            mine = []
            for a in assignments:
                refs = a.input_refs or []
                if refs and isinstance(refs[0], dict) \
                        and refs[0].get("objective_id") == objective_id:
                    mine.append(a)
            deliverables = {}
            for a in mine:
                rows = session.scalars(select(WorkforceDeliverable).where(
                    WorkforceDeliverable.assignment_id == a.id).order_by(
                    WorkforceDeliverable.version.desc())).all()
                if rows:
                    deliverables[a.id] = rows[0]
            by_dept: dict[str, dict] = {}
            for a in mine:
                prof = session.scalar(select(WorkforceProfile).where(
                    WorkforceProfile.agent_id == a.agent_id))
                dept_code = "unknown"
                if prof and prof.department_id:
                    dept = session.get(WorkforceDepartment, prof.department_id)
                    dept_code = dept.code if dept else "unknown"
                entry = by_dept.setdefault(dept_code, {
                    "work_orders": 0, "completed": 0, "in_progress": 0,
                    "deliverables": []})
                entry["work_orders"] += 1
                if a.status == "completed":
                    entry["completed"] += 1
                else:
                    entry["in_progress"] += 1
                d = deliverables.get(a.id)
                if d:
                    entry["deliverables"].append({
                        "employee_code": prof.employee_code if prof else None,
                        "result": d.result,
                        "verification_status": d.verification_status,
                        "review_status": d.review_status,
                        "quality_score": d.quality_score})
            total = len(mine)
            done = sum(1 for a in mine if a.status == "completed")
            report = {
                "objective_id": objective_id, "title": obj.title,
                "work_orders_total": total, "work_orders_completed": done,
                "departments": by_dept,
                "escalations_pending": [r for r in (obj.restricted_actions or [])
                                        if r.get("status") == "pending_owner_approval"],
                "generated_from": "recorded assignments + reviewed deliverables only",
            }
            obj.consolidated_report = report
            obj.status = "completed" if total > 0 and done == total else "in_progress"
            session.add(obj)
            session.commit()
            return report
        finally:
            session.close()
