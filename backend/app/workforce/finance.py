"""Finance Office (§22): analysis and reporting only, never execution.

The workforce prompt's Financial authority (§22, P-07) is represented by a
governed interface, not a spending engine. There is deliberately **no spending
surface** (ADR-0020): this office produces financial *analysis and reporting*
from the records the organization already generates - work-order economics,
resource utilization, departmental activity - and states plainly that it holds
no authority to execute, authorize or move money.

The boundary is enforced twice: the finance employees' tool access excludes
``financial.execute`` and ``spending.authorize`` (both in the catalog's
PROHIBITED set), and this office exposes no method that could spend. A report
that claimed spending authority would be a false assurance.
"""

from __future__ import annotations

from typing import Any

__all__ = ["FinanceOffice"]


class FinanceOffice:
    """Read-only financial analysis over recorded workforce activity (§22)."""

    def __init__(self, *, settings: Any, db: Any) -> None:
        self.settings = settings
        self.db = db

    async def report(self) -> dict[str, Any]:
        """A financial analysis report assembled from real records.

        Aggregates work-order activity into economic views (volume by
        department, completion economics, resource utilization). Every figure
        is counted from the database; nothing is estimated or invented.
        """
        async with self.db.session_factory() as session:
            from ..database.repositories import (
                WorkforceDepartmentRepo, WorkforceEmployeeRepo,
                WorkforceWorkOrderRepo,
            )
            depts = await WorkforceDepartmentRepo(session).list_all()
            employees = await WorkforceEmployeeRepo(session).list_all()
            orders = await WorkforceWorkOrderRepo(session).list_all()

        by_department: dict[str, dict[str, int]] = {}
        for d in depts:
            by_department[d.code] = {"assigned": 0, "completed": 0,
                                     "failed": 0, "total": 0}
        for o in orders:
            # The order's department is the employee's department.
            dept_code = next(
                (e.department_code for e in employees
                 if e.employee_id == o.employee_id), None)
            bucket = by_department.get(dept_code)
            if bucket is None:
                continue
            bucket["total"] += 1
            if o.status == "COMPLETED":
                bucket["completed"] += 1
            elif o.status == "FAILED":
                bucket["failed"] += 1
            else:
                bucket["assigned"] += 1

        completed = sum(1 for o in orders if o.status == "COMPLETED")
        total = len(orders)
        completion_rate = round(completed / total, 4) if total else 0.0

        return {
            "mode": "analysis_and_reporting",
            "authority": "none",
            "boundary": (
                "this office analyzes and reports on recorded activity; it holds "
                "no authority to execute, authorize or move money. Spending "
                "authority is prohibited by ADR-0020 and the capability "
                "catalog's PROHIBITED set (financial.execute, spending.authorize)"
            ),
            "work_order_economics": {
                "total_work_orders": total,
                "completed": completed,
                "failed": sum(1 for o in orders if o.status == "FAILED"),
                "completion_rate": completion_rate,
            },
            "by_department": by_department,
            "resource_utilization": {
                "employees_total": len(employees),
                "departments": len(depts),
                "note": (
                    "resource figures are counted from the workforce registry; "
                    "no monetary value is attached to any employee or activity"
                ),
            },
            "source": "real workforce records; analysis-only (§22)",
        }
