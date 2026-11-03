from __future__ import annotations

import asyncio
import itertools
from dataclasses import dataclass, field


@dataclass(order=True)
class QueueItem:
    priority: int
    sequence: int
    task_id: str = field(compare=False)


class BoundedPriorityQueue:
    def __init__(self, capacity: int):
        self._queue: asyncio.PriorityQueue[QueueItem] = asyncio.PriorityQueue(maxsize=capacity)
        self._counter = itertools.count()

    def put_nowait(self, priority: int, task_id: str) -> None:
        self._queue.put_nowait(QueueItem(priority, next(self._counter), task_id))

    async def get(self) -> QueueItem:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    def qsize(self) -> int:
        return self._queue.qsize()

    def full(self) -> bool:
        return self._queue.full()
