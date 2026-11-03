from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class RetryScheduler:
    def __init__(self, manager, poll_interval: float):
        self.manager = manager
        self.poll_interval = poll_interval
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="retry-scheduler")

    async def _run(self) -> None:
        while self.manager.accepting:
            try:
                await self.manager.promote_due_retries()
                await self.manager.expire_stale_approvals()
            except Exception:
                logger.exception("Retry scheduler tick failed", extra={"component": "tasks"})
            await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass
