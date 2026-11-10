"""System monitor: resources + DB health + queue stats + thresholds (§10)."""
from __future__ import annotations

from ..core.config import Settings
from ..database.connection import check_database
from .metrics import resource_snapshot


class SystemMonitor:
    def __init__(self, settings: Settings, engine, queue_stats=None):
        self.settings = settings
        self.engine = engine
        self.queue_stats = queue_stats
        # P-14 Stage B (DEF-A5): optional provider-probe feed, wired by
        # the application assembly to the intelligence service's cached
        # probe result. Never triggers a probe itself.
        self.provider_probe = None

    def resources(self) -> dict:
        try:
            disk_path = str(self.settings.data_dir.resolve())
        except Exception:
            disk_path = "/"
        return resource_snapshot(disk_path)

    def database_healthy(self) -> bool:
        return check_database(self.engine)

    def threshold_violations(self, resources: dict | None = None) -> list[dict]:
        r = resources or self.resources()
        violations = []
        checks = [
            ("cpu", r.get("cpu_percent", 0), self.settings.cpu_threshold_percent),
            ("memory", r.get("memory_percent", 0), self.settings.memory_threshold_percent),
            ("disk", r.get("disk_percent", 0), self.settings.disk_threshold_percent),
        ]
        for name, value, threshold in checks:
            if value >= threshold:
                violations.append({"resource": name, "value": value, "threshold": threshold})
        return violations

    def admission_block_reason(self) -> str | None:
        """Used by the task manager to block NONESSENTIAL admissions (§10.2)."""
        if not self.settings.block_nonessential_on_threshold:
            return None
        violations = self.threshold_violations()
        if violations:
            names = ", ".join(v["resource"] for v in violations)
            return f"resource threshold exceeded: {names}"
        return None

    def status(self, lifecycle_state: str) -> dict:
        resources = self.resources()
        queue = self.queue_stats.snapshot() if self.queue_stats else None
        result = {
            "lifecycle_state": lifecycle_state,
            "database_healthy": self.database_healthy(),
            "resources": resources,
            "threshold_violations": self.threshold_violations(resources),
            "queue": queue,
        }
        if self.provider_probe is not None:
            try:
                result["ai_providers"] = self.provider_probe()
            except Exception:
                result["ai_providers"] = None
        return result
