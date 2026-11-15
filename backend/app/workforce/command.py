"""Command Center (§18) and natural-language command interpreter (§19).

The Command Center is the backend-only organizational dashboard: one read that
aggregates the whole organization's state from real records - health, the
work-order pipeline, objective progress, KPI summary and recent activity. It
reports what the database holds; it never invents a number.

The natural-language command interpreter maps a plain-language instruction to a
governed workforce operation. It is **deterministic keyword matching, not an
inference call** (consistent with ADR-0017): a fixed vocabulary of intents, each
dispatching to a real service method, with an honest refusal for anything
outside the vocabulary. A command that does not map to an operation is refused
rather than guessed at.
"""

from __future__ import annotations

import re
from typing import Any

from ..core.exceptions import ConflictError
from .schemas import WorkOrderCreate

__all__ = ["CommandCenter", "CommandInterpreter"]


class CommandCenter:
    """The organizational dashboard: aggregated reads over real records (§18)."""

    def __init__(self, *, settings: Any, db: Any, workforce: Any,
                 performance: Any) -> None:
        self.settings = settings
        self.db = db
        self.workforce = workforce
        self.performance = performance

    async def dashboard(self) -> dict[str, Any]:
        """The full Command Center view, assembled from the database.

        Every number is counted from the workforce tables. The dashboard is a
        read-only projection: it changes nothing and reports the present state,
        including the parts that are empty.
        """
        overview = await self.workforce.overview()
        departments = await self.workforce.list_departments()
        async with self.db.session_factory() as session:
            from ..database.repositories import (
                WorkforceObjectiveRepo, WorkforceStatusHistoryRepo,
                WorkforceWorkOrderRepo,
            )
            objectives = await WorkforceObjectiveRepo(session).list_all()
            orders = await WorkforceWorkOrderRepo(session).list_all()
            history = await WorkforceStatusHistoryRepo(session).list_all()

        objective_progress = {"open": 0, "delegated": 0, "in_progress": 0,
                              "completed": 0, "total": len(objectives)}
        for o in objectives:
            key = {"OPEN": "open", "DELEGATED": "delegated",
                   "IN_PROGRESS": "in_progress", "COMPLETED": "completed"}.get(
                o.status, "open")
            objective_progress[key] += 1

        order_pipeline = {"assigned": 0, "accepted": 0, "working": 0,
                          "review_pending": 0, "completed": 0, "failed": 0,
                          "total": len(orders)}
        for o in orders:
            key = {"TASK_ASSIGNED": "assigned", "TASK_ACCEPTED": "accepted",
                   "WORKING": "working", "REVIEW_PENDING": "review_pending",
                   "COMPLETED": "completed", "FAILED": "failed"}.get(o.status)
            if key:
                order_pipeline[key] += 1

        recent_activity = [
            {"employee_id": h.employee_id, "from_status": h.from_status,
             "to_status": h.to_status, "reason": h.reason,
             "at": h.changed_at.isoformat() if h.changed_at else None}
            for h in sorted(history, key=lambda h: h.changed_at or h.created_at,
                            reverse=True)[:20]
        ]

        # A KPI summary across employees that have a computed period. Read-only:
        # it does not recompute, only reports what is stored.
        kpi_summary = await self._kpi_summary()

        return {
            "organization_health": {
                "total_employees": overview["total_employees"],
                "ceo_count": overview["ceo_count"],
                "manager_count": overview["manager_count"],
                "specialist_count": overview["specialist_count"],
                "department_count": overview["department_count"],
                "available_employees": overview["available_employees"],
                "busy_employees": overview["busy_employees"],
                "blocked_employees": overview["blocked_employees"],
                "by_status": overview["by_status"],
            },
            "departments": [
                {
                    "code": d["code"], "name": d["name"],
                    "manager_employee_id": d["manager_employee_id"],
                    "employee_count": d["employee_count"],
                } for d in departments
            ],
            "work_order_pipeline": order_pipeline,
            "objective_progress": objective_progress,
            "kpi_summary": kpi_summary,
            "recent_activity": recent_activity,
            "source": "real workforce records; backend-only dashboard (§18)",
        }

    async def _kpi_summary(self) -> dict[str, Any]:
        """Aggregate the stored KPIs; never recomputes and never invents."""
        async with self.db.session_factory() as session:
            from sqlalchemy import select
            from ..database.models import WorkforcePerformance
            rows = (await session.execute(
                select(WorkforcePerformance))).scalars().all()
        if not rows:
            return {"employees_with_kpis": 0, "average_composite": None,
                    "note": "no KPI period has been computed yet"}
        composites = [r.composite_score for r in rows if r.composite_score is not None]
        return {
            "employees_with_kpis": len(rows),
            "average_composite": round(sum(composites) / len(composites), 2)
            if composites else None,
            "periods": sorted({r.period for r in rows}),
        }


class CommandInterpreter:
    """Map a natural-language command to a governed workforce operation (§19).

    Deterministic keyword matching over a fixed vocabulary. Each recognized
    intent dispatches to a real service method; an unrecognized command is
    refused with the list of supported intents rather than guessed at.
    """

    # (intent, regex, handler-name). Order matters: the first match wins.
    _PATTERNS: list[tuple[str, re.Pattern[str]]] = [
        ("dashboard", re.compile(r"\b(dashboard|overview|organization|status)\b",
                                 re.I)),
        ("briefing", re.compile(r"\b(briefing|daily report|morning)\b", re.I)),
        ("eod_report", re.compile(r"\b(end of day|end-of-day|eod)\b", re.I)),
        ("weekly_review", re.compile(r"\b(weekly|review)\b", re.I)),
        ("finance", re.compile(r"\b(finance|financial)\b", re.I)),
        ("kpis", re.compile(r"\b(kpi|performance|metrics)\b", re.I)),
        ("delegate", re.compile(r"\bdelegate\b", re.I)),
        ("assign", re.compile(r"\bassign\b", re.I)),
    ]

    _EMPLOYEE_RE = re.compile(r"\b(DEV-[A-Z]{2,4}-\d{3})\b")

    def __init__(self, *, settings: Any, db: Any, workforce: Any,
                 ceo: Any, performance: Any, command_center: CommandCenter,
                 finance: Any) -> None:
        self.settings = settings
        self.db = db
        self.workforce = workforce
        self.ceo = ceo
        self.performance = performance
        self.command_center = command_center
        self.finance = finance

    async def interpret(self, command: str, *, actor_id: str | None = None) -> dict[str, Any]:
        """Parse and dispatch one command. Returns the outcome or a refusal."""
        command = (command or "").strip()
        if not command:
            return self._refusal("an empty command", command)

        intent = self._match_intent(command)
        if intent is None:
            return self._refusal(
                "the command is outside the supported vocabulary", command)

        try:
            if intent == "dashboard":
                data = await self.command_center.dashboard()
                return self._result(intent, command, data)
            if intent == "briefing":
                data = await self.ceo.morning_briefing()
                return self._result(intent, command, data)
            if intent == "eod_report":
                data = await self.ceo.end_of_day_report()
                return self._result(intent, command, data)
            if intent == "weekly_review":
                data = await self.ceo.weekly_review()
                return self._result(intent, command, data)
            if intent == "finance":
                data = await self.finance.report()
                return self._result(intent, command, data)
            if intent == "kpis":
                data = await self._kpis_view()
                return self._result(intent, command, data)
            if intent == "delegate":
                data = await self._delegate(command)
                return self._result(intent, command, data)
            if intent == "assign":
                data = await self._assign(command)
                return self._result(intent, command, data)
        except ConflictError as exc:
            # A governed refusal from the operation itself is reported as such,
            # not masked as an interpreter failure.
            return {"intent": intent, "command": command,
                    "outcome": "refused", "reason": str(exc)}
        except Exception as exc:  # noqa: BLE001 - surface the real error
            return {"intent": intent, "command": command,
                    "outcome": "error", "reason": str(exc)}
        return self._refusal("no handler", command)

    def _match_intent(self, command: str) -> str | None:
        for intent, pattern in self._PATTERNS:
            if pattern.search(command):
                return intent
        return None

    async def _assign(self, command: str) -> dict[str, Any]:
        """Parse 'assign <employee> to <task>' into a work order."""
        match = self._EMPLOYEE_RE.search(command)
        if not match:
            raise ConflictError(
                "an assign command needs an employee id (e.g. DEV-RES-001)")
        employee_id = match.group(1)
        # The task text is what follows "assign <emp> to ...".
        after = command[match.end():]
        title = after.lstrip(" ,;:-").removeprefix("to ").strip()
        if not title:
            raise ConflictError("an assign command needs a task description")
        # The assigner is the CEO: the NL command is an owner/CEO directive.
        order = WorkOrderCreate(
            employee_id=employee_id, title=title[:120],
            instructions=title, verification_requirements=[],
        )
        result = await self.workforce.create_work_order(
            order, manager_employee_id="DEV-CEO-001")
        return {"action": "work_order_created", "result": result}

    async def _delegate(self, command: str) -> dict[str, Any]:
        """Parse 'delegate <objective>' into a CEO objective."""
        # Strip the leading verb and any department names mentioned.
        body = command
        for verb in ("delegate", "assign objective", "objective"):
            idx = body.lower().find(verb)
            if idx >= 0:
                body = body[idx + len(verb):]
                break
        objective = body.strip(" ,;:-")
        departments: list[str] = []
        for code in ("RES", "BIZ", "TECH", "MKT", "SAL", "FIN", "OPS",
                     "SEC", "CS", "STR"):
            if re.search(rf"\b{code}\b", objective, re.I):
                departments.append(code)
        if not objective:
            raise ConflictError("a delegate command needs an objective")
        from .schemas import ObjectiveCreate
        result = await self.ceo.submit_objective(
            ObjectiveCreate(objective=objective, departments=departments),
            source="nl_command")
        return {"action": "objective_delegated", "result": result}

    async def _kpis_view(self) -> dict[str, Any]:
        async with self.db.session_factory() as session:
            from ..database.repositories import WorkforceEmployeeRepo
            employees = await WorkforceEmployeeRepo(session).list_all()
        summaries = []
        for e in employees[:20]:
            kpis = await self.performance.employee_kpis(e.employee_id)
            if kpis:
                summaries.append({"employee_id": e.employee_id,
                                  "latest": kpis[0]})
        return {"action": "kpi_summary", "employees": summaries,
                "note": "KPIs are computed from verified outcomes, never self-reported"}

    @staticmethod
    def _result(intent: str, command: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"intent": intent, "command": command, "outcome": "executed",
                "result": data}

    @staticmethod
    def _refusal(reason: str, command: str) -> dict[str, Any]:
        return {
            "intent": None, "command": command, "outcome": "refused",
            "reason": reason,
            "supported": [
                "dashboard / overview / organization / status",
                "briefing / daily report",
                "end of day / eod",
                "weekly / review",
                "finance / financial",
                "kpi / performance",
                "delegate <objective>",
                "assign <employee-id> to <task>",
            ],
        }
