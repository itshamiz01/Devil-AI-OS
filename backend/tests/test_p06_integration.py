"""P-06 integration tests: migration cycle, HTTP surface, and the
end-to-end creation flow over HTTP (fixture opportunity driven through
the real P-03 API, so its level is computed — never asserted)."""
from __future__ import annotations

import time

import pytest

from app.core.exceptions import InvalidStateTransitionError
from tests.conftest import OWNER, auth_headers  # noqa: F401  (fixture import)
from tests.p06_support import DECLARATION, app_rw, client_rw, make_fixture_business

BASE = "/api/v1"


def _wait_research(client, headers, session_id, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"{BASE}/research/{session_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.1)
    raise AssertionError("research session did not finish")


def _fixture_opportunity_http(client, headers, name="FIXTURE — HTTP Ebook"):
    resp = client.post(f"{BASE}/opportunities", headers=headers, json={
        "name": name, "category": "digital_products",
        "description": "FIXTURE — synthetic HTTP fixture for P-06 tests.",
        "target_customer": "fixture customers",
        "geography": "global", "problem_statement": "fixture problem",
        "proposed_solution": "fixture solution",
        "revenue_model": "one-time sales", "discovery_method": "manual"})
    assert resp.status_code == 201, resp.text
    opp = resp.json()["data"]
    for group, classification in (("fixture-interviews", "SUPPORTING"),
                                  ("fixture-survey", "CORROBORATED")):
        resp = client.post(f"{BASE}/opportunities/{opp['id']}/evidence",
                           headers=headers, json={
                               "category": "problem",
                               "evidence_kind": "source_claim",
                               "claim": f"fixture evidence {group}",
                               "source_name": f"src-{group}",
                               "independence_group": group,
                               "classification": classification})
        assert resp.status_code in (200, 201), resp.text
    resp = client.post(f"{BASE}/opportunities/{opp['id']}/research",
                       headers=headers, json={"source_keys": []})
    assert resp.status_code == 201, resp.text
    _wait_research(client, headers, resp.json()["data"]["id"])
    resp = client.post(f"{BASE}/opportunities/{opp['id']}/market-analysis",
                       headers=headers, json={
                           "customer_segment": "fixture segment",
                           "demand_indicators": ["fixture"],
                           "market_size": {"value": "cannot be established",
                                           "classification": "unknown"},
                           "saturation": "unknown", "sources": []})
    assert resp.status_code in (200, 201), resp.text
    resp = client.post(f"{BASE}/opportunities/{opp['id']}/commercial-analysis",
                       headers=headers, json={
                           "startup_costs": [{"name": "design tool",
                                              "amount": 15,
                                              "classification": "estimate"}],
                           "recurring_costs_monthly": [
                               {"name": "store fees", "amount": 5,
                                "classification": "estimate"}],
                           "variable_costs_per_sale": [
                               {"name": "delivery", "amount": 0.5,
                                "classification": "estimate"}],
                           "price": {"amount": 19,
                                     "classification": "estimate",
                                     "basis": "fixture"},
                           "platform_fee_pct": 10,
                           "payment_fee_pct": 3, "budget_amount": 50,
                           "scenario_sales": {
                               "conservative": {"sales_per_month": 2},
                               "base": {"sales_per_month": 6},
                               "optimistic": {"sales_per_month": 15}},
                           "proposed_channels": ["own website"]})
    assert resp.status_code in (200, 201), resp.text
    resp = client.post(f"{BASE}/opportunities/{opp['id']}/score",
                       headers=headers, json={})
    assert resp.status_code in (200, 201), resp.text
    resp = client.post(f"{BASE}/opportunities/{opp['id']}/validate",
                       headers=headers, json={})
    assert resp.status_code in (200, 201), resp.text
    level = resp.json()["data"]["level"]
    assert level == 3, f"fixture level computed by P-03 is {level}, not 3"
    return opp["id"]


# ------------------------------------------------------------------ migration
def test_p06_migration_cycle(tmp_path):
    import sqlite3
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[1]
    db = tmp_path / "cycle.db"
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location",
                        str(backend / "app" / "database" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")

    command.upgrade(cfg, "6ffcc7e899fa")
    con = sqlite3.connect(db)
    before = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()

    command.upgrade(cfg, "a8d7e0c717b4")
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    business_tables = {t for t in tables
                       if t.startswith("business_") or t == "businesses"
                       or t == "product_requirements"}
    assert len(business_tables) == 18, business_tables
    # P-07 disclosure: head advanced again by the additive P-07
    # migration (c3b5cdba2559 revises a8d7e0c717b4); same update,
    # same strictness.
    # P-08 disclosure: this cycle now targets the P-06 head revision
    # explicitly instead of "head". The additive P-08 migration
    # (99902c03a197 revises c3b5cdba2559) adds nine further
    # business_* tables, which the prefix count above would
    # misattribute to P-06; the P-06 assertions are unchanged in
    # kind and strictness, and the P-08 cycle is covered in
    # test_p08_integration.
    assert con.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0] \
        == "a8d7e0c717b4"
    con.close()

    command.downgrade(cfg, "6ffcc7e899fa")
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == before  # exact downgrade, history preserved
    con.close()

    command.upgrade(cfg, "a8d7e0c717b4")
    con = sqlite3.connect(db)
    # P-07 disclosure: head advanced again by the additive P-07
    # migration (c3b5cdba2559 revises a8d7e0c717b4); same update,
    # same strictness.
    # P-08 disclosure: cycle retargeted to the P-06 head revision
    # (see above); same update, same strictness.
    assert con.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0] \
        == "a8d7e0c717b4"
    con.close()


# ------------------------------------------------------------------ HTTP admin
def test_templates_and_settings_over_http(client_rw, auth_headers):
    resp = client_rw.get(f"{BASE}/business/templates", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    names = {t["name"] for t in data}
    assert names == {"ebook_digital_product", "saas_micro_tool",
                     "content_publication", "productized_service"}
    by_name = {t["name"]: t for t in data}
    assert by_name["ebook_digital_product"]["support_level"] == "operational"
    assert by_name["productized_service"]["support_level"] == "prepared_only"
    assert all(t["validation_status"] == "valid" for t in data)

    resp = client_rw.get(f"{BASE}/business/settings", headers=auth_headers)
    assert resp.json()["data"]["min_validation_level"] == 3
    resp = client_rw.put(f"{BASE}/business/settings", headers=auth_headers,
                         json={"values": {"min_validation_level": 2}})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["min_validation_level"] == 2
    resp = client_rw.put(f"{BASE}/business/settings", headers=auth_headers,
                         json={"values": {"min_validation_level": 9}})
    assert resp.status_code == 422, resp.text

    resp = client_rw.get(f"{BASE}/business/status", headers=auth_headers)
    status = resp.json()["data"]
    assert status["money_movement"].startswith("none")
    assert status["external_publishing"].startswith("none")


# ------------------------------------------------------------------ HTTP flow
def test_full_business_flow_over_http(client_rw, auth_headers):
    opp_id = _fixture_opportunity_http(client_rw, auth_headers)

    resp = client_rw.post(f"{BASE}/business/creation-approvals",
                          headers=auth_headers,
                          json={"opportunity_id": opp_id,
                                "template_name": "ebook_digital_product"})
    assert resp.status_code == 200, resp.text
    approval_id = resp.json()["data"]["approval_id"]
    resp = client_rw.post(f"{BASE}/approvals/{approval_id}/decision",
                          headers=auth_headers, json={"approve": True})
    assert resp.status_code == 200, resp.text

    resp = client_rw.post(f"{BASE}/business/eligibility",
                          headers=auth_headers,
                          json={"opportunity_id": opp_id,
                                "template_name": "ebook_digital_product",
                                "approval_id": approval_id})
    assert resp.json()["data"]["decision"] == "ELIGIBLE_FOR_CREATION", resp.text

    resp = client_rw.post(f"{BASE}/business/businesses",
                          headers=auth_headers,
                          json={"opportunity_id": opp_id,
                                "template_name": "ebook_digital_product",
                                "approval_id": approval_id})
    assert resp.status_code == 201, resp.text
    business = resp.json()["data"]
    assert business["is_fixture"] is True
    assert business["status"] == "BLUEPRINTING"
    bid = business["id"]

    resp = client_rw.post(f"{BASE}/business/businesses/{bid}/declarations",
                          headers=auth_headers, json=DECLARATION)
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["status"] == "approved"

    resp = client_rw.post(f"{BASE}/business/businesses/{bid}/blueprint",
                          headers=auth_headers)
    assert resp.status_code == 200, resp.text
    product_id = resp.json()["data"]["product_id"]

    resp = client_rw.post(f"{BASE}/business/businesses/{bid}/creation-run",
                          headers=auth_headers)
    assert resp.status_code == 200, resp.text
    run = resp.json()["data"]
    assert run["workflow_status"] == "COMPLETED"
    assert len(run["assets"]) == 10
    assert all(a["content_hash"] for a in run["assets"])

    resp = client_rw.get(f"{BASE}/business/businesses/{bid}/product",
                         headers=auth_headers)
    product = resp.json()["data"]
    assert product["id"] == product_id
    assert product["quality_review"]["checks"]

    resp = client_rw.post(
        f"{BASE}/business/businesses/{bid}/channels/evaluate",
        headers=auth_headers)
    assert resp.status_code == 200, resp.text
    channels = resp.json()["data"]["channels"]
    kdp = [c for c in channels if c["platform"] == "Amazon KDP"][0]
    assert kdp["platform_gate"]["outcome"] == "REQUIRES_HUMAN_ACTION"
    assert kdp["publish_state"] == "prepared"

    resp = client_rw.post(f"{BASE}/business/businesses/{bid}/readiness",
                          headers=auth_headers)
    assert resp.status_code == 200, resp.text
    review = resp.json()["data"]
    assert review["overall_status"] == "READY_WITH_WARNINGS", review
    assert any("KDP" in w for w in review["warnings"])

    resp = client_rw.post(f"{BASE}/business/businesses/{bid}/transition",
                          headers=auth_headers,
                          json={"target": "READY_FOR_LAUNCH",
                                "reason": "readiness recorded"})
    assert resp.status_code == 200, resp.text

    resp = client_rw.post(f"{BASE}/business/businesses/{bid}/launch/request",
                          headers=auth_headers)
    assert resp.status_code == 200, resp.text
    launch_approval = resp.json()["data"]["approval_id"]

    # No launch while the approval is still pending.
    resp = client_rw.post(f"{BASE}/business/businesses/{bid}/launch",
                          headers=auth_headers,
                          json={"approval_id": launch_approval})
    assert resp.status_code in (401, 403), resp.text

    resp = client_rw.post(f"{BASE}/approvals/{launch_approval}/decision",
                          headers=auth_headers, json={"approve": True})
    assert resp.status_code == 200, resp.text
    resp = client_rw.post(f"{BASE}/business/businesses/{bid}/launch",
                          headers=auth_headers,
                          json={"approval_id": launch_approval})
    assert resp.status_code == 200, resp.text
    launched = resp.json()["data"]
    assert launched["status"] == "OPERATIONAL"
    assert launched["deployment_state"] == "local_package_only"
    assert launched["public_availability"] is False
    assert launched["website_states"]["deployed"] is False

    resp = client_rw.get(f"{BASE}/business/businesses/{bid}/lifecycle",
                         headers=auth_headers)
    states = [e["to_status"] for e in resp.json()["data"]]
    assert states[0] == "PROPOSED" and states[-1] == "OPERATIONAL"


# ------------------------------------------------------- service-level flows
async def test_duplicate_business_for_opportunity_conflicts(app_rw):
    opp_id, business = await make_fixture_business(app_rw)
    svc = app_rw.business
    request = await svc.request_creation_approval(
        OWNER, opp_id, "ebook_digital_product")
    app_rw.approvals.decide(request["approval_id"], OWNER, True)
    with pytest.raises(InvalidStateTransitionError):
        await svc.create_business(
            OWNER, {"opportunity_id": opp_id,
                    "template_name": "ebook_digital_product",
                    "approval_id": request["approval_id"]})


async def test_blueprint_ready_requires_blueprint(app_rw):
    _, business = await make_fixture_business(app_rw)
    svc = app_rw.business
    with pytest.raises(InvalidStateTransitionError):
        await svc.transition_business(OWNER, business["id"],
                                      "BLUEPRINT_READY")
    await svc.generate_blueprint(OWNER, business["id"])
    assert svc.get_business(business["id"])["status"] == "BLUEPRINT_READY"


async def test_financial_inputs_payload(app_rw):
    _, business = await make_fixture_business(app_rw)
    svc = app_rw.business
    await svc.generate_blueprint(OWNER, business["id"])
    payload = svc.financial_inputs(business["id"])
    assert payload["startup_total_estimate"] == 15.0
    assert payload["recurring_monthly_estimate"] == 5.0
    assert payload["pricing"]["amount"] == 19
    assert "no revenue is recorded by P-06" in payload["revenue_recognition"]
