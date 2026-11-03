from __future__ import annotations

import os
from pathlib import Path

import psutil

from ..core.config import Settings


class SystemMonitor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.process = psutil.Process(os.getpid())
        psutil.cpu_percent(interval=None)

    def snapshot(self) -> dict:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(self.settings.data_dir))
        cpu = psutil.cpu_percent(interval=None)
        return {
            "cpu_percent": cpu,
            "memory_percent": memory.percent,
            "memory_available_bytes": memory.available,
            "memory_total_bytes": memory.total,
            "disk_percent": disk.percent,
            "disk_free_bytes": disk.free,
            "disk_total_bytes": disk.total,
            "process_rss_bytes": self.process.memory_info().rss,
            "process_threads": self.process.num_threads(),
            "thresholds": {
                "memory_percent_max": self.settings.memory_percent_max,
                "disk_percent_max": self.settings.disk_percent_max,
                "cpu_percent_max": self.settings.cpu_percent_max,
            },
        }

    def resource_pressure(self) -> list[str]:
        s = self.snapshot()
        reasons = []
        if s["memory_percent"] >= self.settings.memory_percent_max:
            reasons.append("memory")
        if s["disk_percent"] >= self.settings.disk_percent_max:
            reasons.append("disk")
        return reasons

    def admission_allowed(self, essential: bool) -> bool:
        return essential or not self.resource_pressure()
