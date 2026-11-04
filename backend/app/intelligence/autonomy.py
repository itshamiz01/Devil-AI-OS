"""Autonomy levels (P-02 §15).

Separated from the decision engine on purpose: autonomy is a *security boundary*
about who may act, while decisions are about *what* to do. Keeping them apart
means the code that evaluates options has no access to the code that grants
execution authority.

§15's mandatory rule is enforced structurally here. Changing level requires an
owner authorization flag established outside this module, and there is no method
a model could call to raise the level. Levels 3 and 4 are declared only so the
boundary is explicit and refused by code rather than merely absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .schemas import EXECUTION_PERMITTED_LEVELS, UNIMPLEMENTED_LEVELS, AutonomyLevel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AutonomyEscalationError(RuntimeError):
    """Raised when a level change is attempted without owner authority."""


@dataclass
class AutonomyState:
    level: AutonomyLevel
    set_by_principal_id: str | None
    set_at: datetime
    reason: str


#: What each implemented level actually permits, for owner-facing reporting.
LEVEL_PERMISSIONS: dict[AutonomyLevel, tuple[str, ...]] = {
    AutonomyLevel.LEVEL_0_ADVISORY: (
        "answer questions",
        "analyse information",
        "generate recommendations",
        "create draft plans",
    ),
    AutonomyLevel.LEVEL_1_ASSISTED: (
        "prepare plans",
        "submit low-risk authorized tasks",
        "monitor progress",
        "request approval for restricted operations",
    ),
    AutonomyLevel.LEVEL_2_CONTROLLED: (
        "execute approved low-risk workflows",
        "coordinate registered capabilities",
        "retry permitted tasks",
        "replan after failures",
    ),
}


class AutonomyController:
    """Owns the autonomy level and who may change it.

    The default is Level 0 (advisory): the engine may analyse and recommend but
    may not submit execution tasks. Raising that is a deliberate owner act, and
    even at the highest implemented level the P-01 permission engine remains
    authoritative — a level never grants a permission the principal lacks.
    """

    def __init__(self, *, initial: AutonomyLevel = AutonomyLevel.LEVEL_0_ADVISORY) -> None:
        if initial in UNIMPLEMENTED_LEVELS:
            raise AutonomyEscalationError(
                f"autonomy level {initial.value} belongs to a future phase and is not "
                "implemented in P-02; it cannot be activated"
            )
        self._state = AutonomyState(
            level=initial, set_by_principal_id=None, set_at=_now(), reason="phase default"
        )
        self.history: list[AutonomyState] = [self._state]

    @property
    def level(self) -> AutonomyLevel:
        return self._state.level

    @property
    def state(self) -> AutonomyState:
        return self._state

    def may_submit_tasks(self) -> bool:
        """Whether the current level permits submitting execution tasks at all."""
        return self._state.level in EXECUTION_PERMITTED_LEVELS

    def may_replan_autonomously(self) -> bool:
        """Only Level 2 may replan without asking again (§15)."""
        return self._state.level == AutonomyLevel.LEVEL_2_CONTROLLED

    def may_retry_autonomously(self) -> bool:
        """Only Level 2 may retry without a fresh approval (§15)."""
        return self._state.level == AutonomyLevel.LEVEL_2_CONTROLLED

    def request_change(
        self,
        target: AutonomyLevel,
        *,
        principal_id: str,
        authorized_by_owner: bool,
        reason: str,
    ) -> AutonomyState:
        """Change level, or refuse explicitly.

        Refusals are never silent: §16 forbids quietly exceeding limits, and a
        quietly *downgraded* level would be just as misleading as an escalated
        one, so every outcome is recorded in `history`.
        """
        if not reason or not reason.strip():
            raise ValueError("an autonomy level change must record a reason")
        if target in UNIMPLEMENTED_LEVELS:
            raise AutonomyEscalationError(
                f"autonomy level {target.value} is a future-phase capability (P-12/P-13) "
                "and must not be activated in P-02"
            )
        if not authorized_by_owner:
            raise AutonomyEscalationError(
                f"autonomy level change to {target.value} was not authorized by the owner; "
                "a model may not upgrade its own autonomy"
            )
        if not principal_id:
            raise AutonomyEscalationError("an autonomy change must name the authorizing principal")

        self._state = AutonomyState(
            level=target,
            set_by_principal_id=principal_id,
            set_at=_now(),
            reason=reason.strip(),
        )
        self.history.append(self._state)
        return self._state

    def describe(self) -> dict[str, object]:
        """Owner-facing description of what the current level permits."""
        return {
            "level": self._state.level.value,
            "set_by": self._state.set_by_principal_id,
            "set_at": self._state.set_at.isoformat(),
            "reason": self._state.reason,
            "permits": list(LEVEL_PERMISSIONS.get(self._state.level, ())),
            "may_submit_tasks": self.may_submit_tasks(),
            "may_retry_autonomously": self.may_retry_autonomously(),
            "may_replan_autonomously": self.may_replan_autonomously(),
            "note": (
                "The permission engine remains authoritative regardless of this level; "
                "a higher autonomy level never grants a permission the principal lacks."
            ),
        }


__all__ = [
    "AutonomyController",
    "AutonomyEscalationError",
    "AutonomyState",
    "LEVEL_PERMISSIONS",
]
