"""P-13 unit tests: the §4 lifecycle derivation, the §6 evidence
gate, the §8/§20 category and expiry validators. Pure functions —
the governed service behaviour is covered by the integration,
security and scenario suites."""
from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.permissions.models import Principal, PrincipalType
from app.portfolio import constants as C
from app.portfolio.access import _validate_categories, _validate_expiry
from app.portfolio.intelligence import validate_evidence
from tests.p13_support import future_iso, past_iso

OWNER_P = Principal(PrincipalType.OWNER, "owner")
AGENT_P = Principal(PrincipalType.AGENT, "agent-x")


# ------------------------------------------------------- §4 mapping
def test_stage_derivation_follows_p06_states():
    assert C.portfolio_stage("PROPOSED", None) == "IDEA"
    assert C.portfolio_stage("ELIGIBILITY_REVIEW", None) == "VALIDATING"
    assert C.portfolio_stage("BLUEPRINT_READY", None) == "APPROVED"
    assert C.portfolio_stage("IN_DEVELOPMENT", None) == "BUILDING"
    assert C.portfolio_stage("LAUNCHING", None) == "LAUNCHING"
    assert C.portfolio_stage("PAUSED", None) == "PAUSED"
    assert C.portfolio_stage("BLOCKED", None) == "BLOCKED"
    assert C.portfolio_stage("ARCHIVED", None) == "ARCHIVED"


def test_stage_operational_requires_p06_operational():
    # A business mid-build can never be labelled operational by P-13,
    # whatever the overlay claims (§4 honesty rule).
    assert C.portfolio_stage("IN_DEVELOPMENT", "GROWING") == "BUILDING"
    assert C.portfolio_stage("PROPOSED", "SCALING") == "IDEA"
    # Only P-06 OPERATIONAL + a P-08 overlay refines the reading.
    assert C.portfolio_stage("OPERATIONAL", "GROWING") == "OPERATIONAL"
    assert C.portfolio_stage("OPERATIONAL", "SCALING") == "SCALING"
    assert C.portfolio_stage("OPERATIONAL", "OPTIMIZING") == "OPTIMIZING"
    assert C.portfolio_stage("OPERATIONAL", "AT_RISK") == "AT_RISK"
    assert C.portfolio_stage("OPERATIONAL", None) == "OPERATIONAL"


# ------------------------------------------------------ §6 evidence
def test_evidence_gate_rejects_missing_or_untrusted_evidence():
    with pytest.raises(ValidationError):
        validate_evidence(OWNER_P, [])
    with pytest.raises(ValidationError):
        validate_evidence(OWNER_P, None)
    with pytest.raises(ValidationError):
        validate_evidence(OWNER_P, [{"source": "a blog post I read"}])
    with pytest.raises(ValidationError):
        validate_evidence(OWNER_P, [{"detail": "no source at all"}])


def test_evidence_gate_accepts_system_sources():
    assert validate_evidence(
        OWNER_P, [{"source": "p07.metrics", "collected_minor": 100}]
    ) == "VERIFIED"
    assert validate_evidence(
        AGENT_P, [{"source": "p08.concentration", "share_bps": 7000}]
    ) == "VERIFIED"


def test_evidence_gate_owner_attestation_is_owner_only():
    with pytest.raises(ValidationError):
        validate_evidence(AGENT_P, [{"source": "owner.attestation"}])
    assert validate_evidence(
        OWNER_P, [{"source": "owner.attestation"}]) == "VERIFIED"


def test_evidence_gate_labels_speculation():
    assert validate_evidence(OWNER_P, [
        {"source": "p03.opportunity", "speculative": True},
    ]) == "SPECULATIVE"


# ---------------------------------------------- §8/§20 grant rules
def test_categories_credentials_never_grantable():
    for bad in ("credentials", "customer_records", "financial_records",
                "business_memory", "secrets", "platform_accounts"):
        with pytest.raises(ValidationError):
            _validate_categories([bad], C.GRANTABLE_CATEGORIES, "grant")


def test_categories_unknown_and_empty_rejected():
    with pytest.raises(ValidationError):
        _validate_categories(["everything"], C.GRANTABLE_CATEGORIES,
                             "grant")
    with pytest.raises(ValidationError):
        _validate_categories([], C.GRANTABLE_CATEGORIES, "grant")
    assert _validate_categories(
        ["aggregate_metrics"], C.GRANTABLE_CATEGORIES, "grant"
    ) == ["aggregate_metrics"]


def test_portfolio_scope_categories_are_aggregate_only():
    # financial_summary is grantable business-to-agent under a direct
    # grant, but a PORTFOLIO-scope assignment may not carry it (§8).
    with pytest.raises(ValidationError):
        _validate_categories(["financial_summary"],
                             C.PORTFOLIO_SCOPE_CATEGORIES, "assignment")
    assert _validate_categories(["aggregate_metrics"],
                                C.PORTFOLIO_SCOPE_CATEGORIES,
                                "assignment") == ["aggregate_metrics"]


def test_expiry_is_mandatory_and_future():
    with pytest.raises(ValidationError):
        _validate_expiry(None)
    with pytest.raises(ValidationError):
        _validate_expiry(past_iso())
    with pytest.raises(ValidationError):
        _validate_expiry("not a timestamp")
    value = _validate_expiry(future_iso(5))
    assert isinstance(value, str) and value
