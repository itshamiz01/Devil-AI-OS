"""Resource metrics via psutil (P-01 §10). Lightweight, on-demand reads."""
from __future__ import annotations

import psutil


def resource_snapshot(disk_path: str = "/") -> dict:
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(disk_path)
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_percent": vm.percent,
        "memory_available_mb": round(vm.available / (1024 * 1024), 1),
        "memory_total_mb": round(vm.total / (1024 * 1024), 1),
        "disk_percent": disk.percent,
        "disk_free_gb": round(disk.free / (1024 ** 3), 2),
        "disk_total_gb": round(disk.total / (1024 ** 3), 2),
        "process_count": len(psutil.pids()),
    }
