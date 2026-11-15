"""The CEO's autonomous executive operating system (§4, §8).

The CEO is the central management intelligence of the workforce. This module
implements its operating cycle deterministically, over real records - it does
not invent progress to make the organization appear productive (§8: "The CEO
must not invent progress simply to make the organization appear productive").

The cycle:

1. Receive an objective (from the owner, or an authorized trigger).
2. Understand it and identify the expected outcome.
3. Determine the required departments (deterministic keyword mapping).
4. Prepare an execution strategy and assign the objective to managers.
5. Monitor execution (department status, work orders, failures).
6. Review verified results and consolidate an executive report.
7. Report outcomes to the owner, distinguishing actual outcomes from estimates.

The CEO's decision authority is bounded: it delegates through the same
hierarchy and capability system every other employee uses, and cannot bypass
owner approval, financial restrictions, or security policy (§4, §21). Those
bounds are enforced by the existing capability catalog and approval system,
not re-implemented here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..core.config import Settings
from ..database.connection import Database
from .catalog import CEO_ID, DEPARTMENT_BY_CODE
from .schemas import ObjectiveCreate
from .service import WorkforceService

__all__ = ["CeoOffice"]

# Deterministic keyword → department mapping for objective interpretation.
# A real model would refine this; without one, the mapping is transparent and
# reviewable, and every department it names is a real, authorized department.
_DEPARTMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "STR": ("strategy", "strategic", "plan", "roadmap", "executive", "decision"),
    "RES": ("research", "market", "competitor", "analyze", "analysis", "fact", "knowledge"),
    "BIZ": ("business", "product", "saas", "ecommerce", "e-commerce", "publishing",
            "service", "launch", "model"),
    "TECH": ("technology", "software", "code", "api", "database", "architecture",
             "engineer", "development", "devops", "qa", "test", "technical"),
    "MKT": ("marketing", "brand", "seo", "content", "campaign", "audience", "social"),
    "SAL": ("sales", "lead", "customer acquisition", "outreach", "funnel", "conversion"),
    "FIN": ("finance", "financial", "budget", "revenue", "profit", "expense",
            "cash", "cost"),
    "OPS": ("operations", "operational", "workflow", "process", "schedule",
            "resource", "incident", "efficiency"),
    "SEC": ("security", "governance", "risk", "compliance", "audit", "vulnerability"),
    "CS": ("customer success", "support", "onboarding", "feedback", "retention",
           "complaint", "satisfaction"),
}


class CeoOffice:
    """The CEO's operating surface."""

    def __init__(self, *, settings: Settings, db: Database,
                 workforce: WorkforceService) -> None:
        self.settings = settings
        self.db = db
        self.workforce = workforce

    async def submit_objective(self, objective: ObjectiveCreate,
                               *, source: str = "owner") -> dict[str, Any]:
        """Receive an objective, identify the departments, delegate, and
        record the executive plan (§4 operating cycle, steps 1-7)."""
        departments = self._identify_departments(objective.objective,
                                                 objective.departments)
        # Cap fan-out: the CEO consolidates rather than delegating to every
        # department for one objective.
        if len(departments) > self.settings.workforce_max_objective_departments:
            departments = departments[: self.settings.workforce_max_objective_departments]

        objective_record = await self.workforce.create_objective(
            objective, source=source, created_by=CEO_ID)
        delegated = await self.workforce.delegate_objective(
            objective_record["id"], departments=departments)

        strategy = {
            "objective_id": delegated["id"],
            "departments": departments,
            "department_managers": [
                DEPARTMENT_BY_CODE[code]["manager_id"] for code in departments
            ],
            "expected_outcome": objective.expected_outcome or objective.objective,
            "delegation_note": (
                "The CEO has delegated this objective to the identified "
                "department managers. Each manager breaks it into work orders "
                "for its ten specialists; results are reviewed by the manager, "
                "consolidated by the CEO, and reported to the owner."),
        }
        return {"objective": delegated, "execution_strategy": strategy}

    def _identify_departments(self, text: str,
                              explicit: list[str]) -> list[str]:
        """Determine the required departments for an objective.

        If the caller named departments explicitly, those are used (validated
        against the real department set). Otherwise the objective text is
        mapped to departments by keyword. The result is always a subset of the
        ten real departments.
        """
        if explicit:
            return [code for code in explicit if code in DEPARTMENT_BY_CODE]
        lowered = text.lower()
        found: list[str] = []
        for code, keywords in _DEPARTMENT_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                found.append(code)
        return found or ["STR"]

    async def morning_briefing(self) -> dict[str, Any]:
        """The morning executive briefing (§8): organizational status,
        department performance, active projects, deadlines, risks, from real
        records."""
        overview = await self.workforce.overview()
        departments = await self.workforce.list_departments()
        department_status = []
        for d in departments:
            employees = await self.workforce.list_employees(
                department_code=d["code"])
            active = [e for e in employees if e["status"] in ("BUSY", "WAITING", "BLOCKED")]
            department_status.append({
                "code": d["code"], "name": d["name"],
                "manager": d["manager_name"],
                "employee_count": d["employee_count"],
                "active_tasks": len(active),
                "blocked": sum(1 for e in active if e["status"] == "BLOCKED"),
            })
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "organizational_status": overview,
            "department_status": department_status,
            "recommended_priorities": self._recommend_priorities(overview),
            "note": "Counts are read from real backend records; no progress is "
                    "inferred or invented.",
        }

    def _recommend_priorities(self, overview: dict[str, Any]) -> list[str]:
        """Deterministic priority recommendations from the current state."""
        priorities: list[str] = []
        if overview.get("blocked_employees", 0):
            priorities.append(
                f"Resolve {overview['blocked_employees']} blocked employee(s) "
                "before assigning new work.")
        if overview.get("failed_work_orders", 0):
            priorities.append(
                f"Review {overview['failed_work_orders']} failed work order(s) "
                "and escalate root causes to the responsible managers.")
        if overview.get("pending_objectives", 0):
            priorities.append(
                f"Follow up on {overview['pending_objectives']} open objective(s) "
                "awaiting department delivery.")
        if not priorities:
            priorities.append("No blocking issues; maintain current execution.")
        return priorities

    async def end_of_day_report(self) -> dict[str, Any]:
        """The end-of-day executive report (§8): tasks completed, pending,
        failed, department performance, deliverables, incidents - distinguishing
        actual outcomes from estimates."""
        overview = await self.workforce.overview()
        departments = await self.workforce.list_departments()
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tasks_completed": overview["completed_work_orders"],
            "tasks_pending": overview["active_work_orders"],
            "tasks_failed": overview["failed_work_orders"],
            "department_performance": [
                {"code": d["code"], "name": d["name"],
                 "employee_count": d["employee_count"]}
                for d in departments
            ],
            "operational_incidents": overview["blocked_employees"],
            "decisions_requiring_owner_attention": (
                [{"type": "failed_work", "count": overview["failed_work_orders"]}]
                if overview["failed_work_orders"] else []),
            "next_day_priorities": self._recommend_priorities(overview),
            "note": "Completed and failed counts are actual recorded outcomes; "
                    "pending counts are current state, not forecasts.",
        }

    async def weekly_review(self) -> dict[str, Any]:
        """The weekly executive review (§8): department efficiency, employee
        performance, business progress, using verified records."""
        from .performance import PerformanceEngine
        engine = PerformanceEngine(settings=self.settings, db=self.db)
        departments = await self.workforce.list_departments()
        review = []
        for d in departments:
            review.append(await engine.department_kpis(d["code"]))
        overview = await self.workforce.overview()
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "department_efficiency": review,
            "organizational_summary": {
                "total_employees": overview["total_employees"],
                "completed_work_orders": overview["completed_work_orders"],
                "failed_work_orders": overview["failed_work_orders"],
            },
            "note": "Performance scores are computed from verified work-order "
                    "outcomes, not self-reports.",
        }
