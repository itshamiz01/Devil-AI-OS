"""P-03 integration tests: discovery, research-as-tasks, analyses,
scoring, validation and reporting over the real API + task worker.
Covers acceptance scenarios A, B, D, E, F, H, I at API level."""
from __future__ import annotations

import time

import pytest

BASE = "/api/v1"


def _brief(client, headers, **overrides):
    body = {"title": "Find a business", "objective": "Find a legitimate digital business",
            "budget_amount": 50, "currency": "USD", "geography": "global"}
    body.update(overrides)
    resp = client.post(f"{BASE}/opportunities/briefs", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _discover(client, headers, brief_id):
    resp = client.post(f"{BASE}/opportunities/discover", json={"brief_id": brief_id},
                       headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["opportunities"]


def _by_name(opps):
    return {o["name"]: o for o in opps}


def _wait_research(client, headers, session_id, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"{BASE}/research/{session_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.1)
    raise AssertionError(f"research session {session_id} did not finish")


def _research(client, headers, opp_id, source_keys=None):
    body = {}
    if source_keys is not None:
        body["source_keys"] = source_keys
    resp = client.post(f"{BASE}/opportunities/{opp_id}/research", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    session = resp.json()["data"]
    assert session["task_id"], "research must run as a P-01 task"
    return _wait_research(client, headers, session["id"])


async def test_p03_migration_head_and_tables_on_fresh_db(tmp_path):
    """The additive P-03 migration is the chain head on a fresh DB and all
    P-01 (9) + P-02 (5) + P-03 (11) tables coexist."""
    from sqlalchemy import inspect, text

    from app.core.application import Application
    from tests.conftest import make_settings

    settings = make_settings(tmp_path, auto_migrate=True)
    application = Application(settings)
    await application.startup()
    try:
        engine = application.engine
        tables = set(inspect(engine).get_table_names())
        expected = {
            # P-01
            "system_config", "agents", "tasks", "task_executions", "permissions",
            "approvals", "audit_events", "system_events", "app_sessions",
            # P-02
            "missions", "plans", "plan_steps", "decision_records", "model_profiles",
            # P-03
            "research_briefs", "opportunities", "research_sources", "research_sessions",
            "evidence_records", "competitors", "market_analyses", "commercial_analyses",
            "opportunity_scores", "validation_records", "opportunity_history",
        }
        assert expected <= tables
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        # Head advanced by the additive P-04 migration (a694abea811f
        # revises a8ddb3e7260d) and then by the additive P-05 migration
        # (6ffcc7e899fa revises a694abea811f); all tables above remain
        # present and untouched. Exact-head strictness preserved.
        # P-08 disclosure: head advanced again by the additive P-08 migration (99902c03a197 revises c3b5cdba2559); same update, same strictness.
        # P-09 disclosure: head advanced again by the additive P-09 migration (7b13db7e9bfa revises 99902c03a197); same update, same strictness.
        # (P-05 disclosure: head updated, assertion unchanged in kind.)
        # P-06 disclosure: head advanced again by the additive P-06
        # migration (a8d7e0c717b4 revises 6ffcc7e899fa); same update.
        # P-07 disclosure: head advanced again by the additive P-07 migration (c3b5cdba2559 revises a8d7e0c717b4); same update, same strictness.
        # P-10 disclosure: head advanced again by the additive P-10 migration (e37d00443d20 revises 7b13db7e9bfa); same update, same strictness.
        # P-11 disclosure: head advanced again by the additive P-11 migration (193731df4c37 revises e37d00443d20); same update, same strictness.
        # P-12 disclosure: head advanced again by the additive P-12 migration (3a77efe78faa revises 193731df4c37); same update, same strictness.
        # P-13 disclosure: head advanced again by the additive P-13 migration (d02b4208d228 revises 3a77efe78faa); same update, same strictness.
        # P-14 disclosure: head advanced again by the additive P-14 Stage B migration (4d41d6a6a605 revises d02b4208d228); same update, same strictness.
        # P-16 disclosure: head advanced again by the additive P-16 migration (ccd744b29e54 revises d12e4d6cf5ef); same update, same strictness.
        # P-17 disclosure: head advanced again by the additive P-17 migration (afe062122eb5 revises ccd744b29e54); same update, same strictness.
        # P-18 disclosure: head advanced again by the additive P-18 migration (218ddd92a0aa revises afe062122eb5); same update, same strictness.
        # Expansion F01 disclosure: head advanced again by the additive
        # Expansion Feature 1 migration (85b7a9805207 revises 218ddd92a0aa);
        # same update, same strictness.
        # Expansion F02 disclosure: head advanced again by the additive
        # Expansion Feature 2 migration (3f7a1c9e52b4 revises 85b7a9805207);
        # same update, same strictness.
        # Expansion F03 disclosure: head/count advanced by the additive Expansion Feature 3 migration (c41f7a9d03e6 revises 3f7a1c9e52b4; +4 voice tables); same update, same strictness.
        # Expansion F06 disclosure: head/count advanced by the additive Expansion Feature 6 migration (af39baad9c40 revises c41f7a9d03e6; +3 knowledge tables); same update, same strictness.
        assert version == "af39baad9c40"
    finally:
        await application.shutdown()


# ------------------------------------------------------- Scenario A + queue
def test_scenario_a_low_budget_discovery_and_screening(client, auth_headers):
    brief = _brief(client, auth_headers)
    opps = _discover(client, auth_headers, brief["id"])
    by_name = _by_name(opps)
    assert len(opps) == 13
    # Budget-incompatible models are marked, budget never raised (Scenario E).
    assert by_name["Print-on-Demand Mugs and Tees Store"]["status"] == "INCOMPATIBLE"
    assert by_name["Phone Accessories Inventory E-Commerce"]["status"] == "INCOMPATIBLE"
    # Prohibited model hard-blocked at screening.
    assert by_name["Paid Fake-Review Writing Service"]["status"] == "BLOCKED_BY_COMPLIANCE"
    # The deliberate case-variant duplicate is detected.
    dupes = [o for o in opps if o["status"] == "DUPLICATE"]
    assert len(dupes) == 1 and dupes[0]["duplicate_of_id"]
    # Viable low-budget candidates pass screening.
    for name in ("Beginner fitness e-book series (KDP)", "Printable Weekly Planner Templates",
                 "GST Invoice Generator for Indian Freelancers"):
        assert by_name[name]["status"] == "INITIAL_SCREENING"
        assert by_name[name]["validation_level"] == 0


def test_scenario_b_geography_filtering(client, auth_headers):
    india = _brief(client, auth_headers, geography="India", title="India brief")
    opps = _by_name(_discover(client, auth_headers, india["id"]))
    assert "GST Invoice Generator for Indian Freelancers" in opps
    assert "Excel for Shopkeepers Course (Hindi)" in opps

    us = _brief(client, auth_headers, geography="US", title="US brief")
    us_opps = _discover(client, auth_headers, us["id"])
    assert len(us_opps) == 9  # the four India-specific candidates are excluded
    assert all(o["geography"] in ("global", "US") for o in us_opps)


def test_category_filtering(client, auth_headers):
    brief = _brief(client, auth_headers, categories=["software_services"])
    opps = _discover(client, auth_headers, brief["id"])
    assert [o["name"] for o in opps] == ["GST Invoice Generator for Indian Freelancers"]


# ------------------------------------------------------------- research flow
def test_research_collects_evidence_and_corroborates(client, auth_headers):
    brief = _brief(client, auth_headers)
    opps = _by_name(_discover(client, auth_headers, brief["id"]))
    ebook = opps["Beginner fitness e-book series (KDP)"]
    session = _research(client, auth_headers, ebook["id"],
                        ["owner_research_notes", "industry_blog_fixture"])
    assert session["status"] == "completed"
    assert "2 source(s)" in session["findings_summary"]

    resp = client.get(f"{BASE}/opportunities/{ebook['id']}/evidence", headers=auth_headers)
    records = resp.json()["data"]
    assert len(records) >= 4
    royalty = [r for r in records if r["topic_key"] == "kdp-royalty-rate"]
    assert len(royalty) == 2
    # Two independent sources (owner notes + blog) corroborate the claim.
    assert all(r["classification"] == "CORROBORATED" for r in royalty)
    # Provenance is complete on every record.
    assert all(r["source_id"] and r["retrieval_timestamp"] for r in records)

    opp = client.get(f"{BASE}/opportunities/{ebook['id']}", headers=auth_headers).json()["data"]
    assert opp["status"] == "EVIDENCE_REVIEW"


def test_research_unknown_source_rejected(client, auth_headers):
    brief = _brief(client, auth_headers)
    opps = _by_name(_discover(client, auth_headers, brief["id"]))
    ebook = opps["Beginner fitness e-book series (KDP)"]
    resp = client.post(f"{BASE}/opportunities/{ebook['id']}/research",
                       json={"source_keys": ["some_random_blog"]}, headers=auth_headers)
    assert resp.status_code == 422


def test_blocked_opportunity_cannot_be_researched(client, auth_headers):
    brief = _brief(client, auth_headers)
    opps = _by_name(_discover(client, auth_headers, brief["id"]))
    fake = opps["Paid Fake-Review Writing Service"]
    resp = client.post(f"{BASE}/opportunities/{fake['id']}/research",
                       json={}, headers=auth_headers)
    assert resp.status_code == 409


# ------------------------------------------- Scenario D: attractive, no proof
def test_scenario_d_attractive_idea_without_evidence(client, auth_headers):
    resp = client.post(f"{BASE}/opportunities", headers=auth_headers, json={
        "name": "Viral AI Pet Video Empire", "category": "content",
        "description": "AI pet videos that will obviously go viral and print money",
        "target_customer": "Everyone", "revenue_model": "advertising",
        "required_capabilities": ["content_production"]})
    assert resp.status_code == 201, resp.text
    opp = resp.json()["data"]
    score = client.post(f"{BASE}/opportunities/{opp['id']}/score",
                        headers=auth_headers).json()["data"]
    assert score["evidence_quality"] == 0.0
    assert score["dimensions"]["verified_demand"] == 0.0
    assert score["recommendation"] == "REQUIRES MORE RESEARCH"


# --------------------------------------------- Scenario E: budget via numbers
def test_scenario_e_commercial_budget_incompatible_hard_rejection(client, auth_headers):
    brief = _brief(client, auth_headers)
    resp = client.post(f"{BASE}/opportunities", headers=auth_headers, json={
        "name": "Boutique SaaS for Yachts", "category": "software_services",
        "description": "Software for yacht fleets", "revenue_model": "subscription",
        "brief_id": brief["id"], "required_capabilities": ["software_development"]})
    opp = resp.json()["data"]
    analysis = client.post(
        f"{BASE}/opportunities/{opp['id']}/commercial-analysis", headers=auth_headers, json={
            "startup_costs": [{"name": "development", "amount": 4000, "classification": "estimate"}],
            "recurring_costs_monthly": [{"name": "hosting", "amount": 200, "classification": "estimate"}],
            "variable_costs_per_sale": [],
            "price": {"amount": 99, "classification": "estimate", "basis": "stated assumption"},
            "scenario_sales": {"base": {"sales_per_month": 5, "assumptions": ["stated"]}}})
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["data"]["budget"]["compatible"] is False
    assert analysis.json()["data"]["budget"]["budget_amount"] == 50  # owner's figure, unchanged

    score = client.post(f"{BASE}/opportunities/{opp['id']}/score",
                        headers=auth_headers).json()["data"]
    assert score["hard_rejection"]["rule"] == "impossible_budget"
    assert score["recommendation"] == "FINANCIALLY INCOMPATIBLE"
    opp_after = client.get(f"{BASE}/opportunities/{opp['id']}",
                           headers=auth_headers).json()["data"]
    assert opp_after["status"] == "INCOMPATIBLE"


# --------------------------------------------- Scenario F: saturated market
def test_scenario_f_saturated_market_reduces_competitive_score(client, auth_headers):
    resp = client.post(f"{BASE}/opportunities", headers=auth_headers, json={
        "name": "Another To-Do List App", "category": "software_services",
        "description": "A to-do list app", "revenue_model": "freemium",
        "required_capabilities": ["software_development"]})
    opp = resp.json()["data"]
    for i in range(6):
        r = client.post(f"{BASE}/opportunities/{opp['id']}/competitors",
                        headers=auth_headers,
                        json={"name": f"TodoCompetitor {i}", "product": "to-do app"})
        assert r.status_code == 201, r.text
    market = client.post(f"{BASE}/opportunities/{opp['id']}/market-analysis",
                         headers=auth_headers).json()["data"]
    assert market["saturation"]["level"] == "high"
    score = client.post(f"{BASE}/opportunities/{opp['id']}/score",
                        headers=auth_headers).json()["data"]
    assert score["dimensions"]["competitive_opportunity"] <= 1.0


def test_competitor_price_requires_evidence(client, auth_headers):
    resp = client.post(f"{BASE}/opportunities", headers=auth_headers, json={
        "name": "Price Test Opp", "category": "content", "revenue_model": "subscription"})
    opp = resp.json()["data"]
    bad = client.post(f"{BASE}/opportunities/{opp['id']}/competitors", headers=auth_headers,
                      json={"name": "Rival", "pricing_claim": "$10/mo",
                            "pricing_evidence_id": "does-not-exist"})
    assert bad.status_code == 422  # prices are never recorded without evidence


# ----------------------------------- Full pipeline + Scenarios H and I
def _full_pipeline(client, headers):
    """Manual opportunity taken through research/analysis/scoring/validation
    with owner-recorded evidence. Returns the opportunity dict."""
    resp = client.post(f"{BASE}/opportunities", headers=headers, json={
        "name": "Freelancer Invoice Template Studio", "category": "digital_products",
        "description": "Invoice templates for freelancers", "target_customer": "Freelancers",
        "problem_statement": "Freelancers waste time formatting invoices",
        "revenue_model": "one_time_sales", "required_capabilities": ["content_production"],
        "source_keys": ["owner_research_notes"]})
    opp = resp.json()["data"]
    # Owner-recorded supporting evidence from two independent groups.
    for group, classification, claim in (
            ("owner-interviews", "SUPPORTING", "Three interviewed freelancers said invoice formatting wastes ~1 hour weekly"),
            ("freelancer-survey", "CORROBORATED", "Survey respondents rank invoice formatting among their top admin pains")):
        r = client.post(f"{BASE}/opportunities/{opp['id']}/evidence", headers=headers, json={
            "claim": claim, "category": "problem", "classification": classification,
            "topic_key": "invoice-formatting-pain", "independence_group": group})
        assert r.status_code == 201, r.text
    _research(client, headers, opp["id"], [])
    client.post(f"{BASE}/opportunities/{opp['id']}/market-analysis", headers=headers)
    analysis = client.post(f"{BASE}/opportunities/{opp['id']}/commercial-analysis",
                           headers=headers, json={
            "startup_costs": [{"name": "design tool", "amount": 15, "classification": "estimate"}],
            "recurring_costs_monthly": [{"name": "store fees", "amount": 5, "classification": "estimate"}],
            "variable_costs_per_sale": [{"name": "delivery", "amount": 0.5, "classification": "estimate"}],
            "price": {"amount": 19, "classification": "estimate", "basis": "stated assumption"},
            "platform_fee_pct": 10, "payment_fee_pct": 3,
            "budget_amount": 50,
            "scenario_sales": {
                "conservative": {"sales_per_month": 2, "assumptions": ["weak launch"]},
                "base": {"sales_per_month": 6, "assumptions": ["steady marketplace demand"]},
                "optimistic": {"sales_per_month": 15, "assumptions": ["featured listing"]}}})
    assert analysis.status_code == 200, analysis.text
    return opp, analysis.json()["data"]


def test_full_pipeline_reaches_level_3_but_not_5(client, auth_headers):
    opp, analysis = _full_pipeline(client, auth_headers)
    # Break-even: contribution/sale = 19 - 0.5 - 19*0.13 = 16.03; ceil(5/16.03) = 1
    assert analysis["break_even"]["break_even_sales_per_month"] == 1
    assert analysis["budget"]["compatible"] is True

    score = client.post(f"{BASE}/opportunities/{opp['id']}/score",
                        headers=auth_headers).json()["data"]
    assert score["hard_rejection"] is None
    assert score["evidence_quality"] > 0

    validation = client.post(f"{BASE}/opportunities/{opp['id']}/validate",
                             json={}, headers=auth_headers)
    assert validation.status_code == 200, validation.text
    # Scenario I: strong research, no verified sales -> Level 3, never 5.
    assert validation.json()["data"]["level"] == 3

    claim5 = client.post(f"{BASE}/opportunities/{opp['id']}/validate",
                         json={"claimed_level": 5}, headers=auth_headers)
    assert claim5.status_code == 422
    assert "not supported" in claim5.json()["error"]["message"]


def test_scenario_h_no_reliable_market_information(client, auth_headers):
    resp = client.post(f"{BASE}/opportunities", headers=auth_headers, json={
        "name": "Obscure Niche Widget", "category": "software_services",
        "description": "A widget for an extremely obscure niche",
        "revenue_model": "one_time_sales"})
    opp = resp.json()["data"]
    market = client.post(f"{BASE}/opportunities/{opp['id']}/market-analysis",
                         headers=auth_headers).json()["data"]
    assert market["market_size"]["tam"]["value_text"] is None
    assert "cannot be established" in market["market_size"]["tam"]["note"]
    assert market["saturation"]["level"] == "unknown"
    report = client.get(f"{BASE}/opportunities/{opp['id']}/report",
                        headers=auth_headers).json()["data"]
    assert any("market-size" in g for g in report["evidence_gaps"])
    assert report["executive_summary"]["recommendation"] == "NOT SCORED"


def test_owner_evidence_unlocks_levels_4_and_5(client, auth_headers):
    opp, _analysis = _full_pipeline(client, auth_headers)
    client.post(f"{BASE}/opportunities/{opp['id']}/score", headers=auth_headers)
    v = client.post(f"{BASE}/opportunities/{opp['id']}/validate",
                    json={}, headers=auth_headers).json()["data"]
    assert v["level"] == 3

    r = client.post(f"{BASE}/opportunities/{opp['id']}/evidence", headers=auth_headers, json={
        "claim": "12 freelancers joined the waitlist after a community post",
        "category": "purchasing_intent", "classification": "VERIFIED",
        "evidence_kind": "owner_real_world", "topic_key": "waitlist-signups"})
    assert r.status_code == 201, r.text
    v = client.post(f"{BASE}/opportunities/{opp['id']}/validate",
                    json={}, headers=auth_headers).json()["data"]
    assert v["level"] == 4

    r = client.post(f"{BASE}/opportunities/{opp['id']}/evidence", headers=auth_headers, json={
        "claim": "First sale: payment of $19 confirmed in the payment provider dashboard",
        "category": "purchasing_intent", "classification": "VERIFIED",
        "evidence_kind": "owner_payment", "topic_key": "first-sale"})
    assert r.status_code == 201, r.text
    v = client.post(f"{BASE}/opportunities/{opp['id']}/validate",
                    json={}, headers=auth_headers).json()["data"]
    assert v["level"] == 5


# ------------------------------------------------------------- misc endpoints
def test_rankings_reproducible(client, auth_headers):
    opp, _ = _full_pipeline(client, auth_headers)
    first = client.post(f"{BASE}/opportunities/{opp['id']}/score",
                        headers=auth_headers).json()["data"]
    second = client.post(f"{BASE}/opportunities/{opp['id']}/score",
                         headers=auth_headers).json()["data"]
    assert first["weighted_score"] == second["weighted_score"]
    assert first["dimensions"] == second["dimensions"]
    rankings = client.get(f"{BASE}/opportunities/rankings",
                          headers=auth_headers).json()["data"]
    assert rankings and rankings[0]["opportunity_id"] == opp["id"]
    assert rankings[0]["scoring_version"] == "scoring-v1"


def test_illegal_lifecycle_transition_rejected(client, auth_headers):
    resp = client.post(f"{BASE}/opportunities", headers=auth_headers, json={
        "name": "Transition Test", "category": "content", "revenue_model": "subscription"})
    opp = resp.json()["data"]
    assert opp["status"] == "INITIAL_SCREENING"
    bad = client.post(f"{BASE}/opportunities/{opp['id']}/transition",
                      json={"target": "VALIDATED"}, headers=auth_headers)
    assert bad.status_code == 409
    blocked = client.post(f"{BASE}/opportunities/{opp['id']}/transition",
                          json={"target": "RECOMMENDED"}, headers=auth_headers)
    assert blocked.status_code == 409  # validation gate for RECOMMENDED


def test_recheck_deduplicated_and_queue_visible(client, auth_headers):
    resp = client.post(f"{BASE}/opportunities", headers=auth_headers, json={
        "name": "Recheck Test", "category": "content", "revenue_model": "subscription"})
    opp = resp.json()["data"]
    first = client.post(f"{BASE}/opportunities/{opp['id']}/recheck",
                        json={}, headers=auth_headers).json()["data"]
    second = client.post(f"{BASE}/opportunities/{opp['id']}/recheck",
                         json={}, headers=auth_headers).json()["data"]
    assert first["id"] == second["id"]
    queue = client.get(f"{BASE}/opportunities/research-queue",
                       headers=auth_headers).json()["data"]
    assert any(q["session_id"] == first["id"] for q in queue)


def test_report_separates_facts_estimates_recommendations(client, auth_headers):
    opp, _ = _full_pipeline(client, auth_headers)
    client.post(f"{BASE}/opportunities/{opp['id']}/score", headers=auth_headers)
    report = client.get(f"{BASE}/opportunities/{opp['id']}/report",
                        headers=auth_headers).json()["data"]
    assert report["facts_from_evidence"], "report must carry traceable facts"
    assert all("classification" in f and "retrieved_at" in f
               for f in report["facts_from_evidence"])
    assert "estimate_notice" in report["commercial_feasibility"]
    assert report["executive_summary"]["recommendation"] != "NOT SCORED"
    history = client.get(f"{BASE}/opportunities/{opp['id']}/history",
                         headers=auth_headers).json()["data"]
    event_types = {h["event_type"] for h in history}
    assert {"discovered", "scored"} <= event_types
