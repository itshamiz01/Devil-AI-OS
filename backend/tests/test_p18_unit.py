"""P-18 unit tests: the deterministic scoring layer.

Every function here is pure; the tests pin the explainability
contracts — priority floors, SLA honesty (no policy, no target),
metrics that refuse missing data, health that refuses to guess,
knowledge matching thresholds and quality aggregation that
reports missing dimensions instead of hiding them.
"""
from __future__ import annotations

import datetime as dt

from app.experience import constants as C
from app.experience.scoring import (
    article_match, confidence_for, csat, effort, health, nps,
    priority_for, quality_score, rate, sla_state,
)

NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)


# ---------------------------------------------------------------- priority
def test_priority_floor_for_account_access():
    result = priority_for({}, "account_access")
    assert result["level"] == "high"
    assert result["floor_applied"] is True
    assert result["missing_factors"]  # absence is reported, not hidden


def test_priority_security_factor_never_below_high():
    result = priority_for({"security": 2}, "general_inquiry")
    assert result["level"] in ("high", "critical")


def test_priority_bands_and_breakdown():
    factors = {key: 3 for key in C.PRIORITY_FACTORS}
    result = priority_for(factors, "general_inquiry")
    assert result["level"] == "critical"
    assert result["ratio"] == 1.0
    assert result["contributions"]["security"] == 12.0
    low = priority_for({}, "general_inquiry")
    assert low["level"] == "low"


# ---------------------------------------------------------------- SLA
def test_sla_no_policy_is_not_configured():
    state = sla_state(None, created_at=NOW, first_response_at=None,
                      resolved_at=None, now=NOW)
    assert state["status"] == "not_configured"


def test_sla_within_and_breached():
    policy = {"category": "*", "first_response_minutes": 60,
              "resolution_minutes": 480}
    created = NOW - dt.timedelta(minutes=30)
    within = sla_state(policy, created_at=created,
                       first_response_at=None, resolved_at=None,
                       now=NOW)
    assert within["status"] == "within"
    late = NOW + dt.timedelta(minutes=31)
    breached = sla_state(policy, created_at=created,
                         first_response_at=None, resolved_at=None,
                         now=late)
    assert breached["status"] == "breached"
    assert breached["first_response_breached"] is True
    answered_late = sla_state(
        policy, created_at=created,
        first_response_at=(created + dt.timedelta(minutes=90)),
        resolved_at=None, now=NOW)
    assert answered_late["first_response_breached"] is True


# ---------------------------------------------------------------- metrics
def test_metrics_refuse_missing_data():
    assert csat([])["status"] == "INSUFFICIENT_DATA"
    assert nps([])["status"] == "INSUFFICIENT_DATA"
    assert effort([])["status"] == "INSUFFICIENT_DATA"
    assert rate(1, 0, "x")["status"] == "INSUFFICIENT_DATA"


def test_metrics_computed_with_samples():
    result = csat([5, 4, 4, 1])
    assert result["status"] == "computed"
    assert result["value"] == 3.5
    assert result["top2_percent"] == 75.0
    assert result["sample_size"] == 4
    nps_result = nps([10, 9, 6, 0])
    assert nps_result["value"] == 0.0  # 50% promoters - 50% detractors
    assert nps_result["promoters"] == 2
    assert effort([2, 4])["value"] == 3.0


# ---------------------------------------------------------------- health
def test_health_refuses_to_guess_without_signals():
    result = health({}, C.DEFAULT_SETTINGS["health_weights"])
    assert result["classification"] == "insufficient_data"
    assert result["score"] is None


def test_health_critical_ticket_forces_critical():
    signals = {"open_critical_tickets": 1, "open_high_tickets": 0,
               "open_tickets_other": 0, "reopened_tickets": 0,
               "fulfillment_problems": 0,
               "onboarding_incomplete": False, "low_feedback_count": 0}
    result = health(signals, C.DEFAULT_SETTINGS["health_weights"])
    assert result["classification"] == "critical"
    assert result["factors"]["open_critical_ticket"] == 30


def test_health_clean_signals_are_healthy():
    signals = {"open_critical_tickets": 0, "open_high_tickets": 0,
               "open_tickets_other": 0, "reopened_tickets": 0,
               "fulfillment_problems": 0,
               "onboarding_incomplete": False, "low_feedback_count": 0}
    result = health(signals, C.DEFAULT_SETTINGS["health_weights"])
    assert result["classification"] == "healthy"
    assert result["score"] == 100


def test_health_penalties_accumulate_into_bands():
    signals = {"open_critical_tickets": 0, "open_high_tickets": 2,
               "open_tickets_other": 1, "reopened_tickets": 1,
               "fulfillment_problems": 1,
               "onboarding_incomplete": True, "low_feedback_count": 1}
    result = health(signals, C.DEFAULT_SETTINGS["health_weights"])
    # 100 - (2*15 + 5 + 10 + 15 + 10 + 10) = 20 -> at_risk
    assert result["score"] == 20
    assert result["classification"] == "at_risk"


# ---------------------------------------------------------------- knowledge
def test_article_match_ranks_and_thresholds():
    articles = [
        {"id": "a1", "version": 3, "title": "Reset your password",
         "content": "To reset your password open account settings "
                    "and choose reset password."},
        {"id": "a2", "version": 1, "title": "Delivery times",
         "content": "Orders arrive within five working days."},
    ]
    ranked = article_match("how do I reset my password", articles)
    assert ranked and ranked[0]["article_id"] == "a1"
    assert confidence_for(ranked[0]["score"]) in (
        "verified", "partially_verified")
    assert article_match("unrelated zebra question", articles) == []
    assert confidence_for(None) == "insufficient_information"
    assert confidence_for(0.9) == "verified"
    assert confidence_for(0.3) == "partially_verified"
    assert confidence_for(0.05) == "insufficient_information"


# ---------------------------------------------------------------- quality
def test_quality_score_reports_missing_dimensions():
    result = quality_score({"accuracy": 5, "clarity": 3})
    assert result["status"] == "computed"
    assert result["value"] == 4.0
    assert result["scored_dimensions"] == 2
    assert "timeliness" in result["missing_dimensions"]
    assert quality_score({})["status"] == "INSUFFICIENT_DATA"
