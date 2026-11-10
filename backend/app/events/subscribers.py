"""Built-in event subscribers: persistence of critical events (P-01 §8).

Critical events are written to ``system_events`` independently of ordinary
in-memory delivery, so a failing in-memory subscriber cannot lose them.
"""
from __future__ import annotations

from ..database.models.base import utcnow
from ..database.models.core import EventDeadLetter, SystemEvent
from ..database.repositories.core import SystemEventRepository
from .bus import EventBus
from .events import CRITICAL_EVENT_TYPES, Event


def make_persistence_subscriber(session_factory):
    async def _persist(event: Event) -> None:
        if event.event_type not in CRITICAL_EVENT_TYPES:
            return
        session = session_factory()
        try:
            repo = SystemEventRepository(session)
            if session.query(SystemEvent).filter_by(event_id=event.event_id).first():
                return
            repo.add(SystemEvent(
                event_id=event.event_id,
                event_type=event.event_type.value,
                source=event.source,
                correlation_id=event.correlation_id,
                task_id=event.task_id,
                severity=event.severity,
                payload=event.payload,
                created_at=utcnow(),
                business_id=event.business_id,
                workflow_id=event.workflow_id,
                processing_status=event.processing_status,
            ))
        finally:
            session.close()

    return _persist


def make_dead_letter_recorder(session_factory):
    """Durable sink for the bus's dead-letter hook (DEF-I4): one row
    per failed/dropped delivery of a critical event."""
    def _record(event: Event, handler: str, error: str) -> None:
        session = session_factory()
        try:
            session.add(EventDeadLetter(
                event_id=event.event_id,
                event_type=event.event_type.value,
                handler=handler,
                error=error,
                payload=event.payload,
            ))
            session.commit()
        finally:
            session.close()

    return _record


def register_persistence(bus: EventBus, session_factory) -> None:
    bus.subscribe("*", make_persistence_subscriber(session_factory))
    bus.dead_letter_recorder = make_dead_letter_recorder(session_factory)
