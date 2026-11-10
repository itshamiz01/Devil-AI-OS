"""P-04 resource tests (§22.4): fleet ceilings, per-agent concurrency,
shared-inference gate, backpressure under pressure, single model
instance, idle suspension, failed-initialization recovery cap."""
from __future__ import annotations

import asyncio

import pytest

from app.agents.errors import InitializationFailedError, ResourceLimitExceededError
from app.agents.resources import AgentResourceManager
from tests.conftest import OWNER, wait_for_status


# ------------------------------------------------------------ max agent count
async def test_max_agent_count_enforced(application):
    factory = application.agents
    factory.update_settings(OWNER, {"max_total_agents": 2})
    await factory.create_agent({"role": "research_agent"}, principal=OWNER)
    await factory.create_agent({"role": "market_analysis_agent"}, principal=OWNER)
    third = await factory.create_agent(
        {"role": "competitor_analysis_agent"}, principal=OWNER)
    assert third["decision"] == "QUEUE_FOR_LATER"
    assert any("total agent limit" in r for r in third["decision_reasons"])
    # Existing agents continue operating safely.
    status = factory.factory_status()
    assert status["total_agents"] == 2


# ------------------------------------------------- max concurrent tasks/agent
async def test_max_concurrent_tasks_per_agent(application):
    factory = application.agents
    created = await factory.create_agent(
        {"role": "research_agent",
         "config_overrides": {"resource_budget": {"max_concurrent_tasks": 1}}},
        principal=OWNER)
    agent_id = created["created_agent_id"]
    # This agent's effective budget: max_concurrent_tasks == 1.
    first = await factory.assign(
        agent_id, {"objective": "long task", "handler_name": "core.wait",
                   "task_payload": {"milliseconds": 3000}, "timeout_seconds": 10},
        principal=OWNER)
    await wait_for_status(application.tasks, first["task_id"], {"running"},
                          timeout=10)
    with pytest.raises(Exception) as excinfo:
        await factory.assign(
            agent_id, {"objective": "second task", "handler_name": "core.noop",
                       "task_payload": {}},
            principal=OWNER)
    assert any(f["rule"] == "resource_budget"
               for f in excinfo.value.details["failures"])
    await wait_for_status(application.tasks, first["task_id"],
                          {"completed", "failed"}, timeout=15)


# ------------------------------------------------------- inference gate (J)
async def test_model_concurrency_limit_enforced():
    manager = AgentResourceManager(monitor=None)

    class SlowRouter:
        async def select(self, task_class):
            await asyncio.sleep(0.25)
            return "decision"

    manager.bind_router(SlowRouter())
    settings = {"max_concurrent_inference_requests": 1}
    results = await asyncio.gather(
        manager.run_shared_inference("general", settings=settings),
        manager.run_shared_inference("general", settings=settings),
        return_exceptions=True)
    kinds = sorted(type(r).__name__ for r in results)
    assert kinds == ["ResourceLimitExceededError", "str"]
    assert manager.inference_active == 0


async def test_single_shared_router_no_duplicate_instances(application):
    factory = application.agents
    created = await factory.create_agent({"role": "research_agent"}, principal=OWNER)
    agent_id = created["created_agent_id"]
    for _ in range(3):
        out = await factory.run_inference(agent_id, "general", principal=OWNER)
        assert out["router_bindings"] == 1
    # The factory's router IS the P-02 service's router object.
    assert factory.resources._router is application.intelligence._router
    metrics = factory.agent_metrics(agent_id)
    assert metrics["aggregates"]["inference_requests"]["measurement_type"] == "estimated"


# ------------------------------------------------------------- backpressure
async def test_resource_pressure_blocks_nonessential_creation(application):
    factory = application.agents

    class FakeMonitor:
        queue_stats = None

        def threshold_violations(self, resources=None):
            return [{"resource": "cpu", "value": 99.0, "threshold": 90.0},
                    {"resource": "memory", "value": 98.0, "threshold": 90.0}]

        def resources(self):
            return {"cpu_percent": 99.0, "memory_percent": 98.0,
                    "disk_percent": 10.0}

    factory.resources._monitor = FakeMonitor()
    try:
        pressure = factory.resources.pressure()
        assert pressure["level"] == 2
        result = await factory.create_agent({"role": "research_agent"},
                                            principal=OWNER)
        assert result["decision"] == "QUEUE_FOR_LATER"
        assert any("resource pressure" in r for r in result["decision_reasons"])
        # Essential work is never blocked by the ladder.
        essential = await factory.create_agent(
            {"role": "research_agent", "essential": True}, principal=OWNER)
        assert essential["decision"] == "CREATE_AGENT"
    finally:
        factory.resources._monitor = application.monitor


async def test_resource_pressure_queues_low_priority_assignments(application):
    factory = application.agents
    created = await factory.create_agent({"role": "research_agent"}, principal=OWNER)
    agent_id = created["created_agent_id"]

    class FakeMonitor:
        queue_stats = None

        def threshold_violations(self, resources=None):
            return [{"resource": "cpu", "value": 99.0, "threshold": 90.0},
                    {"resource": "memory", "value": 98.0, "threshold": 90.0}]

        def resources(self):
            return {"cpu_percent": 99.0, "memory_percent": 98.0,
                    "disk_percent": 10.0}

    factory.resources._monitor = FakeMonitor()
    try:
        with pytest.raises(Exception) as excinfo:
            await factory.assign(
                agent_id, {"objective": "low priority work",
                           "handler_name": "core.noop", "task_payload": {},
                           "priority": 1},
                principal=OWNER)
        assert any(f["rule"] == "resource_budget"
                   for f in excinfo.value.details["failures"])
    finally:
        factory.resources._monitor = application.monitor


# ----------------------------------------------------------- idle suspension
async def test_idle_agent_suspension_via_maintenance(application):
    factory = application.agents
    created = await factory.create_agent({"role": "research_agent"}, principal=OWNER)
    agent_id = created["created_agent_id"]
    factory.update_settings(OWNER, {"idle_suspend_seconds": 0})
    result = await factory.run_maintenance(principal=OWNER)
    assert agent_id in result["idle_suspended"]
    assert factory.get_agent(agent_id).status == "suspended"
    # Deliberate resume works afterwards.
    await factory.resume_agent(agent_id, principal=OWNER)
    assert factory.get_agent(agent_id).status == "active"


# ------------------------------------------- failed initialization (Scenario F)
async def test_failed_initialization_cap_prevents_endless_replacements(application):
    factory = application.agents
    bad = {"role": "research_agent",
           "config_overrides": {"tool_requirements": {"handlers": ["core.missing"]}}}
    for _ in range(3):
        with pytest.raises(InitializationFailedError):
            await factory.create_agent(bad, principal=OWNER)
    assert factory.factory_status()["agents_by_status"].get("failed") == 3
    # The 4th attempt is refused by decision — no endless replacements.
    result = await factory.create_agent(bad, principal=OWNER)
    assert result["decision"] == "REJECT_CREATION"
    assert any("initialization failures" in r for r in result["decision_reasons"])
    assert factory.factory_status()["total_agents"] == 3
