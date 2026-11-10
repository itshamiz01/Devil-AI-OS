"""P-04 unit tests: lifecycle graph, template validation/versioning,
creation-decision matrix, capability level rules, output contracts,
configuration rollback, scaling policy, backpressure ladder."""
from __future__ import annotations

import copy

import pytest

from app.agents import constants as C
from app.agents.errors import TemplateInvalidError
from app.agents.lifecycle import TRANSITIONS, validate_transition
from app.agents.resources import AgentResourceManager
from app.agents.scaling import ScalingPolicy
from app.agents.validation import validate_output_contract, validate_template_configuration
from app.permissions.models import Principal, PrincipalType
from tests.conftest import OWNER

SYSTEM = Principal(PrincipalType.SYSTEM, "system")


def _valid_config() -> dict:
    return copy.deepcopy(C.SEED_TEMPLATES[0]["configuration"])


def _levels() -> dict:
    return {c["name"]: (c["approval_level"] if c.get("enabled", True) else 3)
            for c in C.CAPABILITY_CATALOGUE}


_CEILINGS = {"max_concurrent_tasks_per_agent": 2, "max_template_task_seconds": 3600,
             "max_template_memory_budget_mb": 4096}


# --------------------------------------------------------------- lifecycle
def test_lifecycle_graph_valid_transitions():
    for src, targets in TRANSITIONS.items():
        for tgt in targets:
            assert validate_transition(src, tgt), f"{src}->{tgt} should be valid"


def test_lifecycle_graph_invalid_transitions_rejected():
    assert not validate_transition("retired", "active")
    assert not validate_transition("retired", "initializing")
    assert not validate_transition("proposed", "active")  # must initialize first
    assert not validate_transition("active", "proposed")
    assert not validate_transition("suspended", "busy")
    assert not validate_transition("pending_approval", "active")


def test_lifecycle_legacy_bridge_is_narrow():
    assert validate_transition("created", "initializing")
    assert validate_transition("created", "retiring")
    assert not validate_transition("created", "active")


# ------------------------------------------------------- template validation
def test_template_validation_accepts_seed_config():
    errors = validate_template_configuration(
        _valid_config(), capability_levels=_levels(),
        model_profile_names=set(), ceilings=_CEILINGS)
    assert errors == []


def test_template_validation_rejects_missing_fields():
    config = _valid_config()
    config["mission"] = ""
    config["system_instruction"] = "  "
    errors = validate_template_configuration(
        config, capability_levels=_levels(), model_profile_names=set(),
        ceilings=_CEILINGS)
    assert any("mission" in e for e in errors)
    assert any("system_instruction" in e for e in errors)


def test_template_validation_rejects_prohibited_capability():
    config = _valid_config()
    config["allowed_capabilities"] = ["internal_reasoning", "reveal_secrets"]
    errors = validate_template_configuration(
        config, capability_levels=_levels(), model_profile_names=set(),
        ceilings=_CEILINGS)
    assert any("PROHIBITED" in e for e in errors)


def test_template_validation_rejects_allowed_restricted_overlap_and_unknown():
    config = _valid_config()
    config["allowed_capabilities"] = ["internal_reasoning", "memory_read"]
    config["restricted_capabilities"] = ["memory_read", "not_a_capability"]
    errors = validate_template_configuration(
        config, capability_levels=_levels(), model_profile_names=set(),
        ceilings=_CEILINGS)
    assert any("both allowed and restricted" in e for e in errors)
    assert any("not_a_capability" in e for e in errors)


def test_template_validation_rejects_budget_above_ceiling():
    config = _valid_config()
    config["resource_budget"]["max_concurrent_tasks"] = 99
    config["resource_budget"]["memory_budget_mb"] = 999999
    errors = validate_template_configuration(
        config, capability_levels=_levels(), model_profile_names=set(),
        ceilings=_CEILINGS)
    assert any("max_concurrent_tasks exceeds" in e for e in errors)
    assert any("memory_budget_mb exceeds" in e for e in errors)


def test_template_validation_rejects_unknown_model_profile():
    config = _valid_config()
    config["model_requirements"] = {"task_class": "general",
                                    "profile_name": "no-such-profile"}
    errors = validate_template_configuration(
        config, capability_levels=_levels(), model_profile_names={"real-profile"},
        ceilings=_CEILINGS)
    assert any("no-such-profile" in e for e in errors)


# --------------------------------------------------------- output contracts
def test_output_contract_validator():
    ok = validate_output_contract({"summary": "x", "ok": True},
                                  {"required_fields": ["summary"]})
    assert ok["valid"] is True
    bad = validate_output_contract({"ok": True},
                                   {"required_fields": ["summary", "evidence_refs"]})
    assert bad["valid"] is False
    assert bad["missing_fields"] == ["summary", "evidence_refs"]
    none_result = validate_output_contract(None, {"required_fields": ["summary"]})
    assert none_result["valid"] is False
    no_req = validate_output_contract({"anything": 1}, {})
    assert no_req["valid"] is True


# --------------------------------------------------------------- templates
async def test_template_versioning_pinning_compare_restore(application):
    factory = application.agents
    settings = factory.settings_values()
    config = _valid_config()
    template = factory.templates.create(
        OWNER, name="Versioning Test Template", category="intelligence",
        description="t", configuration=config, settings=settings)
    factory.templates.publish(OWNER, template.id, version=1)

    result = await factory.create_agent(
        {"role": "research_agent", "template_id": template.id}, principal=OWNER)
    assert result["decision"] == "CREATE_AGENT"
    agent = factory.get_agent(result["created_agent_id"])
    assert agent.template_version == 1

    changed = _valid_config()
    changed["mission"] = "A changed mission for v2."
    factory.templates.update(OWNER, template.id, configuration=changed,
                             settings=settings)
    factory.templates.publish(OWNER, template.id, version=2)
    # The existing agent is PINNED: publishing v2 did not move it.
    agent = factory.get_agent(result["created_agent_id"])
    assert agent.template_version == 1

    v1 = factory.templates.get_version(template.id, 1)
    v2 = factory.templates.get_version(template.id, 2)
    diff = factory.templates.compare(v1.configuration, v2.configuration)
    assert "mission" in diff["changed_fields"]

    factory.templates.restore(OWNER, template.id, version=1, settings=settings)
    v3 = factory.templates.get_version(template.id, 3)
    assert v3.configuration["mission"] == v1.configuration["mission"]


async def test_invalid_template_cannot_publish(application):
    factory = application.agents
    settings = factory.settings_values()
    config = _valid_config()
    config["allowed_capabilities"] = ["internal_reasoning", "disable_security_controls"]
    template = factory.templates.create(
        OWNER, name="Invalid Template", category="intelligence", description="t",
        configuration=config, settings=settings)
    version = factory.templates.get_version(template.id, 1)
    assert version.validation_status == "invalid"
    with pytest.raises(TemplateInvalidError):
        factory.templates.publish(OWNER, template.id, version=1)


async def test_unpublished_template_never_produces_agent(application):
    factory = application.agents
    settings = factory.settings_values()
    template = factory.templates.create(
        OWNER, name="Draft Only Template", category="intelligence",
        description="t", configuration=_valid_config(), settings=settings)
    result = await factory.evaluate_creation(
        {"role": "research_agent", "template_id": template.id}, principal=OWNER)
    assert result["decision"] == "REJECT_CREATION"
    assert any("no published version" in r for r in result["decision_reasons"])


# --------------------------------------------------------- creation decisions
async def test_creation_decision_rejects_prohibited_capability(application):
    factory = application.agents
    result = await factory.evaluate_creation(
        {"role": "research_agent", "capabilities": ["bypass_approvals"]},
        principal=OWNER)
    assert result["decision"] == "REJECT_CREATION"
    assert any("PROHIBITED" in r for r in result["decision_reasons"])


async def test_creation_decision_rejects_unsupported_capability(application):
    # P-05 DISCLOSURE: this test previously used "browser_interaction" as
    # its unsupported-capability example. P-05 genuinely backs
    # browser_interaction (fetch-backend sessions), so the example became
    # "memory_write". P-09 DISCLOSURE: P-09 now genuinely backs
    # memory_write (governed memory engine), so the example is now
    # "external_communication" — still unsupported (no outbound channel
    # exists). Same assertion, same strictness: an unsupported
    # capability rejects creation.
    factory = application.agents
    result = await factory.evaluate_creation(
        {"role": "research_agent", "capabilities": ["external_communication"]},
        principal=OWNER)
    assert result["decision"] == "REJECT_CREATION"
    assert any("not" in r and "backed" in r for r in result["decision_reasons"])


async def test_creation_decision_level2_capability_requires_owner_approval(application):
    factory = application.agents
    result = await factory.create_agent(
        {"role": "research_agent", "capabilities": ["web_research"]}, principal=OWNER)
    assert result["decision"] == "REQUEST_OWNER_APPROVAL"
    assert result["approval_status"] == "pending"
    assert result["approval_id"]
    assert result["created_agent_id"] is None


async def test_creation_decision_agent_requester_requires_approval(application):
    factory = application.agents
    agent_principal = Principal(PrincipalType.AGENT, "requester-agent")
    result = await factory.evaluate_creation(
        {"role": "research_agent"}, principal=agent_principal)
    assert result["decision"] == "REQUEST_OWNER_APPROVAL"


async def test_creation_decision_unknown_role_rejected(application):
    factory = application.agents
    result = await factory.evaluate_creation(
        {"role": "not_a_real_role"}, principal=OWNER)
    assert result["decision"] == "REJECT_CREATION"


async def test_creation_decision_new_taxonomy_role_proposes_template(application):
    factory = application.agents
    result = await factory.evaluate_creation(
        {"role": "trend_detection_agent"}, principal=OWNER)
    assert result["decision"] == "REQUEST_OWNER_APPROVAL"
    assert any("Mode C" in r for r in result["decision_reasons"])


# ------------------------------------------------------------- capabilities
async def test_capability_level_rules(application):
    factory = application.agents
    created = await factory.create_agent({"role": "research_agent"}, principal=OWNER)
    agent_id = created["created_agent_id"]
    # Template capabilities were granted at creation (all Level 0 here).
    assert factory.capabilities.has_capability(agent_id, "internal_reasoning")
    # Level 0 via the REQUEST path: revoke, then re-request -> granted.
    await factory.revoke_capability(agent_id, "memory_read", principal=OWNER)
    assert not factory.capabilities.has_capability(agent_id, "memory_read")
    out = await factory.request_capability(agent_id, "memory_read", principal=OWNER)
    assert out["status"] == "granted"
    assert factory.capabilities.has_capability(agent_id, "memory_read")
    # Level 1 INSIDE the published template (financial agent template
    # includes financial_data_read): policy grant on request.
    fin = await factory.create_agent({"role": "financial_analysis_agent"},
                                     principal=OWNER)
    fin_id = fin["created_agent_id"]
    assert factory.capabilities.has_capability(fin_id, "financial_data_read")
    await factory.revoke_capability(fin_id, "financial_data_read", principal=OWNER)
    out = await factory.request_capability(fin_id, "financial_data_read",
                                           principal=OWNER)
    assert out["status"] == "granted"
    # Level 1 OUTSIDE the template (financial_data_read is not in the
    # Research template): escalates to owner approval, not granted.
    out = await factory.request_capability(agent_id, "financial_data_read",
                                           principal=OWNER)
    assert out["status"] == "approval_required"
    assert not factory.capabilities.has_capability(agent_id, "financial_data_read")
    # Level 2: approval required; the agent remains WITHOUT the capability.
    out = await factory.request_capability(agent_id, "web_research", principal=OWNER)
    assert out["status"] == "approval_required"
    assert not factory.capabilities.has_capability(agent_id, "web_research")


# --------------------------------------------------------- config versioning
async def test_configuration_update_and_rollback(application):
    factory = application.agents
    created = await factory.create_agent({"role": "market_analysis_agent"},
                                         principal=OWNER)
    agent_id = created["created_agent_id"]
    agent = factory.get_agent(agent_id)
    assert agent.configuration_version == 1
    assert len(factory.config_history(agent_id)) == 1

    updated = await factory.update_agent_config(
        agent_id, {"objective": "Analyse the planner niche."}, principal=OWNER,
        reason="owner direction")
    assert updated["configuration_version"] == 2
    assert updated["objective"] == "Analyse the planner niche."
    assert len(factory.config_history(agent_id)) == 2

    rolled = await factory.rollback_agent_config(agent_id, version=1, principal=OWNER)
    assert rolled["configuration_version"] == 3
    assert rolled["objective"] != "Analyse the planner niche."
    assert len(factory.config_history(agent_id)) == 3


# ------------------------------------------------------------------ scaling
def test_scaling_policy_decisions():
    settings = dict(C.DEFAULT_SETTINGS)
    base = {"queue_depth": 0, "active_agents": 2, "busy_agents": 1, "idle_agents": 1,
            "pressure_level": 0, "specialized_demand": False,
            "at_agent_ceiling": False, "avg_task_seconds": 2.0}
    assert ScalingPolicy.evaluate(base, settings)["decision"] == "KEEP_CURRENT_CAPACITY"
    assert ScalingPolicy.evaluate(
        {**base, "queue_depth": 3}, settings)["decision"] == "REASSIGN_WORK"
    assert ScalingPolicy.evaluate(
        {**base, "queue_depth": 3, "idle_agents": 0, "busy_agents": 2,
         "specialized_demand": True}, settings)["decision"] == "CREATE_SPECIALIZED_AGENT"
    assert ScalingPolicy.evaluate(
        {**base, "queue_depth": 3, "idle_agents": 0, "busy_agents": 2,
         "specialized_demand": True, "at_agent_ceiling": True},
        settings)["decision"] == "REQUEST_OWNER_APPROVAL"
    assert ScalingPolicy.evaluate(
        {**base, "pressure_level": 2, "queue_depth": 5}, settings)["decision"] == "QUEUE_WORK"
    assert ScalingPolicy.evaluate(
        {**base, "active_agents": 3, "busy_agents": 0, "idle_agents": 3},
        settings)["decision"] == "REDUCE_AGENT_COUNT"
    out = ScalingPolicy.evaluate({**base, "queue_depth": 2}, settings)
    # Economic honesty: internal work is never claimed as revenue.
    assert out["economic_justification"]["expected_business_benefit"] is None


# -------------------------------------------------------------- backpressure
def test_backpressure_ladder_actions():
    manager = AgentResourceManager(monitor=None)
    assert manager.backpressure_actions(0) == []
    level1 = manager.backpressure_actions(1)
    assert "stop_nonessential_agent_creation" in level1
    assert "queue_low_priority_assignments" in level1
    level2 = manager.backpressure_actions(2)
    assert "suspend_eligible_idle_agents" in level2
    assert "reduce_effective_concurrency_to_minimum" in level2


def test_factory_settings_defaults_are_hardware_aware():
    # CPU-only target hardware: one shared inference slot by default.
    assert C.DEFAULT_SETTINGS["max_concurrent_inference_requests"] == 1
    assert C.DEFAULT_SETTINGS["max_total_agents"] >= 1
