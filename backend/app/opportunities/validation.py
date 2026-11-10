"""Validation levels 0–5 (P-03 §18).

The level is COMPUTED from stored evidence, never asserted. Two levels
have hard evidence gates that the engine cannot manufacture:

- Level 4 (real-world demand) requires an ``owner_real_world`` evidence
  record classified VERIFIED — interviews, waitlist signups, genuine
  inquiries that the OWNER recorded. Search volume, views, likes,
  personas and competitor existence are source_claim records and can
  never satisfy this gate (§18.3).
- Level 5 (revenue verified) additionally requires an ``owner_payment``
  VERIFIED record AND an owner reviewer. P-03 conducts no transactions;
  it only records owner-provided verified evidence (§18.2).
"""
from __future__ import annotations

from .constants import CLASSIFICATION_STRENGTH

_SUPPORTING = CLASSIFICATION_STRENGTH["SUPPORTING"]
_CORROBORATED = CLASSIFICATION_STRENGTH["CORROBORATED"]

LEVEL_NAMES = {
    0: "Idea", 1: "Preliminary research", 2: "Evidence-supported",
    3: "Commercially assessed", 4: "Real-world demand validation",
    5: "Revenue verified",
}


def assess_level(ctx: dict, reviewer_is_owner: bool) -> tuple[int, list[str], list[str]]:
    """ctx keys: records, sessions_completed (bool), has_market (bool),
    competitor_count, commercial (row|None). Returns (level, met, missing)
    where missing describes what the NEXT level still needs."""
    records: list = ctx["records"]
    met: list[str] = ["Level 0 — an opportunity concept is recorded"]
    missing: list[str] = []
    level = 0

    # ---- Level 1
    l1_missing = []
    if not ctx.get("sessions_completed"):
        l1_missing.append("a completed research session")
    if not (ctx.get("has_market") or ctx.get("competitor_count", 0) > 0):
        l1_missing.append("basic market or competitor research")
    if l1_missing:
        return level, met, ["Level 1 requires: " + "; ".join(l1_missing)]
    level = 1
    met.append("Level 1 — preliminary market/competitor research completed")

    # ---- Level 2
    demand_records = [r for r in records
                      if r.category in ("problem", "demand", "purchasing_intent")
                      and r.evidence_kind == "source_claim"]
    independent = {r.independence_group for r in demand_records
                   if CLASSIFICATION_STRENGTH.get(r.classification, 0) >= _SUPPORTING
                   and r.independence_group}
    has_corroborated = any(CLASSIFICATION_STRENGTH.get(r.classification, 0) >= _CORROBORATED
                           for r in demand_records)
    l2_missing = []
    if len(independent) < 2:
        l2_missing.append("supporting problem/demand evidence from at least 2 independent sources")
    if not has_corroborated:
        l2_missing.append("at least one CORROBORATED (or better) problem/demand record")
    if l2_missing:
        return level, met, ["Level 2 requires: " + "; ".join(l2_missing)]
    level = 2
    met.append("Level 2 — multiple independent sources support the problem/demand")

    # ---- Level 3
    commercial = ctx.get("commercial")
    l3_missing = []
    if commercial is None:
        l3_missing.append("a commercial analysis")
    else:
        if not (commercial.scenarios or {}):
            l3_missing.append("computed revenue scenarios (requires a stated price and stated sales assumptions)")
        if not (commercial.break_even or {}):
            l3_missing.append("a break-even analysis")
        if not (commercial.distribution or {}):
            l3_missing.append("a distribution analysis")
    if l3_missing:
        return level, met, ["Level 3 requires: " + "; ".join(l3_missing)]
    level = 3
    met.append("Level 3 — pricing, costs, scenarios, break-even and distribution assessed")

    # ---- Level 4: owner-recorded real-world behaviour ONLY (§18.3)
    if not any(r.evidence_kind == "owner_real_world" and r.classification == "VERIFIED"
               for r in records):
        return level, met, [
            "Level 4 requires owner-recorded real-world demand evidence (interviews, "
            "voluntary survey/waitlist signups, genuine inquiries) classified VERIFIED. "
            "Search volume, views, likes, personas and competitor existence cannot "
            "establish Level 4 (§18.3), and P-03 does not conduct outreach itself."]
    level = 4
    met.append("Level 4 — real-world demand observed and recorded by the owner")

    # ---- Level 5: verified payments ONLY (§18.3)
    l5_missing = []
    if not any(r.evidence_kind == "owner_payment" and r.classification == "VERIFIED"
               for r in records):
        l5_missing.append("independently verified payment evidence recorded by the owner "
                          "(generated invoices, unpaid orders, screenshots and forecasts do not count, §18.3)")
    if not reviewer_is_owner:
        l5_missing.append("an owner reviewer for the Level 5 determination")
    if l5_missing:
        return level, met, ["Level 5 requires: " + "; ".join(l5_missing)]
    level = 5
    met.append("Level 5 — actual payments independently verified from owner-provided financial evidence")
    return level, met, missing
