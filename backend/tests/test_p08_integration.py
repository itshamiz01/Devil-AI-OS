"""P-08 integration tests: migration cycle, application wiring,
and the HTTP surface end-to-end (including the verbatim-P-07
figures proof over the wire)."""
from __future__ import annotations

from alembic import command
from alembic.config import Config

from tests.p08_support import app_surv, client_surv, owner_http_headers  # noqa: F401

SURVIVAL_TABLES = {
    "business_health_snapshots", "business_health_dimensions",
    "business_monitoring_events", "business_observations",
    "business_decisions", "business_decision_alternatives",
    "business_lifecycle_overlays", "business_experiments",
    "experiment_evaluations", "scaling_assessments", "scaling_plans",
    "recovery_plans", "closure_reviews",
    "capital_allocation_proposals", "resource_allocation_proposals",
    "survival_forecasts", "decision_outcomes", "business_pause_controls",
}


def _alembic_config(url: str) -> Config:
    from pathlib import Path
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location",
                           str(backend / "app" / "database" / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _table_names(url: str) -> set[str]:
    from sqlalchemy import create_engine, inspect
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_p08_migration_cycle(tmp_path):
    """P-07 head (90 tables) -> P-08 head (108) -> downgrade (90) ->
    re-upgrade (108): one additive migration, exact and reversible."""
    url = f"sqlite:///{tmp_path}/p08_cycle.db"
    config = _alembic_config(url)
    command.upgrade(config, "c3b5cdba2559")
    before = _table_names(url)
    assert len(before) == 90
    assert not (SURVIVAL_TABLES & before)
    # P-09 disclosure: "head" has since advanced to the additive P-09
    # migration (7b13db7e9bfa revises 99902c03a197), so this cycle now
    # targets the P-08 head explicitly — the exact table-count and
    # downgrade assertions below are unchanged in kind.
    command.upgrade(config, "99902c03a197")
    after = _table_names(url)
    assert len(after) == 108
    assert SURVIVAL_TABLES <= after
    command.downgrade(config, "c3b5cdba2559")
    assert _table_names(url) == before
    command.upgrade(config, "99902c03a197")
    assert _table_names(url) == after


async def test_survival_tables_present_on_startup(app_surv):
    from sqlalchemy import inspect
    tables = set(inspect(app_surv.engine).get_table_names())
    assert SURVIVAL_TABLES <= tables
    assert app_surv.survival is not None
    status = app_surv.survival.status()
    assert status["financial_source"].startswith("p07 only")
    assert status["lifecycle_owner"].startswith("p06")


def test_http_status_and_auth(client_surv):
    headers = owner_http_headers(client_surv)
    resp = client_surv.get("/api/v1/survival/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["engine"] == "survival_and_scaling"
    assert "NOT IMPLEMENTED" in data["frontend"]
    unauthenticated = client_surv.get("/api/v1/survival/status")
    assert unauthenticated.status_code == 401
    settings = client_surv.get("/api/v1/survival/settings",
                               headers=headers)
    assert settings.status_code == 200
    assert settings.json()["data"]["max_increment_ratio"] == "0.5"


def _http_business(client, headers) -> str:
    from tests.p06_support import DECLARATION
    from tests.test_p06_integration import _fixture_opportunity_http
    opp_id = _fixture_opportunity_http(client, headers)
    resp = client.post("/api/v1/business/creation-approvals",
                       headers=headers,
                       json={"opportunity_id": opp_id,
                             "template_name": "ebook_digital_product"})
    assert resp.status_code == 200, resp.text
    approval_id = resp.json()["data"]["approval_id"]
    resp = client.post(f"/api/v1/approvals/{approval_id}/decision",
                       headers=headers, json={"approve": True})
    assert resp.status_code == 200, resp.text
    resp = client.post("/api/v1/business/businesses",
                       headers=headers,
                       json={"opportunity_id": opp_id,
                             "template_name": "ebook_digital_product",
                             "approval_id": approval_id})
    assert resp.status_code == 201, resp.text
    business_id = resp.json()["data"]["id"]
    resp = client.post(
        f"/api/v1/business/businesses/{business_id}/declarations",
        headers=headers, json=DECLARATION)
    assert resp.status_code == 201, resp.text
    resp = client.put("/api/v1/business/settings", headers=headers,
                      json={"values": {"default_currency": "INR"}})
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/api/v1/business/businesses/{business_id}/blueprint",
        headers=headers)
    assert resp.status_code == 200, resp.text
    return business_id


def test_http_evaluate_honesty_then_verbatim_figures(client_surv):
    """Over HTTP: a fresh fixture business evaluates to
    INSUFFICIENT_DATA; after P-07 seeding, the snapshot's figures
    equal a fresh P-07 indicators reading exactly (Lock 1)."""
    headers = owner_http_headers(client_surv)
    business_id = _http_business(client_surv, headers)

    resp = client_surv.post(
        f"/api/v1/survival/businesses/{business_id}/evaluate",
        headers=headers)
    assert resp.status_code == 200, resp.text
    snapshot = resp.json()["data"]["snapshot"]
    assert snapshot["classification"] == "INSUFFICIENT_DATA"

    profile = client_surv.post(
        f"/api/v1/financial/businesses/{business_id}/profile",
        json={}, headers=headers)
    assert profile.status_code in (200, 201), profile.text
    opening = client_surv.post(
        f"/api/v1/financial/businesses/{business_id}/opening-balance",
        json={"amount": "20000.00", "currency": "INR",
              "entry_date": "2026-11-01", "account_ref": "bank:primary",
              "source": "bank_statement",
              "verification_status": "verified"},
        headers=headers)
    assert opening.status_code == 201, opening.text
    revenue = client_surv.post(
        "/api/v1/financial/revenue",
        json={"business_id": business_id, "category": "product_sale",
              "amount": "2500.00", "currency": "INR",
              "transaction_date": "2026-11-05",
              "source": "authorized_provider_report",
              "initial_status": "PAYMENT_SETTLED",
              "customer_ref": "cust-a",
              "creation_method": "provider_report"},
        headers=headers)
    assert revenue.status_code in (200, 201), revenue.text

    resp = client_surv.post(
        f"/api/v1/survival/businesses/{business_id}/evaluate",
        headers=headers)
    assert resp.status_code == 200, resp.text
    snapshot = resp.json()["data"]["snapshot"]
    indicators = client_surv.get(
        f"/api/v1/financial/businesses/{business_id}/indicators",
        headers=headers)
    assert indicators.status_code == 200, indicators.text
    p07 = indicators.json()["data"]
    for key in ("verified_collected_revenue_minor",
                "available_capital_minor", "actual_expenses_minor"):
        assert snapshot["indicators"][key] == p07[key], key

    lifecycle = client_surv.get(
        f"/api/v1/survival/businesses/{business_id}/lifecycle",
        headers=headers)
    assert lifecycle.status_code == 200
    assert lifecycle.json()["data"]["p06_state"] in (
        "PROPOSED", "BLUEPRINTING", "BLUEPRINT_READY")


def test_http_no_delete_routes_for_permanent_records(client_surv):
    """§9.5/§32 rule 18: experiments, evaluations, snapshots,
    decisions, forecasts and outcomes expose no DELETE route."""
    headers = owner_http_headers(client_surv)
    for path in ("/api/v1/survival/experiments/anything",
                 "/api/v1/survival/health/snapshots/anything",
                 "/api/v1/survival/decisions/anything"):
        resp = client_surv.delete(path, headers=headers)
        assert resp.status_code in (404, 405), (path, resp.status_code)


def test_http_portfolio_and_analyst(client_surv):
    headers = owner_http_headers(client_surv)
    overview = client_surv.get("/api/v1/survival/portfolio/overview",
                               headers=headers)
    assert overview.status_code == 200
    assert "p07" in overview.json()["data"]["consolidated_source"]
    answer = client_surv.post(
        "/api/v1/survival/analyst/query", headers=headers,
        json={"intent": "biggest_portfolio_risk"})
    assert answer.status_code == 200
    figures = answer.json()["data"]["figures"]
    assert figures and figures[0]["classification"] in (
        "verified_fact", "calculated_metric", "forecast", "assumption",
        "missing")
    bad = client_surv.post(
        "/api/v1/survival/analyst/query", headers=headers,
        json={"intent": "tell_me_a_story"})
    assert bad.status_code in (400, 422)
