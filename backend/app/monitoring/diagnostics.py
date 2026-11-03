from __future__ import annotations

from ..core.config import Settings


def safe_diagnostics(settings: Settings) -> dict:
    return {
        "environment": settings.environment,
        "host": settings.host,
        "port": settings.port,
        "external_execution_enabled": settings.external_execution_enabled,
        "financial_execution_enabled": settings.financial_execution_enabled,
        "cloud_ai_enabled": settings.cloud_ai_enabled,
        "task_queue_capacity": settings.task_queue_capacity,
        "task_max_concurrency": settings.task_max_concurrency,
    }
