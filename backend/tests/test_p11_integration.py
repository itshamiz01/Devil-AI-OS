"""P-11 integration tests: the Premium Command Center's backend surface.

Covers the additive migration cycle (137 -> 139 -> 137 -> 139), the
dashboard aggregation endpoints' authentication, the zero-state honesty
of a fresh install (acceptance Scenario 12), exact equality between the
dashboard's financial figures and P-07's own consolidated endpoint on
identical fixtures (§15.2/§28.2 — the UI must never show a number the
API does not), principal-scoped preferences, the notification lifecycle
including the §5.4 rule that critical alerts cannot be dismissed, and
unified search validation.

House pattern copied from tests/test_p10_integration.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import make_settings
from tests.p07_support import (
    app_fin,
    business_with_profile,
    client_fin,
    owner_http_headers,
    paid_expense,
    verified_revenue,
)

DASH = "/api/v1/dashboard"


def _alembic_config(url: str):
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location",
                           str(backend / "app" / "database" / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _table_count(url: str) -> int:
    from sqlalchemy import create_engine, inspect

    engine = create_engine(url)
    try:
        return len(inspect(engine).get_table_names())
    finally:
        engine.dispose()


# ------------------------------------------------------------ migration
def test_p11_migration_cycle(tmp_path):
    """137 (P-10 head) -> 139 (P-11: two dashboard-owned tables)
    -> downgrade back to 137 -> re-upgrade to 139. Exact and
    reversible; the only new tables are dashboard_preferences and
    dashboard_notification_states (§25).

    P-12 disclosure: "head" now continues past the P-11 head to the
    P-12 migration (153). The P-11 segment is pinned explicitly to
    193731df4c37 instead of "head" — the step this test verifies is
    unchanged and still exact."""
    from alembic import command

    url = f"sqlite:///{tmp_path / 'p11_mig.db'}"
    config = _alembic_config(url)
    command.upgrade(config, "e37d00443d20")
    assert _table_count(url) == 137
    command.upgrade(config, "193731df4c37")
    assert _table_count(url) == 139
    from sqlalchemy import create_engine, inspect

    engine = create_engine(url)
    names = set(inspect(engine).get_table_names())
    engine.dispose()
    assert "dashboard_preferences" in names
    assert "dashboard_notification_states" in names
    command.downgrade(config, "e37d00443d20")
    assert _table_count(url) == 137
    command.upgrade(config, "193731df4c37")
    assert _table_count(url) == 139


def test_p11_metadata_registers_exactly_two_new_tables():
    from app.database.models.base import Base
    import app.database.models  # noqa: F401  (registers all models)

    assert "dashboard_preferences" in Base.metadata.tables
    assert "dashboard_notification_states" in Base.metadata.tables
    # 136 (P-10) + 2 = 138 model tables.
    # P-12 disclosure: P-12 added 14 operations tables on top; the
    # P-11 increment is still exactly these two tables, and the
    # metadata total is now 152. Strictness preserved (exact count).
    # P-13 disclosure: P-13 added 19 portfolio tables on top; the
    # P-11/P-12 increments are unchanged and the metadata total is
    # now 171. Strictness preserved (exact count).
    # P-14 Stage B disclosure: Stage B added one table
    # (event_dead_letters, DEF-I4); the metadata total is now 172.
    # Strictness preserved (exact count).
    # P-15 disclosure: P-15 added four reliability tables
    # (performance_samples, reliability_incidents, readiness_snapshots,
    # benchmark_runs); the metadata total is now 176.
    # P-16 disclosure: P-16 added fourteen economy tables; the
    # metadata total is now 190. Strictness preserved (exact count).
    # P-17 disclosure: P-17 added eighteen growth tables; the
    # metadata total is now 208. Strictness preserved (exact count).
    # P-18 disclosure: P-18 added fifteen experience tables; the
    # metadata total is now 223. Strictness preserved (exact count).
    # Expansion F01 disclosure: Expansion Feature 1 added two
    # identity/device tables; the metadata total is now 225.
    # Strictness preserved (exact count).
    # Expansion F02 disclosure: Expansion Feature 2 added two
    # integration-framework tables; the metadata total is now 227.
    # Strictness preserved (exact count).
    # Expansion F03 disclosure: Expansion Feature 3 added four
    # voice tables; the metadata total is now 231.
    # Expansion F06 disclosure: Expansion Feature 6 added three
    # knowledge tables; the metadata total is now 234.
    assert len(Base.metadata.tables) == 234


# ------------------------------------------------------- authentication
@pytest.mark.parametrize("path", [
    "/overview", "/system-health", "/activity", "/attention",
    "/agents/summary", "/businesses/summary", "/opportunities/summary",
    "/execution/summary", "/finance/summary", "/security/summary",
    "/survival/overview", "/approvals/summary", "/notifications",
    "/preferences", "/search?q=ab",
])
def test_dashboard_endpoints_require_authentication(client, path):
    resp = client.get(f"{DASH}{path}")
    assert resp.status_code in (401, 403), (path, resp.status_code)


# ------------------------------------------------- zero state (Scen. 12)
def test_overview_zero_state_is_honest(client, auth_headers):
    """A fresh install shows true zeros and an explicitly *unavailable*
    portfolio cash figure — never an invented number (§2 rule 3)."""
    resp = client.get(f"{DASH}/overview", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["counts"]["businesses_total"] == 0
    assert data["counts"]["pending_approvals"] == 0
    kpis = {k["key"]: k for k in data["kpis"]}
    assert kpis["active_businesses"]["value"] == 0
    assert kpis["collected_revenue"]["value"] == 0
    assert kpis["available_cash"]["state"] == "unavailable"
    assert kpis["available_cash"]["value"] is None
    assert data["finance"]["totals"]["net_collected_minor"] == 0


def test_system_health_never_fabricates_gpu(client, auth_headers):
    resp = client.get(f"{DASH}/system-health", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    checks = {c["key"]: c for c in resp.json()["data"]["checks"]}
    assert checks["gpu"]["state"] == "unavailable"
    assert checks["database"]["state"] == "ok"


# ------------------------------------------- data accuracy (§15.2/§28.2)
async def test_overview_finance_equals_p07_consolidated(app_fin, client_fin):
    """Identical fixtures: the dashboard's collected/expenses/profit
    figures must equal P-07's consolidated endpoint exactly (minor
    units), and the finance summary endpoint must agree too."""
    business_id, _profile = await business_with_profile(app_fin)
    await verified_revenue(app_fin, business_id, "1000.00")
    await paid_expense(app_fin, business_id, "250.00")
    headers = owner_http_headers(client_fin)

    consolidated = client_fin.get(
        "/api/v1/financial/overview", headers=headers,
        params={"currency": "INR"})
    assert consolidated.status_code == 200, consolidated.text
    totals = consolidated.json()["data"]["totals"]
    assert totals["net_collected_minor"] == 100000
    assert totals["expenses_minor"] == 25000
    assert totals["net_profit_minor"] == 75000

    overview = client_fin.get(f"{DASH}/overview", headers=headers,
                              params={"currency": "INR"})
    assert overview.status_code == 200, overview.text
    data = overview.json()["data"]
    assert data["finance"]["totals"] == totals
    kpis = {k["key"]: k for k in data["kpis"]}
    assert kpis["collected_revenue"]["value"] == 100000
    assert kpis["net_profit"]["value"] == 75000
    assert data["counts"]["businesses_total"] == 1
    # Fixture provenance is never hidden (§15.2).
    assert data["finance"]["businesses"][0]["is_fixture"] is True

    summary = client_fin.get(f"{DASH}/finance/summary", headers=headers,
                             params={"currency": "INR"})
    assert summary.json()["data"]["totals"] == totals


# ------------------------------------------------------------ preferences
def test_preferences_defaults_update_and_scoping(client, auth_headers,
                                                  service_headers):
    resp = client.get(f"{DASH}/preferences", headers=auth_headers)
    assert resp.status_code == 200
    prefs = resp.json()["data"]["preferences"]
    assert prefs["sidebar_collapsed"] is False
    assert prefs["default_view"] == "overview"

    # The preferences body is FLAT and typed (PreferencesIn): a patch of
    # preference keys, not a nested envelope.
    put = client.put(f"{DASH}/preferences", headers=auth_headers,
                     json={"sidebar_collapsed": True, "currency": "USD"})
    assert put.status_code == 200, put.text
    assert put.json()["data"]["preferences"]["sidebar_collapsed"] is True
    assert put.json()["data"]["preferences"]["currency"] == "USD"

    # Another principal's record is independent (§25 scoping).
    other = client.get(f"{DASH}/preferences", headers=service_headers)
    assert other.json()["data"]["preferences"]["sidebar_collapsed"] is False
    # And the owner's persisted value survives.
    again = client.get(f"{DASH}/preferences", headers=auth_headers)
    assert again.json()["data"]["preferences"]["currency"] == "USD"


def test_preferences_reject_unknown_keys_and_bad_values(client, auth_headers):
    # Unknown keys are forbidden at the route model (extra="forbid") and
    # invalid values fail validation — a typo can never silently no-op.
    bad_key = client.put(f"{DASH}/preferences", headers=auth_headers,
                         json={"theme": "pink"})
    assert bad_key.status_code == 422
    bad_density = client.put(f"{DASH}/preferences", headers=auth_headers,
                             json={"density": "huge"})
    assert bad_density.status_code == 422
    bad_type = client.put(f"{DASH}/preferences", headers=auth_headers,
                          json={"sidebar_collapsed": "not-a-bool"})
    assert bad_type.status_code == 422


# ------------------------------------------- approvals inbox + attention
def _make_approval(client, headers, action="config.change"):
    resp = client.post("/api/v1/approvals", headers=headers, json={
        "action": action, "resource": "system:settings",
        "risk_classification": "high", "reason": "p11 test",
        "requested_permissions": ["modify_system_config"],
        "parameters": {"setting": "alert_threshold", "value": 3}})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def test_pending_approval_surfaces_everywhere(client, auth_headers,
                                              service_headers):
    """Scenario 5 (backend side): one real pending approval appears in
    the unified summary, the attention queue and the overview count —
    with its exact parameters and hash intact."""
    approval = _make_approval(client, service_headers)

    summary = client.get(f"{DASH}/approvals/summary", headers=auth_headers)
    assert summary.status_code == 200
    assert summary.json()["data"]["core_pending"] >= 1

    # The unified inbox list itself is P-01's approvals endpoint; the
    # record must carry its exact parameters and hash (§15.3).
    inbox = client.get("/api/v1/approvals", headers=auth_headers,
                       params={"status": "pending"})
    assert inbox.status_code == 200
    mine = [a for a in inbox.json()["data"] if a["id"] == approval["id"]]
    assert len(mine) == 1
    assert mine[0]["parameters"] == {"setting": "alert_threshold", "value": 3}
    assert mine[0]["parameters_hash"] == approval["parameters_hash"]

    attention = client.get(f"{DASH}/attention", headers=auth_headers)
    kinds = {(i["kind"], i["ref_id"]) for i in attention.json()["data"]["items"]}
    assert ("approval", approval["id"]) in kinds

    overview = client.get(f"{DASH}/overview", headers=auth_headers)
    assert overview.json()["data"]["counts"]["pending_approvals"] >= 1


# ------------------------------------------------------------ notifications
def test_notification_read_and_dismiss_lifecycle(client, auth_headers,
                                                 service_headers):
    approval = _make_approval(client, service_headers, action="deploy.release")
    nid = f"approval:{approval['id']}"

    listing = client.get(f"{DASH}/notifications", headers=auth_headers)
    assert listing.status_code == 200
    items = {i["id"]: i for i in listing.json()["data"]["items"]}
    assert nid in items and items[nid]["is_read"] is False
    assert listing.json()["data"]["unread"] >= 1

    read = client.post(f"{DASH}/notifications/{nid}/read",
                       headers=auth_headers)
    assert read.status_code == 200, read.text
    after = client.get(f"{DASH}/notifications", headers=auth_headers)
    items = {i["id"]: i for i in after.json()["data"]["items"]}
    assert items[nid]["is_read"] is True

    dismiss = client.post(f"{DASH}/notifications/{nid}/dismiss",
                          headers=auth_headers)
    assert dismiss.status_code == 200, dismiss.text
    final = client.get(f"{DASH}/notifications", headers=auth_headers)
    assert nid not in {i["id"] for i in final.json()["data"]["items"]}

    unknown = client.post(f"{DASH}/notifications/approval:nope/read",
                          headers=auth_headers)
    assert unknown.status_code == 404


async def test_critical_security_alert_cannot_be_dismissed(
        application, client, auth_headers):
    """§5.4: a critical alert stays visible until handled at source.
    Chain (the proven P-10 Scenario-16 path): a non-owner policy-change
    attempt at the service layer is denied and audited as
    security.policy_update/deny; alert evaluation raises the critical
    policy_change_attempt alert; the dashboard must refuse to dismiss
    its notification. (An HTTP-layer 403 is recorded by the permission
    layer under a different audit action and does not feed this rule —
    that is P-10's design, not something P-11 changes.)"""
    from app.core.exceptions import PermissionDeniedError
    from app.permissions.models import Principal, PrincipalType

    agent = Principal(PrincipalType.AGENT, "agent-1")
    with pytest.raises(PermissionDeniedError):
        application.security.update_settings(
            agent, {"login_max_failures": 10000})
    created = application.security.monitor.evaluate_alerts()
    assert any(a["rule"] == "policy_change_attempt" for a in created)

    listing = client.get(f"{DASH}/notifications", headers=auth_headers)
    security_items = [i for i in listing.json()["data"]["items"]
                      if i["kind"] == "security_alert"]
    assert security_items, listing.text
    item = security_items[0]
    assert item["severity"] == "critical"
    assert item["dismissible"] is False
    refused = client.post(f"{DASH}/notifications/{item['id']}/dismiss",
                          headers=auth_headers)
    # The app's envelope maps ValidationError to 422.
    assert refused.status_code == 422, refused.text
    assert "cannot be dismissed" in refused.json()["error"]["message"]
    # Still there afterwards.
    again = client.get(f"{DASH}/notifications", headers=auth_headers)
    assert item["id"] in {i["id"] for i in again.json()["data"]["items"]}


# ------------------------------------------------------------------ search
def test_search_validation(client, auth_headers):
    # Query validation is FastAPI's 422 (min_length=2 on q).
    short = client.get(f"{DASH}/search", headers=auth_headers,
                       params={"q": "a"})
    assert short.status_code == 422
    ok = client.get(f"{DASH}/search", headers=auth_headers,
                    params={"q": "nothing-matches-this"})
    assert ok.status_code == 200
    assert ok.json()["data"]["total"] == 0


async def test_search_finds_real_business(app_fin, client_fin):
    business_id, _profile = await business_with_profile(
        app_fin, name="Searchable Fitness Ebook")
    headers = owner_http_headers(client_fin)
    resp = client_fin.get(f"{DASH}/search", headers=headers,
                          params={"q": "Searchable"})
    assert resp.status_code == 200, resp.text
    results = resp.json()["data"]["results"]
    hits = [r for r in results.get("businesses", []) if r["id"] == business_id]
    assert len(hits) == 1
    assert hits[0]["link"] == f"#/businesses/{business_id}"
