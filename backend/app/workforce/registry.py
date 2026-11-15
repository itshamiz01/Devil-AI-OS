"""Idempotent baseline seeding for the 111-employee organization (§3, §5, §6).

``ensure_baseline`` registers the 111 baseline employees - one CEO, ten
managers, one hundred specialists - through the **existing** agent registry
and capability catalog. It does not create a second registry: each employee is
an ``agents`` row keyed on its stable employee ID (``DEV-CEO-001``,
``DEV-MGR-001``, ``DEV-STR-001``, ...), with the reporting hierarchy carried
by ``parent_agent_id`` and the organizational overlay carried by
``workforce_employees``.

**Idempotency is the whole point.** Seeding is keyed on the stable employee
IDs, so restarting the application never duplicates an employee. A baseline
employee that already exists is skipped - its registry row, capability grants
and profile are left exactly as they were. This is the same recovery
philosophy the other subsystems follow: startup restores what is already
there and creates only what is missing.

Order matters and is fixed: the CEO, then the ten managers, then the one
hundred specialists. Managers must exist before their specialists reference
them (both the ``agents.parent_agent_id`` FK and the
``workforce_employees.manager_employee_id`` FK), and the CEO must exist
before the managers reference it. ``BASELINE_DEFINITIONS`` is ordered
exactly so.
"""

from __future__ import annotations

import logging
from typing import Any

from ..agents.catalog import PROHIBITED_CAPABILITIES
from ..agents.lifecycle import AgentStatus, transition
from ..database.connection import Database
from ..database.models import utcnow
from ..database.repositories import AgentRepo, PrincipalRepo
from ..core.config import Settings
from .catalog import BASELINE_DEFINITIONS, DEPARTMENTS

logger = logging.getLogger(__name__)

__all__ = ["ensure_baseline"]


async def _resolve_system_principal_id(db: Database) -> str | None:
    """The system principal's id, for attributing baseline capability grants."""
    from ..database.repositories import PrincipalRepo
    async with db.session_factory() as session:
        principal = await PrincipalRepo(session).by_name("system")
        return principal.id if principal is not None else None


async def ensure_baseline(
    db: Database,
    settings: Settings,
    *,
    capabilities: Any = None,
    bus: Any = None,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Register the 111-employee baseline, idempotently.

    Returns a summary of what was created and what was already present, so a
    caller (and the startup log) can see that the baseline is intact without
    trusting a count alone.
    """
    summary: dict[str, Any] = {
        "created": 0, "skipped": 0, "departments_created": 0,
        "departments_skipped": 0, "grants_active": 0, "grants_pending": 0,
        "grants_refused": 0, "errors": [],
    }

    # Resolve the actor that attributes baseline grants. The capability service
    # records `granted_by` on the audit row, which is a principal FK - passing a
    # name like "system" would violate it. The system principal is created by
    # seed_core_data and is the natural attribution for an unattended seed.
    actor_id = actor_id or await _resolve_system_principal_id(db)

    # --- departments are seeded after all employees exist (the manager FK
    #     references an employee row), so the employee loop runs first.
    # The seed runs in the order the definitions are declared: CEO, managers,
    # specialists. Each employee is created in its own transaction-scoped
    # session via the repository, mirroring how the P-04 creation engine mints
    # an identity (one principal, one agent, lifecycle walked to ACTIVE).
    for definition in BASELINE_DEFINITIONS:
        employee_id = definition["employee_id"]
        async with db.session_factory() as session:
            from ..database.repositories import WorkforceEmployeeRepo
            existing = await WorkforceEmployeeRepo(session).get(employee_id)
        if existing is not None:
            summary["skipped"] += 1
            continue
        try:
            await _register_employee(db, settings, definition,
                                     capabilities=capabilities,
                                     bus=bus, actor_id=actor_id)
            summary["created"] += 1
        except Exception as exc:  # noqa: BLE001 - recorded, never aborts the baseline
            logger.exception("workforce baseline: failed to register %s", employee_id)
            summary["errors"].append({"employee_id": employee_id, "error": str(exc)})

    # --- departments (idempotent by code)
    async with db.session_factory() as session:
        from ..database.repositories import WorkforceDepartmentRepo
        dept_repo = WorkforceDepartmentRepo(session)
        for department in DEPARTMENTS:
            if await dept_repo.by_code(department["code"]) is not None:
                summary["departments_skipped"] += 1
                continue
            await dept_repo.create(
                code=department["code"], name=department["name"],
                manager_employee_id=department["manager_id"],
                mission=department["mission"])
            summary["departments_created"] += 1
        await session.commit()

    # Capability grants are counted from the catalog state for the baseline.
    if capabilities is not None:
        summary["grants_active"], summary["grants_pending"] = (
            await _count_baseline_grants(db, summary["created"]))
    return summary


async def _register_employee(
    db: Database, settings: Settings, definition: dict[str, Any], *,
    capabilities: Any, bus: Any, actor_id: str | None,
) -> None:
    """Mint one baseline employee: principal, registry row, profile, grants."""
    employee_id = definition["employee_id"]
    display_name = definition["display_name"]
    manager_id = definition.get("manager_employee_id")

    async with db.session_factory() as session:
        principals = PrincipalRepo(session)
        agents = AgentRepo(session)
        from ..database.repositories import WorkforceEmployeeRepo
        employees = WorkforceEmployeeRepo(session)

        # Principal: one per agent, unique by name. Reuse an existing principal
        # with the same name if a partial seed left one behind.
        principal = await principals.by_name(display_name)
        if principal is None:
            principal = await principals.create("agent", display_name)

        agent = await agents.create(
            agent_id=employee_id,
            principal_id=principal.id,
            name=display_name,
            role=definition["job_title"],
            status=AgentStatus.PROPOSED.value,
            metadata_json={
                "employee_id": employee_id,
                "department_code": definition["department_code"],
                "is_baseline": True,
                "workforce_seed": True,
            },
            parent_agent_id=manager_id,
        )
        # Walk the lifecycle rather than assigning ACTIVE: PROPOSED ->
        # INITIALIZING -> ACTIVE through the same transition graph the rest of
        # the system uses, so a baseline employee never appears in a state the
        # graph does not permit.
        for target in (AgentStatus.INITIALIZING, AgentStatus.ACTIVE):
            transition(agent.status, target.value)
            await agents.set_status(agent.id, target.value)
            agent.status = target.value

        await employees.create(
            employee_id=employee_id,
            display_name=display_name,
            department_code=definition["department_code"],
            department_name=definition["department_name"],
            job_title=definition["job_title"],
            role_description=definition["role_description"],
            primary_responsibilities=definition["responsibilities"],
            secondary_responsibilities=definition.get("secondary_responsibilities", []),
            manager_employee_id=manager_id,
            seniority=definition["seniority"],
            skills=definition["skills"],
            tool_access=definition["tool_access"],
            memory_scope=definition["memory_scope"],
            system_instructions=definition["system_instructions"],
            communication_style=definition.get("communication_style", "professional"),
            autonomy_level=definition["autonomy_level"],
            permission_scope=definition["permission_scope"],
            status="ACTIVE",
            is_baseline=True,
            is_expansion=False,
            current_assignments=[],
            last_activity=utcnow(),
            configuration_version=1,
        )
        # Commit the identity before leaving the session: the flushes above
        # are not a commit, and a session that closes without one rolls the
        # principal, agent and profile rows back - which is how a manager's
        # parent_agent_id FK then fails to find the CEO it was just created
        # against.
        await session.commit()

    # Grant the employee's capability scope through the existing capability
    # service. Prohibited capabilities are never in a baseline tool list, but
    # the check is here as a defence in depth: the catalog's PROHIBITED set is
    # consulted independently by the service, so a misconfigured tool list
    # cannot grant authority the system forbids.
    if capabilities is not None:
        for capability_key in definition["tool_access"]:
            if capability_key in PROHIBITED_CAPABILITIES:
                logger.warning(
                    "workforce baseline: %s lists prohibited capability %s; skipped",
                    employee_id, capability_key)
                continue
            try:
                await capabilities.grant(
                    employee_id, capability_key,
                    scope=definition["memory_scope"],
                    granted_by=actor_id,
                    reason=f"workforce baseline seed for {employee_id}",
                )
            except Exception as exc:  # noqa: BLE001 - a refused grant is recorded, not fatal
                logger.warning(
                    "workforce baseline: grant %s to %s refused: %s",
                    capability_key, employee_id, exc)


async def _count_baseline_grants(db: Database, created: int) -> tuple[int, int]:
    """Count active and pending capability grants held by baseline employees.

    Counting is direct rather than delegated so the summary reflects the
    database regardless of how many employees were created this run.
    """
    from sqlalchemy import select
    from ..database.models import Agent, AgentPermission
    async with db.session_factory() as session:
        rows = (await session.execute(
            select(AgentPermission.status)
            .join(Agent, Agent.id == AgentPermission.agent_id)
            .where(Agent.metadata_json["employee_id"].as_string() != "")
        )).scalars().all()
    active = sum(1 for s in rows if s == "active")
    pending = sum(1 for s in rows if s == "pending")
    return active, pending
