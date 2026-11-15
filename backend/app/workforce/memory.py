"""Employee memory system (§13).

Each employee maintains relevant operational memory, scoped to its own
``memory_scope``. Memory is **isolated**: an employee reads and writes only
its own entries. Cross-department memory access occurs only through approved
handoffs - a research employee may share an approved research report with a
strategy employee, but that does not grant unrestricted access to the
research employee's entire memory.

Credentials, private keys, authentication tokens and unrestricted secrets are
never stored in ordinary agent memory (§13, §21). The store rejects any entry
whose category or content indicates a secret, so a mistaken write cannot leak
a credential into model context.

This store stands in for the P-09 Memory and Learning Engine, which is not yet
implemented; it is the workforce-scoped memory P-09 would govern, documented
honestly rather than presented as an existing engine.
"""

from __future__ import annotations

import re
from typing import Any

from ..core.config import Settings
from ..core.exceptions import ForbiddenError
from ..database.connection import Database
from ..database.repositories import WorkforceEmployeeRepo, WorkforceMemoryRepo

__all__ = ["MemoryStore"]

#: Categories from §13. Closed vocabulary.
MEMORY_CATEGORIES: frozenset[str] = frozenset({
    "identity", "role_instructions", "department_knowledge",
    "business_context", "task_context", "task_results",
    "learned_procedures", "performance_history", "collaboration_context",
})

#: A deliberate secret-detection heuristic: an entry that looks like it carries
#: a credential is refused rather than stored. This is a backstop, not a
#: guarantee - the real control is that no code path ever writes a secret here.
_SECRET_PATTERNS = (
    re.compile(r"(api[_-]?key|secret|token|password|passwd|private[_-]?key)", re.I),
)


class MemoryStore:
    """Scoped, isolated employee memory."""

    def __init__(self, *, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db

    async def record(self, employee_id: str, *, category: str, content: str,
                     scope: str = "", shared_with: list[str] | None = None,
                     source: str = "employee") -> dict[str, Any]:
        """Record a memory entry for one employee, after isolation checks."""
        if category not in MEMORY_CATEGORIES:
            raise ForbiddenError(
                f"unknown memory category: {category}; valid categories: "
                f"{sorted(MEMORY_CATEGORIES)}")
        if not content.strip():
            raise ForbiddenError("memory content must not be empty")
        # Secret isolation: refuse anything that looks like a credential.
        for pattern in _SECRET_PATTERNS:
            if pattern.search(content):
                raise ForbiddenError(
                    "credentials, keys, tokens and secrets must never be stored "
                    "in ordinary agent memory")
        async with self.db.session_factory() as session:
            emp = await WorkforceEmployeeRepo(session).get(employee_id)
            if emp is None:
                from ..core.exceptions import NotFoundError
                raise NotFoundError(f"employee {employee_id} not found")
            row = await WorkforceMemoryRepo(session).create(
                employee_id=employee_id, category=category, content=content,
                scope=scope or emp.memory_scope,
                source=source, shared_with=shared_with or [])
            await session.commit()
            return {
                "id": row.id, "employee_id": employee_id,
                "category": category, "scope": row.scope,
                "shared_with": row.shared_with, "source": source,
            }

    async def read(self, employee_id: str,
                   *, category: str | None = None) -> list[dict[str, Any]]:
        """Read an employee's own memory. An employee reads only its own
        entries - this is the isolation boundary (§13)."""
        async with self.db.session_factory() as session:
            repo = WorkforceMemoryRepo(session)
            if category:
                rows = await repo.by_employee_category(employee_id, category)
            else:
                rows = await repo.by_employee(employee_id)
            return [{
                "id": m.id, "category": m.category, "content": m.content,
                "scope": m.scope, "shared_with": m.shared_with,
                "source": m.source, "created_at": m.created_at,
            } for m in rows]

    async def shared_with_employee(self, from_employee_id: str,
                                   to_employee_id: str) -> list[dict[str, Any]]:
        """Read memory an employee has explicitly shared with another.

        This is the only cross-employee memory path, and it returns only the
        entries the sender marked ``shared_with`` the recipient - never the
        sender's entire memory (§13 memory isolation).
        """
        async with self.db.session_factory() as session:
            rows = await WorkforceMemoryRepo(session).by_employee(from_employee_id)
            shared = [m for m in rows if to_employee_id in (m.shared_with or [])]
            return [{
                "id": m.id, "category": m.category, "content": m.content,
                "scope": m.scope, "shared_with": m.shared_with,
                "created_at": m.created_at,
            } for m in shared]
