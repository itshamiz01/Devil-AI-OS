"""Emergency stop, safe mode and financial suspension (§20/§16.6).

The current mode lives in the owner-governed ``security.settings``
document; every transition is written through the facade's versioned
policy path AND recorded as an append-only emergency event. Only
the owner may change the mode (§20.5: recovery authority) — the
service-level check here does not trust the API layer to have
checked.

What a transition does (and does not) do, honestly: enforcement
lives at the P-10 authorization layer — the broker's mode gate,
capability issuance, the secret broker and the financial guard all
read the current mode on every call, so a transition takes effect
immediately for everything P-10 governs. P-05's execution engine
keeps its own internal emergency stop (P-05 policy check #10);
P-10 does not reach inside it. Audit records are never touched by
any transition (§20.1 rule 7).
"""
from __future__ import annotations

from ..core.exceptions import PermissionDeniedError
from ..database.models.security import SecurityEmergencyEvent
from ..database.repositories.security import EmergencyEventRepository
from ..permissions.models import Principal
from . import constants as C
from . import policy as P


def emergency_event_to_dict(row: SecurityEmergencyEvent) -> dict:
    return {
        "id": row.id, "from_mode": row.from_mode, "to_mode": row.to_mode,
        "financial_suspension": row.financial_suspension,
        "actor": row.actor, "reason": row.reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class EmergencyService:
    def __init__(self, session_factory, get_settings, apply_settings, audit):
        """``apply_settings(principal, patch, reason)`` is the facade's
        versioned policy-write path; transitions go through it so a
        mode change is a policy version like any other (§23.3)."""
        self._session_factory = session_factory
        self._get_settings = get_settings
        self._apply_settings = apply_settings
        self._audit = audit

    def current_mode(self) -> str:
        try:
            mode = self._get_settings().get("mode", C.MODE_SAFE)
        except Exception:
            return C.MODE_SAFE  # unreadable policy fails closed (§20.3)
        return mode if mode in C.MODES else C.MODE_SAFE

    def financial_suspended(self) -> bool:
        try:
            return bool(self._get_settings().get("financial_suspension", False))
        except Exception:
            return True  # unreadable policy: financial actions suspended

    def set_mode(self, principal: Principal, mode: str,
                 reason: str | None = None) -> dict:
        if not P.is_owner(principal):
            raise PermissionDeniedError(
                "security mode changes are owner-only (§20.5)",
                details={"error_category": "EMERGENCY_OWNER_ONLY"})
        if mode not in C.MODES:
            raise PermissionDeniedError(  # validated again at the policy layer
                f"unknown security mode '{mode}'",
                details={"error_category": "MODE_INVALID"})
        previous = self.current_mode()
        settings = self._apply_settings(principal, {"mode": mode},
                                        reason or f"security mode -> {mode}")
        self._record(principal, previous, mode,
                     bool(settings.get("financial_suspension")), reason)
        self._audit(principal, "security.mode_changed", "security", "mode",
                    "allow", reason or f"mode {previous} -> {mode}",
                    {"from_mode": previous, "to_mode": mode})
        return {"mode": mode, "previous_mode": previous,
                "financial_suspension": bool(settings.get("financial_suspension"))}

    def set_financial_suspension(self, principal: Principal, suspended: bool,
                                 reason: str | None = None) -> dict:
        if not P.is_owner(principal):
            raise PermissionDeniedError(
                "financial suspension is owner-only (§16.6)",
                details={"error_category": "EMERGENCY_OWNER_ONLY"})
        mode = self.current_mode()
        settings = self._apply_settings(
            principal, {"financial_suspension": bool(suspended)},
            reason or f"financial_suspension -> {suspended}")
        self._record(principal, mode, mode, bool(suspended), reason)
        self._audit(principal, "security.financial_suspension_changed",
                    "security", "financial_suspension", "allow",
                    reason or f"financial_suspension -> {suspended}", {})
        return {"mode": mode, "financial_suspension": bool(suspended)}

    def _record(self, principal, from_mode, to_mode, fin_susp, reason) -> None:
        session = self._session_factory()
        try:
            EmergencyEventRepository(session).add(SecurityEmergencyEvent(
                from_mode=from_mode, to_mode=to_mode,
                financial_suspension=fin_susp, actor=P.actor(principal),
                reason=reason))
        finally:
            session.close()

    def list_events(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        session = self._session_factory()
        try:
            rows, total = EmergencyEventRepository(session).list(
                limit=limit, offset=offset)
            return [emergency_event_to_dict(r) for r in rows], total
        finally:
            session.close()
