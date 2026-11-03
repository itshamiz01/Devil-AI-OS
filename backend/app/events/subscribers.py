from __future__ import annotations

import logging

from .bus import EventBus
from .events import Event

logger = logging.getLogger(__name__)


async def log_warning(event: Event) -> None:
    logger.warning("System warning: %s", event.payload, extra={"component": "events", "correlation_id": event.correlation_id})


def register_default_subscribers(bus: EventBus) -> None:
    bus.subscribe("SystemWarning", log_warning)
    bus.subscribe("ResourceThresholdExceeded", log_warning)
