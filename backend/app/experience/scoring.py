"""P-18 deterministic scoring: ticket priority (§7), SLA state
(§7), experience metrics (§10), customer health (§12), knowledge
matching (§6) and quality aggregation (§9).

Pure functions only — every number here can be re-derived by
hand, and every function refuses to compute from missing data
rather than estimating. Times are handled as aware UTC; stored
ISO strings and naive database datetimes are normalised through
``as_utc`` / ``parse_time``.
"""
from __future__ import annotations

import datetime as dt
import re

from ..database.models.base import as_utc
from . import constants as C


def parse_time(value) -> dt.datetime | None:
    """Accept a datetime or an ISO string; return aware UTC."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            value = dt.datetime.fromisoformat(text)
        except ValueError:
            return None
    return as_utc(value)


def iso(value) -> str | None:
    value = parse_time(value)
    return value.isoformat() if value else None


# ------------------------------------------------------------ §7 priority
def priority_for(factors: dict | None, category: str) -> dict:
    """Explainable priority from declared factors (each 0..3).

    Returns the band, the raw weighted score, the per-factor
    contributions and whether a category floor was applied.
    Unknown factor keys are refused by the caller; missing
    factors score 0 and are reported, never hidden."""
    factors = dict(factors or {})
    contributions: dict[str, float] = {}
    missing: list[str] = []
    total = 0.0
    max_total = 0.0
    for key in C.PRIORITY_FACTORS:
        weight = C.PRIORITY_WEIGHTS[key]
        max_total += 3 * weight
        if key not in factors:
            missing.append(key)
            contributions[key] = 0.0
            continue
        value = max(0, min(3, int(factors[key])))
        contributions[key] = float(value * weight)
        total += value * weight
    ratio = (total / max_total) if max_total else 0.0
    if ratio >= 0.75:
        level = "critical"
    elif ratio >= 0.5:
        level = "high"
    elif ratio >= 0.25:
        level = "medium"
    else:
        level = "low"
    floor = C.CATEGORY_PRIORITY_FLOORS.get(category)
    floor_applied = False
    if floor and C.PRIORITY_LEVELS.index(level) < \
            C.PRIORITY_LEVELS.index(floor):
        level = floor
        floor_applied = True
    # A declared security implication is never below high.
    if int(factors.get("security") or 0) >= 2 and \
            C.PRIORITY_LEVELS.index(level) < \
            C.PRIORITY_LEVELS.index("high"):
        level = "high"
        floor_applied = True
    return {"level": level, "score": total, "max_score": max_total,
            "ratio": round(ratio, 4), "contributions": contributions,
            "missing_factors": missing, "floor_applied": floor_applied,
            "category_floor": floor}


# ------------------------------------------------------------ §7 SLA
def sla_state(policy: dict | None, *, created_at, first_response_at,
              resolved_at, now) -> dict:
    """SLA state for one ticket against an owner-configured
    policy. No policy -> ``not_configured`` (never an invented
    target). Breaches are computed from recorded timestamps."""
    if not policy:
        return {"status": "not_configured",
                "note": "no SLA policy is configured for this "
                        "business/category; no target is invented"}
    created = parse_time(created_at)
    now = parse_time(now) or dt.datetime.now(dt.timezone.utc)
    first_due = resolution_due = None
    fr_minutes = policy.get("first_response_minutes")
    res_minutes = policy.get("resolution_minutes")
    if created and fr_minutes:
        first_due = created + dt.timedelta(minutes=int(fr_minutes))
    if created and res_minutes:
        resolution_due = created + dt.timedelta(minutes=int(res_minutes))
    first_at = parse_time(first_response_at)
    resolved = parse_time(resolved_at)
    first_breached = bool(first_due and (
        (first_at is None and now > first_due)
        or (first_at is not None and first_at > first_due)))
    resolution_breached = bool(resolution_due and (
        (resolved is None and now > resolution_due)
        or (resolved is not None and resolved > resolution_due)))
    if first_breached or resolution_breached:
        status = "breached"
    elif first_due is None and resolution_due is None:
        status = "not_configured"
    else:
        status = "within"
    return {"status": status,
            "first_response_due": iso(first_due),
            "resolution_due": iso(resolution_due),
            "first_response_breached": first_breached,
            "resolution_breached": resolution_breached,
            "policy_category": policy.get("category")}


# ------------------------------------------------------------ §10 metrics
def _metric(status: str, value, sample: int, note: str = "") -> dict:
    return {"status": status, "value": value, "sample_size": sample,
            "note": note}


def csat(scores: list[int]) -> dict:
    """CSAT: mean of recorded 1–5 satisfaction scores, reported
    also as the top-2-box percentage. No scores -> no metric."""
    if not scores:
        return _metric("INSUFFICIENT_DATA", None, 0,
                       "no recorded CSAT responses")
    mean = sum(scores) / len(scores)
    top2 = sum(1 for s in scores if s >= 4) / len(scores) * 100
    return {"status": "computed", "value": round(mean, 3),
            "top2_percent": round(top2, 1),
            "sample_size": len(scores), "scale": "1-5"}


def nps(scores: list[int]) -> dict:
    """NPS from recorded 0–10 scores: %promoters (9–10) minus
    %detractors (0–6). Requires a minimum sample of 1 recorded
    response; the sample size is always reported."""
    if not scores:
        return _metric("INSUFFICIENT_DATA", None, 0,
                       "no recorded NPS responses")
    promoters = sum(1 for s in scores if s >= 9)
    detractors = sum(1 for s in scores if s <= 6)
    value = round((promoters - detractors) / len(scores) * 100, 1)
    return {"status": "computed", "value": value,
            "promoters": promoters, "detractors": detractors,
            "passives": len(scores) - promoters - detractors,
            "sample_size": len(scores), "scale": "0-10"}


def effort(scores: list[int]) -> dict:
    """Customer effort: mean of recorded 1–5 effort scores
    (lower is less effort)."""
    if not scores:
        return _metric("INSUFFICIENT_DATA", None, 0,
                       "no recorded effort scores")
    return {"status": "computed",
            "value": round(sum(scores) / len(scores), 3),
            "sample_size": len(scores), "scale": "1-5",
            "note": "lower means less customer effort"}


def rate(numerator: int, denominator: int, label: str) -> dict:
    if not denominator:
        return _metric("INSUFFICIENT_DATA", None, 0,
                       f"no denominator data for {label}")
    return {"status": "computed",
            "value": round(numerator / denominator * 100, 2),
            "numerator": numerator, "denominator": denominator,
            "sample_size": denominator}


# ------------------------------------------------------------ §12 health
def health(signals: dict, weights: dict) -> dict:
    """Customer health from recorded signals only.

    ``signals`` carries counts/flags the service measured from
    real records (open tickets by priority, reopens, fulfillment
    problems, onboarding state, recorded low feedback). The score
    starts at 100 and subtracts weighted penalties; the
    classification band, every contributing factor and the
    evidence counts are returned for persistence. With no signals
    at all the result is ``insufficient_data`` — the engine never
    guesses a customer's state."""
    measured = {k: v for k, v in signals.items() if v is not None}
    if not measured:
        return {"classification": "insufficient_data", "score": None,
                "factors": {}, "confidence": "none",
                "recommended_action": "collect service data before "
                                      "classifying this customer"}
    penalties: dict[str, int] = {}
    def add(key: str, count: int) -> None:
        if count:
            penalties[key] = int(weights.get(key, 0)) * int(count)

    add("open_critical_ticket", measured.get("open_critical_tickets", 0))
    add("open_high_ticket", measured.get("open_high_tickets", 0))
    add("open_ticket", measured.get("open_tickets_other", 0))
    add("reopened_ticket", measured.get("reopened_tickets", 0))
    add("fulfillment_problem", measured.get("fulfillment_problems", 0))
    add("onboarding_incomplete",
        1 if measured.get("onboarding_incomplete") else 0)
    add("low_feedback", measured.get("low_feedback_count", 0))
    score = max(0, 100 - sum(penalties.values()))
    if measured.get("open_critical_tickets"):
        classification = "critical"
    elif score < 40:
        classification = "at_risk"
    elif score < 65:
        classification = "needs_attention"
    elif score < 85:
        classification = "stable"
    else:
        classification = "healthy"
    actions = {
        "critical": "escalate to a human now: an unresolved critical "
                    "case is open",
        "at_risk": "open a service review and resolve the "
                   "contributing cases",
        "needs_attention": "schedule a follow-up and watch the "
                           "contributing factors",
        "stable": "continue standard service monitoring",
        "healthy": "no action required",
    }
    signal_count = sum(1 for v in measured.values()
                       if v not in (0, False))
    confidence = ("high" if signal_count >= 4
                  else "medium" if signal_count >= 2 else "low")
    return {"classification": classification, "score": score,
            "factors": penalties, "confidence": confidence,
            "recommended_action": actions[classification]}


# ------------------------------------------------------------ §6 knowledge
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for",
    "is", "are", "was", "were", "do", "does", "did", "how", "what",
    "when", "where", "why", "can", "i", "my", "me", "we", "you",
    "it", "this", "that", "with", "from", "about", "please",
}


def tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall((text or "").lower())
            if len(t) > 2 and t not in _STOPWORDS}


def article_match(question: str, articles: list[dict]) -> list[dict]:
    """Rank approved articles by keyword containment: the share
    of the question's content tokens that appear in the article's
    title + content. Deterministic; no embeddings, no LLM."""
    q = tokens(question)
    if not q:
        return []
    ranked = []
    for article in articles:
        body = tokens(f"{article.get('title') or ''} "
                      f"{article.get('content') or ''}")
        if not body:
            continue
        overlap = q & body
        if not overlap:
            continue
        ranked.append({
            "article_id": article["id"],
            "version": article.get("version"),
            "title": article.get("title"),
            "score": round(len(overlap) / len(q), 4),
            "matched_terms": sorted(overlap)})
    ranked.sort(key=lambda r: (-r["score"], r["title"] or ""))
    return ranked


def confidence_for(best_score: float | None) -> str:
    if best_score is None:
        return "insufficient_information"
    if best_score >= C.KB_VERIFIED_THRESHOLD:
        return "verified"
    if best_score >= C.KB_PARTIAL_THRESHOLD:
        return "partially_verified"
    return "insufficient_information"


# ------------------------------------------------------------ §9 quality
def quality_score(dimensions: dict | None) -> dict:
    """Aggregate a QA review's dimension scores (each 0..5).
    Missing dimensions are reported, never silently zero-filled
    into the average's denominator claim."""
    dimensions = dict(dimensions or {})
    present = {k: dimensions[k] for k in C.QUALITY_DIMENSIONS
               if k in dimensions and dimensions[k] is not None}
    missing = [k for k in C.QUALITY_DIMENSIONS if k not in present]
    if not present:
        return {"status": "INSUFFICIENT_DATA", "value": None,
                "scored_dimensions": 0, "missing_dimensions": missing}
    value = round(sum(present.values()) / len(present), 3)
    return {"status": "computed", "value": value,
            "scored_dimensions": len(present),
            "missing_dimensions": missing, "scale": "0-5"}
