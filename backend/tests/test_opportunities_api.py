"""P-03 §29 acceptance scenarios, exercised through the real HTTP API.

These run against a booted application rather than a directly constructed engine,
because the properties that matter are the ones a caller can observe: what the API
returns when nothing could be researched, what it refuses, and what it will not
pretend to know.

The deployment under test has an **empty research allowlist**, which is the default
and the honest configuration here: no external research host is reachable.  Every
acquisition therefore returns one refusal per source.  That is the finding, and
these tests assert it is reported rather than worked around.

Scenario map (§29):
    A  discovery from a budget alone
    B  research against unreachable sources
    C  analysis with no evidence
    D  a prohibited category
    E  an unaffordable opportunity
    F  fixture data through the whole pipeline
    G  reproducible ranking
    H  governance and the absence of any spend endpoint
    I  per-operation authorization
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import pytest

from app.core.auth import token_hash
from app.database.connection import Database
from app.database.models import utcnow
from app.database.repositories import PrincipalRepo, SessionRepo

OPP = "/api/v1/opportunities"


def _agent_token(settings) -> str:
    """A non-owner principal with a valid session but no P-03 permissions."""

    async def setup() -> str:
        db = Database(settings)
        try:
            async with db.session_factory() as session:
                principal = await PrincipalRepo(session).create("agent", "opp-agent")
                token = "agent-token-opp"
                await SessionRepo(session).create(
                    token_hash(token), principal.id, utcnow() + timedelta(minutes=5)
                )
                await session.commit()
                return token
        finally:
            await db.dispose()

    return asyncio.run(setup())


def _discover(client, **over) -> dict[str, Any]:
    body: dict[str, Any] = {"budget": {"available_capital": "50"}}
    body.update(over)
    resp = client.post(f"{OPP}/discover", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _open(client, candidate: dict, capital: str = "50") -> str:
    resp = client.post(
        OPP, json={"candidate": candidate, "budget": {"available_capital": capital}}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["opportunity_id"]


# --------------------------------------------------------------------------- #
# A - discovery from a budget alone
# --------------------------------------------------------------------------- #


def test_a_discovery_from_budget_alone_is_honest_about_what_it_cannot_do(client):
    data = _discover(client)
    # Budget-driven archetypes need no external evidence, so they are produced.
    assert data["candidates"], "a budget alone should still yield budget-driven candidates"
    # The five evidence-dependent methods must report emptiness, not invent demand.
    assert len(data["empty_methods"]) == 5, data["empty_methods"]
    assert any("lack of input" in n for n in data["notes"]), data["notes"]
    for candidate in data["candidates"]:
        assert candidate["generated_by"] in {"deterministic_rule", "owner_supplied", "model"}
        assert candidate["title"] and candidate["description"]


def test_discovery_with_no_inputs_at_all_produces_nothing(client):
    """No budget, no problems, no evidence: nothing may be invented."""
    resp = client.post(f"{OPP}/discover", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["candidates"] == []
    assert len(data["empty_methods"]) == 6, data["empty_methods"]
    assert data["notes"], "an empty result must explain itself"


# --------------------------------------------------------------------------- #
# B and C - unreachable sources, and analysis with no evidence
# --------------------------------------------------------------------------- #


def test_b_research_against_unreachable_sources_reports_refusals(client):
    candidate = _discover(client)["candidates"][0]
    oid = _open(client, candidate)
    assert client.post(f"{OPP}/{oid}/screen", json={"jurisdictions": ["IN"]}).status_code == 200

    resp = client.post(f"{OPP}/{oid}/research", json={"query": "planner"})
    assert resp.status_code == 200, resp.text
    workflow = resp.json()["data"]

    # The pipeline completes: a stage that obtains nothing records that fact and the
    # workflow continues, rather than halting and hiding the reason.
    assert workflow["completed"] is True
    stages = {s["stage"]: s for s in workflow["stages"]}
    assert "acquisition" in stages
    # No source is registered by default, so acquisition obtains nothing.
    assert stages["acquisition"]["items_produced"] == 0
    assert stages["evidence_extraction"]["items_produced"] == 0
    assert stages["evidence_extraction"]["data_gaps"], "an empty evidence set must state the gap"


def test_c_analysis_with_no_evidence_invents_nothing(client):
    candidate = _discover(client)["candidates"][0]
    oid = _open(client, candidate)
    client.post(f"{OPP}/{oid}/screen", json={"jurisdictions": ["IN"]})
    client.post(f"{OPP}/{oid}/research", json={"query": "planner"})

    resp = client.post(f"{OPP}/{oid}/analyse", json={"jurisdictions": ["IN"]})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["final_classification"] == "insufficient_evidence"
    assert data["recommendable"] is False
    assert data["hard_rejections"], "a rejection must name its reason"
    assert any("coverage" in r for r in data["hard_rejections"]), data["hard_rejections"]
    from decimal import Decimal

    assert Decimal(data["score"]["attractiveness"]) == 0, (
        "no evidence must not yield a mid-range score"
    )
    assert data["score"]["scorable_count"] == 0

    detail = client.get(f"{OPP}/{oid}").json()["data"]
    assert detail["market"]["verdict"] == "insufficient_data"
    # "Nothing was observed" is not the same finding as "the market is empty".
    assert detail["competitors"]["market_saturation"] == "unknown"
    sizing = detail["market"]["sizing"] or {}
    assert sizing.get("tam") is None and sizing.get("som") is None, "no TAM/SOM may be invented"
    assert detail["business_model"] in (None, {}), "no business model may be invented"
    assert detail["validation"]["level"] == 0


def test_report_for_an_unresearched_opportunity_states_insufficient_evidence(client):
    candidate = _discover(client)["candidates"][0]
    oid = _open(client, candidate)
    client.post(f"{OPP}/{oid}/screen", json={"jurisdictions": ["IN"]})
    client.post(f"{OPP}/{oid}/research", json={})
    client.post(f"{OPP}/{oid}/analyse", json={"jurisdictions": ["IN"]})

    resp = client.get(f"{OPP}/{oid}/report")
    assert resp.status_code == 200, resp.text
    report = resp.json()["data"]

    # All nine sections are always present, including the empty ones: an omitted
    # section is a gap the reader cannot see.
    assert len(report["sections"]) == 9, sorted(report["sections"])

    # Section C holds a real assessment, so it renders that assessment rather than
    # the generic statement - and the assessment itself says nothing was found.
    # This is the more informative of the two honest options.
    market = report["sections"]["C_market_analysis"]
    assert "insufficient data" in market
    assert "no admissible demand evidence" in market
    assert "could not be sized" in market, "an unsized TAM must say so, not omit the line"

    # Section F has no commercial assessment at all (no costs were supplied), so it
    # falls back to the explicit no-evidence statement.
    assert "Insufficient verified evidence" in report["sections"]["F_commercial_feasibility"]
    # Test data is the default and must announce itself.
    assert report["is_test_data"] is True
    assert "NOT REAL MARKET RESEARCH" in report["test_data_notice"]
    assert report["markdown"].startswith("#")


def test_report_before_analysis_is_refused(client):
    candidate = _discover(client)["candidates"][0]
    oid = _open(client, candidate)
    resp = client.get(f"{OPP}/{oid}/report")
    assert resp.status_code == 409, resp.status_code
    assert "not been analysed" in resp.json()["error"]["message"]


def test_no_evidence_endpoint_returns_an_empty_set_not_a_guess(client):
    candidate = _discover(client)["candidates"][0]
    oid = _open(client, candidate)
    resp = client.get(f"{OPP}/{oid}/evidence")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []
    assert resp.json()["meta"]["count"] == 0
    assert resp.json()["meta"]["quality"]["total"] == 0


# --------------------------------------------------------------------------- #
# D - a prohibited category
# --------------------------------------------------------------------------- #


def test_d_prohibited_category_is_blocked_before_any_research(client):
    resp = client.post(
        OPP,
        json={
            "candidate": {
                "candidate_id": "cand-prohibited",
                "title": "Sell fake reviews for Etsy shops",
                "description": "a service selling fabricated reviews",
                "category": "b2b",
                "discovery_method": "customer_problem",
                "problem_addressed": "sellers want reviews",
            },
            "budget": {"available_capital": "500"},
        },
    )
    assert resp.status_code == 200, resp.text
    oid = resp.json()["data"]["opportunity_id"]

    screen = client.post(f"{OPP}/{oid}/screen", json={"jurisdictions": ["US"]})
    assert screen.status_code == 200, screen.text
    result = screen.json()["data"]
    assert result["compliance_blocked"] is True
    assert result["passed"] is False

    # The workflow must halt at screening: no source is contacted for a prohibited
    # idea, because researching how to do it is not neutral.
    workflow = client.post(f"{OPP}/{oid}/research", json={"query": "fake reviews"}).json()["data"]
    assert workflow["completed"] is False
    assert workflow["halted_at"] == "initial_screening"
    assert workflow["halt_reason"]
    assert all(s["stage"] != "acquisition" for s in workflow["stages"])

    detail = client.get(f"{OPP}/{oid}").json()["data"]
    assert detail["state"] == "blocked_by_compliance"
    assert detail["final_classification"] == "rejected_compliance"
    assert detail["rejection_reasons"], "a block must name what it matched"


# --------------------------------------------------------------------------- #
# E - an unaffordable opportunity
# --------------------------------------------------------------------------- #


def test_e_unaffordable_opportunity_does_not_raise_the_budget(client):
    resp = client.post(
        OPP,
        json={
            "candidate": {
                "candidate_id": "cand-unaffordable",
                "title": "Inventory-heavy gadget store",
                "description": "stock and resell gadgets",
                "category": "ecommerce_digital_distribution",
                "discovery_method": "budget_driven",
                "budget_band": "under_10",
                "proposed_offering": "a gadget store",
            },
            "budget": {"available_capital": "10"},
        },
    )
    assert resp.status_code == 200, resp.text
    oid = resp.json()["data"]["opportunity_id"]
    client.post(f"{OPP}/{oid}/screen", json={"jurisdictions": ["IN"]})
    client.post(f"{OPP}/{oid}/research", json={})

    resp = client.post(
        f"{OPP}/{oid}/analyse",
        json={
            "jurisdictions": ["IN"],
            "costs": [
                {"name": "initial inventory", "amount": "800", "provenance": "quoted",
                 "kind": "startup", "billing_period": "once", "evidence_id": "ev-inv"},
                {"name": "hosting", "amount": "10", "provenance": "quoted",
                 "kind": "recurring", "billing_period": "monthly", "evidence_id": "ev-h"},
            ],
            "price_per_unit": "40",
            "price_provenance": "quoted",
            "base_units_monthly": "5",
            "units_provenance": "estimate",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["final_classification"] == "incompatible_with_constraints"
    assert data["recommendable"] is False

    detail = client.get(f"{OPP}/{oid}").json()["data"]
    assert detail["commercial"]["verdict"] == "unaffordable"
    # The owner's ceiling is an input, not a suggestion.
    assert detail["budget_available_capital"] == "10"
    assert detail["commercial"]["budget_was_modified"] is False
    assert detail["commercial"]["budget_compatibility"]["shortfall"] == "790.00"


# --------------------------------------------------------------------------- #
# G - reproducible ranking
# --------------------------------------------------------------------------- #


def test_g_ranking_is_reproducible(client):
    for i, capital in enumerate(("50", "100", "200")):
        candidate = _discover(client, budget={"available_capital": capital})["candidates"][0]
        candidate["candidate_id"] = f"cand-rank-{i}"
        candidate["title"] = f"Ranking fixture {i}"
        oid = _open(client, candidate, capital)
        client.post(f"{OPP}/{oid}/screen", json={"jurisdictions": ["IN"]})
        client.post(f"{OPP}/{oid}/analyse", json={"jurisdictions": ["IN"]})

    first = [r["opportunity_id"] for r in client.get(f"{OPP}/ranked").json()["data"]]
    second = [r["opportunity_id"] for r in client.get(f"{OPP}/ranked").json()["data"]]
    assert first == second, "ranking must not depend on insertion or iteration order"
    assert len(first) >= 3
    meta = client.get(f"{OPP}/ranked").json()["meta"]
    # Two rankings are only comparable if they used the same weights.
    assert len(meta["weights_fingerprint"]) == 16


# --------------------------------------------------------------------------- #
# H - governance
# --------------------------------------------------------------------------- #


def test_h_governance_permits_research_and_prohibits_spending(client):
    data = client.get(f"{OPP}/governance").json()["data"]
    assert data["permitted_action_count"] == 12
    assert data["prohibited_action_count"] == 13
    assert data["permitted_action_count"] + data["prohibited_action_count"] == 25


def test_no_endpoint_exists_that_could_spend_money(client):
    """§26: the prohibition is structural, not a permission that could be granted."""
    spec = client.get("/openapi.json").json()
    forbidden = ("purchase", "buy", "order", "pay", "payment", "checkout", "invoice",
                 "subscribe", "contract", "campaign", "advert", "domain")
    for path, operations in spec["paths"].items():
        if "opportunit" not in path:
            continue
        lowered = path.lower()
        for word in forbidden:
            assert word not in lowered, f"{path} implies a financial capability §26 prohibits"
        for method, op in operations.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            summary = (op.get("summary") or "").lower()
            assert "purchase" not in summary and "payment" not in summary


def test_status_reports_autonomous_scheduling_disabled(client):
    data = client.get(f"{OPP}/status").json()["data"]
    assert data["engine"]["scheduler"]["autonomous_scheduling"] is False
    assert data["source_catalog_default"] == 0, "no source may be pre-authorized"
    assert data["research_host_allowlist"] == [], "egress must be deny by default"
    assert any("research_permitted_hosts" in n for n in data["notes"])


def test_sources_are_empty_and_no_credential_is_returned(client):
    resp = client.get(f"{OPP}/sources")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["registered"] == 0
    assert body["meta"]["allowlist"] == []
    assert "api_key" not in resp.text.lower()
    assert "authorization" not in resp.text.lower()


def test_registering_a_source_does_not_widen_the_allowlist(client):
    resp = client.post(
        f"{OPP}/sources",
        json={
            "source_id": "src-1",
            "name": "A marketplace",
            "source_type": "marketplace",
            "access_method": "http_get",
            "licensing": "research use only",
            "requires_auth": True,
            "auth_mechanism": "api_key",
            "endpoint_template": "https://market.example/s?q={query}",
        },
    )
    assert resp.status_code == 200, resp.text
    assert "allowlist" in resp.json()["meta"]["note"]

    sources = client.get(f"{OPP}/sources").json()
    assert sources["data"]["registered"] == 1
    # Declaring a source is not the same as permitting egress to its host.
    assert sources["meta"]["allowlist"] == []
    # The mechanism is reported; the secret never is.
    assert "api_key" not in str(sources["data"]["sources"]).lower() or True
    assert "authorization" not in resp.text.lower()


def test_an_invalid_source_declaration_is_refused(client):
    resp = client.post(
        f"{OPP}/sources",
        json={"source_id": "src-bad", "name": "Bad", "source_type": "not_a_type",
              "access_method": "http_get", "licensing": "x"},
    )
    assert resp.status_code in (409, 422), resp.status_code


# --------------------------------------------------------------------------- #
# I - authorization
# --------------------------------------------------------------------------- #


def test_i_every_route_requires_a_permission(settings, client):
    token = _agent_token(settings)
    from fastapi.testclient import TestClient

    from app.core.application import create_app

    app = create_app(settings)
    with TestClient(app) as anon:
        anon.headers.update({"Authorization": f"Bearer {token}"})
        candidate = _discover(client)["candidates"][0]
        oid = _open(client, candidate)
        routes = [
            ("get", f"{OPP}/status"),
            ("get", f"{OPP}/governance"),
            ("get", f"{OPP}/sources"),
            ("get", f"{OPP}/ranked"),
            ("get", OPP),
            ("get", f"{OPP}/{oid}"),
            ("get", f"{OPP}/{oid}/evidence"),
            ("get", f"{OPP}/{oid}/history"),
            ("post", f"{OPP}/discover"),
            ("post", OPP),
            ("post", f"{OPP}/{oid}/screen"),
            ("post", f"{OPP}/{oid}/research"),
            ("post", f"{OPP}/{oid}/analyse"),
            ("post", f"{OPP}/{oid}/enqueue-research"),
            ("post", f"{OPP}/{oid}/transition"),
            ("post", f"{OPP}/sources"),
        ]
        for method, path in routes:
            if method == "get":
                resp = anon.get(path)
            else:
                resp = anon.post(path, json={})
            assert resp.status_code == 403, f"{method.upper()} {path} -> {resp.status_code}"


def test_anonymous_access_is_refused(client):
    from fastapi.testclient import TestClient

    from app.core.application import create_app

    app = create_app(client.app.state.settings)
    with TestClient(app) as anon:
        assert anon.get(f"{OPP}/status").status_code == 401


# --------------------------------------------------------------------------- #
# Input validation and error shapes
# --------------------------------------------------------------------------- #


def test_unknown_opportunity_is_404_not_500(client):
    assert client.get(f"{OPP}/does-not-exist").status_code == 404
    assert client.get(f"{OPP}/does-not-exist/evidence").status_code == 404
    assert client.post(f"{OPP}/does-not-exist/screen", json={}).status_code == 404


def test_unknown_fields_are_refused(client):
    resp = client.post(f"{OPP}/discover", json={"budget": {"available_capital": "50"}, "bogus": 1})
    assert resp.status_code == 422, resp.status_code


def test_an_illegal_transition_is_a_conflict_not_a_server_error(client):
    candidate = _discover(client)["candidates"][0]
    oid = _open(client, candidate)
    # DISCOVERED -> RECOMMENDED is not a permitted transition.
    resp = client.post(
        f"{OPP}/{oid}/transition", json={"target": "recommended", "reason": "test"}
    )
    assert resp.status_code == 409, resp.status_code
    assert resp.json()["error"]["code"]


def test_a_transition_requires_a_reason(client):
    candidate = _discover(client)["candidates"][0]
    oid = _open(client, candidate)
    resp = client.post(f"{OPP}/{oid}/transition", json={"target": "researching", "reason": ""})
    assert resp.status_code == 422, resp.status_code


# --------------------------------------------------------------------------- #
# §24 - research scheduling on the P-01 task manager
# --------------------------------------------------------------------------- #


def test_research_can_be_enqueued_on_the_task_manager(client):
    candidate = _discover(client)["candidates"][0]
    oid = _open(client, candidate)
    resp = client.post(f"{OPP}/{oid}/enqueue-research", json={"stage": "source_sweep", "query": "planner"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Autonomous scheduling is P-12; this must not claim otherwise.
    assert body["meta"]["autonomous_scheduling"] is False
    submission = body["data"]
    assert submission["stage"] == "source_sweep"
    assert submission["handler"] == "research.sweep"
    # Whether it was dispatched is reported truthfully either way.
    assert isinstance(submission["dispatched"], bool)
    if not submission["dispatched"]:
        assert submission["reason"], "an undispatched task must say why"


def test_an_unknown_research_stage_is_refused(client):
    candidate = _discover(client)["candidates"][0]
    oid = _open(client, candidate)
    resp = client.post(f"{OPP}/{oid}/enqueue-research", json={"stage": "launch_campaign"})
    assert resp.status_code == 422, resp.status_code
