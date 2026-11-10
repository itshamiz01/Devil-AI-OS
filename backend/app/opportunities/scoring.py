"""Opportunity scoring and ranking (P-03 §16, ADR-005).

Deterministic: every dimension is a documented rule over stored inputs
(evidence records, analyses, competitors, brief budget, capability fit,
compliance). The same stored inputs always reproduce the same score —
the full input snapshot is stored on each score row. An LLM never assigns
or adjusts scores. Weights are configuration (system_config), versioned;
evidence quality is computed by evidence.evidence_quality and reported
separately as well as weighted at 5% (ADR-005).
"""
from __future__ import annotations

from . import analysis as analysis_mod
from .constants import CLASSIFICATION_STRENGTH, REVENUE_MODELS
from .evidence import evidence_quality

SCORING_CONFIG_KEY = "opportunities.scoring_weights"
SCORING_V1_VERSION = "scoring-v1"
SCORING_V1_WEIGHTS: dict[str, float] = {
    "verified_demand": 0.20,
    "profit_potential": 0.15,
    "problem_importance": 0.10,
    "competitive_opportunity": 0.10,
    "revenue_model_viability": 0.10,
    "budget_compatibility": 0.10,
    "distribution_feasibility": 0.10,
    "operational_simplicity": 0.05,
    "strategic_fit": 0.05,
    "evidence_quality": 0.05,
}

_SUPPORTING = CLASSIFICATION_STRENGTH["SUPPORTING"]
_CORROBORATED = CLASSIFICATION_STRENGTH["CORROBORATED"]
_VERIFIED = CLASSIFICATION_STRENGTH["VERIFIED"]


def _strongest(records: list, categories: tuple[str, ...]) -> float:
    values = [CLASSIFICATION_STRENGTH.get(r.classification, 0.0)
              for r in records if r.category in categories]
    return max(values) if values else 0.0


def _ladder(strength: float) -> float:
    """Map a strongest-classification strength to a 0–5 rung."""
    if strength >= _VERIFIED:
        return 5.0
    if strength >= _CORROBORATED:
        return 4.0
    if strength >= _SUPPORTING:
        return 3.0
    if strength >= CLASSIFICATION_STRENGTH["TENTATIVE"]:
        return 2.0
    if strength > 0:
        return 1.0
    return 0.0


def derive_dimensions(ctx: dict) -> tuple[dict, dict]:
    """ctx keys: opportunity, records, market, commercial, competitors,
    capability_fit, compliance. Returns (dimensions, reasons)."""
    opp = ctx["opportunity"]
    records: list = ctx["records"]
    commercial = ctx.get("commercial")
    competitors: list = ctx.get("competitors") or []
    fit: dict = ctx.get("capability_fit") or {}
    compliance: dict = ctx.get("compliance") or {}
    dims: dict[str, float] = {}
    reasons: dict[str, str] = {}

    # --- verified demand (§16: attention is not demand)
    stage = analysis_mod.demand_stage(records)
    dims["verified_demand"] = {
        "none": 0.0, "general_interest": 1.0, "active_problem_awareness": 3.0,
        "purchase_consideration": 4.0, "verified_transactions": 5.0,
    }[stage]
    reasons["verified_demand"] = (
        f"demand stage justified by evidence: {stage} "
        f"({sum(1 for r in records if r.category == 'demand')} demand, "
        f"{sum(1 for r in records if r.category == 'purchasing_intent')} purchasing-intent records)")

    # --- problem importance
    dims["problem_importance"] = _ladder(_strongest(records, ("problem",)))
    reasons["problem_importance"] = (
        "strongest problem evidence classification drives the rung "
        f"({sum(1 for r in records if r.category == 'problem')} problem records)")

    # --- competitive opportunity
    saturation = (ctx.get("market").saturation if ctx.get("market") else None) or \
        analysis_mod.saturation_assessment(competitors, records)
    level = saturation.get("level", "unknown")
    gaps = sum(len(c.weaknesses or []) for c in competitors)
    if level == "unknown":
        dims["competitive_opportunity"] = 1.0
        reasons["competitive_opportunity"] = "saturation unknown — no competitor evidence; unknown is not an opening"
    elif level == "low":
        dims["competitive_opportunity"] = 4.0 if gaps else 3.0
        reasons["competitive_opportunity"] = f"low saturation, {gaps} recorded competitor gap(s)"
    elif level == "moderate":
        dims["competitive_opportunity"] = 3.0 if gaps else 2.0
        reasons["competitive_opportunity"] = f"moderate saturation, {gaps} recorded competitor gap(s)"
    else:  # high
        dims["competitive_opportunity"] = 1.0 if gaps else 0.0
        reasons["competitive_opportunity"] = f"high saturation, {gaps} recorded competitor gap(s); entry needs a defensible differentiation (§29F)"

    # --- revenue model viability
    model = (opp.revenue_model or "").strip()
    if not model:
        dims["revenue_model_viability"] = 0.0
        reasons["revenue_model_viability"] = "no revenue model recorded"
    elif model not in REVENUE_MODELS:
        dims["revenue_model_viability"] = 1.0
        reasons["revenue_model_viability"] = f"revenue model '{model}' is not a supported model (§12)"
    else:
        value = 2.0
        notes = ["supported revenue model"]
        if _strongest(records, ("pricing",)) >= _SUPPORTING:
            value += 1.0
            notes.append("pricing evidence at SUPPORTING or better")
        if commercial and (commercial.price_assumption or {}).get("amount") is not None:
            value += 1.0
            notes.append("a priced commercial analysis exists")
        if any(r.category == "purchasing_intent" and _strength_ok(r) for r in records):
            value += 1.0
            notes.append("purchasing-intent evidence exists")
        dims["revenue_model_viability"] = min(5.0, value)
        reasons["revenue_model_viability"] = "; ".join(notes)

    # --- profit potential: BASE scenario only, never the optimistic one
    base = None
    if commercial:
        base = (commercial.scenarios or {}).get("base")
    if not base:
        dims["profit_potential"] = 0.0
        reasons["profit_potential"] = "no base scenario computed — profit potential has no evidence (§16: 0 = no evidence)"
    else:
        margin = base.get("contribution_margin_pct")
        if margin is None:
            dims["profit_potential"] = 0.0
            reasons["profit_potential"] = "base scenario has no computable contribution margin"
        else:
            if margin < 0:
                value = 0.0
            elif margin < 15:
                value = 1.0
            elif margin < 30:
                value = 2.0
            elif margin < 50:
                value = 3.0
            elif margin < 70:
                value = 4.0
            else:
                value = 5.0
            if base.get("operating_profit", 0) < 0:
                value = min(value, 1.0)
            dims["profit_potential"] = value
            reasons["profit_potential"] = (
                f"base-scenario contribution margin {margin}% (bands: <0→0, <15→1, <30→2, "
                f"<50→3, <70→4, else 5; negative base operating profit caps at 1)")

    # --- budget compatibility (the owner's budget is never raised, §13.6)
    budget_block = (commercial.budget if commercial else None) or {}
    compatible = budget_block.get("compatible")
    if compatible is True:
        budget_amount = budget_block.get("budget_amount") or 0
        ratio = (budget_block.get("first_month_total", 0) / budget_amount) if budget_amount else 1.0
        dims["budget_compatibility"] = 5.0 if ratio <= 0.5 else (4.0 if ratio <= 0.75 else 3.0)
        reasons["budget_compatibility"] = f"fits the owner's budget; first-month total is {round(ratio * 100)}% of budget"
    elif compatible is False:
        dims["budget_compatibility"] = 0.0
        reasons["budget_compatibility"] = "startup + first-month cost exceeds the owner's stated budget"
    else:
        dims["budget_compatibility"] = 1.0
        reasons["budget_compatibility"] = "budget compatibility cannot be established (no budget or no commercial analysis)"

    # --- distribution feasibility
    distribution = (commercial.distribution if commercial else None) or \
        analysis_mod.build_distribution_analysis(opp, records)
    legit = distribution.get("legitimate_channel_count", 0)
    if legit == 0:
        dims["distribution_feasibility"] = 0.0
        reasons["distribution_feasibility"] = "no legitimate distribution channel identified"
    else:
        value = 2.0
        if distribution.get("channels_with_supporting_evidence"):
            value += 1.0
        if _strongest(records, ("distribution",)) >= _CORROBORATED:
            value += 1.0
        dims["distribution_feasibility"] = value
        reasons["distribution_feasibility"] = (
            f"{legit} legitimate candidate channel(s); organic traffic and profitable ads "
            "are never assumed (§14), so this dimension caps at 4 without channel performance data")

    # --- operational simplicity
    from .constants import CATEGORIES
    complexity = CATEGORIES.get(opp.category, {}).get("complexity", 3)
    value = float(6 - complexity)
    notes = [f"category complexity prior {complexity}/5"]
    if (opp.capability_fit or {}).get("physical_inventory"):
        value -= 2.0
        notes.append("physical inventory/shipping penalty (§6.6)")
    missing = fit.get("missing") or []
    if missing:
        penalty = min(2.0, float(len(missing)))
        value -= penalty
        notes.append(f"missing capabilities: {missing}")
    if compliance.get("verdict") == "flagged":
        value -= 1.0
        notes.append("compliance flags add operational burden")
    dims["operational_simplicity"] = max(0.0, min(5.0, value))
    reasons["operational_simplicity"] = "; ".join(notes)

    # --- strategic fit
    coverage = fit.get("coverage")
    if coverage is None:
        dims["strategic_fit"] = 2.0
        reasons["strategic_fit"] = "capability requirements not assessed"
    else:
        dims["strategic_fit"] = round(5.0 * float(coverage), 2)
        reasons["strategic_fit"] = (
            f"{round(float(coverage) * 100)}% of required capabilities are available "
            f"(required: {fit.get('required')}, missing: {fit.get('missing')})")

    # --- evidence quality (same computation as the standalone value)
    eq, _breakdown = evidence_quality(records)
    dims["evidence_quality"] = eq
    reasons["evidence_quality"] = "standalone evidence-quality computation (§16.3), also reported separately"

    return dims, reasons


def _strength_ok(record) -> bool:
    return CLASSIFICATION_STRENGTH.get(record.classification, 0.0) >= _SUPPORTING


def hard_rejection(ctx: dict) -> dict | None:
    """§16.4: these rules override any numeric score."""
    compliance: dict = ctx.get("compliance") or {}
    if compliance.get("verdict") == "prohibited":
        rules = compliance.get("matched_rules") or [{}]
        return {"rule": "prohibited_category",
                "reason": f"compliance screening matched prohibited rule(s): "
                          f"{[r.get('rule') for r in rules]} (§15)"}
    commercial = ctx.get("commercial")
    if commercial and (commercial.budget or {}).get("compatible") is False:
        return {"rule": "impossible_budget",
                "reason": "startup + first-month cost exceeds the owner's stated budget; "
                          "the budget is not raised (§13.6)"}
    distribution = (commercial.distribution if commercial else None) or \
        analysis_mod.build_distribution_analysis(ctx["opportunity"], ctx["records"])
    if distribution.get("legitimate_channel_count", 0) == 0:
        return {"rule": "no_legitimate_distribution",
                "reason": "no legitimate distribution channel exists for this model (§14, §16.4)"}
    fit: dict = ctx.get("capability_fit") or {}
    license_missing = [m for m in (fit.get("missing") or []) if str(m).startswith("license:")]
    if license_missing:
        return {"rule": "unavailable_essential_license",
                "reason": f"essential licence(s) unavailable: {license_missing} (§16.4)"}
    return None


def risk_classification(ctx: dict, eq: float, rejection: dict | None) -> str:
    if rejection:
        return "unacceptable" if rejection["rule"] == "prohibited_category" else "high"
    if (ctx.get("compliance") or {}).get("verdict") == "flagged":
        return "high"
    if eq < 2.0:
        return "high"
    saturation = (ctx.get("market").saturation if ctx.get("market") else {}) or {}
    if saturation.get("level") == "high":
        return "elevated"
    return "standard"


def recommendation_for(weighted: float, eq: float, rejection: dict | None,
                       validation_level: int, professional_review_pending: bool) -> str:
    """§23H labels, with the §16.3 evidence cap applied before attractiveness."""
    if rejection:
        return "FINANCIALLY INCOMPATIBLE" if rejection["rule"] == "impossible_budget" else "REJECTED"
    if eq < 2.0:
        return "REQUIRES MORE RESEARCH"
    if professional_review_pending:
        return "PROMISING BUT UNVALIDATED" if weighted >= 3.0 else "REQUIRES MORE RESEARCH"
    if weighted >= 4.0 and validation_level >= 3:
        return "STRONG CANDIDATE"
    if weighted >= 3.2:
        return "PROMISING BUT UNVALIDATED"
    if weighted >= 2.2:
        return "REQUIRES MORE RESEARCH"
    return "LOW PRIORITY"


def weighted_total(dimensions: dict, weights: dict) -> float:
    return round(sum(dimensions.get(k, 0.0) * w for k, w in weights.items()), 2)
