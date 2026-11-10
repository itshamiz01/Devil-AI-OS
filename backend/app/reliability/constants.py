"""P-15 Performance, Reliability & Production Readiness Engine.

Reliability *infrastructure* over the existing engines — P-15 owns
no queue, scheduler, circuit breaker, backup system or ledger. It
observes the P-01 monitor/queue, P-12 breakers and recovery, P-10
backups/emergency/audit chain and P-07 ledger integrity; records
history, incidents and readiness evidence; and surfaces all of it
in the Command Center. Control stays with the owning engines and
with P-10 governance.
"""
from __future__ import annotations

SETTINGS_KEY = "p15_reliability_settings"

DEFAULT_SETTINGS = {
    # Sampler cadence for the long-duration harness (§11.5). The loop
    # only runs outside the test environment, beside the P-12 loop.
    "sample_interval_seconds": 30,
    # A newest verified backup older than this raises an incident.
    "backup_max_age_hours": 168,
    # A task RUNNING longer than this counts as stuck (§11.5).
    "stuck_task_minutes": 120,
    # Benchmark medians may drift to this multiple of the P-14
    # baseline before the performance category docks them.
    "benchmark_tolerance_multiplier": 2.0,
    # §11.5 long-duration targets (hours). Reported INCOMPLETE until
    # real sample coverage spans them — never back-filled.
    "long_duration_targets_hours": [24, 72, 168],
}

# §13 category weights (must total 100).
CATEGORY_WEIGHTS = {
    "performance": 15,
    "reliability": 20,
    "fault_tolerance_recovery": 15,
    "data_integrity_backup": 15,
    "security_governance": 15,
    "observability": 10,
    "testing_validation": 10,
}

# §13 readiness bands: (minimum score, band name).
READINESS_BANDS = [
    (90, "Production-ready candidate"),
    (75, "Limited production candidate"),
    (60, "Controlled testing"),
    (40, "Development"),
    (0, "Unstable"),
]

SEVERITIES = ("P0", "P1", "P2", "P3")
INCIDENT_STATUSES = ("open", "acknowledged", "resolved")

# Task priority classes (§4.2). P-15 does not schedule; it classifies
# and reports admission state against the existing P-01 substrate.
PRIORITY_CLASSES = {
    1: "critical — security, financial integrity, emergency, data consistency",
    2: "high — approved business execution, time-sensitive, scheduled financial",
    3: "normal — standard agent activity, analysis, routine automation, reporting",
    4: "background — research, enrichment, memory indexing, historical analytics",
}

# P-14 volume-baseline medians (ms), docs/p14/P14_BENCHMARK_RESULTS.json.
# The P-15 performance category compares its own measured medians
# against these — thresholds from the actual baseline (§18), never
# invented speed targets.
P14_BASELINE_MS = {
    "dashboard_overview": 32.61,
    "dashboard_system_health": 8.27,
    "financial_consolidated": 23.61,
    "memory_search": 147.45,
    "journal_page_query_50": 1.17,
}

# Standing external blockers (P-14 register DEF-A1/A2). They are not
# code defects and cannot be closed from staging; while either
# stands, the effective classification is capped at controlled pilot.
EXTERNAL_BLOCKERS = [
    {"key": "windows_unverified", "scope": "external",
     "detail": "Windows 10/11 operation is UNVERIFIED from this Linux "
               "staging (P-14 DEF-A1) — an owner-machine item."},
    {"key": "real_llm_unexercised", "scope": "external",
     "detail": "No real LLM provider has ever been exercised "
               "(P-14 DEF-A2) — model panels report probe truth only."},
]
