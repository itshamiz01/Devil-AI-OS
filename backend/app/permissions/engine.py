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

    async def check(self, principal_id: str | None, permission: str, resource: str = "*", correlation_id: str | None = None) -> None:
        if not principal_id:
            raise UnauthorizedError("Authentication required")
        async with self.db.session_factory() as session:
            principal = await PrincipalRepo(session).get(principal_id)
            if not principal or not principal.active:
                raise UnauthorizedError("Principal is inactive or unknown")
            assignments = await PermissionRepo(session).assignments(principal_id)
            denied = any(a.effect == "deny" and a.permission_code == permission and fnmatch.fnmatchcase(resource, a.resource_scope) for a in assignments)
            allowed = any(a.effect == "allow" and a.permission_code == permission and fnmatch.fnmatchcase(resource, a.resource_scope) for a in assignments)
            if denied or not allowed:
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
