"""Bounded queue accounting (P-01 §7.3).

The durable queue is the ``tasks`` table (statuses queued/retry_pending);
this helper enforces capacity/backpressure and reports ordering stats.
Ordering itself (priority desc, FIFO within equal priority) is applied by
``TaskRepository.due_tasks``.
"""
from __future__ import annotations

from ..database.repositories.core import TaskRepository

ACTIVE_STATUSES = ("queued", "retry_pending", "validating", "waiting_for_approval")


class QueueStats:
    def __init__(self, session_factory, capacity: int):
        self._session_factory = session_factory
        self.capacity = capacity

    def depth(self) -> int:
        session = self._session_factory()
        try:
            repo = TaskRepository(session)
            return sum(repo.count_by_status(s) for s in ACTIVE_STATUSES)
        finally:
            session.close()

    def running(self) -> int:
        session = self._session_factory()
        try:
            return TaskRepository(session).count_by_status("running")
        finally:
            session.close()

    def has_capacity(self) -> bool:
        return self.depth() < self.capacity

    def snapshot(self) -> dict:
        session = self._session_factory()
        try:
            repo = TaskRepository(session)
            by_status = {}
            for status in ("created", "validating", "queued", "running", "completed", "failed",
                           "cancelled", "paused", "waiting_for_approval", "retry_pending"):
                count = repo.count_by_status(status)
                if count:
                    by_status[status] = count
            return {"capacity": self.capacity, "depth": self.depth(),
                    "running": by_status.get("running", 0), "by_status": by_status}
        finally:
            session.close()
