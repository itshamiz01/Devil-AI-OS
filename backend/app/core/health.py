"""Health semantics (P-01 §10.1): liveness vs readiness vs degraded."""
from __future__ import annotations


def liveness(lifecycle_state: str) -> dict:
    return {"status": "alive", "lifecycle_state": lifecycle_state}


def readiness(lifecycle_state: str, db_healthy: bool, threshold_violations: list) -> tuple[dict, bool]:
    ready_states = ("ready", "degraded")
    is_ready = lifecycle_state in ready_states and db_healthy
    status = "ready" if is_ready and not threshold_violations else (
        "degraded" if is_ready else "not_ready")
    return {
        "status": status,
        "lifecycle_state": lifecycle_state,
        "database_healthy": db_healthy,
        "threshold_violations": threshold_violations,
    }, is_ready
