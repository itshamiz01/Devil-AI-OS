"""Fixture opportunities for P-06 acceptance testing.

A fixture is built **only** through P-03's own machinery: the opportunity
is created through the OpportunityService, its evidence is stored as
P-03 evidence records (two independent sources, corroborated), research
runs through the P-03 research path, market/commercial analyses are
computed by P-03, and the validation level is whatever P-03's
``validate()`` computes. Nothing here asserts a level. Every fixture is
labelled FIXTURE in its name and description, and businesses created
from fixtures carry ``is_fixture=True`` in every report.

Fixtures prove the creation machinery. They are not market truth: with
real evidence, nothing in staging currently qualifies for business
creation (the real investigations sit at Validation Level 1).
"""
from __future__ import annotations

from ..permissions.models import Principal, PrincipalType

OWNER = Principal(PrincipalType.OWNER, "owner")

FIXTURE_DESCRIPTION = (
    "FIXTURE — synthetic opportunity created for P-06 acceptance "
    "testing. Its evidence records are fixture data stored through "
    "P-03's evidence machinery so that its validation level is computed "
    "by P-03, not asserted. It does not describe a real market.")


async def build_fixture_opportunity(application, *, name: str,
                                    category: str = "digital_products",
                                    description_extra: str = "") -> str:
    """Create a fixture opportunity and drive it through P-03 research,
    market/commercial analysis, scoring and validation. Returns the
    opportunity id. The resulting level is P-03's computation (Level 3
    with the standard fixture evidence set)."""
    opportunities = application.opportunities
    opp = opportunities.create_opportunity(OWNER, {
        "name": f"FIXTURE — {name}",
        "description": FIXTURE_DESCRIPTION + (" " + description_extra
                                              if description_extra else ""),
        "category": category,
        "target_customer": "fixture target customer (acceptance testing)",
        "geography": "global (fixture)",
        "problem_statement": "Fixture problem statement: the target "
                             "customer lacks a simple, honest starter "
                             "resource (fixture data).",
        "proposed_solution": "A small digital product solving the fixture "
                             "problem, sold as a prepared package.",
        "revenue_model": "one-time digital product sales",
        "discovery_method": "manual",
    })
    opportunities.add_evidence(OWNER, opp.id, {
        "category": "problem",
        "evidence_kind": "source_claim",
        "claim": "Fixture evidence A: interviews indicate the problem "
                 "exists for the target customer.",
        "source_name": "fixture-source-a",
        "independence_group": "fixture-interviews",
        "classification": "SUPPORTING",
    })
    opportunities.add_evidence(OWNER, opp.id, {
        "category": "problem",
        "evidence_kind": "source_claim",
        "claim": "Fixture evidence B: an independent survey corroborates "
                 "the problem.",
        "source_name": "fixture-source-b",
        "independence_group": "fixture-survey",
        "classification": "CORROBORATED",
    })
    session = await opportunities.start_research(OWNER, opp.id, [])
    await opportunities.run_research_stage(session.id)
    opportunities.run_market_analysis(OWNER, opp.id, {
        "customer_segment": "fixture segment",
        "demand_indicators": ["fixture indicator"],
        "market_size": {"value": "cannot be established",
                        "classification": "unknown"},
        "saturation": "unknown (fixture)",
        "sources": [],
    })
    await opportunities.run_commercial_analysis(OWNER, opp.id, {
        "startup_costs": [{"label": "design tool", "amount": 15,
                           "classification": "estimate"}],
        "recurring_costs_monthly": [{"label": "store fees", "amount": 5,
                                     "classification": "estimate"}],
        "variable_costs_per_sale": [{"label": "delivery", "amount": 0.5,
                                     "classification": "estimate"}],
        "price": {"amount": 19, "classification": "estimate",
                  "basis": "fixture price assumption"},
        "platform_fee_pct": 10, "payment_fee_pct": 3,
        "budget_amount": 50,
        "scenario_sales": {
            "conservative": {"sales_per_month": 2},
            "base": {"sales_per_month": 6},
            "optimistic": {"sales_per_month": 15}},
        "proposed_channels": ["own website",
                              "marketplace listing (prepared)"],
        "sources": [],
    })
    await opportunities.score(OWNER, opp.id)
    await opportunities.validate(OWNER, opp.id)
    return opp.id
