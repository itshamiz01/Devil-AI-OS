"""Opportunity eligibility evaluation (§6).

A pure, deterministic evaluation over facts assembled from P-03's own
report/validation machinery. An evaluation creates nothing; creation is
a separate, approval-bound step. The validation level is always the
level P-03 computed from stored evidence — P-06 never asserts one.
"""
from __future__ import annotations

from . import constants as C

_SUPPORTING = {"SUPPORTING", "CORROBORATED", "VERIFIED"}


def _check(name: str, outcome: str, reason: str) -> dict:
    return {"check": name, "outcome": outcome, "reason": reason}


def evaluate(ctx: dict, *, min_level: int, creation_approval_ok: bool,
             require_creation_approval: bool) -> tuple[str, list[dict]]:
    """ctx keys (assembled by the service from P-03):
    status, validation_level, validation_missing, hard_rejection,
    evidence (list of {category, classification}), target_customer,
    problem, revenue_model, has_commercial, startup_costs_present,
    budget_compatible (bool|None), distribution_present, compliance.
    Returns (decision, checks)."""
    checks: list[dict] = []
    status = ctx.get("status") or ""
    hard = ctx.get("hard_rejection")
    level = int(ctx.get("validation_level") or 0)

    if status in {"REJECTED", "BLOCKED_BY_COMPLIANCE"}:
        checks.append(_check("opportunity_status", "fail",
                             f"opportunity status is {status}"))
        return C.REJECTED, checks
    checks.append(_check("opportunity_status", "pass", f"status {status}"))
    if hard:
        checks.append(_check("hard_rejection", "fail",
                             f"P-03 hard rejection: {hard.get('rule')}: "
                             f"{hard.get('reason')}"))
        return C.REJECTED, checks
    checks.append(_check("hard_rejection", "pass", "no hard rejection recorded"))

    budget_compatible = ctx.get("budget_compatible")
    if budget_compatible is False:
        checks.append(_check("budget_compatibility", "fail",
                             "commercial analysis shows the opportunity "
                             "exceeds the owner's declared budget/resources"))
        return C.REJECTED, checks
    checks.append(_check("budget_compatibility", "pass",
                         "within declared budget" if budget_compatible
                         else "no incompatibility recorded"))

    # ---- research / validation depth --------------------------------
    research_blockers: list[str] = []
    if level < min_level:
        research_blockers.append(
            f"validation level {level} is below the required minimum "
            f"{min_level} (missing: {'; '.join(ctx.get('validation_missing') or []) or 'see P-03 validation record'})")
    supporting = [e for e in ctx.get("evidence") or []
                  if e.get("classification") in _SUPPORTING
                  and e.get("category") in {"problem", "demand"}]
    if not supporting:
        research_blockers.append(
            "no supporting problem/demand evidence is stored in P-03")
    if not ctx.get("startup_costs_present"):
        research_blockers.append(
            "startup requirements cannot be estimated (no commercial "
            "analysis with startup costs)")
    for reason in research_blockers:
        checks.append(_check("research_depth", "fail", reason))
    if research_blockers:
        decision = (C.REQUIRES_MORE_RESEARCH if level <= 1
                    else C.REQUIRES_MORE_VALIDATION)
        return decision, checks
    checks.append(_check("research_depth", "pass",
                         f"validation level {level} >= minimum {min_level}; "
                         f"{len(supporting)} supporting problem/demand "
                         "evidence record(s); startup estimable"))

    # ---- completeness for blueprinting -------------------------------
    validation_blockers: list[str] = []
    if not (ctx.get("target_customer") or "").strip():
        validation_blockers.append("target customer is not defined")
    if not (ctx.get("problem") or "").strip():
        validation_blockers.append("customer problem is not defined")
    if not (ctx.get("revenue_model") or "").strip():
        validation_blockers.append("revenue model is not specified")
    if not ctx.get("has_commercial"):
        validation_blockers.append("no commercial analysis exists")
    if not ctx.get("distribution_present"):
        validation_blockers.append(
            "no plausible distribution approach is recorded")
    for reason in validation_blockers:
        checks.append(_check("blueprint_completeness", "fail", reason))
    if validation_blockers:
        return C.REQUIRES_MORE_VALIDATION, checks
    checks.append(_check("blueprint_completeness", "pass",
                         "customer, problem, revenue model, commercial "
                         "analysis and distribution approach present"))

    # ---- owner approval ----------------------------------------------
    if require_creation_approval and not creation_approval_ok:
        checks.append(_check("owner_approval", "fail",
                             "no verified hash-bound owner creation "
                             "approval is bound to this opportunity and "
                             "template version"))
        return C.REQUIRES_OWNER_APPROVAL, checks
    checks.append(_check("owner_approval", "pass",
                         "verified owner creation approval bound"
                         if creation_approval_ok else
                         "creation approval not required by settings"))

    # ---- conditions ----------------------------------------------------
    conditions: list[str] = []
    compliance = ctx.get("compliance") or {}
    if compliance.get("requires_professional_review"):
        conditions.append(
            "compliance screening flags this opportunity for professional "
            "review before launch (creation may proceed; launch readiness "
            "will require owner review)")
    if ctx.get("startup_all_unknown"):
        conditions.append(
            "all startup-cost inputs are classified 'unknown' — figures "
            "are placeholders until the owner supplies real costs")
    for reason in conditions:
        checks.append(_check("conditions", "condition", reason))
    if conditions:
        return C.ELIGIBLE_WITH_CONDITIONS, checks
    checks.append(_check("conditions", "pass", "no conditions recorded"))
    return C.ELIGIBLE_FOR_CREATION, checks
