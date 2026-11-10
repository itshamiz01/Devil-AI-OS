"""The §12 operational decision engine. Pure and deterministic.

Before any step executes, the engine answers one question — should
this work proceed, and under what control? — from recorded evidence:
business state, P-07 budget state, agent health, system load,
security mode and the autonomy resolution. The checks run in a
fixed order (safety first, money second, capacity third, autonomy
last) so the same evidence always yields the same category, and the
full context is stored on the decision record.
"""
from __future__ import annotations


def decide_step(ctx: dict) -> dict:
    """ctx keys (all optional; missing = unknown, never assumed good):
    security_mode, financial_suspended, business_paused,
    budget {status: ok|exceeded|held|blocked|missing, utilisation_pct},
    inputs_complete, agent_required, agent_available, agent_healthy,
    overloaded, autonomy {may_execute, approval_required,
    effective_level}.
    """
    checks: dict[str, str] = {}

    def done(category: str, rationale: str, approval: bool = False,
             limits: dict | None = None) -> dict:
        return {"category": category, "rationale": rationale,
                "approval_required": approval, "limits": limits or {},
                "policy_checks": checks}

    mode = ctx.get("security_mode", "normal")
    checks["security_mode"] = mode
    if mode == "emergency_stop":
        return done("PAUSE", "P-10 emergency stop is active; autonomous "
                             "work is halted until the owner restarts it")
    if ctx.get("financial_suspended") and ctx.get("step_is_financial"):
        return done("PAUSE", "financial operations are suspended by the owner (P-10)")

    if ctx.get("business_paused"):
        checks["business_state"] = "paused"
        return done("PAUSE", "the business is paused (P-08 pause control); "
                             "its workflows do not run")
    checks["business_state"] = "active"

    if ctx.get("conflict_with"):
        checks["conflict"] = ctx["conflict_with"]
        return done("DEFER", "another workflow is modifying the same "
                             f"shared resource ({ctx['conflict_with']}); "
                             "queued safely behind it (§11 conflict rule)")

    budget = ctx.get("budget") or {}
    bstatus = budget.get("status", "ok")
    checks["budget"] = bstatus
    if bstatus in ("exceeded", "blocked"):
        # §10 rule 1 + Scenario 7: a budget violation BLOCKS. This is
        # a REJECT decision, not a retry.
        return done("REJECT", f"budget check failed ({bstatus}): P-07 "
                              "refuses this spend; execution is blocked")
    if bstatus == "held":
        return done("REQUEST_APPROVAL",
                    "P-07 is holding this spend for an owner decision",
                    approval=True)
    if bstatus == "missing":
        return done("REJECT", "the step declares a spend but references "
                              "no existing P-07 budget")

    if ctx.get("inputs_complete") is False:
        checks["inputs"] = "incomplete"
        return done("RESEARCH_MORE", "required inputs are missing; gather "
                                     "evidence before executing")
    checks["inputs"] = "complete"

    if ctx.get("agent_required"):
        if ctx.get("agent_available") is False:
            checks["agent"] = "unavailable"
            return done("DEFER", "no eligible agent is available for this "
                                 "task right now; deferred, not forced")
        if ctx.get("agent_healthy") is False:
            checks["agent"] = "unhealthy"
            return done("ESCALATE", "the assigned agent is unhealthy; "
                                    "escalating for reassignment or owner review")
        checks["agent"] = "ok"

    if ctx.get("overloaded"):
        checks["capacity"] = "overloaded"
        return done("DEFER", "system load is above the safe threshold; "
                             "deferred by the admission guard")
    checks["capacity"] = "ok"

    autonomy = ctx.get("autonomy") or {}
    checks["autonomy_level"] = str(autonomy.get("effective_level"))
    if autonomy.get("approval_required"):
        return done("REQUEST_APPROVAL",
                    "autonomy policy requires owner approval at the "
                    f"effective level ({autonomy.get('effective_level_name')}) "
                    f"for this action (risk {autonomy.get('action_risk')})",
                    approval=True)
    if not autonomy.get("may_execute", False):
        return done("REJECT", "autonomy policy does not permit this action "
                              "at the effective level and no approval path "
                              "applies")

    utilisation = budget.get("utilisation_pct")
    if utilisation is not None and utilisation >= 80:
        return done("EXECUTE_WITH_LIMITS",
                    f"budget utilisation is high ({utilisation}%); executing "
                    "with reduced concurrency limits",
                    limits={"max_concurrent_tasks": 1})
    return done("EXECUTE", "all policy, budget, capacity and autonomy "
                           "checks passed")
