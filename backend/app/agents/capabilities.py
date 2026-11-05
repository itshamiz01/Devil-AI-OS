"""The capability catalog and the only place a capability is granted or denied
(P-04 Stage 5).

A capability is a named authority an agent may hold. This module owns three
things: the catalog of what exists, the four-level authority model that decides
what it takes to hold one, and the check that answers "may this agent do this?"
— the same check Stage 6 will call at every tool boundary.

The catalog itself — what exists, at what risk and level — lives in
:mod:`app.agents.catalog`, which is data. This module is the authority: it
reconciles that catalog into the database, grants and revokes against it, and
answers the boundary question. Two properties of the catalog matter here and are
enforced here rather than trusted: it is defined in code with no endpoint that
can edit it, and the level-3 prohibition list is consulted independently of any
database row, so no edit to a row can make a prohibited capability grantable.

The four levels are the ones the P-04 design fixes:

=====  ==================  =====================================================
Level  Name                What it takes
=====  ==================  =====================================================
L0     autonomous          policy allows it; the grant is audited
L1     conditional         conditions checked in code must hold
L2     owner approval      an `approvals` row must reach `granted` first
L3     prohibited          refused unconditionally; no approval path exists
=====  ==================  =====================================================

Two rules apply at every level, because a rule that applies only at one level is
a rule that can be stepped around by choosing another:

* **No self-grant.** The principal an agent acts as may not grant a capability to
  that agent. An agent widening its own authority is the failure the whole phase
  is built to prevent, and at level 2 the same intent is caught a second time by
  the central self-approval block, because the approval is opened at risk `high`.
* **A suspended, failed, retiring or retired agent holds no authority.** Grants
  are refused to it and `check()` denies it, so suspending an agent stops it
  using what it already holds rather than merely stopping new work.

`check()` deliberately does **not** consult the emergency stop. The stop already
governs admission through the task manager, and a second mechanism answering the
same question with different semantics would leave two authorities and no way to
tell which one refused. Grants *are* blocked during an emergency — expanding
authority while the owner has halted the system is not a read — but revocation
never is, because taking authority away is exactly what an emergency calls for.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from ..core.config import Settings
from ..core.exceptions import (
    ConflictError,
    EmergencyBlockedError,
    ForbiddenError,
    NotFoundError,
)
from ..database.connection import Database
from ..database.models import utcnow
from ..database.repositories import (
    AgentCapabilityRepo,
    AgentPermissionRepo,
    AgentRepo,
    AuditRepo,
)
from .governance import (
    CAPABILITY_APPROVAL_ACTION,
    ProhibitedCapabilityError,
    approval_risk_for,
    describe_level,
    open_capability_approval,
    requires_owner_approval,
)
from .catalog import (
    AUTHORITYLESS_AGENT_STATES,
    BUILTIN_CATALOG,
    PROHIBITED_CAPABILITIES,
    UNGRANTABLE_AGENT_STATES,
)
from .schemas import (
    AGENT_PERMISSION_STATUSES,
    APPROVAL_LEVELS,
    ApprovalLevel,
)

__all__ = [
    "AUTHORITYLESS_AGENT_STATES",
    "BUILTIN_CATALOG",
    "PROHIBITED_CAPABILITIES",
    "UNGRANTABLE_AGENT_STATES",
    "AgentNotGrantableError",
    "CapabilityConditionsUnmetError",
    "CapabilityDeniedError",
    "CapabilityDisabledError",
    "CapabilityNotFoundError",
    "CapabilityService",
    "CheckResult",
    "GrantResult",
    "register_capability_approval_subscribers",
]

# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class CapabilityNotFoundError(NotFoundError):
    code = "capability_not_found"


class CapabilityDisabledError(ConflictError):
    code = "capability_disabled"


class CapabilityDeniedError(ForbiddenError):
    """A grant refused for a governance reason rather than a missing capability."""

    code = "capability_denied"


class AgentNotGrantableError(ConflictError):
    code = "agent_not_grantable"


class CapabilityConditionsUnmetError(ConflictError):
    code = "capability_conditions_unmet"


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
@dataclass
class GrantResult:
    permission_id: str
    capability_key: str
    capability_id: str
    approval_level: int
    status: str
    scope: str
    reason: str
    approval_id: str | None = None
    replayed: bool = False
    conditions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "permission_id": self.permission_id, "capability_key": self.capability_key,
            "capability_id": self.capability_id, "approval_level": self.approval_level,
            "level_description": describe_level(self.approval_level),
            "status": self.status, "scope": self.scope, "reason": self.reason,
            "approval_id": self.approval_id, "replayed": self.replayed,
            "conditions": list(self.conditions),
        }


@dataclass
class CheckResult:
    """The answer at a boundary. Never raises: a denial is a result."""

    allowed: bool
    capability_key: str
    reason: str
    permission_id: str | None = None
    approval_level: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "capability_key": self.capability_key,
                "reason": self.reason, "permission_id": self.permission_id,
                "approval_level": self.approval_level}


def _aware(moment: datetime) -> datetime:
    """A datetime that can be compared with ``utcnow()``.

    SQLite hands back naive datetimes, so comparing a stored expiry with an aware
    "now" raises instead of answering - and a boundary that raises turns a denial
    into an outage. A naive value is treated as UTC, which is what it was written
    as. The approval service normalises the same way for the same reason.
    """
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


class CapabilityService:
    """Grants, revokes and answers the boundary question."""

    def __init__(self, db: Database, settings: Settings, approvals: Any = None,
                 bus: Any = None, emergency: Any = None) -> None:
        self.db = db
        self.settings = settings
        self.approvals = approvals
        self.bus = bus
        self.emergency = emergency

    # ------------------------------------------------------------------ #
    # Catalog
    # ------------------------------------------------------------------ #
    async def reconcile_catalog(self, correlation_id: str | None = None) -> dict[str, Any]:
        """Write `BUILTIN_CATALOG` into the table, and report what changed.

        Additive and corrective, never destructive: an entry that is no longer in
        the catalog is left alone rather than deleted, because grants may point at
        it and deleting a capability out from under an existing grant would make
        the grant unreadable. An event is published only when something actually
        changed, so a normal startup stays quiet.
        """
        created, updated, unchanged = [], [], []
        async with self.db.session_factory() as session:
            repo = AgentCapabilityRepo(session)
            for definition in BUILTIN_CATALOG:
                row = await repo.by_key(definition.capability_key)
                if row is None:
                    await repo.upsert_definition(**definition.model_dump())
                    created.append(definition.capability_key)
                    continue
                changed = [
                    field for field, value in definition.model_dump().items()
                    if field != "capability_key" and getattr(row, field) != value
                ]
                if changed:
                    await repo.upsert_definition(**definition.model_dump())
                    updated.append({"capability_key": definition.capability_key,
                                    "fields": changed})
                else:
                    unchanged.append(definition.capability_key)
            if created or updated:
                await AuditRepo(session).record(
                    "capability.catalog_reconciled", "allowed",
                    action="reconcile_capability_catalog",
                    payload={"created": created, "updated": updated})
            await session.commit()
        if created or updated:
            await self._emit("CapabilityCatalogChanged", {
                "created": created, "updated": updated,
                "unchanged_count": len(unchanged)}, correlation_id)
        return {"created": created, "updated": updated,
                "unchanged_count": len(unchanged),
                "catalog_size": len(BUILTIN_CATALOG)}

    async def list_capabilities(self, *, category: str | None = None,
                                risk_level: str | None = None,
                                approval_level: int | None = None,
                                enabled: bool | None = None,
                                limit: int = 100, offset: int = 0):
        async with self.db.session_factory() as session:
            repo = AgentCapabilityRepo(session)
            rows = await repo.list(limit, offset, category=category,
                                   risk_level=risk_level, approval_level=approval_level,
                                   enabled=enabled)
            total = await repo.count(category=category, risk_level=risk_level,
                                     approval_level=approval_level, enabled=enabled)
        return rows, total

    async def get_capability(self, capability_key: str):
        async with self.db.session_factory() as session:
            return await AgentCapabilityRepo(session).by_key(capability_key)

    async def list_permissions(self, agent_id: str, *, status: str | None = None,
                               limit: int = 200, offset: int = 0):
        """Grants for one agent, with the capability key resolved alongside."""
        async with self.db.session_factory() as session:
            grants = await AgentPermissionRepo(session).for_agent(
                agent_id, status=status, limit=limit, offset=offset)
            repo = AgentCapabilityRepo(session)
            keys = await repo.keys_by_ids([g.capability_id for g in grants])
            total = await AgentPermissionRepo(session).count_for_agent(agent_id, status)
        # Keyed by capability_id, which is what the batch lookup returns; a grant
        # whose capability row has gone reads as None rather than raising, so one
        # unreadable row cannot make an agent's whole authority list unreadable.
        return [(g, keys.get(g.capability_id)) for g in grants], total

    # ------------------------------------------------------------------ #
    # Granting
    # ------------------------------------------------------------------ #
    async def grant(self, agent_id: str, capability_key: str, *, scope: str = "",
                    granted_by: str | None = None, reason: str = "",
                    expires_at: datetime | None = None,
                    correlation_id: str | None = None) -> GrantResult:
        """Grant one capability to one agent, or refuse and say why.

        Refusals raise rather than returning a result: a prohibition, a
        self-grant and an unmet condition are errors a caller must not be able to
        ignore, unlike the boundary question in `check()`, where a denial is an
        ordinary answer.
        """
        conditions: list[str] = []
        if self.emergency is not None and await self.emergency.is_active():
            raise EmergencyBlockedError(
                "capabilities cannot be granted while the emergency stop is active")

        async with self.db.session_factory() as session:
            agent = await AgentRepo(session).get(agent_id)
        if agent is None:
            raise NotFoundError("Agent not found")

        # The code-level list is consulted before the row exists, so a missing or
        # edited row cannot make a prohibited capability grantable.
        if capability_key in PROHIBITED_CAPABILITIES:
            definition = next((c for c in BUILTIN_CATALOG
                               if c.capability_key == capability_key), None)
            why = definition.prohibited_reason if definition else (
                "the capability is on the code-level prohibition list")
            await self._refuse(agent_id, capability_key, granted_by,
                               f"prohibited at level 3: {why}", correlation_id,
                               level=int(ApprovalLevel.PROHIBITED))
            raise ProhibitedCapabilityError(
                f"{capability_key} is prohibited and cannot be granted at any "
                "approval level",
                {"capability_key": capability_key, "approval_level": 3,
                 "prohibited_reason": why})

        async with self.db.session_factory() as session:
            capability = await AgentCapabilityRepo(session).by_key(capability_key)
        if capability is None:
            raise CapabilityNotFoundError(
                f"capability '{capability_key}' is not in the catalog",
                {"capability_key": capability_key,
                 "hint": "the catalog is defined in code; adding one is a code change"})
        if int(capability.approval_level) == int(ApprovalLevel.PROHIBITED):
            await self._refuse(agent_id, capability_key, granted_by,
                               "the catalog records this capability at level 3",
                               correlation_id, level=3)
            raise ProhibitedCapabilityError(
                f"{capability_key} is recorded at approval level 3",
                {"capability_key": capability_key,
                 "prohibited_reason": capability.prohibited_reason})
        if not capability.enabled:
            await self._refuse(agent_id, capability_key, granted_by,
                               "the capability is disabled", correlation_id,
                               level=int(capability.approval_level))
            raise CapabilityDisabledError(
                f"{capability_key} is disabled: {capability.description}",
                {"capability_key": capability_key})
        if agent.status in UNGRANTABLE_AGENT_STATES:
            raise AgentNotGrantableError(
                f"the agent is {agent.status} and may not hold new capabilities",
                {"agent_id": agent_id, "status": agent.status})
        if granted_by and granted_by == agent.principal_id:
            await self._refuse(agent_id, capability_key, granted_by,
                               "an agent may not grant a capability to itself",
                               correlation_id, level=int(capability.approval_level))
            raise CapabilityDeniedError(
                "an agent may not grant a capability to itself",
                {"agent_id": agent_id, "capability_key": capability_key,
                 "granted_by": granted_by})

        async with self.db.session_factory() as session:
            repo = AgentPermissionRepo(session)
            existing = await repo.find(agent_id, capability.id, scope)
        if existing is not None:
            return GrantResult(
                permission_id=existing.id, capability_key=capability_key,
                capability_id=capability.id,
                approval_level=int(existing.approval_level), status=existing.status,
                scope=existing.scope, replayed=True,
                reason=(f"a {existing.status} grant of this capability at this scope "
                        "already exists; nothing new was created"),
                approval_id=existing.approval_id, conditions=conditions)

        if capability.requires_scope and not scope.strip():
            raise CapabilityConditionsUnmetError(
                f"{capability_key} must be granted with a non-empty scope",
                {"capability_key": capability_key, "scope": scope})
        conditions.append("scope requirement satisfied" if capability.requires_scope
                          else "capability requires no scope")

        ceiling = self.settings.agent_max_active_capabilities
        async with self.db.session_factory() as session:
            active = await AgentPermissionRepo(session).count_for_agent(agent_id, "active")
        if active >= ceiling:
            raise CapabilityConditionsUnmetError(
                f"the agent already holds {active} active capabilities and the "
                f"ceiling is {ceiling}",
                {"agent_id": agent_id, "active": active, "ceiling": ceiling})
        conditions.append(f"{active}/{ceiling} active capabilities held")

        level = int(capability.approval_level)
        if requires_owner_approval(level):
            if self.approvals is None:
                await self._refuse(agent_id, capability_key, granted_by,
                                   "owner approval is required but no approval "
                                   "service is available", correlation_id, level=level)
                raise CapabilityDeniedError(
                    f"{capability_key} needs owner approval and no approval service "
                    "is available; it was refused rather than granted ungated",
                    {"capability_key": capability_key, "approval_level": level})
            # The approval is opened *before* the grant row, so a crash between
            # the two leaves an approval with no grant rather than a grant with no
            # approval. Failing toward not-granting is the only safe direction.
            # The requester recorded on the approval is the agent that would hold
            # the authority, not the actor asking for it. The actor travels in the
            # approval's parameters - and so is bound into its payload hash - and
            # is recorded on the grant's audit row; the approvals table stores no
            # parameters column, so it is the audit trail and the event, not the
            # approval row, that names who asked. This is deliberate and it is load-bearing. The approval opens at
            # risk high, and the approval service forbids a requester deciding
            # their own high-risk approval. Only the owner holds `approvals.decide`
            # and it is not a system permission, so recording the actor as the
            # requester would make an owner-requested level-2 grant undecidable by
            # anybody: pending forever, with no way to reach it.
            approval = await open_capability_approval(
                self.approvals,
                requester_id=agent.principal_id or granted_by or "system",
                capability_key=capability_key,
                resource=f"agent_permission:{agent_id}:{capability_key}:{scope or '*'}",
                reason=reason or f"grant {capability_key} to agent {agent_id}",
                approval_level=level, agent_id=agent_id, scope=scope,
                granted_by=granted_by, correlation_id=correlation_id)
            conditions.append(f"owner approval opened at risk "
                              f"{approval_risk_for(level)}")
            result = await self._write_grant(
                agent_id, capability.id, capability_key, scope, level,
                status="pending", approval_id=approval.id, expires_at=expires_at,
                granted_by=granted_by, correlation_id=correlation_id,
                conditions=conditions,
                reason=f"level 2 requires the owner's decision; the grant is pending "
                       f"approval {approval.id}")
            result.approval_id = approval.id
            await self._emit("AgentCapabilityApprovalRequested", {
                "agent_id": agent_id, "capability_key": capability_key,
                "permission_id": result.permission_id, "approval_id": approval.id,
                "scope": scope, "approval_level": level,
                # The approval row names the beneficiary as its requester, so the
                # event is what carries the actor. Without it the stream would show
                # authority being requested with nobody attributed to the request.
                "requested_by": granted_by}, correlation_id)
            return result

        conditions.append(describe_level(level))
        result = await self._write_grant(
            agent_id, capability.id, capability_key, scope, level, status="active",
            expires_at=expires_at, granted_by=granted_by,
            correlation_id=correlation_id, conditions=conditions,
            reason=f"{describe_level(level)}; no owner approval is required")
        await self._emit("AgentCapabilityGranted", {
            "agent_id": agent_id, "capability_key": capability_key,
            "permission_id": result.permission_id, "scope": scope,
            "approval_level": level}, correlation_id)
        return result

    async def _write_grant(self, agent_id: str, capability_id: str, capability_key: str,
                           scope: str, level: int, *, status: str,
                           approval_id: str | None = None,
                           expires_at: datetime | None = None,
                           granted_by: str | None, correlation_id: str | None,
                           conditions: Sequence[str], reason: str) -> GrantResult:
        async with self.db.session_factory() as session:
            row = await AgentPermissionRepo(session).create(
                agent_id=agent_id, capability_id=capability_id, scope=scope,
                approval_level=level, status=status, approval_id=approval_id,
                expires_at=expires_at)
            await AuditRepo(session).record(
                "capability.granted" if status == "active" else "capability.pending",
                "allowed", principal_id=granted_by, resource=row.id,
                action=CAPABILITY_APPROVAL_ACTION, correlation_id=correlation_id,
                payload={"agent_id": agent_id, "capability_key": capability_key,
                         "scope": scope, "approval_level": level, "status": status,
                         "approval_id": approval_id, "conditions": list(conditions),
                         "expires_at": expires_at.isoformat() if expires_at else None})
            await session.commit()
            return GrantResult(permission_id=row.id, capability_key=capability_key,
                               capability_id=capability_id, approval_level=level,
                               status=status, scope=scope, reason=reason,
                               approval_id=approval_id, conditions=list(conditions))

    async def _refuse(self, agent_id: str, capability_key: str, granted_by: str | None,
                      reason: str, correlation_id: str | None, *, level: int) -> None:
        """Record a refusal. No grant row is written.

        A refusal lives in the audit log and on the bus rather than in
        ``agent_permissions``: that table records authority an agent holds, and
        storing a denial there would make "what can this agent do?" a query that
        has to know which rows to ignore.
        """
        async with self.db.session_factory() as session:
            await AuditRepo(session).record(
                "capability.denied", "denied", principal_id=granted_by,
                resource=agent_id, action=CAPABILITY_APPROVAL_ACTION,
                correlation_id=correlation_id,
                payload={"agent_id": agent_id, "capability_key": capability_key,
                         "approval_level": level, "reason": reason})
            await session.commit()
        await self._emit("AgentCapabilityDenied", {
            "agent_id": agent_id, "capability_key": capability_key,
            "approval_level": level, "reason": reason}, correlation_id)

    # ------------------------------------------------------------------ #
    # Revocation and expiry
    # ------------------------------------------------------------------ #
    async def revoke(self, permission_id: str, *, revoked_by: str | None = None,
                     reason: str = "", correlation_id: str | None = None) -> dict[str, Any]:
        """Take a capability away. Never blocked by the emergency stop."""
        async with self.db.session_factory() as session:
            repo = AgentPermissionRepo(session)
            row = await repo.get(permission_id)
            if row is None:
                raise NotFoundError("capability grant not found")
            if row.status in ("revoked", "expired"):
                raise ConflictError(
                    f"the grant is already {row.status}",
                    {"permission_id": permission_id, "status": row.status})
            capability = await AgentCapabilityRepo(session).get(row.capability_id)
            key = capability.capability_key if capability else None
            await repo.set_status(permission_id, "revoked", revoked_at=utcnow())
            await AuditRepo(session).record(
                "capability.revoked", "allowed", principal_id=revoked_by,
                resource=permission_id, action=CAPABILITY_APPROVAL_ACTION,
                correlation_id=correlation_id,
                payload={"agent_id": row.agent_id, "capability_key": key,
                         "scope": row.scope, "reason": reason,
                         "previous_status": row.status})
            await session.commit()
            agent_id, scope = row.agent_id, row.scope
        await self._emit("AgentCapabilityRevoked", {
            "agent_id": agent_id, "capability_key": key, "permission_id": permission_id,
            "scope": scope, "reason": reason}, correlation_id)
        return {"permission_id": permission_id, "status": "revoked",
                "capability_key": key, "agent_id": agent_id}

    async def sweep_expired(self, correlation_id: str | None = None) -> dict[str, int]:
        """Mark grants past their expiry as expired, so a lapsed grant cannot be
        read as a live one by anything that queries the table directly."""
        now = utcnow()
        expired = 0
        async with self.db.session_factory() as session:
            repo = AgentPermissionRepo(session)
            rows = await repo.expirable(now)
            for row in rows:
                await repo.set_status(row.id, "expired")
                await AuditRepo(session).record(
                    "capability.expired", "allowed", resource=row.id,
                    action=CAPABILITY_APPROVAL_ACTION, correlation_id=correlation_id,
                    payload={"agent_id": row.agent_id,
                             "capability_id": row.capability_id,
                             "previous_status": row.status,
                             "expires_at": row.expires_at.isoformat()
                             if row.expires_at else None})
                expired += 1
            await session.commit()
        return {"expired": expired}

    # ------------------------------------------------------------------ #
    # The boundary question
    # ------------------------------------------------------------------ #
    async def check(self, agent_id: str, capability_key: str, *,
                    scope: str = "") -> CheckResult:
        """May this agent exercise this capability at this scope?

        This is the single enforcement point Stage 6 will call at every tool
        boundary. It never raises: a denial is an ordinary answer, and a boundary
        that had to handle an exception would be a boundary that could be tempted
        to let the call through when one arrived.

        Scope matching uses the same ``fnmatch`` semantics as the P-01 permission
        engine, so a grant of ``*`` covers any scope and a grant of
        ``opportunity:12`` covers exactly that.
        """
        if capability_key in PROHIBITED_CAPABILITIES:
            return CheckResult(False, capability_key,
                               "prohibited at level 3; no grant can authorize it")
        now = utcnow()
        async with self.db.session_factory() as session:
            permissions = AgentPermissionRepo(session)
            capabilities = AgentCapabilityRepo(session)
            capability = await capabilities.by_key(capability_key)
            if capability is None:
                return CheckResult(False, capability_key,
                                   "the capability is not in the catalog")
            if int(capability.approval_level) == int(ApprovalLevel.PROHIBITED):
                return CheckResult(False, capability_key,
                                   "the catalog records this capability at level 3")
            if not capability.enabled:
                return CheckResult(False, capability_key, "the capability is disabled")
            agent = await AgentRepo(session).get(agent_id)
            if agent is None:
                return CheckResult(False, capability_key, "the agent does not exist")
            if agent.status in AUTHORITYLESS_AGENT_STATES:
                return CheckResult(
                    False, capability_key,
                    f"the agent is {agent.status} and holds no authority")
            lapsed = False
            for grant in await permissions.for_agent(agent_id, status="active"):
                if grant.capability_id != capability.id:
                    continue
                if grant.expires_at is not None and _aware(grant.expires_at) <= now:
                    await permissions.set_status(grant.id, "expired")
                    lapsed = True
                    continue
                if fnmatch.fnmatchcase(scope or "", grant.scope or "*"):
                    await session.commit()
                    return CheckResult(
                        True, capability_key,
                        f"an active grant at scope '{grant.scope}' covers this request",
                        permission_id=grant.id,
                        approval_level=int(grant.approval_level))
            await session.commit()
        if lapsed:
            # Distinguish "you never held this" from "what you held ran out". At a
            # boundary the two need different responses: one is a missing grant,
            # the other is a renewal, and only the second has a history to look at.
            return CheckResult(
                False, capability_key,
                "a grant of this capability had lapsed and was marked expired")
        return CheckResult(False, capability_key,
                           "no active grant covers this capability and scope")

    # ------------------------------------------------------------------ #
    # Approval completion
    # ------------------------------------------------------------------ #
    async def on_approval_granted(self, event: Any) -> None:
        await self._apply_approval(event.payload.get("approval_id"),
                                   event.correlation_id, granted=True)

    async def on_approval_rejected(self, event: Any) -> None:
        await self._apply_approval(event.payload.get("approval_id"),
                                   event.correlation_id, granted=False)

    async def _apply_approval(self, approval_id: str | None,
                              correlation_id: str | None, *, granted: bool) -> None:
        if not approval_id:
            return
        async with self.db.session_factory() as session:
            repo = AgentPermissionRepo(session)
            row = await repo.by_approval(approval_id)
            if row is None or row.status != "pending":
                return
            capability = await AgentCapabilityRepo(session).get(row.capability_id)
            key = capability.capability_key if capability else None
            agent_id, permission_id, scope = row.agent_id, row.id, row.scope
            if granted:
                await repo.set_status(permission_id, "active")
            else:
                await repo.set_status(permission_id, "revoked", revoked_at=utcnow())
            await AuditRepo(session).record(
                "capability.approval_" + ("granted" if granted else "rejected"),
                "allowed" if granted else "denied", resource=permission_id,
                action=CAPABILITY_APPROVAL_ACTION, correlation_id=correlation_id,
                payload={"agent_id": agent_id, "capability_key": key,
                         "approval_id": approval_id, "scope": scope})
            await session.commit()
        await self._emit("AgentCapabilityGranted" if granted else "AgentCapabilityRevoked",
                         {"agent_id": agent_id, "capability_key": key,
                          "permission_id": permission_id, "approval_id": approval_id,
                          "scope": scope,
                          "reason": ("the owner granted the approval" if granted
                                     else "the owner rejected the approval")},
                         correlation_id)

    # ------------------------------------------------------------------ #
    # Reporting
    # ------------------------------------------------------------------ #
    async def status(self) -> dict[str, Any]:
        """What the catalog holds and what the grants look like."""
        by_level = {int(level): 0 for level in APPROVAL_LEVELS}
        async with self.db.session_factory() as session:
            caps = AgentCapabilityRepo(session)
            permissions = AgentPermissionRepo(session)
            for level in APPROVAL_LEVELS:
                by_level[level] = await caps.count(approval_level=level)
            total = await caps.count()
            enabled = await caps.count(enabled=True)
            counted = await permissions.count_by_status()
            # Every status is reported, including the ones holding nothing: an
            # absent key would leave a reader guessing whether zero grants and
            # no grants recorded are the same answer.
            grants = {status: int(counted.get(status, 0))
                      for status in AGENT_PERMISSION_STATUSES}
            unexpected = sorted(set(counted) - set(AGENT_PERMISSION_STATUSES))
            if unexpected:
                # A status outside the vocabulary means a row the CHECK did not
                # catch, which is worth surfacing rather than silently dropping.
                grants["unexpected"] = {s: counted[s] for s in unexpected}
        return {
            "catalog_size": total,
            "enabled": enabled,
            "disabled": total - enabled,
            "by_approval_level": by_level,
            "prohibited_keys": sorted(PROHIBITED_CAPABILITIES),
            "catalog_is_code_defined": True,
            "max_active_capabilities_per_agent":
                self.settings.agent_max_active_capabilities,
            "grants_by_status": grants,
            "enforcement_note": (
                "check() is the single enforcement point, but no tool boundary "
                "calls it yet: adapters and the tool registry are P-05, and "
                "assignment output contracts are P-04 Stage 6"
            ),
        }

    async def _emit(self, event_type: str, payload: dict[str, Any],
                    correlation_id: str | None) -> None:
        if self.bus is None:
            return
        await self.bus.publish_new(event_type, "agent_capabilities", payload,
                                   correlation_id=correlation_id)


def register_capability_approval_subscribers(bus: Any, service: CapabilityService) -> None:
    """Route approval outcomes into pending capability grants.

    Separate from `register_default_subscribers` for the same reason as the task
    and creation-engine equivalents: it needs a service that does not exist when
    the bus is first attached. Each handler ignores approvals it did not open, by
    finding no grant row carrying that approval id.
    """
    bus.subscribe("ApprovalGranted", service.on_approval_granted)
    bus.subscribe("ApprovalRejected", service.on_approval_rejected)
