"""P-13 §21 mandatory acceptance scenarios — one named test each.

Every scenario runs against the real composed application (P-06
fixture businesses, P-07 money paths, P-09 memory, P-12 workflows).
Scenario 17's UI half lives in the frontend suite
(frontend/src/views/Portfolio.test.tsx) and the live smoke; the
backend half here pins API values the UI must mirror.
"""
from __future__ import annotations

import pytest

from app.core.exceptions import PermissionDeniedError, ValidationError
from tests.p09_support import make_record
from tests.p13_support import (  # noqa: F401
    AGENT, AGENT2, OWNER, SYSTEM, app_portfolio, business_with_collected,
    client_portfolio, future_iso, make_business, make_portfolio,
    make_service_with_access, owner_http_headers,
)

pytestmark = pytest.mark.asyncio


def _audit_count(application, action: str) -> int:
    from sqlalchemy import func, select
    from app.database.models.core import AuditEvent
    session = application.session_factory()
    try:
        return session.scalar(select(func.count()).select_from(AuditEvent)
                              .where(AuditEvent.action == action)) or 0
    finally:
        session.close()


async def test_scenario_01_two_businesses_operate_independently(app_portfolio):
    """§21.1: two businesses operate with complete isolation."""
    svc = app_portfolio.portfolio
    a = await business_with_collected(app_portfolio, name="Indep A",
                                      amount="5000")
    b = await business_with_collected(app_portfolio, name="Indep B",
                                      amount="2000")
    await make_portfolio(app_portfolio, business_ids=[a, b])
    register = app_portfolio  # agents homed to each business
    from tests.p09_support import register_agent
    register_agent(register, AGENT.id, business_ref=a)
    register_agent(register, AGENT2.id, business_ref=b)
    # Each business's finance is its own P-07 view.
    fa = svc.business_finance(OWNER, a)["summary"]["revenue"]
    fb = svc.business_finance(OWNER, b)["summary"]["revenue"]
    assert fa["net_collected_minor"] == 5000_00
    assert fb["net_collected_minor"] == 2000_00
    # B's agent cannot read A's finance; A's agent cannot read B's.
    with pytest.raises(PermissionDeniedError):
        svc.business_finance(AGENT2, a)
    with pytest.raises(PermissionDeniedError):
        svc.business_finance(AGENT, b)
    # …but each agent reads its own business.
    assert svc.business_finance(AGENT, a)["business_id"] == a


async def test_scenario_02_shared_service_reduces_duplication(app_portfolio):
    """§21.2: one shared service serves two businesses; cost is
    allocated internally by usage instead of duplicated."""
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Share A")
    b = await make_business(app_portfolio, name="Share B")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    service = make_service_with_access(app_portfolio, business_ids=[a, b])
    svc.record_usage(OWNER, service["id"], {"business_id": a, "units": 75})
    svc.record_usage(OWNER, service["id"], {"business_id": b, "units": 25})
    allocation = svc.create_allocation(OWNER, {
        "service_id": service["id"], "portfolio_id": portfolio["id"],
        "method": "usage_based",
        "total_cost_minor": 10000, "business_ids": [a, b]})
    amounts = {r["business_id"]: r["amount_minor"]
               for r in allocation["allocations"]}
    assert amounts == {a: 7500, b: 2500}
    assert allocation["kind"] == "INTERNAL_ALLOCATION"


async def test_scenario_03_cross_business_opportunity_detected(app_portfolio):
    """§21.3: the engine detects a cross-business opportunity from
    system evidence (shared-service fit), deterministically."""
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Opp A")
    b = await make_business(app_portfolio, name="Opp B")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    make_service_with_access(app_portfolio, business_ids=[a])
    result = svc.analyze_portfolio(OWNER, portfolio["id"])
    assert result["opportunities_created"] >= 1
    opportunities = svc.list_opportunities(OWNER, portfolio["id"])["items"]
    shared = [o for o in opportunities if o["category"] == "SHARED_SERVICE"]
    assert shared and set(shared[0]["involved_business_ids"]) == {a, b}
    assert shared[0]["evidence_status"] == "VERIFIED"
    assert shared[0]["evidence"][0]["source"] == "p13.shared_service"
    # Re-running analysis creates no duplicates.
    again = svc.analyze_portfolio(OWNER, portfolio["id"])
    assert again["opportunities_created"] == 0


async def test_scenario_04_unauthorized_cross_business_access_blocked(
        app_portfolio):
    """§21.4: unauthorized cross-business access is blocked and the
    denial is audited."""
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Guard A")
    b = await make_business(app_portfolio, name="Guard B")
    from tests.p09_support import register_agent
    register_agent(app_portfolio, AGENT.id, business_ref=a)
    before = _audit_count(app_portfolio, "portfolio.isolation_violation")
    result = svc.check_agent_access(AGENT, business_id=b,
                                    category="aggregate_metrics")
    assert result["allowed"] is False
    after = _audit_count(app_portfolio, "portfolio.isolation_violation")
    assert after == before + 1
    # Portfolio aggregates are not visible to agents at all.
    with pytest.raises(PermissionDeniedError):
        svc.list_portfolios(AGENT)
    with pytest.raises(PermissionDeniedError):
        svc.portfolio_finance(AGENT, "any")


async def test_scenario_05_credentials_never_shared(app_portfolio):
    """§21.5: credentials (and the other never-grantable categories)
    cannot be granted, assigned, contributed or memorized across
    businesses — every surface refuses them."""
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Cred A")
    b = await make_business(app_portfolio, name="Cred B")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    from tests.p09_support import register_agent
    register_agent(app_portfolio, AGENT.id, business_ref=a)
    for category in ("credentials", "customer_records", "secrets"):
        with pytest.raises(ValidationError):
            svc.grant_access(OWNER, {
                "portfolio_id": portfolio["id"],
                "grantee_agent_id": AGENT.id, "business_id": b,
                "categories": [category], "rationale": "test",
                "expires_at": future_iso()})
        with pytest.raises(ValidationError):
            svc.assign_agent(OWNER, {
                "portfolio_id": portfolio["id"],
                "agent_id": AGENT.id, "scope_type": "BUSINESS",
                "business_id": b, "categories": [category],
                "expires_at": future_iso()})
    # The checked surface denies credentials even for the home business.
    result = svc.check_agent_access(AGENT, business_id=a,
                                    category="credentials")
    assert result["allowed"] is False
    # A portfolio workflow cannot take credentials as a contribution.
    with pytest.raises(ValidationError):
        svc.create_portfolio_workflow(OWNER, portfolio["id"], {
            "name": "Bad workflow", "participations": [
                {"business_id": a, "contribution_category": "research"},
                {"business_id": b,
                 "contribution_category": "credentials"}]})
    # Memory: only ORGANIZATION_SHARED records are visible to the
    # portfolio layer; a business-scoped record never appears.
    make_record(app_portfolio, business_id=b,
                access_scope="BUSINESS_SHARED", title="B-only secret plan",
                content="Business B internal plan details.")
    shared = make_record(app_portfolio,
                         access_scope="ORGANIZATION_SHARED",
                         title="General lesson")
    lessons = svc._shared_lessons()
    assert [row["id"] for row in lessons] == [shared["id"]]


async def test_scenario_06_unsupported_synergy_rejected(app_portfolio):
    """§21.6: a synergy claim without system evidence is rejected by
    the engine's own rules; speculation is labelled and can never be
    accepted as verified."""
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Syn A")
    b = await make_business(app_portfolio, name="Syn B")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    with pytest.raises(ValidationError):
        svc.submit_opportunity(OWNER, portfolio["id"], {
            "category": "SHARED_AUDIENCE", "involved_business_ids": [a, b],
            "title": "Trust me, huge synergy", "evidence": []})
    with pytest.raises(ValidationError):
        svc.submit_opportunity(OWNER, portfolio["id"], {
            "category": "SHARED_AUDIENCE", "involved_business_ids": [a, b],
            "title": "Blog-based synergy",
            "evidence": [{"source": "a blog post"}]})
    speculative = svc.submit_opportunity(OWNER, portfolio["id"], {
        "category": "SHARED_AUDIENCE", "involved_business_ids": [a, b],
        "title": "Maybe synergy",
        "evidence": [{"source": "p03.opportunity", "speculative": True}]})
    assert speculative["evidence_status"] == "SPECULATIVE"
    with pytest.raises(ValidationError):
        svc.decide_opportunity(OWNER, speculative["id"], "ACCEPTED")
    decided = svc.decide_opportunity(OWNER, speculative["id"], "REJECTED",
                                     "no verified evidence")
    assert decided["status"] == "REJECTED"


async def test_scenario_07_one_business_monopolizes_resources(app_portfolio):
    """§21.7: anti-monopolization — one business cannot take all
    shared capacity; the cap and the capacity both bind."""
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Mono A")
    b = await make_business(app_portfolio, name="Mono B")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    for bid in (a, b):
        svc.set_quota(OWNER, portfolio["id"], {
            "business_id": bid, "resource_kind": "inference_slots",
            "max_units": 4})
    # Share cap is 50% of 4 slots = 2: A cannot take 3 or 4.
    with pytest.raises(ValidationError):
        svc.propose_resource_allocation(OWNER, portfolio["id"], {
            "business_id": a, "resource_kind": "inference_slots",
            "units": 4})
    alloc_a = svc.propose_resource_allocation(OWNER, portfolio["id"], {
        "business_id": a, "resource_kind": "inference_slots", "units": 2})
    svc.decide_resource_allocation(OWNER, alloc_a["id"], True)
    alloc_b = svc.propose_resource_allocation(OWNER, portfolio["id"], {
        "business_id": b, "resource_kind": "inference_slots", "units": 2})
    svc.decide_resource_allocation(OWNER, alloc_b["id"], True)
    view = svc.resource_view(OWNER, portfolio["id"])
    assert view["kinds"]["inference_slots"]["available_units"] == 0


async def test_scenario_08_revoked_business_loses_shared_service(
        app_portfolio):
    """§21.8: revoking a business's service access ends its use
    immediately — usage and agent checks both refuse."""
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Revoke A")
    from tests.p09_support import register_agent
    register_agent(app_portfolio, AGENT.id, business_ref=a)
    service = svc.create_service(OWNER, {
        "name": "Revocable Analytics", "kind": "analytics"})
    access = svc.request_access(OWNER, service["id"], {"business_id": a})
    svc.decide_access(OWNER, access["id"], True)
    svc.activate_access(OWNER, access["id"])
    check = svc.check_service_access(AGENT, service_id=service["id"])
    assert check["allowed"] is True
    svc.record_usage(OWNER, service["id"], {"business_id": a, "units": 3})
    svc.revoke_access(OWNER, access["id"])
    with pytest.raises(PermissionDeniedError):
        svc.record_usage(OWNER, service["id"],
                         {"business_id": a, "units": 1})
    check = svc.check_service_access(AGENT, service_id=service["id"])
    assert check["allowed"] is False


async def test_scenario_09_cross_business_workflow_isolated(app_portfolio):
    """§21.9: a portfolio workflow runs through P-12 with per-
    business authorization and creates no access between
    participants."""
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Flow A")
    b = await make_business(app_portfolio, name="Flow B")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    from tests.p09_support import register_agent
    register_agent(app_portfolio, AGENT.id, business_ref=a)
    workflow = svc.create_portfolio_workflow(OWNER, portfolio["id"], {
        "name": "Joint research sprint", "objective": "shared research",
        "participations": [
            {"business_id": a, "contribution_category": "research",
             "contribution_description": "market scan"},
            {"business_id": b, "contribution_category": "content",
             "contribution_description": "summary draft"}]})
    # Cannot start until EVERY business authorized its contribution.
    with pytest.raises(ValidationError):
        svc.start_portfolio_workflow(OWNER, workflow["id"])
    svc.authorize_participation(OWNER, workflow["id"], a)
    with pytest.raises(ValidationError):
        svc.start_portfolio_workflow(OWNER, workflow["id"])
    svc.authorize_participation(OWNER, workflow["id"], b)
    started = svc.start_portfolio_workflow(OWNER, workflow["id"])
    assert started["status"] == "ACTIVE"
    ops_ids = {}
    for part in started["participations"]:
        assert part["status"] == "LINKED"
        view = app_portfolio.operations.get_workflow(
            OWNER, part["operations_workflow_id"])
        # Each sub-workflow lives in its OWN business's scope.
        assert view["business_id"] == part["business_id"]
        ops_ids[part["business_id"]] = part["operations_workflow_id"]
    assert ops_ids[a] != ops_ids[b]
    # Participation granted A's agent nothing in B.
    result = svc.check_agent_access(AGENT, business_id=b,
                                    category="aggregate_metrics")
    assert result["allowed"] is False
    # Drive both P-12 sub-workflows; the coordination roll-up follows.
    ops = app_portfolio.operations
    for wid in ops_ids.values():
        ops.validate_workflow(OWNER, wid)
        await ops.start_workflow(OWNER, wid)
    refreshed = svc.refresh_portfolio_workflow(OWNER, workflow["id"])
    assert refreshed["status"] == "COMPLETED"
    # Completing the workflow changed no business's lifecycle (§4).
    assert app_portfolio.business.get_business(a)["status"] not in (
        "OPERATIONAL",)


async def test_scenario_10_failing_business_contained(app_portfolio):
    """§21.10: a failing/paused business is flagged, survival mode
    blocks discretionary spend of shared resources, other businesses
    are untouched, and P-13 has no mechanism to move money."""
    svc = app_portfolio.portfolio
    healthy = await business_with_collected(
        app_portfolio, name="Healthy", amount="8000")
    failing = await make_business(app_portfolio, name="Failing")
    portfolio = await make_portfolio(
        app_portfolio, business_ids=[healthy, failing])
    app_portfolio.survival.pause_business(OWNER, failing)
    risk = svc.assess_risk(OWNER, portfolio["id"])
    failing_row = next(r for r in risk["per_business"]
                       if r["business_id"] == failing)
    assert any("paused" in s for s in failing_row["signals"])
    svc.set_survival_mode(OWNER, portfolio["id"], True)
    svc.set_quota(OWNER, portfolio["id"], {
        "business_id": healthy, "resource_kind": "agent_hours",
        "max_units": 100})
    with pytest.raises(ValidationError):
        svc.propose_resource_allocation(OWNER, portfolio["id"], {
            "business_id": healthy, "resource_kind": "agent_hours",
            "units": 10})
    essential = svc.propose_resource_allocation(OWNER, portfolio["id"], {
        "business_id": healthy, "resource_kind": "agent_hours",
        "units": 10, "essential": True})
    assert essential["status"] == "PROPOSED"
    # The healthy business's money is exactly where P-07 left it.
    finance = svc.portfolio_finance(OWNER, portfolio["id"])
    assert finance["totals"]["net_collected_minor"] == 8000_00
    # P-13 exposes no transfer capability at all.
    assert not any(name.startswith("transfer")
                   for name in dir(svc) if not name.startswith("_"))


async def test_scenario_11_portfolio_concentration_risk_detected(
        app_portfolio):
    """§21.11: verified-revenue concentration above the threshold is
    detected by concentration view, risk assessment and analysis."""
    svc = app_portfolio.portfolio
    big = await business_with_collected(app_portfolio, name="Big",
                                        amount="9000")
    small = await business_with_collected(app_portfolio, name="Small",
                                          amount="1000")
    portfolio = await make_portfolio(app_portfolio,
                                     business_ids=[big, small])
    view = svc.concentration_view(OWNER, portfolio["id"])
    shares = {r["business_id"]: r["share_bps"] for r in view["businesses"]}
    assert shares[big] == 9000 and shares[small] == 1000
    assert shares[big] >= view["threshold_bps"]
    risk = svc.assess_risk(OWNER, portfolio["id"])
    assert any(f["kind"] == "concentration" and
               f["business_id"] == big for f in risk["findings"])
    svc.analyze_portfolio(OWNER, portfolio["id"])
    recs = svc.list_recommendations(OWNER, portfolio["id"])["items"]
    assert any(r["kind"] == "RISK_REDUCTION" and
               "concentration" in r["title"].lower() for r in recs)


async def test_scenario_12_internal_allocations_not_external_payments(
        app_portfolio):
    """§21.12: an internal allocation never appears as an external
    payment, a revenue/expense, or a change to P-07 totals."""
    svc = app_portfolio.portfolio
    a = await business_with_collected(app_portfolio, name="Ledger A",
                                      amount="4000")
    b = await business_with_collected(app_portfolio, name="Ledger B",
                                      amount="4000")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    service = make_service_with_access(app_portfolio, business_ids=[a, b])
    svc.record_usage(OWNER, service["id"], {"business_id": a, "units": 10})
    before = app_portfolio.financial.consolidated("INR")
    allocation = svc.create_allocation(OWNER, {
        "service_id": service["id"], "portfolio_id": portfolio["id"],
        "method": "equal", "total_cost_minor": 2000,
        "business_ids": [a, b]})
    svc.decide_allocation(OWNER, allocation["id"], True)
    after = app_portfolio.financial.consolidated("INR")
    assert after == before  # P-07 did not move a single minor unit
    finance = svc.portfolio_finance(OWNER, portfolio["id"])
    assert finance["totals"]["net_collected_minor"] == 8000_00
    # Regression guard: the per-business rows must remain the
    # businesses (a variable-shadowing bug once replaced them with
    # allocation rows, which also broke report serialization).
    assert len(finance["businesses"]) == 2
    assert all("business_id" in r and "name" in r
               for r in finance["businesses"])
    listed = finance["internal_allocations"]
    # One row per charged business; every row carries the label.
    assert len(listed) == 2
    assert sum(r["amount_minor"] for r in listed) == 2000
    for row in listed:
        assert row["kind"] == "INTERNAL_ALLOCATION"
        assert row["is_external_payment"] is False
        assert "not an external" in row["presentation"]


async def test_scenario_13_businesses_compared_without_combining_finances(
        app_portfolio):
    """§21.13: comparison shows each business's own figures side by
    side; cash is never combined into a portfolio figure."""
    svc = app_portfolio.portfolio
    a = await business_with_collected(app_portfolio, name="Cmp A",
                                      amount="3000")
    b = await business_with_collected(app_portfolio, name="Cmp B",
                                      amount="1500")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    comparison = svc.compare_businesses(OWNER, [a, b])
    rows = {r["business_id"]: r for r in comparison["businesses"]}
    assert rows[a]["net_collected_minor"] == 3000_00
    assert rows[b]["net_collected_minor"] == 1500_00
    finance = svc.portfolio_finance(OWNER, portfolio["id"])
    assert finance["combined_available_cash"] is None
    assert "never summed" in finance["combined_cash_note"]
    # Flow totals are sums of flows only (collected), labelled as such.
    assert finance["totals"]["net_collected_minor"] == 4500_00


async def test_scenario_14_new_venture_recommendation_not_auto_created(
        app_portfolio):
    """§21.14: a venture proposal — even approved and handed off —
    creates no business. Creation remains P-06's, through P-03."""
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Base Biz")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a])

    def business_count() -> int:
        from sqlalchemy import func, select
        from app.database.models.business import Business
        session = app_portfolio.session_factory()
        try:
            return session.scalar(
                select(func.count()).select_from(Business)) or 0
        finally:
            session.close()

    before = business_count()
    venture = svc.propose_venture(OWNER, portfolio["id"], {
        "name": "Adjacent Venture", "category": "digital_products",
        "rationale": "adjacent audience",
        "evidence": [{"source": "p06.business",
                      "business_id": a}]})
    assert venture["status"] == "PROPOSED"
    assert business_count() == before
    svc.decide_venture(OWNER, venture["id"], True)
    assert business_count() == before
    handed = svc.handoff_venture(OWNER, venture["id"])
    assert handed["status"] == "HANDED_TO_P06"
    assert handed["linked_opportunity_id"]
    opportunity = app_portfolio.opportunities.get_opportunity(
        handed["linked_opportunity_id"])
    assert opportunity is not None
    assert business_count() == before  # still no new business


async def test_scenario_15_shared_agent_access_revoked(app_portfolio):
    """§21.15: a shared agent's scoped access works while granted
    and stops the moment it is revoked — grant and assignment both."""
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Agent Home")
    b = await make_business(app_portfolio, name="Agent Target")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    from tests.p09_support import register_agent
    register_agent(app_portfolio, AGENT.id, business_ref=a)
    grant = svc.grant_access(OWNER, {
        "portfolio_id": portfolio["id"],
        "grantee_agent_id": AGENT.id, "business_id": b,
        "categories": ["aggregate_metrics"],
        "rationale": "portfolio reporting", "expires_at": future_iso()})
    check = svc.check_agent_access(AGENT, business_id=b,
                                   category="aggregate_metrics")
    assert check["allowed"] is True and check["via"].startswith("grant:")
    svc.revoke_grant(OWNER, grant["id"])
    check = svc.check_agent_access(AGENT, business_id=b,
                                   category="aggregate_metrics")
    assert check["allowed"] is False
    # Same lifecycle for a portfolio-scope assignment.
    assignment = svc.assign_agent(OWNER, {
        "agent_id": AGENT.id, "scope_type": "PORTFOLIO",
        "portfolio_id": portfolio["id"],
        "categories": ["aggregate_metrics"], "expires_at": future_iso()})
    check = svc.check_agent_access(AGENT, business_id=b,
                                   category="aggregate_metrics")
    assert check["allowed"] is True
    svc.revoke_assignment(OWNER, assignment["id"])
    check = svc.check_agent_access(AGENT, business_id=b,
                                   category="aggregate_metrics")
    assert check["allowed"] is False


async def test_scenario_16_portfolio_report_reflects_actual_state(
        app_portfolio):
    """§21.16: a generated report contains the actual live state —
    the same figures the APIs return, with sources named."""
    svc = app_portfolio.portfolio
    a = await business_with_collected(app_portfolio, name="Rep A",
                                      amount="2500")
    b = await business_with_collected(app_portfolio, name="Rep B",
                                      amount="2500")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    report = svc.generate_report(OWNER, portfolio["id"],
                                 {"report_type": "FINANCIAL"})
    finance = svc.portfolio_finance(OWNER, portfolio["id"])
    assert report["content"]["finance"]["totals"] == finance["totals"]
    assert "p07.financial_service" in report["sources"]
    snapshot = svc.generate_report(OWNER, portfolio["id"],
                                   {"report_type": "SNAPSHOT"})
    assert snapshot["content"]["overview"]["total_businesses"] == 2
    exported = svc.export_report(OWNER, report["id"])
    assert exported["format"] == "json"
    assert exported["pdf"] == "NOT IMPLEMENTED"


def test_scenario_17_command_center_displays_portfolio(client_portfolio):
    """§21.17 (backend half): the API values the Command Center
    renders are consistent and complete; the UI half — the React
    Portfolio view rendering exactly these values — is verified in
    frontend/src/views/Portfolio.test.tsx and the live smoke."""
    headers = owner_http_headers(client_portfolio)
    created = client_portfolio.post(
        "/api/v1/portfolio/portfolios", headers=headers,
        json={"name": "CC Portfolio"})
    portfolio_id = created.json()["data"]["id"]
    overview = client_portfolio.get(
        f"/api/v1/portfolio/portfolios/{portfolio_id}/overview",
        headers=headers).json()["data"]
    assert overview["portfolio"]["name"] == "CC Portfolio"
    assert overview["total_businesses"] == 0
    finance = client_portfolio.get(
        f"/api/v1/portfolio/portfolios/{portfolio_id}/finance",
        headers=headers).json()["data"]
    assert finance["combined_available_cash"] is None
    assert finance["totals"]["net_collected_minor"] == 0
