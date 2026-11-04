"""Owner-controlled global emergency stop.

Implements the P-01 portion of ``SECURITY_FOUNDATION.md`` §10 ("Emergency
controls"), which requires that a global emergency stop:

1. persists emergency mode,
2. stops new non-essential work,
3. cancels eligible work already in flight,
4. **survives restart**, and
5. **is never cleared automatically**.

Scope note: ``SECURITY_FOUNDATION.md`` §11 assigns the *restart-safe* emergency
state with lease fencing and duplicate-effect prevention to **P-12**. This module
is the foundation only — durable state, owner-only control and admission
blocking. It deliberately does not implement execution leases, because P-01 has
no external actions to fence.

State lives in the existing ``system_configurations`` table, so no schema
migration is required and the state is as durable as the database itself.

Single-process assumption: state is read from the database on every check rather
than trusted from an in-memory cache, so a stale process cannot believe an
emergency is over. The in-memory ``_state`` snapshot exists only to drive the
startup lifecycle decision and is refreshed by :meth:`load`.

The ``reason`` supplied by the owner is treated as untrusted free text: it is
persisted and returned to authorized callers, but never written into log
messages, so it cannot be used to smuggle secrets past log redaction.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..database.connection import Database
from ..database.repositories import AuditRepo, ConfigRepo
from ..events.bus import EventBus

logger = logging.getLogger(__name__)

CONFIG_KEY = "emergency_state"

# Audit/event names for the emergency control. Kept module-level so tests and
# documentation reference the same literals the code emits.
AUDIT_ACTIVATED = "emergency.activated"
AUDIT_DEACTIVATED = "emergency.deactivated"
AUDIT_BLOCKED = "task.emergency_blocked"
EVENT_ACTIVATED = "EmergencyActivated"
EVENT_DEACTIVATED = "EmergencyDeactivated"


def _blank_state() -> dict[str, Any]:
    """The canonical shape of a persisted emergency record.

    Every key is always present so consumers never need defensive ``.get``
    chaining, and a partially written record cannot be misread as inactive.
    """
    return {
        "active": False,
        "reason": None,
        "activated_at": None,
        "activated_by": None,
        "deactivated_at": None,
        "deactivated_by": None,
        "deactivate_reason": None,
    }


class EmergencyController:
    """Durable, owner-only global emergency stop."""

    def __init__(self, db: Database, bus: EventBus | None = None):
        self.db = db
        self.bus = bus
        self._state: dict[str, Any] = _blank_state()

    # --- reads -----------------------------------------------------------

    async def _read(self) -> dict[str, Any]:
        """Authoritative state, read from the database every time."""
        async with self.db.session_factory() as session:
            row = await ConfigRepo(session).get(CONFIG_KEY)
        return {**_blank_state(), **(row.value if row else {})}

    async def state(self) -> dict[str, Any]:
        return await self._read()

    async def is_active(self) -> bool:
        return bool((await self._read())["active"])

    async def load(self) -> dict[str, Any]:
        """Read persisted state at startup and refresh the in-memory snapshot.

        An emergency that was active when the process died is still active now:
        nothing here clears it, which is the "must not be cleared automatically"
        requirement.
        """
        self._state = await self._read()
        if self._state["active"]:
            # Reason deliberately omitted from the log record.
            logger.critical(
                "Emergency stop is ACTIVE (restored from persistent storage); "
                "non-essential task admission stays blocked until the owner clears it",
                extra={"component": "emergency"},
            )
        return dict(self._state)

    # --- writes ----------------------------------------------------------

    async def activate(self, principal_id: str, reason: str, correlation_id: str | None = None) -> dict[str, Any]:
        """Engage the emergency stop. Idempotent: re-activating is a no-op.

        Requires a non-empty reason so the audit trail records why the owner
        halted the system.
        """
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("A reason is required to activate the emergency stop")
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.session_factory() as session:
            repo = ConfigRepo(session)
            row = await repo.get(CONFIG_KEY)
            existing = {**_blank_state(), **(row.value if row else {})}
            if existing["active"]:
                await session.commit()
                self._state = existing
                return dict(existing)
            state = {
                **_blank_state(),
                "active": True,
                "reason": reason,
                "activated_at": now,
                "activated_by": principal_id,
            }
            await repo.set(CONFIG_KEY, state)
            await AuditRepo(session).record(
                AUDIT_ACTIVATED, "allowed", principal_id=principal_id, resource="system",
                action="emergency_activate", correlation_id=correlation_id, payload={"reason": reason},
            )
            await session.commit()
        self._state = state
        logger.critical("Emergency stop ACTIVATED by owner", extra={"component": "emergency", "correlation_id": correlation_id})
        if self.bus:
            await self.bus.publish_new(EVENT_ACTIVATED, "emergency", {"reason": reason}, severity="critical", correlation_id=correlation_id)
        return dict(state)

    async def deactivate(self, principal_id: str, reason: str, correlation_id: str | None = None) -> dict[str, Any]:
        """Clear the emergency stop. Idempotent, and only ever owner-invoked.

        There is no timer, no health-check path and no startup path that calls
        this: clearing requires an explicit authorized request.
        """
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("A reason is required to clear the emergency stop")
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.session_factory() as session:
            repo = ConfigRepo(session)
            row = await repo.get(CONFIG_KEY)
            existing = {**_blank_state(), **(row.value if row else {})}
            if not existing["active"]:
                await session.commit()
                self._state = existing
                return dict(existing)
            state = {
                **existing,
                "active": False,
                "deactivated_at": now,
                "deactivated_by": principal_id,
                "deactivate_reason": reason,
            }
            await repo.set(CONFIG_KEY, state)
            await AuditRepo(session).record(
                AUDIT_DEACTIVATED, "allowed", principal_id=principal_id, resource="system",
                action="emergency_deactivate", correlation_id=correlation_id, payload={"reason": reason},
            )
            await session.commit()
        self._state = state
        logger.warning("Emergency stop CLEARED by owner", extra={"component": "emergency", "correlation_id": correlation_id})
        if self.bus:
            await self.bus.publish_new(EVENT_DEACTIVATED, "emergency", {"reason": reason}, severity="warning", correlation_id=correlation_id)
        return dict(state)
