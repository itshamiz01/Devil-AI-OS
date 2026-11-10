"""P-06 acceptance scenarios A–J (§29.4), mapped by name.

The honesty rule governs this file: Scenario D uses a REAL P-03
investigation (the seed e-book opportunity, researched through P-03's
machinery) and must be BLOCKED. Scenarios needing a qualifying
opportunity use clearly-labelled FIXTURE opportunities whose levels
P-03 computes from stored fixture evidence.
"""
from __future__ import annotations

import pytest

from app.business.fixtures import build_fixture_opportunity
from app.core.application import Application
from app.core.exceptions import InvalidStateTransitionError, PermissionDeniedError
from app.permissions.models import Principal, PrincipalType
from tests.conftest import OWNER, make_settings
from tests.p06_support import (
    DECLARATION, app_rw, make_fixture_business, run_full_creation,
)

AGENT_P = Principal(PrincipalType.AGENT, "some-agent")


# ---------------------------------------------------------- Scenario D first
async def test_scenario_d_real_low_validation_opportunity_blocked(app_rw):
    """D — a real staging opportunity at Validation Level 1 (the P-03
    e-book investigation shape) is blocked by the eligibility gate;
    reasons are recorded; zero infrastructure is created."""
    opps = app_rw.opportunities
    brief = opps.create_brief(OWNER, {
        "title": "P-06 Scenario D investigation", "objective": "validate",
        "budget_amount": 50, "currency": "USD", "geography": "global"})
    discovered = await opps.discover(OWNER, brief.id)
    ebook = [o for o in discovered["opportunities"]
             if o.name == "Beginner fitness e-book series (KDP)"][0]
    session = await opps.start_research(
        OWNER, ebook.id, ["owner_research_notes", "industry_blog_fixture"])
    await opps.run_research_stage(session.id)
    record = await opps.validate(OWNER, ebook.id)
    assert record.level < 3, f"real opportunity computed level {record.level}"

    svc = app_rw.business
    evaluation = await svc.evaluate_eligibility(
        OWNER, ebook.id, template_name="ebook_digital_product")
    assert evaluation["decision"] in (
        "REQUIRES_MORE_RESEARCH", "REQUIRES_MORE_VALIDATION")
    assert evaluation["checks"]
    with pytest.raises(InvalidStateTransitionError):
        await svc.create_business(
            OWNER, {"opportunity_id": ebook.id,
                    "template_name": "ebook_digital_product"})
    businesses, total = svc.list_businesses(opportunity_id=ebook.id)
    assert total == 0 and businesses == []


# ---------------------------------------------------------------- Scenario A
async def test_scenario_a_digital_product_business_end_to_end(app_rw):
    """A — fixture digital product: validated opportunity → blueprint →
    product → assets in its own workspace → distribution prep with the
    KDP platform gate → readiness."""
    _, business = await make_fixture_business(app_rw)
    svc = app_rw.business
    bid = business["id"]
    assert business["is_fixture"] is True
    assert business["validation_level_at_creation"] == 3

    result = await run_full_creation(app_rw, bid)
    assert result["workflow_status"] == "COMPLETED"
    assert len(result["assets"]) == 10
    assert all(a["content_hash"] for a in result["assets"])

    # Files really exist in the business's own workspace (verified
    # through the execution engine, not by trusting the registry).
    from app.execution.schemas import ExecutionRequestIn
    from tests.p06_support import OWNER as O
    assets, _ = svc.list_assets(bid)
    read = await app_rw.execution.submit_and_execute(O, ExecutionRequestIn(
        agent_id=assets[0]["creator_agent_id"], tool="documents",
        action="read_text",
        parameters={"workspace": f"business:{bid}",
                    "path": "blueprint/blueprint.md"},
        business_ref=bid))
    assert read.status == "COMPLETED"
    from app.database.repositories.execution import ExecutionRunRepository
    _session = app_rw.session_factory()
    try:
        _runs = ExecutionRunRepository(_session).for_request(read.id)
        content = (_runs[-1].result or {})["output"]["content"]
    finally:
        _session.close()
    assert "FIXTURE BUSINESS" in content

    channels, _ = svc.list_channels(bid)
    kdp = [c for c in channels if c["platform"] == "Amazon KDP"][0]
    assert kdp["platform_gate"]["outcome"] == "REQUIRES_HUMAN_ACTION"
    attempt = await svc.record_publish_attempt(OWNER, bid, kdp["id"])
    assert attempt["published"] is False
    assert attempt["requires_human_action"] is True

    review = await svc.evaluate_readiness(OWNER, bid)
    assert review["overall_status"] in ("READY", "READY_WITH_WARNINGS")
    assert svc.get_business(bid)["status"] == "LAUNCH_REVIEW"


# ---------------------------------------------------------------- Scenario B
async def test_scenario_b_saas_tool_creation(app_rw):
    """B — SaaS template: specification + a verified prototype execution
    step through the P-05 code adapter (process controls)."""
    _, business = await make_fixture_business(
        app_rw, name="Fixture GST Helper", template="saas_micro_tool",
        category="software")
    svc = app_rw.business
    result = await run_full_creation(app_rw, business["id"])
    assert result["workflow_status"] == "COMPLETED"
    asset_types = {a["asset_type"] for a in result["assets"]}
    assert "technical_architecture" in asset_types
    # The prototype step really ran: find its step run in the workflow.
    from sqlalchemy import select
    from app.database.models.execution import WorkflowStepRun
    session = app_rw.session_factory()
    try:
        steps = list(session.scalars(select(WorkflowStepRun).where(
            WorkflowStepRun.workflow_run_id == result["workflow_run_id"])))
    finally:
        session.close()
    code_steps = [s for s in steps if s.step_id == "verify_prototype"]
    assert code_steps and all(s.status == "completed" for s in code_steps)


# ---------------------------------------------------------------- Scenario C
async def test_scenario_c_content_business_no_autoposting(app_rw):
    """C — content business: publication package prepared; the platform
    gate records human publishing; no auto-posting exists."""
    _, business = await make_fixture_business(
        app_rw, name="Fixture Fitness Notes", template="content_publication",
        category="content")
    svc = app_rw.business
    result = await run_full_creation(app_rw, business["id"])
    assert result["workflow_status"] == "COMPLETED"
    assert "sample_content" in {a["asset_type"] for a in result["assets"]}
    channels, _ = svc.list_channels(business["id"])
    substack = [c for c in channels if c["platform"] == "Substack"][0]
    attempt = await svc.record_publish_attempt(
        OWNER, business["id"], substack["id"])
    assert attempt["published"] is False
    draft = svc.create_campaign_draft(OWNER, business["id"], {
        "name": "launch drafts", "objective": "prepare launch posts",
        "channel": "Substack"})
    assert draft["status"] == "draft"


# ---------------------------------------------------------------- Scenario E
async def test_scenario_e_invalid_transitions_rejected(app_rw):
    """E — the lifecycle refuses skips, reversals and artefact-free
    advances, deterministically."""
    _, business = await make_fixture_business(app_rw)
    svc = app_rw.business
    bid = business["id"]
    with pytest.raises(InvalidStateTransitionError):
        await svc.transition_business(OWNER, bid, "OPERATIONAL")
    with pytest.raises(InvalidStateTransitionError):
        await svc.transition_business(OWNER, bid, "IN_DEVELOPMENT")
    with pytest.raises(InvalidStateTransitionError):
        await svc.transition_business(OWNER, bid, "READY_FOR_LAUNCH")
    await svc.generate_blueprint(OWNER, bid)
    with pytest.raises(InvalidStateTransitionError):
        await svc.transition_business(OWNER, bid, "LAUNCHING")
    events, total = svc.lifecycle_events(bid)
    assert total >= 3  # every accepted move recorded; rejects are audited


# ---------------------------------------------------------------- Scenario F
async def test_scenario_f_readiness_blocks_unready_business(app_rw):
    """F — a business with no creation run (no quality tests, no support
    assets) is NOT_READY with blockers listed, and READY_FOR_LAUNCH is
    refused."""
    _, business = await make_fixture_business(app_rw)
    svc = app_rw.business
    bid = business["id"]
    await svc.create_declaration(OWNER, bid, DECLARATION)
    await svc.generate_blueprint(OWNER, bid)
    review = await svc.evaluate_readiness(OWNER, bid)
    assert review["overall_status"] == "NOT_READY"
    assert review["blockers"]
    assert any(b["dimension"] == "B" for b in review["blockers"])
    assert review["outstanding_requirements"]
    with pytest.raises(InvalidStateTransitionError):
        await svc.transition_business(OWNER, bid, "READY_FOR_LAUNCH")


# ---------------------------------------------------------------- Scenario G
async def test_scenario_g_cross_business_isolation(app_rw):
    """G — an agent assigned to business A is denied business B's
    workspace; the denial is a persisted critical event."""
    _, business_a = await make_fixture_business(app_rw, name="Fixture Alpha")
    await run_full_creation(app_rw, business_a["id"])
    _, business_b = await make_fixture_business(app_rw, name="Fixture Beta")
    svc = app_rw.business
    assignments, _ = svc.assignments(business_a["id"])
    agent_a = assignments[0]["agent_id"]

    probe = await svc.probe_workspace_access(
        OWNER, business_b["id"], agent_a)
    assert probe["allowed"] is False
    with pytest.raises(PermissionDeniedError):
        await svc.assert_business_access(
            Principal(PrincipalType.AGENT, agent_a), business_b["id"])

    from sqlalchemy import select
    from app.database.models.core import SystemEvent
    session = app_rw.session_factory()
    try:
        events = list(session.scalars(select(SystemEvent).where(
            SystemEvent.event_type == "BusinessIsolationViolation")))
    finally:
        session.close()
    assert events, "isolation violations must persist as critical events"
    assert any(e.payload.get("business_id") == business_b["id"]
               for e in events)


# ---------------------------------------------------------------- Scenario H
async def test_scenario_h_modes_respected(tmp_path):
    """H — simulation produces drafts only (P-05 policy refuses the
    side-effecting workflow; the run cannot complete), and emergency
    mode halts creation outright."""
    sim = Application(make_settings(tmp_path / "sim", mode="simulation"))
    await sim.startup()
    try:
        _, business = await make_fixture_business(sim)
        svc = sim.business
        await svc.create_declaration(OWNER, business["id"], DECLARATION)
        await svc.generate_blueprint(OWNER, business["id"])
        with pytest.raises(InvalidStateTransitionError):
            await svc.run_creation(OWNER, business["id"])
        assert svc.get_business(business["id"])["status"] == "BLOCKED"
    finally:
        await sim.shutdown()

    emg = Application(make_settings(tmp_path / "emg", mode="emergency"))
    await emg.startup()
    try:
        opp = emg.opportunities.create_opportunity(OWNER, {
            "name": "Emergency probe", "category": "digital_products",
            "target_customer": "x", "problem_statement": "y",
            "proposed_solution": "z", "revenue_model": "sales"})
        with pytest.raises(InvalidStateTransitionError):
            await emg.business.create_business(
                OWNER, {"opportunity_id": opp.id,
                        "template_name": "ebook_digital_product"})
    finally:
        await emg.shutdown()


# ---------------------------------------------------------------- Scenario I
async def test_scenario_i_existing_agents_reused(app_rw):
    """I — the factory's reuse-first decision gives the second business
    the existing agents rather than duplicates."""
    _, business_one = await make_fixture_business(app_rw, name="Fixture One")
    await run_full_creation(app_rw, business_one["id"])
    first, _ = app_rw.business.assignments(business_one["id"])
    _, business_two = await make_fixture_business(app_rw, name="Fixture Two")
    await run_full_creation(app_rw, business_two["id"])
    second, _ = app_rw.business.assignments(business_two["id"])
    assert {a["agent_id"] for a in first} == {a["agent_id"] for a in second}
    assert len(second) == len(first) == 3


# ---------------------------------------------------------------- Scenario J
async def test_scenario_j_launch_requires_owner_approval(app_rw):
    """J — a READY fixture business reaches LAUNCH_APPROVAL_PENDING and
    does not launch without the hash-bound owner approval; with it, the
    staging demonstration reaches OPERATIONAL asserting no deployment,
    no public availability and no revenue."""
    _, business = await make_fixture_business(app_rw)
    svc = app_rw.business
    bid = business["id"]
    await run_full_creation(app_rw, bid)
    review = await svc.evaluate_readiness(OWNER, bid)
    assert review["overall_status"] in ("READY", "READY_WITH_WARNINGS")
    await svc.transition_business(OWNER, bid, "READY_FOR_LAUNCH",
                                  reason="readiness passed")
    request = await svc.request_launch(OWNER, bid)
    assert svc.get_business(bid)["status"] == "LAUNCH_APPROVAL_PENDING"

    with pytest.raises(PermissionDeniedError):
        await svc.launch(OWNER, bid, request["approval_id"])  # undecided
    with pytest.raises(Exception):
        await svc.launch(OWNER, bid, "nonexistent-approval")
    assert svc.get_business(bid)["status"] == "LAUNCH_APPROVAL_PENDING"

    app_rw.approvals.decide(request["approval_id"], OWNER, True)
    launched = await svc.launch(OWNER, bid, request["approval_id"])
    assert launched["status"] == "OPERATIONAL"
    assert launched["deployment_state"] == "local_package_only"
    assert launched["public_availability"] is False
    assert "revenue" not in launched and "profit" not in launched
