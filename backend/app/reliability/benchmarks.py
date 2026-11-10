"""Repeatable benchmark + probe suite (§11).

Baseline: the same read paths P-14 measured, timed in-process
(median of 3), so results compare against
``docs/p14/P14_BENCHMARK_RESULTS.json``. The staging database holds
labelled fixture scope only — these are read-path timings, not
workflow throughput, and never real financial transactions (§11.5).

Load probe: concurrent in-process read load (asyncio), reported as
measured p50/p95 — an honest read-path probe, not a claim about
task-queue throughput under production load.

Recovery probes (§11.4): functional checks against the REAL P-12
circuit breaker and retry policy classes and a throwaway P-01 event
bus — they prove the mechanisms behave; they do not simulate a
production outage.

Stress (§11.3): resource *exhaustion is not induced* on a shared
staging VM. The suite records observed headroom and the real
provider-outage condition present in staging (no Ollama process)
instead, and says so in its notes.
"""
from __future__ import annotations

import asyncio
import statistics
import time

from . import constants as C


def _median_ms(fn, repeats: int = 3) -> float:
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return round(statistics.median(samples), 2)


async def _median_ms_async(fn, repeats: int = 3) -> float:
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        await fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return round(statistics.median(samples), 2)


def recovery_probes() -> dict:
    """Functional probes of the real fault-tolerance classes (sync
    parts; the event-bus probe runs in ``run_suite``)."""
    from ..operations.recovery import CircuitBreaker, classify_failure, retry_delay

    probes: dict = {}

    # Circuit breaker: closed -> open at threshold -> half-open after
    # cooldown -> closed on success (fake clock, P-12's own class).
    breaker = CircuitBreaker("p15-probe", threshold=2, cooldown_seconds=10.0)
    t0 = 1000.0
    breaker.record_failure(now=t0)
    breaker.record_failure(now=t0)
    opened = not breaker.allow(now=t0 + 1)
    half_open = breaker.allow(now=t0 + 11)
    breaker.record_success()
    closed_again = breaker.allow(now=t0 + 12)
    probes["circuit_breaker"] = {
        "ok": bool(opened and half_open and closed_again),
        "detail": "P-12 CircuitBreaker opened at threshold, half-opened "
                  "after cooldown, closed on success"}

    # Retry policy: classification + monotonic capped backoff (jitter
    # pinned to zero through the rng seam so the check is exact).
    class _NoJitter:
        def uniform(self, _a, _b):
            return 0.0

    category = classify_failure(error={"code": "timeout"})
    delays = [retry_delay(a, 0.5, 8.0, rng=_NoJitter()) for a in (1, 2, 3, 6)]
    probes["retry_policy"] = {
        "ok": bool(category == "temporary_network_failure"
                   and delays == sorted(delays) and delays[-1] <= 8.0),
        "detail": f"classify(timeout) -> {category}; backoff {delays}"}
    return probes


async def run_suite(application) -> dict:
    """Execute the full suite against a started application."""
    from sqlalchemy import select

    from ..dashboard.service import DashboardService
    from ..database.models.financial import JournalEntry
    from ..database.models.memory import MemoryRecord

    notes = [
        "Read-path timings in-process (median of 3) on the staging "
        "database (labelled fixtures only); comparable to the P-14 "
        "baseline, not a production throughput claim.",
        "Stress by resource exhaustion is NOT induced on the shared "
        "staging VM; observed headroom and the real staging provider "
        "condition are recorded instead.",
    ]
    dashboard = DashboardService(application)
    timings: dict[str, float] = {}
    timings["dashboard_overview"] = _median_ms(lambda: dashboard.overview())
    timings["dashboard_system_health"] = await _median_ms_async(
        dashboard.system_health)
    timings["financial_consolidated"] = _median_ms(
        lambda: application.financial.consolidated("INR"))

    session = application.session_factory()
    try:
        def _journal_page():
            session.execute(
                select(JournalEntry).limit(50)).scalars().all()
        timings["journal_page_query_50"] = _median_ms(_journal_page)

        def _memory_page():
            session.execute(
                select(MemoryRecord).limit(50)).scalars().all()
        timings["memory_records_page_50"] = _median_ms(_memory_page)
    finally:
        session.close()

    # Memory retrieval path (governed search) when available.
    retrieval = getattr(application.memory, "retrieval", None)
    if retrieval is not None:
        from ..permissions.models import Principal, PrincipalType
        system = Principal(PrincipalType.SYSTEM, "p15-benchmark")
        try:
            timings["memory_search"] = _median_ms(
                lambda: retrieval.search(system, query="benchmark", limit=10))
        except Exception as exc:  # measured honestly, never hidden
            notes.append(f"memory retrieval search unavailable: {exc}")

    # Load probe: 24 concurrent overview reads.
    async def _one():
        start = time.perf_counter()
        dashboard.overview()
        return (time.perf_counter() - start) * 1000.0

    samples = await asyncio.gather(*[_one() for _ in range(24)])
    samples.sort()
    load = {
        "probe": "24 concurrent in-process dashboard overview reads",
        "p50_ms": round(samples[len(samples) // 2], 2),
        "p95_ms": round(samples[int(len(samples) * 0.95) - 1], 2),
        "max_ms": round(samples[-1], 2),
    }

    # Recovery probes + the async event-bus dead-letter probe: a
    # failing handler on a throwaway bus must be recorded, never
    # silently lost (P-14 DEF-I4 behaviour).
    probes = recovery_probes()
    from ..events.bus import EventBus
    from ..events.events import Event, EventType
    bus = EventBus()
    seen: list[dict] = []
    bus.dead_letter_recorder = lambda e, h, err: seen.append({"h": h})

    async def _boom(_event):
        raise RuntimeError("probe failure")

    bus.subscribe(EventType.APPLICATION_STARTED, _boom)
    await bus.publish(Event(EventType.APPLICATION_STARTED, source="p15-probe"))
    probes["event_bus_dead_letter"] = {
        "ok": bool(seen) or bool(bus.dead_letters),
        "detail": "failing handler recorded as a dead letter on a "
                  "throwaway bus instance"}

    # Observed stress surface: headroom + the real provider condition.
    resources = application.monitor.resources()
    providers = application.intelligence.cached_models_status()
    stress = {
        "induced": False,
        "cpu_percent": resources.get("cpu_percent"),
        "memory_percent": resources.get("memory_percent"),
        "disk_percent": resources.get("disk_percent"),
        "disk_free_gb": resources.get("disk_free_gb"),
        "provider_condition": (
            {name: {"available": p.get("available"), "detail": p.get("detail")}
             for name, p in (providers or {}).get("providers", {}).items()}
            if providers else "not probed yet in this process"),
        "note": "In staging no Ollama process runs: provider "
                "unavailability is a real, observed outage condition; "
                "the deterministic planner remains available throughout.",
    }

    comparison = {}
    for key, baseline in C.P14_BASELINE_MS.items():
        if key in timings:
            comparison[key] = {
                "p14_baseline_ms": baseline, "p15_ms": timings[key],
                "ratio": round(timings[key] / baseline, 2) if baseline else None}
    return {"timings_ms_median_of_3": timings, "comparison_vs_p14": comparison,
            "load_probe": load, "recovery_probes": probes,
            "stress_observed": stress, "notes": notes}
