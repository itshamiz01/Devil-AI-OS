from __future__ import annotations

from collections import Counter
from threading import Lock


class Metrics:
    def __init__(self):
        self._counters: Counter[str] = Counter()
        self._lock = Lock()

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)
