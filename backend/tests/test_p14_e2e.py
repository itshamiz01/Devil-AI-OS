"""P-14 Stage A (§11) — six end-to-end scenarios driving the REAL
module chain P-01..P-13 as far as it genuinely goes.

AUDIT-ONLY file: no production code is touched by these tests.
Honesty rules (P-14 §21 rule 14 / §11):
- Where two modules connect only through test choreography (this
  file calling both APIs in sequence) rather than a real interface,
  the test says so in its docstring and the gap is recorded in
  docs/p14/P14_E2E_EVIDENCE_NOTES.md — choreography is NEVER
  presented as integration.
- Where a step cannot execute on the real system, the test asserts
  the honest blocking state instead of faking a pass.
- Fixtures only: businesses come from the governed P-06 fixture
  path (``make_fixture_business`` / ``build_fixture_opportunity``);
  the real-evidence path's BLOCKED state is asserted explicitly in
  Scenario 1.

Dashboard steps: the P-11 routes are a thin wrapper —
``DashboardService(application)`` constructed per request in
``app/api/routes/dashboard.py`` — so most scenarios assert through
that exact service object, and Scenarios 1 and 6 additionally assert
through real HTTP (``client_ops`` shares the same SQLite file via
the same ``tmp_path`` as ``app_ops``; the established P-11 pattern).
"""
from __future__ import annotations

import pytest

from app.core.exceptions import (
    InvalidStateTransitionError, PermissionDeniedError, ValidationError)
from app.dashboard.service import DashboardService
from app.permissions.models import Principal, PrincipalType
from tests.conftest import OWNER, make_settings
from tests.p06_support import DECLARATION, make_fixture_business
from tests.p07_support import business_with_profile, money, paid_expense, verified_revenue
from tests.p08_support import opening_balance
from tests.p09_support import AGENT, AGENT2, make_record, register_agent
from tests.p12_support import (  # noqa: F401
    app_ops, client_ops, echo_step, grant_permission, make_workflow,
    owner_http_headers, run_workflow,
)
from tests.p13_support import make_business, make_portfolio, make_service_with_access

AGENT_B = Principal(PrincipalType.AGENT, "agent-b")


def _audit_count(application, action: str) -> int:
    from sqlalchemy import func, select
    from app.database.models.core import AuditEvent
    session = application.session_factory()
    try:
        return session.scalar(select(func.count()).select_from(AuditEvent)
                              .where(AuditEvent.action == action)) or 0
    finally:
        session.close()


def _dash(application) -> DashboardService:
    return DashboardService(application)


# ======================================================================
# Scenario 1 — opportunity -> business (full chain)
# ======================================================================
async def test_scenario_01_opportunity_to_business_end_to_end(app_ops, client_ops):
    """P-03 -> (P-02 GAP) -> P-06 eligibility (real P-06->P-03 interface,
    incl. P-03 commercial analysis = the pre-creation feasibility
    surface) -> owner approval (P-01, hash-bound) -> P-06 business ->
    declaration/blueprint -> P-07 profile via the real P-06->P-07
    payload (``financial_inputs``/``ensure_profile``) -> P-08 survival
    evaluation -> P-10 broker validation -> P-13 registration ->
    P-04 assignments (created by the P-06 creation run) -> P-12
    workflow -> P-05 direct execution -> P-11 dashboard (service +
    HTTP).

    DOCUMENTED GAPS exercised honestly below:
    * (Stage B update, DEF-E1) Stage A found P-02 had NO interface
      consuming a P-03 opportunity; Stage B repaired it with the thin
      assessment path, and step 1c now exercises that real interface
      (P-02 consumes P-03's own score/report; scoring stays in P-03).
    * P-07 cannot evaluate a business before it exists (profiles are
      keyed by business_id), so pre-creation financial feasibility is
      P-03's commercial analysis via P-06 eligibility; the P-07 step
      runs immediately after blueprint, through the real payload.
    * P-08 likewise keys evaluations by business_id, so its step
      runs on the created business.
    """
    app = app_ops

    # --- 1a. REAL evidence path: honestly BLOCKED (itself an assertion)
    opps = app.opportunities
    brief = opps.create_brief(OWNER, {
        "title": "P-14 S1 real investigation", "objective": "validate",
        "budget_amount": 50, "currency": "USD", "geography": "global"})
    discovered = await opps.discover(OWNER, brief.id)
    ebook = [o for o in discovered["opportunities"]
             if o.name == "Beginner fitness e-book series (KDP)"][0]
    session = await opps.start_research(
        OWNER, ebook.id, ["owner_research_notes", "industry_blog_fixture"])
    await opps.run_research_stage(session.id)
    record = await opps.validate(OWNER, ebook.id)
    assert record.level < 3, f"real opportunity computed level {record.level}"
    evaluation = await app.business.evaluate_eligibility(
        OWNER, ebook.id, template_name="ebook_digital_product")
    assert evaluation["decision"] in (
        "REQUIRES_MORE_RESEARCH", "REQUIRES_MORE_VALIDATION")
    with pytest.raises(InvalidStateTransitionError):
        await app.business.create_business(
            OWNER, {"opportunity_id": ebook.id,
                    "template_name": "ebook_digital_product"})
    _rows, total = app.business.list_businesses(opportunity_id=ebook.id)
    assert total == 0

    # --- 1b. FIXTURE path (labelled; level computed by P-03 itself)
    from app.business.fixtures import build_fixture_opportunity
    opp_id = await build_fixture_opportunity(
        app, name="P14 Chain Ebook", category="digital_products")
    validation = opps.latest_validation(opp_id)
    assert validation is not None and validation.level >= 3
    score = opps.latest_score(opp_id)
    assert score is not None
    report = opps.report(opp_id)
    assert report["opportunity"]["id"] == opp_id

    # --- 1c. P-02 consumes P-03 through the real interface
    #         (P-14 Stage B, DEF-E1: the Stage A gap asserted here —
    #         "no IntelligenceService method references opportunities" —
    #         was repaired by the thin assessment path; this section
    #         now exercises it instead of asserting the gap).
    assessment = await app.intelligence.assess_opportunity(OWNER, opp_id)
    assert assessment["opportunity_id"] == opp_id
    assert assessment["source"] == "p03_evaluation_report"
    assert assessment["score_id"] == score.id
    assert assessment["overall_score"] is not None
    assert assessment["decision_record_id"]  # P-02 decision recorded
    # P-02 can also plan an unrelated governed mission (its real
    # surface); the deterministic planner answers (no LLM configured).
    mission = await app.intelligence.create_mission(
        OWNER, "Check system health and report whether the task system is working")
    plan = await app.intelligence.create_plan(OWNER, mission.id)
    assert plan.planner == "rule-engine"  # deterministic; no LLM configured

    # --- 1d. P-06 eligibility = real P-06->P-03 interface incl.
    #         P-03 commercial analysis (pre-creation feasibility).
    elig = await app.business.evaluate_eligibility(
        OWNER, opp_id, template_name="ebook_digital_product")
    assert elig["decision"] not in (
        "REQUIRES_MORE_RESEARCH", "REQUIRES_MORE_VALIDATION"), elig

    # --- 1e. Owner approval (P-01, hash-bound) gates creation.
    svc = app.business
    request = await svc.request_creation_approval(
        OWNER, opp_id, "ebook_digital_product",
        reason="P-14 scenario 1 creation")
    with pytest.raises(Exception):
        await svc.create_business(OWNER, {
            "opportunity_id": opp_id,
            "template_name": "ebook_digital_product",
            "approval_id": request["approval_id"]})  # undecided -> refused
    app.approvals.decide(request["approval_id"], OWNER, True)
    business = await svc.create_business(OWNER, {
        "opportunity_id": opp_id, "template_name": "ebook_digital_product",
        "approval_id": request["approval_id"]})
    bid = business["id"]
    assert business["is_fixture"] is True
    assert business["validation_level_at_creation"] == 3

    # --- 1f. Declaration -> blueprint -> P-07 via real payload.
    await svc.create_declaration(OWNER, bid, DECLARATION)
    await svc.generate_blueprint(OWNER, bid)
    fin_inputs = svc.financial_inputs(bid)
    assert fin_inputs["business_id"] == bid
    assert "P-07 owns collected-revenue truth" in fin_inputs["revenue_recognition"]
    svc.update_settings(OWNER, {"default_currency": "INR"})
    profile = await app.financial.ensure_profile(OWNER, bid)
    assert profile["business_id"] == bid
    result = await svc.run_creation(OWNER, bid)
    assert result["workflow_status"] == "COMPLETED"
    await svc.evaluate_channels(OWNER, bid)

    # --- 1g. P-08 survival evaluation on the created business:
    #         honest INSUFFICIENT_DATA-era snapshot (no revenue yet).
    surv = app.survival.evaluate(OWNER, bid)
    assert surv["snapshot"]["business_id"] == bid
    assert surv["snapshot"]["classification"] in (
        "INSUFFICIENT_DATA", "EARLY_OPERATIONS", "AT_RISK", "STABLE",
        "CRITICAL", "FAILING", "HEALTHY", "EXCELLENT")

    # --- 1h. P-10 / permission validation for the business scope.
    register_agent(app, AGENT.id, business_ref=bid)
    own = app.security.broker.authorize(
        AGENT, permission="read_business_data", action="business.read",
        business_ref=bid)
    assert own["allowed"] is True, own
    foreign = app.security.broker.authorize(
        AGENT, permission="read_business_data", action="business.read",
        business_ref="some-other-business")
    assert foreign["allowed"] is False

    # --- 1i. P-13 portfolio registration (real interface).
    portfolio = await make_portfolio(app, business_ids=[bid])
    members = app.portfolio.list_members(OWNER, portfolio["id"])
    member_ids = {m["business_id"] for m in members["items"]} \
        if "items" in members else {m["business_id"] for m in members}
    assert bid in member_ids

    # --- 1j. P-04 agent assignment: the creation run's assignments
    #         are real P-04 factory agents.
    assignments, assign_total = svc.assignments(bid)
    assert assign_total >= 1
    factory_agent = app.agents.get_agent(assignments[0]["agent_id"])
    assert factory_agent.id == assignments[0]["agent_id"]

    # --- 1k. P-12 workflow for the business (governed, verified).
    wf = make_workflow(app, steps=[echo_step("chain-step")], business_id=bid)
    wf_result = await run_workflow(app, OWNER, wf["id"])
    assert wf_result["status"] == "COMPLETED"
    assert wf_result["verified_outcome"] == "verified"

    # --- 1l. P-05 direct execution: read a real asset file from the
    #         business workspace through the execution engine.
    from app.execution.schemas import ExecutionRequestIn
    assets, _ = svc.list_assets(bid)
    assert assets
    read = await app.execution.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=assets[0]["creator_agent_id"], tool="documents",
        action="read_text",
        parameters={"workspace": f"business:{bid}",
                    "path": "blueprint/blueprint.md"},
        business_ref=bid))
    assert read.status == "COMPLETED"

    # --- 1m. P-11 dashboard: service surface + real HTTP surface.
    summary = _dash(app).businesses_summary()
    assert any(b["id"] == bid for b in summary["businesses"])
    headers = owner_http_headers(client_ops)
    resp = client_ops.get("/api/v1/dashboard/businesses/summary",
                          headers=headers)
    assert resp.status_code == 200, resp.text
    http_ids = {b["id"] for b in resp.json()["data"]["businesses"]}
    assert bid in http_ids
    overview = client_ops.get("/api/v1/dashboard/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    assert overview.json()["data"]["counts"]["businesses_total"] >= 1


# ======================================================================
# Scenario 2 — autonomous task
# ======================================================================
async def test_scenario_02_autonomous_task_end_to_end(app_ops):
    """Owner task -> P-02 plan (real) -> P-09 retrieval (P-14 Stage B,
    DEF-E2: P-02's ContextManager is now wired to P-09 and recalls
    governed memory into mission context building — exercised below
    through the real interface; Stage A recorded this as a
    choreography gap) -> P-10
    broker validation -> P-02 approve+execute through P-01 tasks ->
    P-12 workflow executed by a P-04 factory agent -> verification
    gate -> P-09 learning record ONLY for the verified workflow
    (real P-12->_record_learning -> P-09 interface) -> operations +
    dashboard reporting.
    """
    app = app_ops

    # P-09 memory seeded through the governed path; the owner-side
    # retrieval confirms it is searchable before planning.
    seeded = make_record(
        app, title="Health check runbook",
        content="System health check procedure: snapshot system health, "
                "then run the task system echo self-test and verify it.",
        category="TECHNICAL_KNOWLEDGE", access_scope="ORGANIZATION_SHARED")
    found = app.memory.retrieval.search(OWNER, query="system health check")
    assert any(r["id"] == seeded["id"] for r in found["results"])

    # P-02 plan from the owner's task text (deterministic planner).
    mission = await app.intelligence.create_mission(
        OWNER, "Check system health and report whether the task system is working")
    plan = await app.intelligence.create_plan(OWNER, mission.id)
    assert plan.status == "draft" and plan.planner == "rule-engine"
    assert plan.steps, "baseline planner produced no steps"

    # P-14 Stage B (DEF-E2): mission context building retrieves P-09
    # memory through the wired ContextManager — the seeded runbook is
    # recalled into this mission's context by the real interface,
    # under P-09's classification policy (not widened by P-02).
    ctx = app.intelligence.context.build_context(mission.id)
    assert ctx["memory"]["available"] is True, ctx["memory"]
    assert any(r["id"] == seeded["id"] for r in ctx["memory"]["records"]), \
        ctx["memory"]

    # P-10 validation surface: the broker authorizes the reading
    # agent; a foreign-scope read is refused (validation is real).
    register_agent(app, AGENT.id)
    decision = app.security.broker.authorize(
        AGENT, permission="read_system_data", action="read")
    assert decision["allowed"] is True, decision

    # Approval (hash-bound, inside approve_plan) + execution via
    # P-01 TaskManager; every step independently verified by P-02.
    plan = await app.intelligence.approve_plan(OWNER, plan.id)
    plan = await app.intelligence.execute_plan(OWNER, plan.id)
    assert plan.status == "completed", plan.status
    assert all(s.status == "completed" for s in plan.steps)
    assert all(s.task_id for s in plan.steps)  # real P-01 tasks ran

    # P-12 workflow whose step is assigned to a real P-04 agent.
    from tests.p05_support import make_agent
    agent_id = await make_agent(app)  # P-04 factory creation path
    register_agent(app, agent_id)
    wf = make_workflow(app, steps=[echo_step(
        "work", assigned_agent_id=agent_id)], name="P14 autonomous task")
    result = await run_workflow(app, OWNER, wf["id"])
    assert result["status"] == "COMPLETED"
    assert result["verified_outcome"] == "verified"
    detail = app.operations.get_workflow(OWNER, wf["id"])
    task = next(t for t in detail["tasks"] if t["step_key"] == "work")
    assert task["assigned_agent_id"] == agent_id
    assert task["verification_status"] == "verified"

    # Learning: exactly one P-09 record, created by P-12 itself for
    # the verified outcome — and NONE for a failed-verification run.
    assert result["learning_record_id"]
    from app.database.models.memory import LearningRecord
    session = app.session_factory()
    try:
        good_records = list(session.query(LearningRecord)
                            .filter_by(source_ref=wf["id"]))
    finally:
        session.close()
    assert len(good_records) == 1
    assert good_records[0].confidence == "LOW"  # P-09 mechanical cap

    bad_step = echo_step("check")
    bad_step["acceptance_criteria"] = {"result_equals": {"ok": False}}
    bad = make_workflow(app, steps=[bad_step], name="P14 unverified task")
    failed = await run_workflow(app, OWNER, bad["id"])
    assert failed["status"] == "FAILED"
    assert failed["learning_record_id"] is None

    # Reporting: operations overview + dashboard execution summary.
    overview = app.operations.overview(OWNER)
    assert overview["workflows"].get("COMPLETED", 0) >= 1
    assert overview["workflows"].get("FAILED", 0) >= 1
    exec_summary = _dash(app).execution_summary()
    assert sum(exec_summary["tasks_by_status"].values()) >= 1


# ======================================================================
# Scenario 3 — financial distress
# ======================================================================
async def test_scenario_03_financial_distress_end_to_end(app_ops):
    """Deteriorating finances (P-07 records) -> P-07 summary detects
    loss -> P-08 evaluate raises the loss gate + scaling refuses ->
    P-13 portfolio finance/risk reflect it -> owner-decision surface
    (P-08 decision + P-01 hash-bound approval; dashboard survival
    overview lists the decision) -> approved Level-3 decision
    executes through the governed P-08 path (idempotent).
    """
    app = app_ops
    business_id, _profile = await business_with_profile(
        app, name="P14 Distress Ebook")
    fin = app.financial
    opening_balance(app, business_id, "50000.00")
    await verified_revenue(app, business_id, "10000.00")
    await paid_expense(app, business_id, "8000.00")
    first = app.survival.evaluate(OWNER, business_id)["snapshot"]
    assert not any(g["gate"] == "loss_making" for g in first["hard_gates"])

    # Deterioration: revenue grows, expenses grow faster (P-08 S1 shape).
    await verified_revenue(app, business_id, "20000.00", date="2026-11-07")
    await paid_expense(app, business_id, "27000.00", date="2026-11-08")

    # P-07 detection: paid expenses now exceed collected revenue.
    summary = fin.business_summary(business_id)
    assert summary["revenue"]["net_collected_minor"] == 30000_00
    assert summary["expenses"]["pl_expense_paid_minor"] == 35000_00
    assert summary["profitability"] is not None
    consolidated = fin.consolidated("INR")
    row = next(b for b in consolidated["businesses"]
               if b["business_id"] == business_id)
    assert row["net_profit_minor"] == -5000_00

    # P-08 detection: loss gate + checks, scaling not ready.
    evaluated = app.survival.evaluate(OWNER, business_id)
    snapshot = evaluated["snapshot"]
    assert "loss_making" in {g["gate"] for g in snapshot["hard_gates"]}
    assert "loss_making" in {e["kind"] for e in evaluated["checks"]}
    assessment = app.survival.scaling.assess(OWNER, business_id, snapshot)
    assert assessment["status"] in ("NOT_READY", "BLOCKED")

    # P-13 impact view: the same P-07 figures, per business.
    portfolio = await make_portfolio(app, business_ids=[business_id])
    pfin = app.portfolio.portfolio_finance(OWNER, portfolio["id"])
    prow = next(b for b in pfin["businesses"]
                if b["business_id"] == business_id)
    assert prow["net_collected_minor"] == 30000_00
    risk = app.portfolio.assess_risk(OWNER, portfolio["id"])
    assert any(r["business_id"] == business_id
               for r in risk["per_business"])

    # Owner-decision surface: P-08 RECOVER decision (Level 3).
    decision = app.survival.decisions.create_decision(
        OWNER, business_id, {
            "decision_type": "RECOVER",
            "trigger": "loss_making gate raised by P-08 health evaluation",
            "evidence": [{"source": "p08.health_snapshot",
                          "id": snapshot["id"]}]})
    assert decision["autonomy_level"] == 3
    # Execution before approval is refused at the governed gate.
    with pytest.raises(PermissionDeniedError):
        app.survival.decisions.execute(OWNER, decision["id"], "p14-rec-1")
    approval = app.survival.decisions.request_approval(
        OWNER, decision["id"])
    app.approvals.decide(approval["approval_id"], OWNER, True)
    reviewed = app.survival.decisions.review(OWNER, decision["id"], {})
    assert reviewed["status"] == "APPROVED"
    # Dashboard survival overview surfaces the decision for the owner.
    surv_view = _dash(app).survival_overview()
    assert surv_view["decisions_by_status"].get("APPROVED", 0) >= 1
    assert any(s["business_id"] == business_id
               for s in surv_view["latest_health_by_business"])
    # Approved change executes via the governed path, idempotently.
    executed = app.survival.decisions.execute(
        OWNER, decision["id"], "p14-rec-1")
    assert executed["status"] == "EXECUTED"
    replay = app.survival.decisions.execute(
        OWNER, decision["id"], "p14-rec-1")
    assert replay["idempotent_replay"] is True


# ======================================================================
# Scenario 4 — multi-business collaboration
# ======================================================================
async def test_scenario_04_multi_business_collaboration(app_ops):
    """P-13 shared service (usage allocation, internal only) + P-13
    cross-business workflow: BOTH businesses must authorize before
    P-12 sub-workflows exist; each sub-workflow runs in its own
    business scope; P-07 records stay per-business; participation
    grants zero cross-access (asserted + audited).
    """
    app = app_ops
    from tests.p13_support import business_with_collected
    a = await business_with_collected(app, name="P14 Collab A", amount="4000")
    b = await business_with_collected(app, name="P14 Collab B", amount="2000")
    portfolio = await make_portfolio(app, business_ids=[a, b])
    svc = app.portfolio

    # Shared service: one service, usage-split internal allocation.
    service = make_service_with_access(app, business_ids=[a, b])
    svc.record_usage(OWNER, service["id"], {"business_id": a, "units": 75})
    svc.record_usage(OWNER, service["id"], {"business_id": b, "units": 25})
    before = app.financial.consolidated("INR")
    allocation = svc.create_allocation(OWNER, {
        "service_id": service["id"], "portfolio_id": portfolio["id"],
        "method": "usage_based", "total_cost_minor": 10000,
        "business_ids": [a, b]})
    amounts = {r["business_id"]: r["amount_minor"]
               for r in allocation["allocations"]}
    assert amounts == {a: 7500, b: 2500}
    assert allocation["kind"] == "INTERNAL_ALLOCATION"
    svc.decide_allocation(OWNER, allocation["id"], True)
    # Internal allocation moved NO P-07 money.
    assert app.financial.consolidated("INR") == before

    # A real per-business expense lands only on A's P-07 records.
    await paid_expense(app, a, "500.00")
    fa = svc.business_finance(OWNER, a)
    fb = svc.business_finance(OWNER, b)
    assert fa["summary"]["revenue"]["net_collected_minor"] == 4000_00
    assert fb["summary"]["revenue"]["net_collected_minor"] == 2000_00
    assert fa["summary"]["expenses"]["pl_expense_paid_minor"] == 500_00
    assert fb["summary"]["expenses"]["pl_expense_paid_minor"] == 0

    # Cross-business workflow: authorization required from BOTH.
    register_agent(app, AGENT.id, business_ref=a)
    workflow = svc.create_portfolio_workflow(OWNER, portfolio["id"], {
        "name": "P14 joint sprint", "objective": "shared research",
        "participations": [
            {"business_id": a, "contribution_category": "research",
             "contribution_description": "market scan"},
            {"business_id": b, "contribution_category": "content",
             "contribution_description": "summary draft"}]})
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
        view = app.operations.get_workflow(
            OWNER, part["operations_workflow_id"])
        assert view["business_id"] == part["business_id"]  # own scope
        ops_ids[part["business_id"]] = part["operations_workflow_id"]
    assert ops_ids[a] != ops_ids[b]
    for wid in ops_ids.values():
        app.operations.validate_workflow(OWNER, wid)
        await app.operations.start_workflow(OWNER, wid)
    refreshed = svc.refresh_portfolio_workflow(OWNER, workflow["id"])
    assert refreshed["status"] == "COMPLETED"

    # Zero cross-access created by participation (asserted + audited).
    before_denials = _audit_count(app, "portfolio.isolation_violation")
    check = svc.check_agent_access(AGENT, business_id=b,
                                   category="aggregate_metrics")
    assert check["allowed"] is False
    assert _audit_count(app, "portfolio.isolation_violation") \
        == before_denials + 1
    with pytest.raises(PermissionDeniedError):
        svc.business_finance(AGENT, b)

    # Portfolio outcome view: figures side by side, cash never combined.
    pfin = svc.portfolio_finance(OWNER, portfolio["id"])
    assert pfin["combined_available_cash"] is None
    assert pfin["totals"]["net_collected_minor"] == 6000_00
    assert _dash(app).businesses_summary()["total"] == 2


# ======================================================================
# Scenario 5 — infrastructure failure (AI provider killed mid-chain)
# ======================================================================
async def test_scenario_05_ai_provider_failure_fallback(app_ops):
    """A P-12 workflow completes on the deterministic path; the AI
    provider is then KILLED (dead Ollama URL injected, cloud disabled
    by default settings) with an enabled LLM profile pointing at it;
    P-02 detects unavailability (models_status + router decision
    record), falls back to the deterministic baseline planner, an
    unplannable mission fails HONESTLY (planning_failed, no fabricated
    plan), the earlier workflow's state is preserved, a new P-12
    workflow still completes deterministically, and the failure is
    visible on the P-11 system-health surface.
    """
    app = app_ops

    # Baseline chain works before the failure.
    wf = make_workflow(app, steps=[echo_step("pre")], name="P14 pre-kill")
    result = await run_workflow(app, OWNER, wf["id"])
    assert result["status"] == "COMPLETED"

    # Kill the provider mid-chain: replace the Ollama adapter with a
    # dead-endpoint one and enable a profile that selects it.
    from app.intelligence.providers import OllamaProvider
    app.intelligence.providers["ollama"] = OllamaProvider(
        "http://127.0.0.1:9", timeout_seconds=0.5)
    app.intelligence.upsert_profile(OWNER, "dead-local", {
        "task_classes": ["planning"], "provider": "ollama",
        "model_id": "dead-1", "enabled": True, "limits": {"size_rank": 1}})

    # Detection surface 1: models_status reports both providers down.
    status = await app.intelligence.models_status()
    assert status["providers"]["ollama"]["available"] is False
    assert status["providers"]["cloud"]["available"] is False

    # Detection + fallback: a template-matched mission is still
    # planned — by the deterministic baseline, with the router's
    # decision record naming the unavailable provider.
    mission = await app.intelligence.create_mission(
        OWNER, "Check system health and report whether the task system is working")
    plan = await app.intelligence.create_plan(OWNER, mission.id)
    assert plan.planner == "rule-engine"
    rows, _total = app.intelligence.recorder.list(
        mission_id=mission.id, limit=200)
    router_rows = [r for r in rows if r.decision_type == "router_selection"]
    assert router_rows, "router selection must be recorded (P-02 recorder)"
    assert any("baseline" in (r.reason or "") for r in router_rows)
    assert any("ollama" in (r.reason or "") for r in router_rows), \
        [r.reason for r in router_rows]

    # No fabricated success: an unplannable mission fails honestly.
    hopeless = await app.intelligence.create_mission(
        OWNER, "Plan an underwater basket weaving championship tour")
    with pytest.raises(ValidationError):
        await app.intelligence.create_plan(OWNER, hopeless.id)
    assert app.intelligence.get_mission(hopeless.id).status == "planning_failed"
    rows, _ = app.intelligence.recorder.list(
        mission_id=hopeless.id, limit=200)
    assert any(r.decision_type == "plan_failed" for r in rows)

    # State preservation + deterministic operations continue.
    assert app.operations.get_workflow(OWNER, wf["id"])["status"] == "COMPLETED"
    wf2 = make_workflow(app, steps=[echo_step("post")], name="P14 post-kill")
    result2 = await run_workflow(app, OWNER, wf2["id"])
    assert result2["status"] == "COMPLETED"
    assert result2["verified_outcome"] == "verified"

    # Visibility: P-11 system health names the provider as unavailable.
    health = await _dash(app).system_health()
    ai_check = next(c for c in health["checks"] if c["key"] == "ai_provider")
    assert ai_check["state"] == "unavailable"
    assert "ollama" in ai_check["detail"]


# ======================================================================
# Scenario 6 — security incident
# ======================================================================
async def test_scenario_06_security_incident_end_to_end(app_ops, client_ops):
    """An agent of Business A attempts (1) a cross-business portfolio
    read, (2) a cross-business broker read, (3) a protected-file read
    and (4) a security-policy change. Every attempt is blocked; the
    denials are in the P-01 audit trail; alert evaluation raises a
    CRITICAL policy_change_attempt alert; the dashboard security
    surface (service + HTTP) shows it; the critical notification
    cannot be dismissed (§5.4); an owner incident record exists.
    """
    app = app_ops
    a = await make_business(app, name="P14 Guard A")
    b = await make_business(app, name="P14 Guard B")
    await make_portfolio(app, business_ids=[a, b])
    register_agent(app, AGENT.id, business_ref=a)
    svc = app.portfolio

    # (1) Cross-business portfolio access: denied + isolation audit.
    before_iso = _audit_count(app, "portfolio.isolation_violation")
    check = svc.check_agent_access(AGENT, business_id=b,
                                   category="aggregate_metrics")
    assert check["allowed"] is False
    assert _audit_count(app, "portfolio.isolation_violation") == before_iso + 1

    # (2) Cross-business broker read: denied regardless of reasoning.
    broker_decision = app.security.broker.authorize(
        AGENT, permission="read_business_data", action="business.read",
        business_ref=b)
    assert broker_decision["allowed"] is False
    assert "cross-business" in broker_decision["reason"]

    # (3) Protected file read via the P-10 filesystem guard: denied,
    #     no content, audited.
    guard = app.security.filesystem_guard.evaluate(
        AGENT, operation="read", raw_path="credentials/prod-api-keys.txt")
    assert guard["allowed"] is False and "content" not in guard
    from tests.p10_support import audit_events
    events = audit_events(app, "security.filesystem_guard")
    assert any(e.decision == "deny" and e.actor_id == AGENT.id
               for e in events)

    # (4) Policy manipulation attempt: denied, audited, alerted.
    with pytest.raises(PermissionDeniedError):
        app.security.update_settings(AGENT, {"login_max_failures": 10000})
    created = app.security.monitor.evaluate_alerts()
    assert any(al["rule"] == "policy_change_attempt"
               and al["severity"] == "critical" for al in created)
    alerts, alert_total = app.security.monitor.list_alerts(status="open")
    assert any(al["rule"] == "policy_change_attempt" for al in alerts)

    # Owner incident record on the P-10 incident surface.
    incident = app.security.create_incident(OWNER, {
        "title": "P14 cross-business access attempts",
        "category": "access", "severity": "high",
        "description": "Agent of Business A attempted Business B reads "
                       "and a policy change; all denied.",
        "related_ref": b})
    incidents, inc_total = app.security.list_incidents(status="open")
    assert any(i["id"] == incident["id"] for i in incidents)

    # Dashboard security surface (service — the route's own object).
    dash = _dash(app)
    sec_summary = dash.security_summary()
    assert sec_summary["alerts_by_status"].get("open", 0) >= 1
    assert sec_summary["incidents_by_status"].get("open", 0) >= 1
    attention = dash.attention()
    assert any(i["kind"] == "security_alert" for i in attention["items"])

    # Critical alert is non-dismissible through the notification centre.
    notes = dash.notifications(OWNER)
    crit = [n for n in notes["items"]
            if n["kind"] == "security_alert" and n["severity"] == "critical"]
    assert crit and crit[0]["dismissible"] is False
    with pytest.raises(ValidationError):
        dash.dismiss_notification(OWNER, crit[0]["id"])

    # Same surfaces over real HTTP (shared-DB client fixture).
    headers = owner_http_headers(client_ops)
    resp = client_ops.get("/api/v1/dashboard/security/summary",
                          headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["alerts_by_status"].get("open", 0) >= 1
    http_notes = client_ops.get("/api/v1/dashboard/notifications",
                                headers=headers)
    assert http_notes.status_code == 200, http_notes.text
    http_crit = [n for n in http_notes.json()["data"]["items"]
                 if n["kind"] == "security_alert"
                 and n["severity"] == "critical"]
    assert http_crit, http_notes.text
    refused = client_ops.post(
        f"/api/v1/dashboard/notifications/{http_crit[0]['id']}/dismiss",
        headers=headers)
    assert refused.status_code == 422, refused.text
    assert "cannot be dismissed" in refused.json()["error"]["message"]
