"""P-15 unit tests: the §13 readiness scorer as pure functions,
the §11 recovery probes, and the module's constant contracts."""
from __future__ import annotations

from app.reliability import constants as C
from app.reliability.benchmarks import recovery_probes
from app.reliability.readiness import band_for, score_readiness


def healthy_evidence() -> dict:
    return {
        "resources": {"cpu_percent": 10.0, "memory_percent": 30.0,
                      "disk_percent": 40.0, "threshold_violations": []},
        "database": {"healthy": True, "integrity_ok": True,
                     "integrity_detail": "ok", "latency_ms": 0.5},
        "components": [{"key": "backend", "state": "ok"},
                       {"key": "database", "state": "ok"}],
        "queue": {"by_status": {"completed": 10, "failed": 0}},
        "incidents": {"open_by_severity": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
                      "recovery_rate": 1.0},
        "breakers": [{"target": "substrate:x", "state": "closed"}],
        "dead_letters": {"operations_open": 0, "event_total": 0},
        "backups": {"count": 2, "latest_verified": True, "stale": False},
        "audit_chain": {"ok": True, "detail": "verified"},
        "financial": {"integrity_ok": True},
        "security": {"mode": "normal", "open_alerts": 0,
                     "financial_suspended": False, "controls_wired": True},
        "samples": {"count": 25, "latest_at": "2026-11-10T00:00:00+00:00"},
        "benchmarks": {"latest": {"id": "b1"}, "within_tolerance": True,
                       "tolerance_detail": "within"},
        "self_checks": [{"key": "a", "ok": True}, {"key": "b", "ok": True}],
        "recovery": {"mechanism_present": True},
        "migration": {"database_revision": "x", "head": "x", "is_head": True},
        "logging_configured": True,
    }


def test_weights_total_100():
    assert sum(C.CATEGORY_WEIGHTS.values()) == 100
    assert set(C.CATEGORY_WEIGHTS) == {
        "performance", "reliability", "fault_tolerance_recovery",
        "data_integrity_backup", "security_governance", "observability",
        "testing_validation"}


def test_band_boundaries():
    assert band_for(100) == "Production-ready candidate"
    assert band_for(90) == "Production-ready candidate"
    assert band_for(89.9) == "Limited production candidate"
    assert band_for(75) == "Limited production candidate"
    assert band_for(60) == "Controlled testing"
    assert band_for(40) == "Development"
    assert band_for(39.9) == "Unstable"
    assert band_for(0) == "Unstable"


def test_healthy_evidence_scores_high_and_gate_ok():
    result = score_readiness(healthy_evidence())
    assert result["critical_gate_ok"] is True
    assert result["overall_score"] >= 90
    assert result["band"] == "Production-ready candidate"
    # External blockers still cap the effective classification.
    assert result["classification"].startswith("READY FOR CONTROLLED PILOT")
    blocker_keys = {b["key"] for b in result["blockers"]}
    assert {"windows_unverified", "real_llm_unexercised"} <= blocker_keys


def test_database_down_fails_critical_gate_regardless_of_score():
    ev = healthy_evidence()
    ev["database"] = {"healthy": False, "integrity_ok": False,
                      "integrity_detail": "FAILED", "latency_ms": None}
    result = score_readiness(ev)
    assert result["critical_gate_ok"] is False
    assert result["classification"].startswith("NOT PRODUCTION READY")
    assert any(b["scope"] == "critical" for b in result["blockers"])


def test_open_p0_incident_fails_critical_gate():
    ev = healthy_evidence()
    ev["incidents"]["open_by_severity"]["P0"] = 1
    result = score_readiness(ev)
    assert result["critical_gate_ok"] is False
    assert result["classification"].startswith("NOT PRODUCTION READY")


def test_audit_chain_failure_fails_critical_gate():
    ev = healthy_evidence()
    ev["audit_chain"] = {"ok": False, "detail": "mismatch"}
    result = score_readiness(ev)
    assert result["critical_gate_ok"] is False


def test_missing_benchmarks_dock_performance_not_inflate():
    ev = healthy_evidence()
    ev["benchmarks"] = {"latest": None, "within_tolerance": None,
                        "tolerance_detail": "none"}
    result = score_readiness(ev)
    perf = result["categories"]["performance"]
    assert perf["score"] < 60
    assert "benchmarks_recorded" in perf["failed_checks"]


def test_missing_evidence_scores_as_missing():
    result = score_readiness({})
    assert result["critical_gate_ok"] is False  # database state unknown
    assert result["overall_score"] < 40
    assert result["failed_checks"], "empty evidence must surface failures"


def test_every_category_reports_failed_checks():
    result = score_readiness(healthy_evidence())
    for cat in result["categories"].values():
        assert "failed_checks" in cat and "checks" in cat
        assert cat["weight"] == C.CATEGORY_WEIGHTS[cat["key"]]


def test_recovery_probes_pass():
    probes = recovery_probes()
    assert probes["circuit_breaker"]["ok"] is True
    assert probes["retry_policy"]["ok"] is True
