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


def register_task_approval_subscribers(bus: EventBus, task_manager) -> None:
    """Release or close approval-gated tasks when a decision is recorded.

    Kept separate from register_default_subscribers because it needs the task
    manager, which does not exist yet when the default subscribers are attached.
    """
    bus.subscribe("ApprovalGranted", task_manager.on_approval_granted)
    bus.subscribe("ApprovalRejected", task_manager.on_approval_rejected)
