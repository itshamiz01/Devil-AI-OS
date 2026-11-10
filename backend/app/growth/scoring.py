"""P-17 pure growth mathematics.

Every function is deterministic arithmetic over caller-supplied
figures — P-07 read models and recorded growth state in production,
literals in unit tests. No function reads a database, invents a
customer, or upgrades an estimate into a fact: where the inputs
cannot support a claim, the result is an explicit INSUFFICIENT_DATA
marker (the P-08/P-16 honesty posture).

Labels are part of the math here, not decoration: CAC divides only
*eligible recorded spend*; LTV separates actual collected (a fact
about the past) from projected contribution (an ESTIMATE with its
methodology attached); a lead score is a prioritisation estimate,
never a purchase probability.
"""
from __future__ import annotations

import math

from . import constants as C


# ------------------------------------------------------------ generic
def weighted_score(factors: dict, weights: dict, keys: tuple) -> dict:
    """Weighted mean of 0–100 factor attractiveness over ``keys``.
    Missing factors score 0 and are reported, so a thin assessment
    can never look complete (the P-16 §4.3 pattern)."""
    total_weight = sum(weights.get(k, 0) for k in keys) or 1
    contributions: dict[str, float] = {}
    missing: list[str] = []
    weighted = 0.0
    for key in keys:
        raw = factors.get(key)
        if raw is None:
            missing.append(key)
            contributions[key] = 0.0
            continue
        value = max(0.0, min(100.0, float(raw)))
        contribution = value * weights.get(key, 0) / total_weight
        contributions[key] = round(contribution, 2)
        weighted += contribution
    return {"score": round(weighted, 1), "contributions": contributions,
            "missing_factors": missing,
            "weights": {k: weights.get(k, 0) for k in keys}}


def icp_priority(factors: dict, weights: dict | None = None) -> dict:
    """§4.2 ICP priority score from the six declared factors."""
    result = weighted_score(factors, weights or C.DEFAULT_ICP_WEIGHTS,
                            C.ICP_FACTOR_KEYS)
    result["note"] = ("prioritisation estimate from declared factor "
                      "scores; not a demand measurement")
    return result


def channel_value(factors: dict, weights: dict | None = None) -> dict:
    """§4.3 channel expected-value score. The economics factor is
    what keeps the engine from recommending paid traffic merely
    because it can generate visits (§4.3 final rule)."""
    result = weighted_score(factors, weights or C.DEFAULT_CHANNEL_WEIGHTS,
                            C.CHANNEL_FACTOR_KEYS)
    result["note"] = ("expected commercial value from declared "
                      "estimates; validate against recorded CAC "
                      "before committing spend")
    return result


# ------------------------------------------------------------ §9 leads
def band_for(score: int) -> str:
    for threshold, band in C.SCORE_BANDS:
        if score >= threshold:
            return band
    return "low_priority"


def lead_score(factors: dict, weights: dict | None = None) -> dict:
    """§9 lead score 0–100 with the full factor explanation. The
    factor vocabulary is closed (constants.LEAD_SCORE_FACTORS):
    unknown keys are refused by the caller, and sensitive personal
    attributes are not in the vocabulary at all."""
    weights = weights or C.DEFAULT_LEAD_SCORE_WEIGHTS
    result = weighted_score(factors, weights, C.LEAD_SCORE_FACTORS)
    score = int(round(result["score"]))
    return {"score": score, "band": band_for(score),
            "contributions": result["contributions"],
            "missing_factors": result["missing_factors"],
            "weights": result["weights"],
            "factors": {k: factors.get(k) for k in C.LEAD_SCORE_FACTORS},
            "note": "prioritisation estimate, not a guarantee or "
                    "probability of purchase (§9)"}


# ------------------------------------------------------------ §11/§17 health
def customer_health(*, days_since_interaction: int | None,
                    days_since_purchase: int | None,
                    open_support_issues: int,
                    lifecycle_stage: str) -> dict:
    """Deterministic customer health 0–100 with every deduction
    explained. Recency dominates: a customer nobody has heard from
    and who has not bought in a long time is at risk regardless of
    history. Unknown recency is reported, not assumed good."""
    score = 100
    factors: list[dict] = []

    def deduct(points: int, factor: str, detail: str) -> None:
        nonlocal score
        if points:
            score -= points
            factors.append({"factor": factor, "effect": -points,
                            "detail": detail})

    if days_since_interaction is None:
        deduct(25, "interaction_recency",
               "no interaction has ever been recorded")
    elif days_since_interaction > 90:
        deduct(30, "interaction_recency",
               f"last interaction {days_since_interaction} days ago")
    elif days_since_interaction > 30:
        deduct(15, "interaction_recency",
               f"last interaction {days_since_interaction} days ago")
    elif days_since_interaction > 14:
        deduct(5, "interaction_recency",
               f"last interaction {days_since_interaction} days ago")

    if days_since_purchase is None:
        deduct(20, "purchase_recency",
               "no verified purchase recorded in P-07 for this "
               "customer reference")
    elif days_since_purchase > 180:
        deduct(25, "purchase_recency",
               f"last verified purchase {days_since_purchase} days ago")
    elif days_since_purchase > 90:
        deduct(12, "purchase_recency",
               f"last verified purchase {days_since_purchase} days ago")

    if open_support_issues:
        deduct(min(20, 7 * open_support_issues), "open_support",
               f"{open_support_issues} support interaction(s) without "
               "a recorded resolution outcome")

    if lifecycle_stage in ("at_risk", "dormant"):
        deduct(15, "lifecycle", f"lifecycle stage is {lifecycle_stage}")
    elif lifecycle_stage == "churned":
        deduct(60, "lifecycle", "customer is recorded as churned")

    score = max(0, min(100, score))
    band = ("healthy" if score >= 70 else
            "watch" if score >= 40 else "at_risk")
    return {"score": score, "band": band, "factors": factors,
            "note": "deterministic estimate from recorded recency, "
                    "support and lifecycle factors; not a satisfaction "
                    "measurement"}


# ------------------------------------------------------------ §13 funnel
def funnel_rates(stage_counts: list[tuple[str, int]]) -> dict:
    """Stage-to-stage conversion over the ordered §13 funnel.
    ``stage_counts`` must arrive in funnel order with zero-count
    stages included; a rate is None (not 0, not invented) when the
    earlier stage has no count to divide by."""
    steps: list[dict] = []
    bottleneck: dict | None = None
    for (stage, count), (next_stage, next_count) in zip(
            stage_counts, stage_counts[1:]):
        rate = (round(next_count / count, 4) if count > 0 else None)
        steps.append({"from": stage, "to": next_stage, "from_count": count,
                      "to_count": next_count, "rate": rate})
        if rate is not None and count >= 10:  # ignore noise-level drops
            if bottleneck is None or rate < bottleneck["rate"]:
                bottleneck = {"from": stage, "to": next_stage, "rate": rate}
    overall = None
    if stage_counts and stage_counts[0][1] > 0:
        overall = round(stage_counts[-1][1] / stage_counts[0][1], 4)
    return {"steps": steps, "bottleneck": bottleneck,
            "overall_rate": overall}


# ------------------------------------------------------------ §17/§27 economics
def cac(eligible_spend_minor: int | None, new_customers: int | None) -> dict:
    """CAC = eligible acquisition expenditure / new customers (§27).
    Eligible = P-07 paid P&L expenses in the configured marketing
    categories. INSUFFICIENT_DATA — never a flattering zero — when
    spend is unrecorded or no customers were acquired."""
    if eligible_spend_minor is None:
        return {"status": "INSUFFICIENT_DATA", "cac_minor": None,
                "reason": "no eligible acquisition spend is recorded "
                          "in P-07 for the period"}
    if not new_customers:
        return {"status": "INSUFFICIENT_DATA", "cac_minor": None,
                "reason": "no new customers were acquired in the "
                          "period; a CAC would divide by zero",
                "eligible_spend_minor": eligible_spend_minor}
    return {"status": "computed",
            "cac_minor": eligible_spend_minor // new_customers,
            "eligible_spend_minor": eligible_spend_minor,
            "new_customers": new_customers,
            "methodology": "eligible P-07 acquisition spend (paid, "
                           "P&L kinds, configured categories) / new "
                           "CRM customers in period"}


def ltv(*, actual_collected_minor: int,
        contribution_margin_ratio: float | None,
        expected_periods: int | None) -> dict:
    """Customer lifetime value, honestly split (§17): the *actual*
    collected figure is a fact; the projection is an ESTIMATE that
    exists only when a contribution margin (from P-07 verified
    profitability) and an expected relationship length are known.
    Revenue-based LTV is never presented as profit-based LTV."""
    result: dict = {
        "actual_collected_minor": actual_collected_minor,
        "actual_label": "verified collected revenue recorded in P-07 "
                        "for this customer reference (fact)"}
    if contribution_margin_ratio is None or expected_periods is None:
        result.update({
            "status": "INSUFFICIENT_DATA", "projected_ltv_minor": None,
            "reason": "projection needs a contribution margin from "
                      "P-07 verified profitability and an expected "
                      "relationship length; one or both are unknown"})
        return result
    projected = int(actual_collected_minor * contribution_margin_ratio
                    * expected_periods)
    result.update({
        "status": "ESTIMATE", "projected_ltv_minor": projected,
        "contribution_margin_ratio": contribution_margin_ratio,
        "expected_periods": expected_periods,
        "methodology": "actual collected × contribution margin ratio "
                       "(P-07 net profit / verified collected) × "
                       "expected periods; a contribution estimate, "
                       "not a revenue figure and not a promise"})
    return result


def ltv_cac_ratio(ltv_minor: int | None, cac_minor: int | None) -> dict:
    if ltv_minor is None or cac_minor is None or cac_minor <= 0:
        return {"status": "INSUFFICIENT_DATA", "ratio": None,
                "reason": "both a projected LTV and a computed CAC "
                          "are required"}
    return {"status": "ESTIMATE", "ratio": round(ltv_minor / cac_minor, 2),
            "note": "compares a projected contribution LTV with a "
                    "recorded CAC; read with both methodologies"}


def retention_rate(customers_start: int, customers_end: int,
                   new_customers: int) -> dict:
    """§27 retention = (end − new) / start × 100."""
    if customers_start <= 0:
        return {"status": "INSUFFICIENT_DATA", "rate": None,
                "reason": "no customers at period start"}
    rate = round((customers_end - new_customers) / customers_start * 100, 2)
    return {"status": "computed", "rate": rate,
            "customers_start": customers_start,
            "customers_end": customers_end, "new_customers": new_customers}


def churn_rate(customers_start: int, churned: int) -> dict:
    if customers_start <= 0:
        return {"status": "INSUFFICIENT_DATA", "rate": None,
                "reason": "no customers at period start"}
    return {"status": "computed",
            "rate": round(churned / customers_start * 100, 2),
            "customers_start": customers_start, "churned": churned}


# ------------------------------------------------------------ §14 experiments
def ab_result(control: dict, test: dict, min_per_variant: int) -> dict:
    """A/B conclusion discipline (§14): no winner exists below the
    declared minimum evaluation, whatever the observed rates say.
    With enough data, rates are compared with a two-proportion
    z-test and the verdict still carries the sample sizes."""
    cn, cs = int(control.get("n", 0)), int(control.get("successes", 0))
    tn, ts = int(test.get("n", 0)), int(test.get("successes", 0))
    base = {"control": {"n": cn, "successes": cs,
                        "rate": round(cs / cn, 4) if cn else None},
            "test": {"n": tn, "successes": ts,
                     "rate": round(ts / tn, 4) if tn else None},
            "minimum_per_variant": min_per_variant}
    if cn < min_per_variant or tn < min_per_variant:
        return {**base, "verdict": "insufficient_data",
                "recommendation": "keep collecting observations; "
                "declaring a winner now would be a decision on "
                "insufficient data (§14)"}
    cr, tr = cs / cn, ts / tn
    pooled = (cs + ts) / (cn + tn)
    se = math.sqrt(pooled * (1 - pooled) * (1 / cn + 1 / tn)) or 1e-9
    z = (tr - cr) / se
    significant = abs(z) >= 1.96
    winner = "test" if tr > cr else "control" if cr > tr else "tie"
    return {**base, "verdict": winner, "z_score": round(z, 3),
            "statistically_significant_95": significant,
            "recommendation": (
                f"adopt the {winner} variant" if significant and winner != "tie"
                else "no statistically reliable difference at 95%; "
                     "prefer the control unless other evidence argues "
                     "otherwise")}
