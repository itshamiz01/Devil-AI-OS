"""P-16 security tests: isolation, owner authority, hash-bound
approval integrity, the freeze/pause switches, and the structural
guarantees — P-16 cannot move money, cannot create businesses, and
leaves P-07's books byte-equal after every write flow.
"""
from __future__ import annotations

import pytest

from app.core.exceptions import PermissionDeniedError, ValidationError
from tests.conftest import OWNER
from tests.p16_support import (
    AGENT, app_eco, profitable_business, strong_evidence,
)


# ------------------------------------------------------------- isolation
async def test_agent_cannot_read_economy_aggregates(app_eco):
    svc = app_eco.economy
    for call in (lambda: svc.overview(AGENT),
                 lambda: svc.engine_status(AGENT),
                 lambda: svc.list_classifications(AGENT),
                 lambda: svc.list_opportunities(AGENT),
                 lambda: svc.capital_overview(AGENT),
                 lambda: svc.latest_risk_assessment(AGENT)):
        with pytest.raises(PermissionDeniedError):
            call()


async def test_agent_cannot_write_economy_state(app_eco):
    svc = app_eco.economy
    with pytest.raises(PermissionDeniedError):
        svc.create_opportunity(AGENT, {"title": "x",
                                       "kind": "new_business"})
    with pytest.raises(PermissionDeniedError):
        svc.create_market_report(AGENT, {
            "title": "x", "sector": "other",
            "classification": "emerging",
            "evidence_sources": [{"ref": "fixture://1"}]})
    with pytest.raises(PermissionDeniedError):
        svc.update_settings(AGENT, {"autonomy_level": 4})
    with pytest.raises(PermissionDeniedError):
        svc.compute_risk_assessment(AGENT)


async def test_agent_cannot_approve_or_override(app_eco):
    svc = app_eco.economy
    strategy = svc.create_strategy(OWNER, {
        "title": "Improve", "horizon": "short",
        "kind": "improve_existing"})
    with pytest.raises(PermissionDeniedError):
        svc.approve_strategy(AGENT, strategy["id"])
    opp = svc.create_opportunity(OWNER, {
        "title": "Venture", "kind": "new_business",
        "evidence": strong_evidence()})
    with pytest.raises(PermissionDeniedError):
        svc.record_opportunity_override(AGENT, opp["id"], "agent tries")
    with pytest.raises(PermissionDeniedError):
        svc.advance_opportunity(AGENT, opp["id"], "under_research")


# ------------------------------------------------- approval integrity
async def test_allocation_approval_binding_mismatch_refused(app_eco):
    business_id = await profitable_business(app_eco, name="Bind Books")
    svc = app_eco.economy
    rec = svc.create_allocation(OWNER, {
        "scenario": "conservative", "business_id": business_id,
        "proposed": {"amount_minor": 100_00, "purpose": "x",
                     "target_kind": "business"}})
    # An owner-decided P-01 approval for DIFFERENT parameters must
    # not bind to this recommendation (hash-bound, §P-10 posture).
    foreign = app_eco.approvals.create(
        OWNER, action="economy.allocation", resource=rec["id"],
        risk_classification="high", reason="different amount",
        requested_permissions=["approve_actions"],
        parameters={"recommendation_id": rec["id"],
                    "amount_minor": 999_00, "business_id": business_id})
    app_eco.approvals.decide(foreign.id, OWNER, True)
    with pytest.raises(PermissionDeniedError):
        svc.decide_allocation(OWNER, rec["id"], approve=True,
                              approval_id=foreign.id)
    listed = svc.list_allocations(OWNER)
    assert listed["items"][0]["status"] == "proposed"  # unchanged


async def test_agent_supplied_approval_id_refused(app_eco):
    business_id = await profitable_business(app_eco, name="Bind Two")
    svc = app_eco.economy
    rec = svc.create_allocation(OWNER, {
        "scenario": "conservative", "business_id": business_id,
        "proposed": {"amount_minor": 100_00, "purpose": "x",
                     "target_kind": "business"}})
    with pytest.raises(PermissionDeniedError):
        svc.decide_allocation(AGENT, rec["id"], approve=True)


# ------------------------------------------------------- freeze / pause
async def test_capital_freeze_blocks_approvals_not_rejections(app_eco):
    business_id = await profitable_business(app_eco, name="Frozen Co")
    svc = app_eco.economy
    rec = svc.create_allocation(OWNER, {
        "scenario": "balanced", "business_id": business_id,
        "proposed": {"amount_minor": 100_00, "purpose": "x",
                     "target_kind": "business"}})
    svc.update_settings(OWNER, {"capital_commitments_frozen": True})
    with pytest.raises(PermissionDeniedError):
        svc.decide_allocation(OWNER, rec["id"], approve=True)
    rejected = svc.decide_allocation(OWNER, rec["id"], approve=False)
    assert rejected["status"] == "rejected"


async def test_expansion_pause_blocks_pipeline_and_handoff(app_eco):
    business_id = await profitable_business(app_eco, name="Paused Co")
    svc = app_eco.economy
    opp = svc.create_opportunity(OWNER, {
        "title": "Stream", "kind": "new_revenue_stream",
        "evidence": strong_evidence()})
    svc.update_settings(OWNER, {"expansion_paused": True,
                                "autonomy_level": 3})
    with pytest.raises(PermissionDeniedError):
        svc.advance_opportunity(OWNER, opp["id"], "under_research")
    # Exits remain available while paused (stopping is always safe).
    exited = svc.advance_opportunity(OWNER, opp["id"], "archived")
    assert exited["stage"] == "archived"


# ------------------------------------------------- structural guarantees
async def test_p07_books_byte_equal_after_p16_writes(app_eco):
    business_id = await profitable_business(app_eco, name="Invariant")
    fin = app_eco.financial
    before_metrics = fin.revenue.metrics(business_id, "INR")
    before_expenses = fin.expenses.totals(business_id, "INR")
    before_summary = fin.business_summary(business_id)
    svc = app_eco.economy
    svc.set_classification(OWNER, business_id, {"industry": "x"})
    svc.create_market_report(OWNER, {
        "title": "m", "sector": "other", "classification": "emerging",
        "evidence_sources": [{"ref": "fixture://inv"}]})
    rec = svc.create_allocation(OWNER, {
        "scenario": "balanced", "business_id": business_id,
        "proposed": {"amount_minor": 100_00, "purpose": "x",
                     "target_kind": "business"}})
    svc.decide_allocation(OWNER, rec["id"], approve=True)
    plan = svc.create_reinvestment_plan(OWNER,
                                        {"business_id": business_id})
    svc.decide_reinvestment_plan(OWNER, plan["id"], approve=True)
    svc.compute_risk_assessment(OWNER)
    assert fin.revenue.metrics(business_id, "INR") == before_metrics
    assert fin.expenses.totals(business_id, "INR") == before_expenses
    assert fin.business_summary(business_id) == before_summary


def test_no_execution_surface_on_the_service():
    from app.economy.service import EconomyService
    for dangerous in ("transfer", "transfer_funds", "execute_spend",
                      "spend", "pay", "move_money", "invest",
                      "create_business", "launch_business",
                      "withdraw", "deposit"):
        assert not hasattr(EconomyService, dangerous), dangerous


async def test_commercialization_handoff_requires_approval(app_eco):
    svc = app_eco.economy
    asset = svc.create_asset(OWNER, {
        "name": "Tool", "kind": "software",
        "ownership_status": "verified_owner",
        "commercial_use_permitted": True})
    proposal = svc.create_commercialization(OWNER,
                                            {"asset_id": asset["id"]})
    with pytest.raises(ValidationError):
        svc.handoff_commercialization(OWNER, proposal["id"])


async def test_settings_weights_validation(app_eco):
    svc = app_eco.economy
    with pytest.raises(ValidationError):
        svc.update_settings(OWNER, {"factor_weights": {"bogus": 5}})
    with pytest.raises(ValidationError):
        svc.update_settings(OWNER, {"concentration_threshold_bps": 0})
