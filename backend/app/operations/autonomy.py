"""Autonomy resolution (§4). Pure module.

The effective autonomy for a (business, agent, workflow, action) is
the MINIMUM of every applicable ceiling — global default, business
policy, agent policy, agent-in-business policy, workflow policy and
declaration, action-category caps — further capped by the
Constitution mode and the P-10 security mode. Taking the minimum is
what makes cross-business leakage structurally impossible: a Level 3
row scoped to Business A is simply never among the candidates when
resolving for Business B (Scenario 5's named test exercises exactly
this).

Levels never self-promote: policy rows are owner-written only (the
service enforces that), and this resolver only ever lowers.
"""
from __future__ import annotations

from ..security.policy import classify_action
from . import constants as C


def _row(policies: list[dict], scope_type: str, scope_ref: str,
         agent_ref: str | None = None) -> dict | None:
    for row in policies:
        if row.get("scope_type") != scope_type:
            continue
        if row.get("scope_ref", "") != scope_ref:
            continue
        if (row.get("agent_ref") or None) != agent_ref:
            continue
        return row
    return None


def resolve_autonomy(policies: list[dict], *, business_id: str | None,
                     agent_id: str | None, workflow_id: str | None,
                     workflow_declared_level: int, action_class: str,
                     default_level: int, constitution_mode: str,
                     security_mode: str,
                     declared_by_owner: bool = False) -> dict:
    """Resolve the effective autonomy level + execution rights for one
    prospective step execution. Returns the level, the full ceiling
    trace (for the decision record), and the approval requirement.

    Ceiling semantics: explicit policy ROWS always cap. The seeded
    global default caps too — EXCEPT against an owner-declared
    workflow level: when the owner declares a level on their own
    workflow, that declaration is itself the owner's grant for that
    workflow (Scenario 15), still bounded by any explicit rows and by
    the mode caps. An agent's declaration never raises anything."""
    ceilings: dict[str, int] = {}

    global_row = _row(policies, "global", "")
    if global_row:
        ceilings["global_policy"] = int(global_row["level"])
    elif not declared_by_owner:
        ceilings["global_default"] = int(default_level)
    if business_id:
        row = _row(policies, "business", business_id)
        if row:
            ceilings["business_policy"] = int(row["level"])
    if agent_id:
        row = _row(policies, "agent", agent_id)
        if row:
            ceilings["agent_policy"] = int(row["level"])
    if business_id and agent_id:
        row = _row(policies, "agent_business", business_id, agent_id)
        if row:
            ceilings["agent_in_business_policy"] = int(row["level"])
    if workflow_id:
        row = _row(policies, "workflow", workflow_id)
        if row:
            # A workflow-scope row is the owner's CURRENT instruction
            # for this workflow: it supersedes the creation-time
            # declaration (Scenario 15 — raising one workflow must
            # actually raise it), while every other scope still caps.
            ceilings["workflow_policy"] = int(row["level"])
        else:
            ceilings["workflow_declared"] = int(workflow_declared_level)
    else:
        ceilings["workflow_declared"] = int(workflow_declared_level)

    # Action-category caps recorded on any applicable row.
    applicable = [r for r in policies if _applies(
        r, business_id=business_id, agent_id=agent_id,
        workflow_id=workflow_id)]
    risk = classify_action(action_class)
    for row in applicable:
        caps = row.get("action_caps") or {}
        for key in (action_class, f"risk:{risk}"):
            if key in caps:
                ceilings[f"action_cap:{row['scope_type']}:{key}"] = int(caps[key])

    ceilings["constitution_mode_cap"] = C.MODE_AUTONOMY_CAPS.get(
        constitution_mode, 0)
    ceilings["security_mode_cap"] = C.SECURITY_MODE_CAPS.get(security_mode, 0)

    effective = min(ceilings.values())
    binding = sorted(k for k, v in ceilings.items() if v == effective)

    # Execution rights by level (§4.1):
    #  L0 observation only — risk-0 reads may run; nothing else.
    #  L1 assisted — prepares work; execution needs owner approval
    #     (risk-0 reads are preparation/observation and may run).
    #  L2 controlled — low-risk (<=1) steps run inside policy;
    #     risk-2 steps need approval or a P-10 capability.
    #  L3 bounded — risk-2 steps inside the business may run inside
    #     policy; risk-3 and financial actions still need approval.
    #  L4 strategic — proposes portfolio actions; its execution
    #     rights are identical to L3 (it never widens execution).
    if risk == 0:
        # Observation runs in normal and safe mode (safe mode is
        # read-only by design); P-10 emergency stop and Constitution
        # emergency mode halt even that for autonomous actors.
        may_execute = (security_mode != "emergency_stop"
                       and constitution_mode != "emergency")
        approval_required = False
    elif risk == 1:
        may_execute = effective >= 2
        approval_required = effective < 2
    elif risk == 2:
        may_execute = effective >= 3
        approval_required = effective < 3
    else:  # risk 3 — always owner-approved, at every level (§4.1/§22)
        may_execute = False
        approval_required = True
    if action_class.startswith("financial."):
        # Financial execution is never autonomy-alone: it flows
        # through P-07's spending decision (+ owner when P-07 holds).
        approval_required = True
        may_execute = False
    if constitution_mode == "simulation" and risk > 0:
        may_execute = False
        approval_required = True
    if security_mode == "emergency_stop":
        may_execute = False
        approval_required = approval_required or risk > 0
    elif security_mode == "safe_mode" and risk > 0:
        # Safe mode: observation only for non-owners.
        may_execute = False
        approval_required = True

    return {
        "effective_level": effective,
        "effective_level_name": C.AUTONOMY_LEVELS.get(effective, "unknown"),
        "ceilings": ceilings,
        "binding_constraints": binding,
        "action_class": action_class,
        "action_risk": risk,
        "may_execute": bool(may_execute),
        "approval_required": bool(approval_required),
    }


def _applies(row: dict, *, business_id, agent_id, workflow_id) -> bool:
    scope = row.get("scope_type")
    if scope == "global":
        return True
    if scope == "business":
        return business_id is not None and row.get("scope_ref") == business_id
    if scope == "agent":
        return agent_id is not None and row.get("scope_ref") == agent_id
    if scope == "agent_business":
        return (business_id is not None and agent_id is not None
                and row.get("scope_ref") == business_id
                and row.get("agent_ref") == agent_id)
    if scope == "workflow":
        return workflow_id is not None and row.get("scope_ref") == workflow_id
    return False
