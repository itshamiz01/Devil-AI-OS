"""Lightweight in-process async event bus (P-01 §8).

Guarantees: multiple subscribers per type (plus ``*`` wildcard), failure
isolation per subscriber, correlation propagation, recursion-depth guard
and a per-second flood limit (events beyond the limit are dropped and
counted, never queued unboundedly).
"""
from __future__ import annotations

import asyncio
import collections
import contextvars
import datetime as dt
import time
from typing import Awaitable, Callable

from ..core.logging import get_logger
from .events import CRITICAL_EVENT_TYPES, Event, EventType

Handler = Callable[[Event], Awaitable[None]]
# Signature: (event, handler_name, error_text) -> None. Wired by the
# application assembly to the durable dead-letter store (DEF-I4).
DeadLetterRecorder = Callable[[Event, str, str], None]
_depth: contextvars.ContextVar[int] = contextvars.ContextVar("event_depth", default=0)
# P-14 Stage B (DEF-I2): ambient correlation id for the current unit of
# work (HTTP request, background task). The bus stamps it onto events
# whose publisher left correlation_id unset.
correlation_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "event_correlation_id", default=None)


class EventBus:
    def __init__(self, rate_limit_per_second: int = 200, max_depth: int = 3):
        self._subscribers: dict[str, list[Handler]] = collections.defaultdict(list)
        self.rate_limit = rate_limit_per_second
        self.max_depth = max_depth
        self._window_start = time.monotonic()
        self._window_count = 0
        self.dropped_count = 0
        self.subscriber_error_count = 0
        self.published_count = 0
        # P-14 Stage B (DEF-I4): failed and dropped deliveries are
        # recorded, never silently lost. ``dead_letters`` is the
        # in-process record (all events); ``dead_letter_recorder`` is
        # the optional durable sink, invoked for critical events only.
        self.dead_letter_recorder: DeadLetterRecorder | None = None
        self.dead_letters: list[dict] = []
        self._log = get_logger("events.bus")

    def _record_dead_letter(self, event: Event, handler: str, error: str) -> None:
        self.dead_letters.append({
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "handler": handler,
            "error": error,
            "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        if event.event_type in CRITICAL_EVENT_TYPES and self.dead_letter_recorder is not None:
            try:
                self.dead_letter_recorder(event, handler, error)
            except Exception:  # recording must never break publishing
                self._log.exception("dead-letter recorder failed",
                                    extra={"correlation_id": event.correlation_id})

    def subscribe(self, event_type: EventType | str, handler: Handler) -> None:
        key = event_type.value if isinstance(event_type, EventType) else event_type
        self._subscribers[key].append(handler)

    def unsubscribe_all(self) -> None:
        self._subscribers.clear()

    def _flood_check(self) -> bool:
        now = time.monotonic()
        if now - self._window_start >= 1.0:
            self._window_start = now
            self._window_count = 0
        self._window_count += 1
        return self._window_count <= self.rate_limit

    async def publish(self, event: Event) -> bool:
        """Returns False when the event was dropped (flood/depth guard)."""
        # DEF-I2: inherit the ambient correlation id when the publisher
        # did not set one explicitly.
        if event.correlation_id is None:
            event.correlation_id = correlation_context.get()
        if _depth.get() >= self.max_depth:
            self.dropped_count += 1
            event.processing_status = "dropped"
            self._record_dead_letter(event, "bus.depth_guard",
                                     "dropped: recursion depth guard")
            self._log.warning("event dropped: recursion depth guard", extra={"correlation_id": event.correlation_id})
            return False
        if not self._flood_check():
            self.dropped_count += 1
            event.processing_status = "dropped"
            self._record_dead_letter(event, "bus.flood_guard",
                                     "dropped: flood limit")
            self._log.warning("event dropped: flood limit", extra={"correlation_id": event.correlation_id})
            return False
        self.published_count += 1
        handlers = list(self._subscribers.get(event.event_type.value, [])) + list(self._subscribers.get("*", []))
        token = _depth.set(_depth.get() + 1)
        failures = 0
        try:
            for handler in handlers:
                try:
                    await handler(event)
                except Exception as exc:  # failure isolation: one bad subscriber must not break others
                    failures += 1
                    self.subscriber_error_count += 1
                    self._log.exception("event subscriber failed",
                                        extra={"correlation_id": event.correlation_id})
                    # DEF-I4: the failure is recorded with the handler
                    # identity, not merely counted.
                    self._record_dead_letter(
                        event,
                        getattr(handler, "__qualname__", None)
                        or getattr(handler, "__name__", None) or repr(handler),
                        f"{type(exc).__name__}: {exc}")
        finally:
            _depth.reset(token)
        event.processing_status = "partially_failed" if failures else "delivered"
        return True

    def publish_sync_safe(self, event: Event) -> None:
        """Fire-and-forget publish from sync code when a loop is running."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.publish(event))
