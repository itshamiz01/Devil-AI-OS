"""Pure security policy functions (§8.1, §20.2, §23.5, §7.3/§15.3).

Everything here is deterministic and side-effect free so the unit
suite can pin the rules directly. No function in this module reads a
database, calls a model, or trusts caller-supplied claims about
safety — enforcement layers (broker, guards, facade) call these and
then apply the P-01 permission engine on top.
"""
from __future__ import annotations

from ..permissions.models import Principal, PrincipalType
from . import constants as C


def actor(principal: Principal) -> str:
    return f"{principal.type.value}:{principal.id}"


def classify_action(action: str) -> int:
    """§8.1 risk level for an action name. Unknown actions classify
    at the highest level (fail closed): an unclassified action is
    never treated as low-risk by accident."""
    return C.ACTION_RISK.get(action, C.RISK_CRITICAL)


def is_owner(principal: Principal) -> bool:
    return principal.type is PrincipalType.OWNER


# ------------------------------------------------------------ modes (§20)
def mode_allows(mode: str, principal: Principal, risk_level: int) -> tuple[bool, str]:
    """Whether the current security mode permits an authorization to
    proceed to the remaining gates. The owner is never locked out by
    a mode (the owner must always be able to inspect and recover);
    modes restrain autonomous principals.

    - normal: everything proceeds to the other gates.
    - safe_mode (§20.2): read-only (Level 0) only for non-owners.
    - emergency_stop (§20.1): no non-owner authorization at all.
    An unrecognised mode string fails closed as safe_mode.
    """
    if is_owner(principal):
        return True, "owner is never blocked by security mode"
    if mode == C.MODE_NORMAL:
        return True, "normal mode"
    if mode == C.MODE_EMERGENCY:
        return False, "emergency stop is active; autonomous operations are halted"
    # safe_mode, and any unknown mode value (fail closed)
    if risk_level <= C.RISK_READ_ONLY:
        return True, "safe mode permits read-only actions"
    return False, "safe mode permits only read-only actions for non-owner principals"


# ------------------------------------------------- delegation rules (§7.3)
def delegation_violation(issuer: Principal, holder: Principal,
                         permission: str) -> str | None:
    """Why issuing ``permission`` as a capability from ``issuer`` to
    ``holder`` is refused, or None when the issuance may proceed to
    the grant checks. Rules (§7.3/§15.3):

    - owner-only permissions are never capabilities for agents;
    - nobody issues a capability to themselves (self-issue is
      self-grant, i.e. escalation) — the owner grants their own
      authority directly through P-01 rules, not capabilities;
    - a non-owner issuer cannot delegate owner-only permissions
      to anyone.
    Holding the permission is verified separately against the P-01
    engine by the broker.
    """
    if holder.type is PrincipalType.AGENT and permission in C.OWNER_ONLY_PERMISSIONS:
        return (f"permission '{permission}' is owner-only and can never "
                f"be delegated to an agent as a capability")
    if not is_owner(issuer) and permission in C.OWNER_ONLY_PERMISSIONS:
        return f"only the owner may delegate permission '{permission}'"
    if issuer.type is holder.type and issuer.id == holder.id:
        return "a principal cannot issue a capability to itself"
    return None


# ------------------------------------------- settings validation (§23.5)
def validate_settings_patch(patch: dict, current: dict) -> tuple[dict, list[str]]:
    """Validate a proposed settings patch against the known keys and
    value shapes. Returns (merged_settings, changed_keys) or raises
    ValueError with a precise reason. Unknown keys are rejected:
    silently ignoring a misspelled security key would be a
    fail-open configuration error (§18.4)."""
    if not isinstance(patch, dict) or not patch:
        raise ValueError("settings patch must be a non-empty object")
    merged = dict(current)
    changed: list[str] = []
    for key, value in patch.items():
        if key not in C.DEFAULT_SETTINGS:
            raise ValueError(f"unknown security setting '{key}'")
        expected = C.DEFAULT_SETTINGS[key]
        if isinstance(expected, bool):
            if not isinstance(value, bool):
                raise ValueError(f"security setting '{key}' must be a boolean")
        elif isinstance(expected, int):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"security setting '{key}' must be a non-negative integer")
        elif isinstance(expected, list):
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ValueError(f"security setting '{key}' must be a list of strings")
        elif isinstance(expected, str):
            if not isinstance(value, str):
                raise ValueError(f"security setting '{key}' must be a string")
        if key == "mode" and value not in C.MODES:
            raise ValueError(f"security mode must be one of {sorted(C.MODES)}")
        if merged.get(key) != value:
            changed.append(key)
        merged[key] = value
    return merged, changed
