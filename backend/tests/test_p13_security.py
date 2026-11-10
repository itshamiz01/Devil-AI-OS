"""P-13 security tests (§20): owner-only governance, grant expiry,
agent scoping, audited denials, Article 0 surfaces."""
from __future__ import annotations

import pytest

from app.core.exceptions import PermissionDeniedError, ValidationError
from app.permissions.models import Principal, PrincipalType
from tests.p13_support import (  # noqa: F401
    AGENT, AGENT2, EXTERNAL, OWNER, SERVICE, app_portfolio, future_iso,
    make_business, make_portfolio, past_iso,
)

pytestmark = pytest.mark.asyncio

AGENT_PRINCIPAL = Principal(PrincipalType.AGENT, AGENT.id)


async def test_portfolio_writes_are_owner_only(app_portfolio):
    svc = app_portfolio.portfolio
    for principal in (AGENT_PRINCIPAL, SERVICE, EXTERNAL):
        with pytest.raises(PermissionDeniedError):
            svc.create_portfolio(principal, {"name": "Nope"})
        with pytest.raises(PermissionDeniedError):
            svc.create_service(principal, {
                "name": "Nope", "kind": "analytics"})
        with pytest.raises(PermissionDeniedError):
            svc.update_settings(principal, {
                "concentration_threshold_bps": 100})


async def test_agent_cannot_read_portfolio_aggregates(app_portfolio):
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Agg A")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a])
    for call in (
            lambda: svc.portfolio_overview(AGENT_PRINCIPAL,
                                           portfolio["id"]),
            lambda: svc.concentration_view(AGENT_PRINCIPAL,
                                           portfolio["id"]),
            lambda: svc.assess_risk(AGENT_PRINCIPAL, portfolio["id"]),
            lambda: svc.strategy_view(AGENT_PRINCIPAL, portfolio["id"]),
            lambda: svc.list_grants(AGENT_PRINCIPAL),
            lambda: svc.list_assignments(AGENT_PRINCIPAL)):
        with pytest.raises(PermissionDeniedError):
            call()


async def test_expired_grant_stops_working(app_portfolio):
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Exp Home")
    b = await make_business(app_portfolio, name="Exp Target")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    from tests.p09_support import register_agent
    register_agent(app_portfolio, AGENT.id, business_ref=a)
    # Past expiry is refused at creation time.
    with pytest.raises(ValidationError):
        svc.grant_access(OWNER, {
            "portfolio_id": portfolio["id"],
            "grantee_agent_id": AGENT.id, "business_id": b,
            "categories": ["aggregate_metrics"], "rationale": "x",
            "expires_at": past_iso()})
    grant = svc.grant_access(OWNER, {
        "portfolio_id": portfolio["id"],
        "grantee_agent_id": AGENT.id, "business_id": b,
        "categories": ["aggregate_metrics"], "rationale": "x",
        "expires_at": future_iso(1)})
    assert svc.check_agent_access(
        AGENT_PRINCIPAL, business_id=b,
        category="aggregate_metrics")["allowed"] is True
    # Force expiry (time passing) — access ends without any action.
    from datetime import datetime, timedelta, timezone
    session = app_portfolio.session_factory()
    try:
        from app.database.models.portfolio import CrossBusinessPermission
        row = session.get(CrossBusinessPermission, grant["id"])
        row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        session.commit()
    finally:
        session.close()
    assert svc.check_agent_access(
        AGENT_PRINCIPAL, business_id=b,
        category="aggregate_metrics")["allowed"] is False


async def test_grant_is_scoped_to_one_business_and_categories(
        app_portfolio):
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Scope Home")
    b = await make_business(app_portfolio, name="Scope B")
    c = await make_business(app_portfolio, name="Scope C")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b, c])
    from tests.p09_support import register_agent
    register_agent(app_portfolio, AGENT.id, business_ref=a)
    svc.grant_access(OWNER, {
        "portfolio_id": portfolio["id"],
        "grantee_agent_id": AGENT.id, "business_id": b,
        "categories": ["aggregate_metrics"], "rationale": "reporting",
        "expires_at": future_iso()})
    # Granted category on granted business: allowed.
    assert svc.check_agent_access(
        AGENT_PRINCIPAL, business_id=b,
        category="aggregate_metrics")["allowed"] is True
    # Ungranted category on the same business: denied.
    assert svc.check_agent_access(
        AGENT_PRINCIPAL, business_id=b,
        category="financial_summary")["allowed"] is False
    # Granted category on a different business: denied.
    assert svc.check_agent_access(
        AGENT_PRINCIPAL, business_id=c,
        category="aggregate_metrics")["allowed"] is False
    # A different agent gets nothing from this grant.
    register_agent(app_portfolio, AGENT2.id, business_ref=a)
    assert svc.check_agent_access(
        AGENT2, business_id=b,
        category="aggregate_metrics")["allowed"] is False


async def test_home_business_access_via_checked_surface(app_portfolio):
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Home Biz")
    from tests.p09_support import register_agent
    register_agent(app_portfolio, AGENT.id, business_ref=a)
    result = svc.check_agent_access(AGENT_PRINCIPAL, business_id=a,
                                    category="aggregate_metrics")
    assert result["allowed"] is True
    assert result["via"] == "home_business"


async def test_portfolio_settings_do_not_touch_security_or_money(
        app_portfolio):
    """Article 0 adjacency: P-13 settings govern portfolio
    thresholds only — there is no path from portfolio configuration
    to P-10 policy or P-07 limits."""
    svc = app_portfolio.portfolio
    updated = svc.update_settings(OWNER, {
        "concentration_threshold_bps": 5000,
        "capacities": {"inference_slots": 2}})
    assert updated["concentration_threshold_bps"] == 5000
    assert updated["capacities"]["inference_slots"] == 2
    with pytest.raises(ValidationError):
        svc.update_settings(OWNER, {"capacities": {"money": 5}})
    # No settings key can name a financial or security control.
    assert not any("approval" in k or "limit" in k or "policy" in k
                   for k in svc.get_settings())


async def test_relationship_grants_no_access(app_portfolio):
    """§7: an ACTIVE relationship is a declaration, not access."""
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="RelIso A")
    b = await make_business(app_portfolio, name="RelIso B")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    from tests.p09_support import register_agent
    register_agent(app_portfolio, AGENT.id, business_ref=a)
    rel = svc.create_relationship(OWNER, {
        "portfolio_id": portfolio["id"],
        "source_business_id": a, "target_business_id": b,
        "relationship_type": "PARTNERSHIP",
        "sharing_policy": "SPECIFIC_RECORDS"})
    svc.transition_relationship(OWNER, rel["id"], "APPROVED")
    svc.transition_relationship(OWNER, rel["id"], "ACTIVE")
    assert svc.check_agent_access(
        AGENT_PRINCIPAL, business_id=b,
        category="aggregate_metrics")["allowed"] is False
