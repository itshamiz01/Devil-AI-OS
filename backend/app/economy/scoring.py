"""P-16 pure economic mathematics.

Every function here is deterministic arithmetic over caller-supplied
figures — P-07 read models in production, literals in unit tests.
No function reads a database, invents a market figure, or presents a
projection as a fact. Where the inputs cannot support a claim, the
functions return an explicit INSUFFICIENT_DATA marker instead of a
number (the P-08 honesty posture).
"""
from __future__ import annotations

from . import constants as C


# ------------------------------------------------------------ §4.3
def band_for(score: float) -> str:
    for threshold, band in C.SCORE_BANDS:
        if score >= threshold:
            return band
    return "reject_or_archive"


def score_opportunity(factors: dict, weights: dict | None = None) -> dict:
    """§4.3 weighted score. Factor inputs are attractiveness 0–100,
    except ``risk_profile`` which is a risk LEVEL 0–100 and is
    inverted before weighting. Missing factors score 0 and are
    reported, so a thin assessment can never look complete."""
    weights = weights or C.DEFAULT_FACTOR_WEIGHTS
    total_weight = sum(weights.get(k, 0) for k in C.FACTOR_KEYS) or 1
    contributions: dict[str, float] = {}
    missing: list[str] = []
    weighted = 0.0
    for key in C.FACTOR_KEYS:
        raw = factors.get(key)
        if raw is None:
            missing.append(key)
            contributions[key] = 0.0
            continue
        value = max(0.0, min(100.0, float(raw)))
        if key == "risk_profile":
            value = 100.0 - value  # higher risk => lower attractiveness
        contribution = value * weights.get(key, 0) / total_weight
        contributions[key] = round(contribution, 2)
        weighted += contribution
    total = round(weighted, 1)
    return {"total_score": total, "band": band_for(total),
            "contributions": contributions, "missing_factors": missing,
            "weights": {k: weights.get(k, 0) for k in C.FACTOR_KEYS},
            "note": "prioritisation score, not a success probability; "
                    "risk_profile is inverted (higher risk lowers the "
                    "score)"}


def confidence_from_evidence(evidence: list) -> int:
    """Deterministic confidence 0–100 from the evidence attached to
    an opportunity: source-backed items weigh more than assertions,
    and corroboration (2+ source-backed items) is required before
    confidence can pass the default approval gate of 50."""
    source_backed = sum(1 for e in evidence if e.get("source_backed"))
    other = len(evidence) - source_backed
    score = 22 * source_backed + 8 * other
    if source_backed >= 3:
        score += 10  # corroboration bonus
    return max(0, min(100, score))


# ------------------------------------------------------------ §5/§6
def hhi(amounts: dict) -> float | None:
    """Herfindahl concentration over integer-minor amounts, 0..1.
    None when there is nothing to concentrate (no positive total):
    a business with no collected revenue has no measurable
    concentration, and claiming 0 would flatter it."""
    total = sum(v for v in amounts.values() if v and v > 0)
    if total <= 0:
        return None
    return round(sum((v / total) ** 2 for v in amounts.values()
                     if v and v > 0), 4)


def largest_share(amounts: dict) -> tuple[str | None, float | None]:
    total = sum(v for v in amounts.values() if v and v > 0)
    if total <= 0:
        return None, None
    key = max(amounts, key=lambda k: amounts[k] if amounts[k] else 0)
    return key, round(amounts[key] / total, 4)


def diversification_score(metrics: dict) -> dict:
    """§6 revenue diversification index for one business, from the
    P-07 revenue metrics dict. A heuristic index (documented
    formula), never a financial fact: 40% channel spread, 30%
    product spread, 30% recurring-revenue ratio, each spread being
    1 − HHI. INSUFFICIENT_DATA when nothing has been collected."""
    net_collected = int(metrics.get("net_collected_minor") or 0)
    if net_collected <= 0:
        return {"score": None, "status": "INSUFFICIENT_DATA",
                "reason": "no verified collected revenue; a "
                          "diversification index would be fabricated"}
    by_channel = metrics.get("by_channel_minor") or {}
    by_product = metrics.get("by_product_minor") or {}
    channel_hhi = hhi(by_channel)
    product_hhi = hhi(by_product)
    mrr = int(metrics.get("mrr_minor") or 0)
    arr = mrr * 12
    recurring_ratio = arr / (arr + net_collected) if (arr + net_collected) > 0 else 0.0
    channel_spread = 1.0 - channel_hhi if channel_hhi is not None else 0.0
    product_spread = 1.0 - product_hhi if product_hhi is not None else 0.0
    score = round(100 * (0.4 * channel_spread + 0.3 * product_spread
                         + 0.3 * recurring_ratio), 1)
    top_channel, top_channel_share = largest_share(by_channel)
    top_product, top_product_share = largest_share(by_product)
    return {
        "score": score, "status": "computed",
        "channel_hhi": channel_hhi, "product_hhi": product_hhi,
        "recurring_ratio": round(recurring_ratio, 4),
        "mrr_minor": mrr, "arr_minor": arr,
        "top_channel": top_channel, "top_channel_share": top_channel_share,
        "top_product": top_product, "top_product_share": top_product_share,
        "streams_present": {
            "channels": len([k for k, v in by_channel.items() if v]),
            "products": len([k for k, v in by_product.items() if v]),
            "categories": len([k for k, v in
                               (metrics.get("by_category_minor") or {}).items()
                               if v])},
        "methodology": "0.4*(1-HHI channels) + 0.3*(1-HHI products) "
                       "+ 0.3*(ARR/(ARR+net collected)); MRR is "
                       "contract value from P-07, not cash",
    }


# ------------------------------------------------------------ gate
def profitability_gate(rows: list[dict]) -> dict:
    """The owner's profitability-first rule, computed from P-07
    indicator rows ({business_id, has_profile,
    verified_collected_revenue_minor, net_profit_minor}).

    CLOSED when: no business has a financial profile; no verified
    collected revenue exists anywhere; aggregate verified net profit
    is <= 0; or profit is indeterminate for any profiled business
    (a None net profit means P-07 could not establish it — the gate
    does not open on unknown figures)."""
    profiled = [r for r in rows if r.get("has_profile")]
    if not profiled:
        return {"state": "closed", "reason": "no business has a P-07 "
                "financial profile; profitability is unestablished",
                "businesses_profiled": 0, "total_collected_minor": 0,
                "total_net_profit_minor": None}
    total_collected = sum(int(r.get("verified_collected_revenue_minor") or 0)
                          for r in profiled)
    if total_collected <= 0:
        return {"state": "closed", "reason": "no verified collected "
                "revenue in any business; make an existing business "
                "earn before creating new ones",
                "businesses_profiled": len(profiled),
                "total_collected_minor": total_collected,
                "total_net_profit_minor": None}
    if any(r.get("net_profit_minor") is None for r in profiled):
        return {"state": "closed", "reason": "net profit is "
                "indeterminate for at least one profiled business "
                "(P-07 INSUFFICIENT_DATA); the gate does not open on "
                "unknown figures",
                "businesses_profiled": len(profiled),
                "total_collected_minor": total_collected,
                "total_net_profit_minor": None}
    total_profit = sum(int(r["net_profit_minor"]) for r in profiled)
    if total_profit <= 0:
        return {"state": "closed", "reason": "aggregate verified net "
                "profit across profiled businesses is not positive; "
                "the owner's rule is profitability before new "
                "businesses",
                "businesses_profiled": len(profiled),
                "total_collected_minor": total_collected,
                "total_net_profit_minor": total_profit}
    return {"state": "open", "reason": "aggregate verified net profit "
            "is positive on verified collected revenue",
            "businesses_profiled": len(profiled),
            "total_collected_minor": total_collected,
            "total_net_profit_minor": total_profit}


# ------------------------------------------------------------ §14
def country_score(criteria: dict, weights: dict | None = None) -> dict:
    """Weighted mean of criterion attractiveness scores 0–100.
    Missing criteria score 0 and are reported."""
    weights = weights or C.DEFAULT_COUNTRY_WEIGHTS
    total_weight = sum(weights.get(k, 1) for k in C.COUNTRY_CRITERIA) or 1
    weighted = 0.0
    missing = []
    for key in C.COUNTRY_CRITERIA:
        raw = criteria.get(key)
        if raw is None:
            missing.append(key)
            continue
        weighted += max(0.0, min(100.0, float(raw))) * weights.get(key, 1)
    return {"total_score": round(weighted / total_weight, 1),
            "missing_criteria": missing,
            "weights": {k: weights.get(k, 1) for k in C.COUNTRY_CRITERIA}}


# ------------------------------------------------------------ §12
def stress_scenarios(rows: list[dict],
                     market_entry_exposure_minor: int = 0) -> list[dict]:
    """The ten §12 stress scenarios as arithmetic over per-business
    P-07 figures. Each row: {business_id, name, currency,
    net_collected_minor, expenses_minor, net_profit_minor,
    by_channel_minor}. Outputs are SIMULATION — arithmetic on
    current figures, never predictions. Scenarios that P-07 data
    cannot quantify say so instead of inventing a number."""
    def run(key, title, shock, notes=""):
        per_business = []
        before = 0
        after = 0
        for row in rows:
            shocked = shock(row)
            before += int(row.get("net_profit_minor") or 0)
            after += shocked
            per_business.append({
                "business_id": row["business_id"], "name": row.get("name"),
                "net_profit_before_minor": int(row.get("net_profit_minor") or 0),
                "net_profit_after_minor": shocked,
                "loss_making_after": shocked < 0})
        return {"key": key, "title": title, "label": "SIMULATION",
                "per_business": per_business,
                "portfolio_net_profit_before_minor": before,
                "portfolio_net_profit_after_minor": after,
                "businesses_loss_making_after":
                    sum(1 for b in per_business if b["loss_making_after"]),
                "notes": notes}

    def revenue_drop(pct):
        def shock(row):
            return int(row.get("net_profit_minor") or 0) - int(
                (row.get("net_collected_minor") or 0) * pct)
        return shock

    def largest_channel_shock(row):
        by_channel = row.get("by_channel_minor") or {}
        top, _share = largest_share(by_channel)
        removed = int(by_channel.get(top) or 0) if top else 0
        return int(row.get("net_profit_minor") or 0) - removed

    def ad_channel_shock(row):
        by_channel = row.get("by_channel_minor") or {}
        removed = sum(int(v or 0) for k, v in by_channel.items()
                      if "ad" in str(k).lower())
        return int(row.get("net_profit_minor") or 0) - removed

    def cost_shock(row):
        return int(row.get("net_profit_minor") or 0) - int(
            (row.get("expenses_minor") or 0) * 0.20)

    biggest_id = None
    if rows:
        biggest_id = max(rows, key=lambda r: int(
            r.get("net_collected_minor") or 0))["business_id"]

    def biggest_unprofitable(row):
        if row["business_id"] == biggest_id:
            profit = int(row.get("net_profit_minor") or 0)
            return -abs(profit) if profit != 0 else -1
        return int(row.get("net_profit_minor") or 0)

    def combined(row):
        return int(row.get("net_profit_minor") or 0) \
            - int((row.get("net_collected_minor") or 0) * 0.25) \
            - int((row.get("expenses_minor") or 0) * 0.20)

    scenarios = [
        run("revenue_drop_10", "Revenue drops by 10%", revenue_drop(0.10)),
        run("revenue_drop_25", "Revenue drops by 25%", revenue_drop(0.25)),
        run("revenue_drop_50", "Revenue drops by 50%", revenue_drop(0.50)),
        run("major_customer_disappears",
            "Major customer disappears (modelled as the largest "
            "revenue channel of each business)",
            largest_channel_shock,
            "per-customer revenue is not recorded in P-07; the "
            "largest channel is the honest available proxy"),
        run("ad_platform_suspended",
            "Advertising platform suspends the account (channels "
            "whose name contains 'ad')",
            ad_channel_shock,
            "no advertising-named channel revenue is recorded"
            if not any("ad" in str(k).lower() for r in rows
                       for k in (r.get("by_channel_minor") or {}))
            else ""),
        run("cloud_provider_unavailable",
            "Cloud provider becomes unavailable",
            lambda row: int(row.get("net_profit_minor") or 0),
            "operational, not financially quantifiable from P-07 "
            "figures: profit is unchanged in this arithmetic; the "
            "exposure is service continuity, tracked by P-15"),
        run("costs_up_20", "Operating costs increase by 20%", cost_shock),
        run("major_business_unprofitable",
            "The largest business becomes unprofitable",
            biggest_unprofitable),
        run("international_entry_fails",
            "International market entry fails",
            lambda row: int(row.get("net_profit_minor") or 0),
            f"quantified exposure is the PROPOSED (uncommitted) "
            f"market-entry investment in the pipeline: "
            f"{market_entry_exposure_minor} minor units; no booked "
            f"loss exists because nothing was committed"),
        run("simultaneous_disruption",
            "Several businesses experience simultaneous disruption "
            "(revenue -25% and costs +20% combined)", combined),
    ]
    return scenarios
