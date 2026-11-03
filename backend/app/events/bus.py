from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Awaitable, Callable

from ..core.exceptions import QueueFullError
from ..database.connection import Database
from ..database.repositories import EventRepo
from .events import Event, EVENT_TYPES

logger = logging.getLogger(__name__)
Subscriber = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self, db: Database, max_pending: int = 1000, max_subscribers: int = 32):
        self.db = db
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=max_pending)
        self.subscribers: dict[str, list[Subscriber]] = defaultdict(list)
        self.max_subscribers = max_subscribers
        self._dispatcher: asyncio.Task | None = None
        self._stopped = False

    def subscribe(self, event_type: str, callback: Subscriber) -> None:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Unknown event type: {event_type}")
        if len(self.subscribers[event_type]) >= self.max_subscribers:
            raise QueueFullError("Subscriber limit reached")
        self.subscribers[event_type].append(callback)

    async def start(self) -> None:
        self._stopped = False
        self._dispatcher = asyncio.create_task(self._dispatch(), name="event-dispatcher")

    async def publish(self, event: Event) -> None:
        if self._stopped:
            raise QueueFullError("Event bus is stopped")
        if event.event_type not in EVENT_TYPES:
            raise ValueError(f"Unknown event type: {event.event_type}")
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull as exc:
            raise QueueFullError("Event bus backpressure limit reached") from exc

    async def publish_new(self, event_type: str, source: str, payload: dict | None = None, **kwargs) -> None:
        await self.publish(Event(event_type=event_type, source=source, payload=payload or {}, **kwargs))

    async def _dispatch(self) -> None:
        while True:
            event = await self.queue.get()
            try:
                async with self.db.session_factory() as session:
                    await EventRepo(session).record(event.event_type, event.source, event.payload, event.severity, event.correlation_id, event.task_id)
                    await session.commit()
                for callback in list(self.subscribers.get(event.event_type, [])) + list(self.subscribers.get("*", [])):
                    try:
                        await asyncio.wait_for(callback(event), timeout=5.0)
                    except Exception:
                        logger.exception("Event subscriber failed", extra={"component": "events", "correlation_id": event.correlation_id})
            except Exception:
                logger.exception("Event dispatch failed", extra={"component": "events"})
            finally:
                self.queue.task_done()

    async def drain(self) -> None:
        await self.queue.join()

    async def stop(self) -> None:
        self._stopped = True
        await self.queue.join()
        if self._dispatcher:
            self._dispatcher.cancel()
            try: await self._dispatcher
            except asyncio.CancelledError: pass
