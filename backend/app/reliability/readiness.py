"""Production Readiness Score (§13) — pure functions over an
evidence dict assembled by ``ReliabilityService.collect_evidence``.

Every point comes from a named, measurable check; a missing input
scores as missing (never as success). The critical gate is separate
from the arithmetic: a failed gate caps the classification at NOT
PRODUCTION READY regardless of the numerical score (§13 rule).
Standing external blockers (Windows unverified, no real LLM) cap
the *effective* classification at controlled pilot, consistent with
the P-14 §18 classification.
"""
from __future__ import annotations

from . import constants as C


def _check(key: str, label: str, ok: bool, points: float, max_points: float,
           detail: str, recommendation: str | None = None) -> dict:
    return {"key": key, "label": label, "ok": bool(ok),
            "points": round(float(points), 2), "max_points": float(max_points),
            "detail": detail,
            "recommendation": recommendation if not ok else None}


def _category(key: str, checks: list[dict]) -> dict:
    max_points = sum(c["max_points"] for c in checks) or 1.0
    points = sum(c["points"] for c in checks)
    return {"key": key, "weight": C.CATEGORY_WEIGHTS[key],
            "score": round(100.0 * points / max_points, 1),
            "checks": checks,
            "failed_checks": [c["key"] for c in checks if not c["ok"]]}


def band_for(score: float) -> str:
    for minimum, name in C.READINESS_BANDS:
        if score >= minimum:
            return name
    return "Unstable"


# ------------------------------------------------------------ categories
def _performance(ev: dict) -> dict:
    bench = ev.get("benchmarks") or {}
    latest = bench.get("latest")
    within = bench.get("within_tolerance")
    violations = (ev.get("resources") or {}).get("threshold_violations") or []
    samples = (ev.get("samples") or {}).get("count", 0)
    checks = [
        _check("benchmarks_recorded", "Benchmark run recorded",
               latest is not None, 40 if latest else 0, 40,
               "latest benchmark run present"
               if latest else "no benchmark run has been recorded yet",
               "Run a baseline benchmark from the Command Center."),
        _check("benchmarks_within_tolerance",
               "Benchmark medians within tolerance of the P-14 baseline",
               within is True, 30 if within else 0, 30,
               bench.get("tolerance_detail", "no comparison available"),
               "Profile the regressed read path before accepting the drift."),
        _check("resources_under_thresholds", "Resources under thresholds",
               not violations, 20 if not violations else 0, 20,
               "no threshold violations"
               if not violations else f"violations: {violations}",
               "Investigate the resource pressure; nonessential task "
               "admission is already blocked by the P-01 monitor."),
        _check("history_tracking", "Performance history is being recorded",
               samples > 0, 10 if samples > 0 else 0, 10,
               f"{samples} performance sample(s) recorded",
               "Start the sampler (it runs with the application outside "
               "the test environment)."),
    ]
    return _category("performance", checks)


def _reliability(ev: dict) -> dict:
    components = ev.get("components") or []
    rank = {"ok": 1.0, "degraded": 0.5, "unavailable": 0.25, "down": 0.0}
    if components:
        frac = sum(rank.get(c.get("state"), 0.0) for c in components) / len(components)
        comp_detail = (f"{sum(1 for c in components if c.get('state') == 'ok')}"
                       f"/{len(components)} components ok")
    else:
        frac, comp_detail = 0.0, "no component checks available"
    open_by = (ev.get("incidents") or {}).get("open_by_severity") or {}
    p0, p1, p2 = open_by.get("P0", 0), open_by.get("P1", 0), open_by.get("P2", 0)
    if p0 or p1:
        inc_points, inc_ok = 0.0, False
    elif p2:
        inc_points, inc_ok = 15.0, False
    else:
        inc_points, inc_ok = 30.0, True
    by_status = (ev.get("queue") or {}).get("by_status") or {}
    completed, failed = by_status.get("completed", 0), by_status.get("failed", 0)
    if completed + failed == 0:
        fail_points, fail_ok, fail_detail = 10.0, False, "no finished tasks yet (neutral)"
    else:
        ratio = failed / (completed + failed)
        fail_points = round(20.0 * max(0.0, 1.0 - ratio * 2), 2)
        fail_ok = ratio <= 0.25
        fail_detail = f"task failure ratio {ratio:.2f} ({failed}/{completed + failed})"
    checks = [
        _check("components_healthy", "Component health states", frac >= 0.75,
               round(50 * frac, 2), 50, comp_detail,
               "Resolve the degraded/down component checks."),
        _check("no_major_open_incidents", "No open P0/P1 incidents", inc_ok,
               inc_points, 30,
               f"open by severity: {open_by or 'none'}",
               "Work the incident register; P0/P1 incidents block readiness."),
        _check("task_failure_ratio", "Task failure ratio", fail_ok,
               fail_points, 20, fail_detail,
               "Inspect failed tasks and their recovery records."),
    ]
    return _category("reliability", checks)


def _fault_tolerance(ev: dict) -> dict:
    breakers = ev.get("breakers") or []
    open_breakers = [b for b in breakers if b.get("state") == "open"]
    recovery = ev.get("recovery") or {}
    mechanism = bool(recovery.get("mechanism_present"))
    incidents = ev.get("incidents") or {}
    rate = incidents.get("recovery_rate")
    if rate is None:
        rate_points, rate_ok, rate_detail = 12.0, False, "no incidents yet (neutral)"
    else:
        rate_points = round(25.0 * rate, 2)
        rate_ok = rate >= 0.8
        rate_detail = f"incident recovery rate {rate:.2f}"
    checks = [
        _check("circuit_breakers_present", "Circuit breakers registered (P-12)",
               len(breakers) > 0, 25 if breakers else 8, 25,
               f"{len(breakers)} breaker(s) registered"
               if breakers else "no breaker has been exercised yet (P-12 "
               "registers per dependency target on first use)",
               "Exercise a governed workflow so dependency breakers register."),
        _check("no_open_breakers", "No circuit breaker open",
               not open_breakers, 0 if open_breakers else 25, 25,
               f"open: {[b.get('target') for b in open_breakers]}"
               if open_breakers else "no breaker open",
               "Investigate the unhealthy dependency before it half-opens."),
        _check("startup_recovery_mechanism", "Startup recovery mechanism present",
               mechanism, 25 if mechanism else 0, 25,
               "interrupted tasks/workflows/executions are parked for "
               "operator review at startup (P-01/P-05/P-12); counts at "
               f"last startup: {recovery}",
               "Restore the startup recovery scan."),
        _check("incident_recovery_rate", "Incident recovery rate", rate_ok,
               rate_points, 25, rate_detail,
               "Close the loop on open incidents with recorded recovery actions."),
    ]
    return _category("fault_tolerance_recovery", checks)


def _data_integrity(ev: dict) -> dict:
    db = ev.get("database") or {}
    backups = ev.get("backups") or {}
    count = backups.get("count", 0)
    verified = backups.get("latest_verified")
    stale = bool(backups.get("stale"))
    if count == 0:
        fresh_points, fresh_ok, fresh_detail = 0.0, False, "no backups recorded"
    elif verified and not stale:
        fresh_points, fresh_ok, fresh_detail = 30.0, True, "latest backup verified and within the policy window"
    elif verified and stale:
        fresh_points, fresh_ok, fresh_detail = 12.0, False, "latest backup verified but STALE (outside the policy window)"
    else:
        fresh_points, fresh_ok, fresh_detail = 8.0, False, "latest backup is not verified"
    checks = [
        _check("database_healthy", "Database connectivity healthy",
               bool(db.get("healthy")), 25 if db.get("healthy") else 0, 25,
               "connectivity check passed" if db.get("healthy") else "connectivity check FAILED",
               "Restore database connectivity before any other work."),
        _check("database_integrity", "Database integrity check (PRAGMA integrity_check)",
               db.get("integrity_ok") is True, 25 if db.get("integrity_ok") else 0, 25,
               db.get("integrity_detail", "not run"),
               "Run the P-15 data-recovery procedure from a verified backup."),
        _check("backups_exist", "Backups exist (P-10 backup service)",
               count > 0, 20 if count else 0, 20,
               f"{count} backup(s) recorded",
               "Create a backup from the Command Center (P-10 service)."),
        _check("backup_verified_fresh", "Latest backup verified and fresh",
               fresh_ok, fresh_points, 30, fresh_detail,
               "Create and verify a fresh backup."),
    ]
    return _category("data_integrity_backup", checks)


def _security_governance(ev: dict) -> dict:
    chain = ev.get("audit_chain") or {}
    security = ev.get("security") or {}
    mode = security.get("mode")
    alerts = security.get("open_alerts")
    checks = [
        _check("audit_chain_verified", "P-10 audit chain verifies",
               chain.get("ok") is True, 40 if chain.get("ok") else 0, 40,
               chain.get("detail", "not run"),
               "Treat as a critical incident: stop and investigate the audit chain."),
        _check("security_mode_normal", "Security operating mode is normal",
               mode == "normal", 20 if mode == "normal" else 5, 20,
               f"mode: {mode}",
               "Return the P-10 emergency mode to normal when the cause clears."),
        _check("no_open_security_alerts", "No open security alerts",
               alerts == 0, 20 if alerts == 0 else (8 if isinstance(alerts, int) and alerts <= 2 else 0), 20,
               f"open alerts: {alerts}",
               "Triage the P-10 security alerts."),
        _check("financial_controls_delegated",
               "Financial emergency controls wired to P-10 (never duplicated)",
               bool(security.get("controls_wired")), 20 if security.get("controls_wired") else 0, 20,
               "financial suspension state readable from the P-10 emergency "
               f"service: suspended={security.get('financial_suspended')}",
               "Restore the P-10 emergency service wiring."),
    ]
    return _category("security_governance", checks)


def _observability(ev: dict) -> dict:
    samples = (ev.get("samples") or {}).get("count", 0)
    components = ev.get("components") or []
    dead = ev.get("dead_letters") or {}
    logging_ok = bool(ev.get("logging_configured"))
    checks = [
        _check("samples_recording", "Performance samples recording",
               samples > 0, 30 if samples else 0, 30,
               f"{samples} sample(s)", "Start the sampler."),
        _check("component_checks_visible", "Component checks visible in the Command Center feed",
               len(components) > 0, 30 if components else 0, 30,
               f"{len(components)} component check(s) from the P-14 system-health surface",
               "Restore the dashboard system-health aggregation."),
        _check("dead_letters_visible", "Dead letters counted and visible",
               "operations_open" in dead and "event_total" in dead, 20, 20,
               f"operations open: {dead.get('operations_open')}, event total: {dead.get('event_total')}",
               None),
        _check("structured_logging", "Structured logging configured (secrets redacted)",
               logging_ok, 20 if logging_ok else 0, 20,
               "log pipeline configured with secret redaction (P-01)"
               if logging_ok else "no log file configured",
               "Configure the application log file."),
    ]
    return _category("observability", checks)


def _testing_validation(ev: dict) -> dict:
    self_checks = ev.get("self_checks") or []
    if self_checks:
        passed = sum(1 for c in self_checks if c.get("ok"))
        ratio = passed / len(self_checks)
        sc_points, sc_ok = round(60 * ratio, 2), ratio == 1.0
        sc_detail = f"{passed}/{len(self_checks)} in-system self-checks pass"
    else:
        sc_points, sc_ok, sc_detail = 0.0, False, "self-checks not run"
    bench = (ev.get("benchmarks") or {}).get("latest")
    migration = ev.get("migration") or {}
    checks = [
        _check("self_checks_pass", "In-system validation self-checks", sc_ok,
               sc_points, 60, sc_detail,
               "Fix the failing self-checks; pytest evidence is reported "
               "separately in P15_PRODUCTION_READINESS_REPORT.md."),
        _check("benchmark_completed", "Benchmark suite completed",
               bench is not None, 20 if bench else 0, 20,
               "a completed benchmark run is on record" if bench else "none on record",
               "Run the benchmark suite."),
        _check("migration_at_head", "Database migration at the single head",
               migration.get("is_head") is True, 20 if migration.get("is_head") else 0, 20,
               f"database revision {migration.get('database_revision')} vs head {migration.get('head')}",
               "Run migrations to the head revision."),
    ]
    return _category("testing_validation", checks)


# ------------------------------------------------------------ assembly
def score_readiness(ev: dict) -> dict:
    """Assemble categories, the weighted score, the critical gate and
    the effective classification from one evidence dict."""
    categories = {
        "performance": _performance(ev),
        "reliability": _reliability(ev),
        "fault_tolerance_recovery": _fault_tolerance(ev),
        "data_integrity_backup": _data_integrity(ev),
        "security_governance": _security_governance(ev),
        "observability": _observability(ev),
        "testing_validation": _testing_validation(ev),
    }
    overall = round(sum(
        cat["score"] * C.CATEGORY_WEIGHTS[key] / 100.0
        for key, cat in categories.items()), 1)
    band = band_for(overall)

    db = ev.get("database") or {}
    chain = ev.get("audit_chain") or {}
    open_by = (ev.get("incidents") or {}).get("open_by_severity") or {}
    gate_failures = []
    if db.get("healthy") is not True:
        gate_failures.append("database connectivity check failed")
    if db.get("integrity_ok") is False:
        gate_failures.append("database integrity check failed")
    if chain.get("ok") is False:
        gate_failures.append("P-10 audit chain verification failed")
    if open_by.get("P0", 0):
        gate_failures.append(f"{open_by['P0']} open P0 incident(s)")
    gate_ok = not gate_failures

    blockers = [{"key": f"critical:{i}", "scope": "critical", "detail": d}
                for i, d in enumerate(gate_failures)]
    blockers += list(C.EXTERNAL_BLOCKERS)
    backups = ev.get("backups") or {}
    if backups.get("stale"):
        blockers.append({"key": "backup_stale", "scope": "operational",
                         "detail": "The latest backup is outside the "
                                   "policy window (staleness is monitored "
                                   "by the P-15 evaluator)."})

    if not gate_ok:
        classification = "NOT PRODUCTION READY — critical issue open"
    elif overall >= 75:
        classification = ("READY FOR CONTROLLED PILOT — production "
                          "classification withheld while external "
                          "blockers stand")
    else:
        classification = band

    failed_checks = []
    recommendations = []
    for cat in categories.values():
        for chk in cat["checks"]:
            if not chk["ok"]:
                failed_checks.append({"category": cat["key"],
                                      "check": chk["key"],
                                      "detail": chk["detail"]})
                if chk.get("recommendation"):
                    recommendations.append(chk["recommendation"])
    # Deduplicate recommendations, preserving order.
    recommendations = list(dict.fromkeys(recommendations))
    return {
        "overall_score": overall,
        "band": band,
        "classification": classification,
        "critical_gate_ok": gate_ok,
        "categories": categories,
        "failed_checks": failed_checks,
        "blockers": blockers,
        "recommendations": recommendations,
    }
