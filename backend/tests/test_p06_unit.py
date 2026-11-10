"""P-06 unit tests: lifecycle transition table, template validation,
financial values/arithmetic, redaction, eligibility decision matrix,
readiness precedence (§29.1/§29.2 pure-logic coverage)."""
from __future__ import annotations

import pytest

from app.business import eligibility as elig
from app.business import financial as fin
from app.business import lifecycle as lc
from app.business import readiness as rd
from app.business import templates as tpl
from app.business.blueprint import redact
from app.core.exceptions import ValidationError


# ---------------------------------------------------------------- lifecycle
def test_lifecycle_happy_path_transitions():
    path = ["PROPOSED", "ELIGIBILITY_REVIEW", "BLUEPRINTING",
            "BLUEPRINT_READY", "PRODUCT_PLANNING", "IN_DEVELOPMENT",
            "INTERNAL_TESTING", "DISTRIBUTION_PREPARATION", "LAUNCH_REVIEW",
            "READY_FOR_LAUNCH", "LAUNCH_APPROVAL_PENDING", "LAUNCHING",
            "OPERATIONAL", "ARCHIVED"]
    for a, b in zip(path, path[1:]):
        assert lc.can_transition(a, b), f"{a} -> {b}"


def test_lifecycle_rejects_skips_and_reversals():
    assert not lc.can_transition("PROPOSED", "OPERATIONAL")
    assert not lc.can_transition("BLUEPRINTING", "OPERATIONAL")
    assert not lc.can_transition("OPERATIONAL", "IN_DEVELOPMENT")
    assert not lc.can_transition("ARCHIVED", "PROPOSED")
    assert not lc.can_transition("FAILED", "IN_DEVELOPMENT")
    assert not lc.can_transition("IN_DEVELOPMENT", "BLUEPRINT_READY")


def test_lifecycle_pause_returns_only_to_origin():
    assert lc.can_transition("IN_DEVELOPMENT", "PAUSED")
    assert not lc.can_transition("OPERATIONAL", "PAUSED")
    assert lc.can_transition("PAUSED", "IN_DEVELOPMENT",
                             paused_from="IN_DEVELOPMENT")
    assert not lc.can_transition("PAUSED", "BLUEPRINT_READY",
                                 paused_from="IN_DEVELOPMENT")
    assert not lc.can_transition("PAUSED", "IN_DEVELOPMENT",
                                 paused_from=None)


# ---------------------------------------------------------------- templates
class _Tool:
    def __init__(self, name, status="available"):
        self.name = name
        self.status = status


class _Registry:
    TOOLS = {"filesystem": {"mkdir", "create"}, "documents": {"create_text"},
             "code_python": {"run"}}

    def get_tool(self, name):
        return _Tool(name) if name in self.TOOLS else None

    def action_spec(self, tool, action):
        return object() if action in self.TOOLS.get(tool.name, set()) else None


def _minimal_template():
    import copy
    return copy.deepcopy(tpl.EBOOK_TEMPLATE)


def test_seed_templates_validate_against_stub_registry_shape():
    # Only the tools the stub knows are used by the ebook template plus
    # filesystem.create; code_python appears only in the SaaS template.
    errors = tpl.validate_template_definition(tpl.EBOOK_TEMPLATE, _Registry())
    assert errors == [], errors


def test_template_validation_rejects_unknown_tool():
    bad = _minimal_template()
    bad["workflow"]["steps"].append(
        {"id": "x", "tool": "teleporter", "action": "beam", "parameters": {}})
    errors = tpl.validate_template_definition(bad, _Registry())
    assert any("unknown tool" in e for e in errors)


def test_template_validation_rejects_disabled_desktop_and_interactive_browser():
    bad = _minimal_template()
    bad["workflow"]["steps"].append(
        {"id": "x", "tool": "desktop", "action": "screenshot", "parameters": {}})
    errors = tpl.validate_template_definition(bad, _Registry())
    assert any("disabled" in e for e in errors)
    bad2 = _minimal_template()
    bad2["workflow"]["steps"].append(
        {"id": "y", "tool": "browser", "action": "interact", "parameters": {}})
    errors2 = tpl.validate_template_definition(bad2, _Registry())
    assert any("unavailable" in e for e in errors2)


def test_template_validation_rejects_money_and_sending_constructs():
    bad = _minimal_template()
    bad["workflow"]["steps"][0]["parameters"]["payment"] = {"amount": 5}
    errors = tpl.validate_template_definition(bad, _Registry())
    assert any("forbidden key" in e for e in errors)
    bad2 = _minimal_template()
    bad2["required_capabilities"] = ["external_communication"]
    errors2 = tpl.validate_template_definition(bad2, _Registry())
    assert any("external_communication" in e for e in errors2)


def test_template_validation_rejects_missing_sections_and_orphan_assets():
    bad = _minimal_template()
    del bad["readiness_criteria"]
    bad["asset_requirements"].append(
        {"asset_type": "x", "path": "x.md", "input_key": "nonexistent_key"})
    errors = tpl.validate_template_definition(bad, _Registry())
    assert any("missing required sections" in e for e in errors)
    assert any("not produced" in e for e in errors)


# ---------------------------------------------------------------- financial
def test_financial_value_shape_and_arithmetic():
    v = fin.financial_value(amount=15, source="test", classification="estimate")
    assert v["amount"] == 15 and v["currency"] == "USD" and v["source"]
    assert fin.sum_amounts([v, fin.financial_value(
        range_low=10, range_high=20, source="t")]) == 30.0
    with pytest.raises(ValidationError):
        fin.financial_value(amount=1, source="t", classification="guessed")
    with pytest.raises(ValidationError):
        fin.financial_value(amount=1, source="")


def test_financial_boundary_rejects_revenue_and_profit_keys():
    for key in ("collected_revenue", "profit", "revenue", "earnings"):
        with pytest.raises(ValidationError):
            fin.validate_financial_value(
                {"key": key, "amount": 100, "source": "x",
                 "classification": "verified"}, field=key)


# ---------------------------------------------------------------- redaction
def test_redaction_removes_secret_shapes():
    text = "key is sk-abcdef1234567890 and api_key=<REDACTED> done"
    out, n = redact(text)
    assert "sk-abcdef" not in out and "hunter2secret" not in out and n >= 2
    clean, n2 = redact("an ordinary sentence about fitness")
    assert clean == "an ordinary sentence about fitness" and n2 == 0


# ---------------------------------------------------------------- eligibility
def _ctx(**overrides):
    base = {
        "status": "VALIDATED", "validation_level": 3,
        "validation_missing": [], "hard_rejection": None,
        "evidence": [{"category": "problem", "classification": "CORROBORATED"}],
        "target_customer": "beginners", "problem": "no starter plan",
        "revenue_model": "one-time sales", "has_commercial": True,
        "startup_costs_present": True, "startup_all_unknown": False,
        "budget_compatible": True, "distribution_present": True,
        "compliance": {},
    }
    base.update(overrides)
    return base


def _decide(ctx, **kw):
    return elig.evaluate(ctx, min_level=kw.get("min_level", 3),
                         creation_approval_ok=kw.get("approval", True),
                         require_creation_approval=True)[0]


def test_eligibility_decision_matrix():
    assert _decide(_ctx()) == "ELIGIBLE_FOR_CREATION"
    assert _decide(_ctx(), approval=False) == "REQUIRES_OWNER_APPROVAL"
    assert _decide(_ctx(validation_level=1)) == "REQUIRES_MORE_RESEARCH"
    assert _decide(_ctx(validation_level=2)) == "REQUIRES_MORE_VALIDATION"
    assert _decide(_ctx(evidence=[])) == "REQUIRES_MORE_VALIDATION"
    assert _decide(_ctx(target_customer="")) == "REQUIRES_MORE_VALIDATION"
    assert _decide(_ctx(status="BLOCKED_BY_COMPLIANCE")) == "REJECTED"
    assert _decide(_ctx(hard_rejection={"rule": "x", "reason": "y"})) == "REJECTED"
    assert _decide(_ctx(budget_compatible=False)) == "REJECTED"
    assert _decide(_ctx(compliance={"requires_professional_review": True}),
                   approval=True) == "ELIGIBLE_WITH_CONDITIONS"


def test_eligibility_level_gate_uses_configured_minimum():
    assert _decide(_ctx(validation_level=2), min_level=2) == \
        "ELIGIBLE_FOR_CREATION"
    assert _decide(_ctx(validation_level=4), min_level=5) == \
        "REQUIRES_MORE_VALIDATION"


# ---------------------------------------------------------------- readiness
def _facts(**overrides):
    base = {
        "validation_level": 3, "min_level": 3, "customer_defined": True,
        "competitor_count": 1, "market_analysis": True,
        "pricing_documented": True, "product_exists": True,
        "quality_review": {"checks": [{"name": "a", "status": "passed"}],
                           "reviewed_by": "qa"},
        "limitations_documented": True, "documentation_assets": True,
        "identity_exists": True, "brand_assets": True,
        "product_description_asset": True, "rights_unresolved": False,
        "primary_channel_selected": True, "gates_recorded": True,
        "primary_gate_outcome": "PASS_PREPARED_ONLY",
        "channel_assets_ready": True, "human_action_pending": [],
        "onboarding_prepared": True, "support_procedures": True,
        "refund_documented": True, "monitoring_noted": True,
        "backup_noted": True, "recovery_noted": True,
        "dependencies_identified": True, "agents_assigned": True,
        "legal_requirements_identified": True, "policies_prepared": True,
        "platform_terms_reviewed": True,
        "professional_review_required": False, "costs_documented": True,
        "risks_recorded": True, "p07_payload_ok": True,
        "declaration": {"present": True, "approved": True,
                        "success_criteria": ["x"], "budget_cap": 50,
                        "currency": "USD", "startup_total": 15.0},
    }
    base.update(overrides)
    return base


def test_readiness_ready_and_warnings():
    assert rd.evaluate(_facts())["overall_status"] == "READY"
    result = rd.evaluate(_facts(human_action_pending=["Amazon KDP"]))
    assert result["overall_status"] == "READY_WITH_WARNINGS"
    assert result["warnings"]


def test_readiness_blockers_override_scores():
    result = rd.evaluate(_facts(product_exists=False))
    assert result["overall_status"] == "NOT_READY"
    assert any(b["dimension"] == "B" for b in result["blockers"])
    result2 = rd.evaluate(_facts(primary_gate_outcome="BLOCKED"))
    assert result2["overall_status"] == "BLOCKED"


def test_readiness_owner_review_and_declaration_budget_test():
    result = rd.evaluate(_facts(professional_review_required=True))
    assert result["overall_status"] == "OWNER_REVIEW_REQUIRED"
    over = _facts()
    over["declaration"] = {**over["declaration"], "startup_total": 500.0}
    result2 = rd.evaluate(over)
    assert result2["overall_status"] == "NOT_READY"
    assert any("budget cap" in b["blocker"] for b in result2["blockers"])
    assert "NOT independently certified" in result2["disclaimer"]
