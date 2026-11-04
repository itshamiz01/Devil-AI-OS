from __future__ import annotations

import fnmatch
import logging

from ..core.exceptions import ForbiddenError, UnauthorizedError
from ..database.connection import Database
from ..database.repositories import AuditRepo, PrincipalRepo, PermissionRepo

logger = logging.getLogger(__name__)


class PermissionEngine:
    def __init__(self, db: Database):
        self.db = db

    async def _evaluate(self, principal_id: str, permission: str, resource: str) -> tuple[bool, bool]:
        """Return ``(granted, principal_is_usable)``. Read-only: writes nothing.

        The single place the allow/deny/scope predicate lives, so ``check`` and
        ``is_granted`` cannot drift apart. A caller that asks a question must get
        the same answer as a caller that is being enforced.
        """
        async with self.db.session_factory() as session:
            principal = await PrincipalRepo(session).get(principal_id)
            if not principal or not principal.active:
                return False, False
            assignments = await PermissionRepo(session).assignments(principal_id)
            denied = any(a.effect == "deny" and a.permission_code == permission and fnmatch.fnmatchcase(resource, a.resource_scope) for a in assignments)
            allowed = any(a.effect == "allow" and a.permission_code == permission and fnmatch.fnmatchcase(resource, a.resource_scope) for a in assignments)
            return (allowed and not denied), True

    async def is_granted(self, principal_id: str | None, permission: str, resource: str = "*") -> bool:
        """Answer a permission question without enforcing or auditing it.

        Needed by components that must branch on what a principal *could*
        authorize rather than refuse it: the P-04 creation engine uses it to tell
        an owner-initiated gated creation (whose requester already holds the
        deciding authority) from an agent-initiated one. ``check`` would answer
        the same question by raising, and would write a ``permission.denied``
        audit row for a probe nobody was refused, so it is the wrong tool here.
        """
        if not principal_id:
            return False
        granted, _usable = await self._evaluate(principal_id, permission, resource)
        return granted

    async def check(self, principal_id: str | None, permission: str, resource: str = "*", correlation_id: str | None = None) -> None:
        if not principal_id:
            raise UnauthorizedError("Authentication required")
        granted, usable = await self._evaluate(principal_id, permission, resource)
        if not usable:
            raise UnauthorizedError("Principal is inactive or unknown")
        if not granted:
            async with self.db.session_factory() as session:
                await AuditRepo(session).record("permission.denied", "denied", principal_id=principal_id, resource=resource, action=permission, correlation_id=correlation_id, payload={"permission": permission})
                await session.commit()
            raise ForbiddenError("Permission denied", {"permission": permission, "resource": resource})

    async def grant_owner_permissions(self, principal_id: str) -> None:
        from .policies import OWNER_PERMISSIONS
        async with self.db.session_factory() as session:
            repo = PermissionRepo(session)
            for code in OWNER_PERMISSIONS:
                await repo.assign(principal_id, code)
            await AuditRepo(session).record("permission.owner_granted", "allowed", principal_id=principal_id, action="grant_owner_permissions")
            await session.commit()
