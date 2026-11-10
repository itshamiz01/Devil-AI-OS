"""Diagnostics: a compact self-check summary (no secrets, no raw env)."""
from __future__ import annotations

import platform
import sys


def diagnostics(settings, lifecycle_state: str, db_healthy: bool) -> dict:
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "environment": settings.environment,
        "mode": settings.mode,
        "lifecycle_state": lifecycle_state,
        "database_healthy": db_healthy,
        "database_backend": settings.effective_database_url.split(":", 1)[0],
        "queue_capacity": settings.queue_capacity,
        "max_concurrency": settings.max_concurrency,
    }
