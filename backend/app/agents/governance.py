"""Mapping P-04 approval levels onto the central approval service (Stage 5).

This module exists to prevent one specific failure: a component deciding for
itself what risk a capability carries, or opening its own approval-shaped record
instead of using `ApprovalService`. Every P-04 approval goes through the central
service, and the level-to-risk mapping lives here in exactly one place, so the
owner sees one approval queue rather than several that disagree.

The mapping is deliberately sparse:

============  ==========================  =====================================
Level         Meaning                     Approval
============  ==========================  =====================================
L0 autonomous policy allows it            none — the grant is audited
L1 conditional conditions hold in code    none — the conditions are the control
L2 owner      an approvals row must reach none until it does; opened at risk
   approval   `granted` first             `high`
L3 prohibited refused unconditionally     **no mapping exists**
============  ==========================  =====================================

Level 2 is opened at risk ``high`` on purpose. That is the risk level at which
`ApprovalService` refuses to let a requester decide its own approval, so an agent
cannot authorize a capability for itself — the same reason the creation engine
opens gated creations at ``high``.

Level 3 has no risk value, and asking for one raises. Returning a plausible risk
for a prohibited capability would create exactly the approval path the
prohibition exists to remove, and a caller could then reach "granted" by
persuading an owner to click the wrong thing. Raising makes that impossible to
do by accident.
"""

from __future__ import annotations

from typing import Any

from ..core.exceptions import AppError, ForbiddenError
from ..permissions.models import ApprovalCreateRequest
from .schemas import ApprovalLevel

__all__ = [
    "CAPABILITY_APPROVAL_ACTION",
    "OWNER_APPROVAL_RISK",
    "ProhibitedCapabilityError",
    "approval_risk_for",
    "describe_level",
    "open_capability_approval",
    "requires_owner_approval",
]

#: The approval action recorded for a capability grant. Distinct from the
#: creation engine's ``agent.create`` so an owner can tell the two kinds of
#: authority apart in one queue.
CAPABILITY_APPROVAL_ACTION = "agent.capability.grant"

#: The risk every owner-approval-level grant is opened at. See the module
#: docstring: this is what engages the self-approval block.
OWNER_APPROVAL_RISK = "high"

_LEVEL_DESCRIPTIONS = {
    ApprovalLevel.AUTONOMOUS: "L0 autonomous: policy allows it and the grant is audited",
    ApprovalLevel.CONDITIONAL: "L1 conditional: allowed only while conditions checked in code hold",
    ApprovalLevel.OWNER_APPROVAL: "L2 owner approval: an approvals row must reach granted first",
    ApprovalLevel.PROHIBITED: "L3 prohibited: refused unconditionally, with no approval path",
}


class ProhibitedCapabilityError(ForbiddenError):
    """A level-3 capability was asked for through a path that cannot serve it.

    Subclasses ``ForbiddenError``, so it is a **403**: the principal may well hold
    ``agents.permissions.grant``, and the refusal is about the capability rather
    than the caller. It carries its own code so a reader can tell a prohibition
    from an ordinary permission denial.
    """

    code = "capability_prohibited"


def describe_level(level: int | ApprovalLevel) -> str:
    """The plain-language meaning of a level, for reasons and API responses."""
    return _LEVEL_DESCRIPTIONS[ApprovalLevel(int(level))]


def requires_owner_approval(level: int | ApprovalLevel) -> bool:
    return ApprovalLevel(int(level)) is ApprovalLevel.OWNER_APPROVAL


def approval_risk_for(level: int | ApprovalLevel) -> str | None:
    """The ``approvals.risk`` a grant at this level is opened with.

    ``None`` means the level opens no approval at all (L0 and L1). Level 3
    **raises** rather than returning a value: a prohibited capability has no
    approval path, and any risk value returned here would be an invitation to
    build one.
    """
    resolved = ApprovalLevel(int(level))
    if resolved is ApprovalLevel.PROHIBITED:
        raise ProhibitedCapabilityError(
            "a level-3 capability has no approval risk because it has no approval path",
            {"approval_level": int(resolved)})
    if resolved is ApprovalLevel.OWNER_APPROVAL:
        return OWNER_APPROVAL_RISK
    return None


async def open_capability_approval(approvals: Any, *, requester_id: str,
                                   capability_key: str, resource: str, reason: str,
                                   approval_level: int, agent_id: str, scope: str,
                                   granted_by: str | None,
                                   correlation_id: str | None = None) -> Any:
    """Open the approval that gates an L2 capability grant.

    ``approvals`` is required: a caller with no approval service must refuse the
    grant rather than perform it ungated, and that refusal belongs to the caller,
    which knows whether it can fall back to anything. This function never
    downgrades the risk, never widens the requested permissions, and records the
    capability, the agent and the scope as parameters so an owner can see exactly
    what authority is being asked for.
    """
    risk = approval_risk_for(approval_level)
    if risk is None:
        raise AppError(
            "this approval level does not open an approval",
            {"approval_level": int(approval_level)})
    request = ApprovalCreateRequest(
        action=CAPABILITY_APPROVAL_ACTION,
        resource=resource,
        risk=risk,
        reason=reason[:2000],
        requested_permissions=[],
        parameters={
            "capability_key": capability_key,
            "agent_id": agent_id,
            "scope": scope,
            "approval_level": int(approval_level),
            "level_description": describe_level(approval_level),
            "requested_by": granted_by,
        },
    )
    return await approvals.create(requester_id, request, correlation_id)
