"""Market, competitor and distribution analysis (P-03 §10, §11, §14).

Everything here is a deterministic derivation over stored opportunity
fields, evidence records and competitor rows. Where the stored data
cannot support a conclusion, the output says so — market size in
particular is reported as "cannot be established" unless a VERIFIED or
CORROBORATED market-size evidence record carries a figure (§10.4).
"""
from __future__ import annotations

import re

from .constants import CLASSIFICATION_STRENGTH, INSUFFICIENT_EVIDENCE

_SUPPORTING = CLASSIFICATION_STRENGTH["SUPPORTING"]
_CORROBORATED = CLASSIFICATION_STRENGTH["CORROBORATED"]


def _strength(record) -> float:
    return CLASSIFICATION_STRENGTH.get(record.classification, 0.0)


def demand_stage(records: list) -> str:
    """The strongest demand stage the evidence actually justifies (§10.3).
    Attention is not purchasing intent; only owner payment evidence can
    produce 'verified_transactions'."""
    if any(r.evidence_kind == "owner_payment" and r.classification == "VERIFIED" for r in records):
        return "verified_transactions"
    if any(r.category == "purchasing_intent" and _strength(r) >= _SUPPORTING for r in records):
        return "purchase_consideration"
    if any(r.category in ("demand", "problem") and _strength(r) >= _SUPPORTING for r in records):
        return "active_problem_awareness"
    if any(r.category in ("demand", "problem") for r in records):
        return "general_interest"
    return "none"


def market_size_from_evidence(records: list) -> dict:
    """TAM/SAM/SOM only from VERIFIED/CORROBORATED market-size evidence
    whose claim itself states a figure and a basis. Otherwise each level
    is explicitly 'cannot be established' (§10.4)."""
    out: dict = {}
    usable = [r for r in records
              if r.category == "market_size" and _strength(r) >= _CORROBORATED]
    for level in ("tam", "sam", "som"):
        match = None
        for record in usable:
            if level in record.topic_key.lower() or level in record.claim.lower()[:12]:
                figure = re.search(r"[$₹€£]?\s?(\d[\d,]*(?:\.\d+)?)\s*(billion|million|crore|lakh|bn|m)?",
                                   record.claim, re.IGNORECASE)
                if figure:
                    match = {"value_text": figure.group(0),
                             "methodology": ("Figure stated by an independently corroborated "
                                             "market-size source; basis: " + record.claim),
                             "evidence_id": record.id}
                    break
        out[level] = match or {
            "value_text": None,
            "methodology": None,
            "note": f"{INSUFFICIENT_EVIDENCE}: a reliable {level.upper()} estimate cannot be established from the available evidence.",
        }
    return out


def saturation_assessment(competitors: list, records: list) -> dict:
    """Saturation from recorded competitors + competitor evidence (§10,
    §29F). Zero recorded competitors means 'unknown', never 'empty market'."""
    direct = [c for c in competitors if c.competitor_type == "direct"]
    crowding = any(r.topic_key.endswith("crowding") or "crowded" in r.claim.lower()
                   or "saturated" in r.claim.lower() for r in records if r.category == "competitor")
    if not competitors and not crowding:
        return {"level": "unknown", "direct_competitors_recorded": 0,
                "note": "No competitor evidence recorded: saturation cannot be assessed. "
                        "Absence of recorded competitors is not evidence of an empty market."}
    count = len(direct)
    if count >= 6 or (count >= 3 and crowding):
        level = "high"
    elif count >= 3 or crowding:
        level = "moderate"
    else:
        level = "low"
    return {
        "level": level, "direct_competitors_recorded": count,
        "crowding_signal": crowding,
        "note": ("Saturation is assessed from recorded competitors and competitor "
                 "evidence only; customer-acquisition difficulty rises with saturation "
                 "and no differentiation may mean rejection (§29F)."),
    }


def build_market_analysis(opportunity, records: list, competitors: list) -> dict:
    problem_records = [r for r in records if r.category == "problem"]
    problem_analysis = {
        "statement": opportunity.problem_statement or "",
        "affected_group": opportunity.target_customer or "",
        "evidence_count": len(problem_records),
        "strongest_classification": max((r.classification for r in problem_records),
                                        key=lambda c: CLASSIFICATION_STRENGTH.get(c, 0), default=None),
        "note": ("Frequency, severity and current-workaround cost are only stated "
                 "where evidence records support them; they are not assumed."),
    }
    stage = demand_stage(records)
    return {
        "customer_segment": opportunity.target_customer or "",
        "geographic_market": opportunity.geography,
        "problem_analysis": problem_analysis,
        "demand_indicators": {
            "stage": stage,
            "demand_records": sum(1 for r in records if r.category == "demand"),
            "purchasing_intent_records": sum(1 for r in records if r.category == "purchasing_intent"),
            "note": ("Stages: none < general_interest < active_problem_awareness < "
                     "purchase_consideration < verified_transactions. Search volume, "
                     "views and likes can justify at most 'general_interest' (§10.3, §18.3)."),
        },
        "market_size": market_size_from_evidence(records),
        "saturation": saturation_assessment(competitors, records),
    }


def build_competitor_analysis(opportunity, competitors: list) -> dict:
    matrix = [{
        "name": c.name, "type": c.competitor_type, "product": c.product,
        "pricing": c.pricing_claim,  # verbatim claim or None — never invented (§11.2)
        "pricing_evidence_id": c.pricing_evidence_id,
        "features": c.features, "strengths": c.strengths, "weaknesses": c.weaknesses,
        "positioning": c.positioning,
    } for c in competitors]
    gaps = []
    for c in competitors:
        for weakness in c.weaknesses:
            gaps.append({"competitor": c.name, "gap": weakness,
                         "commercial_significance": "unassessed — a weakness is not by itself "
                                                    "evidence customers will switch (§7.3)"})
    return {
        "competitors": matrix,
        "comparison_note": ("Prices appear only where a pricing claim was recorded with "
                            "evidence; competitor revenue, customer counts and market share "
                            "are never estimated (§11.2)."),
        "identified_gaps": gaps,
        "differentiation_candidates": (
            ["More focused product for the stated segment",
             "Better localisation for the stated geography",
             "Simpler workflow than recorded alternatives"]
            if competitors else []),
        "differentiation_note": ("A recommendation must explain why customers would switch; "
                                 "'competitors are expensive' is not sufficient (§11.4)."),
    }


# Candidate distribution channels per category: CANDIDATES ONLY. Listing a
# channel here never asserts it will work (§14).
CANDIDATE_CHANNELS: dict[str, list[str]] = {
    "digital_products": ["authorized_marketplace", "search_engines", "educational_content"],
    "software_services": ["search_engines", "partnerships", "b2b_outreach_authorized"],
    "content": ["search_engines", "social_media", "email_with_consent"],
    "freelance_services": ["authorized_marketplace", "partnerships", "b2b_outreach_authorized"],
    "online_education": ["authorized_marketplace", "educational_content", "social_media"],
    "ecommerce_digital": ["authorized_marketplace", "social_media", "search_engines"],
    "b2b_services": ["b2b_outreach_authorized", "partnerships", "search_engines"],
}

PROHIBITED_CHANNELS = {"spam", "fake_reviews", "unsolicited_bulk_messaging",
                       "platform_manipulation", "misleading_endorsements"}


def build_distribution_analysis(opportunity, records: list,
                                proposed_channels: list[str] | None = None) -> dict:
    proposed = proposed_channels or CANDIDATE_CHANNELS.get(opportunity.category, [])
    legitimate = [c for c in proposed if c not in PROHIBITED_CHANNELS]
    prohibited = [c for c in proposed if c in PROHIBITED_CHANNELS]
    supported = {r.topic_key for r in records
                 if r.category == "distribution" and _strength(r) >= _SUPPORTING}
    return {
        "candidate_channels": legitimate,
        "prohibited_channels_rejected": prohibited,
        "channels_with_supporting_evidence": sorted(supported),
        "organic_traffic_assumption": "not assumed — organic traffic must be earned and is not forecast (§14)",
        "paid_advertising_assumption": "not assumed profitable — no ad economics are claimed without cost evidence (§14)",
        "legitimate_channel_count": len(legitimate),
        "note": ("Channel availability does not imply acquisition success; conversion "
                 "requirements and acquisition cost remain unproven until real evidence exists."),
    }
