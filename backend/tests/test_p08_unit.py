"""P-08 unit tests: settings governance, monitoring honesty,
experiment pre-declaration, decision records, and the structural
proofs (no financial computation in P-08)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.exceptions import PermissionDeniedError, ValidationError
from tests.conftest import OWNER
from tests.p06_support import make_fixture_business
from tests.p08_support import (
    AGENT, EXPERIMENT, app_surv, healthy_snapshot,  # noqa: F401
    operational_business, profile_only_business, verified_sale,
)

SURVIVAL_SRC = Path(__file__).resolve().parents[1] / "app" / "survival"


# ------------------------------------------------------------ settings
async def test_settings_seeded_with_owner_governed_defaults(app_surv):
    settings = app_surv.survival.get_settings()
    assert settings["health_weights"]["financial"] == 25
    assert settings["max_increment_ratio"] == "0.5"
    assert settings["inference_slots"] == 1
    assert settings["max_concurrent_agents"] == 4


async def test_settings_update_is_owner_only(app_surv):
    with pytest.raises(PermissionDeniedError):
        app_surv.survival.update_settings(
            AGENT, {"max_concurrent_agents": 99})
    updated = app_surv.survival.update_settings(
        OWNER, {"concentration_threshold": "0.5"})
    assert updated["concentration_threshold"] == "0.5"
    with pytest.raises(ValidationError):
        app_surv.survival.update_settings(OWNER, {"unknown_key": 1})


# ------------------------------------------------------ monitoring honesty
async def test_collect_reports_missing_profile(app_surv):
    _opp, business = await make_fixture_business(app_surv)
    reading = app_surv.survival.monitoring.collect(business["id"])
    assert reading["profile_missing"] is True
    assert reading["indicators"] is None


async def test_vanity_observation_capped_tentative(app_surv):
    business_id, _profile = await profile_only_business(app_surv)
    observation = app_surv.survival.monitoring.record_observation(
        OWNER, business_id, {
            "kind": "traffic", "source": "imported_report",
            "reliability": "verified",
            "metrics": {"followers": 50000, "page_views": 90000}})
    # Vanity kinds can never carry verified reliability (§6.2).
    assert observation["reliability"] == "tentative"
    assert observation["is_vanity"] is True


async def test_customer_counts_come_from_p07_records(app_surv):
    business_id, _profile = await profile_only_business(app_surv)
    verified_sale(app_surv, business_id, "1000.00", customer="cust-a")
    verified_sale(app_surv, business_id, "1000.00", customer="cust-a")
    verified_sale(app_surv, business_id, "1000.00", customer="cust-b")
    reading = app_surv.survival.monitoring.collect(business_id)
    assert reading["counts"]["distinct_customers"] == 2
    assert reading["counts"]["repeat_customers"] == 1
    assert reading["counts"]["source"].startswith("p07.revenue")


# ------------------------------------------------------------- experiments
async def test_experiment_pre_declaration_required_fields(app_surv):
    business_id, _ = await profile_only_business(app_surv)
    incomplete = {k: v for k, v in EXPERIMENT.items()
                  if k not in ("hypothesis", "max_duration_days")}
    with pytest.raises(ValidationError) as excinfo:
        app_surv.survival.experiments.create_experiment(
            OWNER, business_id, incomplete)
    assert "hypothesis" in str(excinfo.value)
    rows, total = app_surv.survival.experiments.list_experiments(
        business_id=business_id)
    assert total == 0  # nothing was recorded half-declared


async def test_experiment_declared_before_start(app_surv):
    business_id, _ = await profile_only_business(app_surv)
    experiment = app_surv.survival.experiments.create_experiment(
        OWNER, business_id, dict(EXPERIMENT))
    assert experiment["status"] == "DESIGNED"
    assert experiment["approved_budget_minor"] == 200_000
    with pytest.raises(PermissionDeniedError):
        app_surv.survival.experiments.start_experiment(
            OWNER, experiment["id"])  # not approved yet


# -------------------------------------------------------------- decisions
async def test_agent_cannot_originate_close_decision(app_surv):
    business_id, _ = await operational_business(app_surv)
    with pytest.raises(PermissionDeniedError):
        app_surv.survival.decisions.create_decision(AGENT, business_id, {
            "decision_type": "CLOSE", "trigger": "agent wants out"})


async def test_decision_defaults_three_alternatives(app_surv):
    business_id, _ = await operational_business(app_surv)
    decision = app_surv.survival.decisions.create_decision(
        OWNER, business_id, {
            "decision_type": "MONITOR", "trigger": "routine review",
            "confidence": "high"})
    assert len(decision["alternatives"]) >= 3
    kinds = {a["kind"] for a in decision["alternatives"]}
    assert "maintain" in kinds  # the do-nothing alternative (§8.3)
    assert decision["intelligence_record_id"]  # P-02 record linked


async def test_decision_execution_is_idempotent(app_surv):
    business_id, _ = await operational_business(app_surv)
    decision = app_surv.survival.decisions.create_decision(
        OWNER, business_id, {
            "decision_type": "MONITOR", "trigger": "routine review"})
    first = app_surv.survival.decisions.execute(
        OWNER, decision["id"], "exec-key-1")
    assert first["executed_at"] is not None
    second = app_surv.survival.decisions.execute(
        OWNER, decision["id"], "exec-key-1")
    assert second.get("idempotent_replay") is True
    assert second["executed_at"] == first["executed_at"]


# ------------------------------------------------------- structural proofs
def test_no_financial_calculation_primitives_in_survival_package():
    """Lock 1 (§6.1/§32 rule 3): P-08 contains no float arithmetic
    and no reference to P-07's ledger/journal/revenue internals —
    it reads financial truth only through P-07's services."""
    forbidden = ["float(", "JournalEntry", "JournalLine",
                 "LedgerService", "RevenueRepository",
                 "ExpenseRepository", "LedgerRepository"]
    offenders = []
    for path in SURVIVAL_SRC.glob("*.py"):
        text = path.read_text()
        for token in forbidden:
            if token in text:
                offenders.append((path.name, token))
    assert offenders == []


def test_no_revenue_or_profit_columns_on_survival_models():
    """Snapshot/proposal tables may carry verbatim P-07 payloads and
    declared proposal amounts, but no P-08-owned revenue/profit
    figure exists as a column (mirrors P-06's schema proof)."""
    from app.database.models import survival as models
    bad = []
    for name in dir(models):
        cls = getattr(models, name)
        if hasattr(cls, "__table__"):
            for column in cls.__table__.columns:
                if re.search(r"(revenue|profit|collected)_minor$",
                             column.name) and \
                        "expected" not in column.name and \
                        "proposed" not in column.name and \
                        "current" not in column.name:
                    bad.append((name, column.name))
    assert bad == []
