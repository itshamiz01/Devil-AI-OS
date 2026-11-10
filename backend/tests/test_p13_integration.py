"""P-13 integration tests: migration cycle, registry, relationships,
shared services + allocation maths, resources, HTTP surface."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from tests.p13_support import (  # noqa: F401
    AGENT, OWNER, SYSTEM, app_portfolio, business_with_collected,
    client_portfolio, future_iso, make_business, make_portfolio,
    make_service_with_access, owner_http_headers,
)

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------ migration
def test_p13_migration_cycle(tmp_path):
    from alembic import command
    from alembic.config import Config

    db = tmp_path / "p13_cycle.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    engine = create_engine(f"sqlite:///{db}")

    def count() -> int:
        with engine.connect() as conn:
            return conn.execute(text(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            )).scalar_one()

    command.upgrade(config, "head")
    # P-14 Stage B disclosure: head now includes the Stage B
    # migration (event_dead_letters, DEF-I4): 173 physical tables.
    # P-15 disclosure: head now also includes the P-15 migration
    # (four reliability tables): 177 physical tables.
    # P-16 disclosure: head now also includes the P-16 migration
    # (fourteen economy tables): 191 physical tables.
    # P-17 disclosure: head now also includes the P-17 migration
    # (eighteen growth tables): 209 physical tables.
    # P-18 disclosure: head now also includes the P-18 migration
    # (fifteen experience tables): 224 physical tables.
    # Expansion F01 disclosure: head now also includes the Expansion
    # Feature 1 migration (two identity/device tables): 226 physical tables.
    # Expansion F02 disclosure: head now also includes the Expansion
    # Feature 2 migration (two integration-framework tables): 228 physical tables.
    # Expansion F06 disclosure: head now also includes the Expansion
    # Feature 6 migration (three knowledge tables): 235 physical tables.
    assert count() == 235  # 224 at P-18 head + 2 F01 + 2 F02 + 4 F03 + 3 F06 tables
    command.downgrade(config, "3a77efe78faa")
    assert count() == 153
    command.upgrade(config, "head")
    assert count() == 235


def test_p13_metadata_registers_exactly_nineteen_new_tables():
    from app.database.models.base import Base
    import app.database.models  # noqa: F401

    # P-14 Stage B disclosure: Stage B added one table
    # (event_dead_letters, DEF-I4); the exact total is now 172.
    # The P-13 increment (19) is unchanged. Strictness preserved.
    # P-15 disclosure: P-15 added four reliability tables; the exact
    # total is now 176. The P-13 increment is unchanged.
    # P-16 disclosure: P-16 added fourteen economy tables; the exact
    # total is now 190. The P-13 increment is unchanged.
    # P-17 disclosure: P-17 added eighteen growth tables; the exact
    # total is now 208. The P-13 increment is unchanged.
    # P-18 disclosure: P-18 added fifteen experience tables; the
    # exact total is now 223. The P-13 increment is unchanged.
    # Expansion F01 disclosure: F01 added two identity/device tables;
    # the exact total is now 225. The P-13 increment is unchanged.
    # Expansion F02 disclosure: F02 added two integration-framework tables;
    # the exact total is now 227. The P-13 increment is unchanged.
    # Expansion F06 disclosure: F06 added three knowledge tables;
    # the exact total is now 234. The P-13 increment is unchanged.
    assert len(Base.metadata.tables) == 234  # 223 pre-F01 + 2 F01 + 2 F02 + 4 F03 + 3 F06
    expected = {
        "business_portfolios", "portfolio_business_memberships",
        "portfolio_objectives", "business_relationships",
        "cross_business_opportunities", "portfolio_recommendations",
        "shared_services", "shared_service_access",
        "shared_service_usage", "internal_cost_allocations",
        "resource_quotas", "resource_allocations",
        "cross_business_permissions", "portfolio_agent_assignments",
        "portfolio_workflows", "portfolio_workflow_participations",
        "portfolio_risk_assessments", "portfolio_reports",
        "new_venture_proposals",
    }
    assert expected <= set(Base.metadata.tables)


async def test_engine_wired_and_status(app_portfolio):
    status = app_portfolio.portfolio.engine_status()
    assert status["engine"].startswith("P-13")
    settings = app_portfolio.portfolio.get_settings()
    assert settings["concentration_threshold_bps"] == 6000
    assert settings["capacities"]["inference_slots"] == 4


# -------------------------------------------------------------- registry
async def test_portfolio_and_membership_lifecycle(app_portfolio):
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Alpha Ebook")
    b = await make_business(app_portfolio, name="Beta Ebook")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    overview = svc.portfolio_overview(OWNER, portfolio["id"])
    assert overview["total_businesses"] == 2
    assert overview["active_businesses"] == 2
    # Registry references P-06 records — the names are P-06's (the
    # fixture path prefixes them, exactly as P-06 presents them).
    names = {m["business"]["name"] for m in overview["members"]}
    assert any("Alpha Ebook" in n for n in names)
    assert any("Beta Ebook" in n for n in names)
    # Duplicate registration is refused; removal touches nothing else.
    with pytest.raises(Exception):
        svc.register_business(OWNER, portfolio["id"], {"business_id": a})
    svc.set_membership_status(OWNER, portfolio["id"], a, "REMOVED")
    overview = svc.portfolio_overview(OWNER, portfolio["id"])
    assert overview["total_businesses"] == 1
    assert "Alpha Ebook" in app_portfolio.business.get_business(a)["name"]


async def test_business_can_join_multiple_groups_without_duplication(
        app_portfolio):
    a = await make_business(app_portfolio, name="Shared Biz")
    p1 = await make_portfolio(app_portfolio, name="Group One",
                              business_ids=[a])
    p2 = await make_portfolio(app_portfolio, name="Group Two",
                              business_ids=[a])
    assert p1["id"] != p2["id"]
    session = app_portfolio.session_factory()
    try:
        from sqlalchemy import func, select
        from app.database.models.business import Business
        count = session.scalar(
            select(func.count()).select_from(Business)
            .where(Business.id == a))
        assert count == 1  # one P-06 record, two memberships
    finally:
        session.close()


async def test_objectives(app_portfolio):
    svc = app_portfolio.portfolio
    portfolio = await make_portfolio(app_portfolio)
    objective = svc.create_objective(OWNER, portfolio["id"], {
        "title": "Reach ₹1L collected", "horizon": "90_DAY",
        "targets": {"net_collected_minor": 10_000_00}})
    assert objective["horizon"] == "90_DAY"
    assert svc.list_objectives(OWNER, portfolio["id"])["total"] == 1
    with pytest.raises(Exception):
        svc.create_objective(OWNER, portfolio["id"], {
            "title": "Bad horizon", "horizon": "WHENEVER"})


# --------------------------------------------------------- relationships
async def test_relationship_governed_transitions(app_portfolio):
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Rel A")
    b = await make_business(app_portfolio, name="Rel B")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    rel = svc.create_relationship(OWNER, {
        "portfolio_id": portfolio["id"],
        "source_business_id": a, "target_business_id": b,
        "relationship_type": "SHARED_AUDIENCE",
        "sharing_policy": "AGGREGATE_ONLY"})
    assert rel["status"] == "PROPOSED"
    with pytest.raises(Exception):
        svc.transition_relationship(OWNER, rel["id"], "ACTIVE")
    svc.transition_relationship(OWNER, rel["id"], "UNDER_REVIEW")
    svc.transition_relationship(OWNER, rel["id"], "APPROVED")
    rel = svc.transition_relationship(OWNER, rel["id"], "ACTIVE")
    assert rel["status"] == "ACTIVE"
    assert rel["approved_by"].startswith("owner")
    listed = svc.list_relationships(
        OWNER, portfolio_id=portfolio["id"], business_id=a)
    assert listed["total"] == 1


# ------------------------------------------------------- shared services
async def test_service_access_flow_and_usage_gate(app_portfolio):
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Svc A")
    b = await make_business(app_portfolio, name="Svc B")
    service = svc.create_service(OWNER, {
        "name": "Shared Research", "kind": "research_infrastructure"})
    # Usage before any access: refused.
    with pytest.raises(Exception):
        svc.record_usage(OWNER, service["id"],
                         {"business_id": a, "units": 5})
    access = svc.request_access(OWNER, service["id"], {"business_id": a})
    # Approved but not yet ACTIVE: still refused.
    svc.decide_access(OWNER, access["id"], True)
    with pytest.raises(Exception):
        svc.record_usage(OWNER, service["id"],
                         {"business_id": a, "units": 5})
    svc.activate_access(OWNER, access["id"])
    svc.record_usage(OWNER, service["id"], {"business_id": a, "units": 40})
    svc.record_usage(OWNER, service["id"], {"business_id": a, "units": 10})
    view = svc.usage_view(OWNER, service["id"])
    assert view["per_business_units"] == {a: 50}
    # Business B never had access.
    with pytest.raises(Exception):
        svc.record_usage(OWNER, service["id"],
                         {"business_id": b, "units": 5})


async def test_allocation_methods_math(app_portfolio):
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Alloc A")
    b = await make_business(app_portfolio, name="Alloc B")
    portfolio = await make_portfolio(
        app_portfolio, business_ids=[a, b], priorities={a: 75, b: 25})
    service = make_service_with_access(
        app_portfolio, business_ids=[a, b])
    svc.record_usage(OWNER, service["id"], {"business_id": a, "units": 30})
    svc.record_usage(OWNER, service["id"], {"business_id": b, "units": 10})

    def amounts(allocation):
        return {row["business_id"]: row["amount_minor"]
                for row in allocation["allocations"]}

    equal = svc.create_allocation(OWNER, {
        "service_id": service["id"], "portfolio_id": portfolio["id"],
        "method": "equal",
        "total_cost_minor": 10001, "business_ids": [a, b]})
    assert sum(amounts(equal).values()) == 10001
    assert amounts(equal)[a] == 5001 and amounts(equal)[b] == 5000

    usage = svc.create_allocation(OWNER, {
        "service_id": service["id"], "portfolio_id": portfolio["id"],
        "method": "usage_based",
        "total_cost_minor": 8000, "business_ids": [a, b]})
    assert amounts(usage) == {a: 6000, b: 2000}

    fixed = svc.create_allocation(OWNER, {
        "service_id": service["id"], "portfolio_id": portfolio["id"],
        "method": "fixed",
        "total_cost_minor": 5000, "business_ids": [a, b],
        "allocations": [{"business_id": a, "share_bps": 6000},
                        {"business_id": b, "share_bps": 4000}]})
    assert amounts(fixed) == {a: 3000, b: 2000}

    weighted = svc.create_allocation(OWNER, {
        "service_id": service["id"], "method": "priority_weighted",
        "portfolio_id": portfolio["id"],
        "total_cost_minor": 4000, "business_ids": [a, b]})
    assert amounts(weighted) == {a: 3000, b: 1000}

    with pytest.raises(Exception):
        svc.create_allocation(OWNER, {
            "service_id": service["id"], "portfolio_id": portfolio["id"],
            "method": "fixed",
            "total_cost_minor": 5000, "business_ids": [a, b],
            "allocations": [{"business_id": a, "share_bps": 5000},
                            {"business_id": b, "share_bps": 4000}]})


# --------------------------------------------------------------- resources
async def test_resource_quota_capacity_and_cap(app_portfolio):
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Res A")
    b = await make_business(app_portfolio, name="Res B")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a, b])
    svc.set_quota(OWNER, portfolio["id"], {
        "business_id": a, "resource_kind": "inference_slots",
        "max_units": 4})
    svc.set_quota(OWNER, portfolio["id"], {
        "business_id": b, "resource_kind": "inference_slots",
        "max_units": 4})
    # Capacity is 4 slots; the share cap (50%) allows at most 2 each.
    with pytest.raises(Exception):
        svc.propose_resource_allocation(OWNER, portfolio["id"], {
            "business_id": a, "resource_kind": "inference_slots",
            "units": 3})
    alloc = svc.propose_resource_allocation(OWNER, portfolio["id"], {
        "business_id": a, "resource_kind": "inference_slots", "units": 2})
    svc.decide_resource_allocation(OWNER, alloc["id"], True)
    svc.activate_resource_allocation(OWNER, alloc["id"])
    view = svc.resource_view(OWNER, portfolio["id"])
    assert view["kinds"]["inference_slots"]["allocated_units"] == 2
    assert view["kinds"]["inference_slots"]["available_units"] == 2
    # Releasing frees capacity.
    svc.release_resource_allocation(OWNER, alloc["id"], "done")
    view = svc.resource_view(OWNER, portfolio["id"])
    assert view["kinds"]["inference_slots"]["allocated_units"] == 0


async def test_resource_reclaim_for_removed_member(app_portfolio):
    svc = app_portfolio.portfolio
    a = await make_business(app_portfolio, name="Reclaim A")
    portfolio = await make_portfolio(app_portfolio, business_ids=[a])
    svc.set_quota(OWNER, portfolio["id"], {
        "business_id": a, "resource_kind": "storage_mb", "max_units": 500})
    alloc = svc.propose_resource_allocation(OWNER, portfolio["id"], {
        "business_id": a, "resource_kind": "storage_mb", "units": 100})
    svc.decide_resource_allocation(OWNER, alloc["id"], True)
    svc.set_membership_status(OWNER, portfolio["id"], a, "REMOVED")
    result = svc.reclaim_idle(OWNER, portfolio["id"])
    assert len(result["actions"]) == 1
    assert result["actions"][0]["units_freed"] == 100


# ------------------------------------------------------------------- HTTP
def test_portfolio_http_round_trip(client_portfolio):
    headers = owner_http_headers(client_portfolio)
    created = client_portfolio.post(
        "/api/v1/portfolio/portfolios", headers=headers,
        json={"name": "HTTP Portfolio"})
    assert created.status_code == 201, created.text
    portfolio_id = created.json()["data"]["id"]
    listed = client_portfolio.get("/api/v1/portfolio/portfolios",
                                  headers=headers)
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1
    overview = client_portfolio.get(
        f"/api/v1/portfolio/portfolios/{portfolio_id}/overview",
        headers=headers)
    assert overview.status_code == 200
    assert overview.json()["data"]["total_businesses"] == 0
    status = client_portfolio.get("/api/v1/portfolio/status",
                                  headers=headers)
    assert status.status_code == 200
    assert status.json()["data"]["engine"].startswith("P-13")


def test_portfolio_http_requires_auth(client_portfolio):
    resp = client_portfolio.get("/api/v1/portfolio/portfolios")
    assert resp.status_code in (401, 403)
