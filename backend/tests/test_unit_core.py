import asyncio

import pytest

from app.core.logging import redact
from app.tasks.models import ALLOWED_TRANSITIONS, TaskState
from app.tasks.queue import BoundedPriorityQueue
from app.core.exceptions import QueueFullError


def test_redaction():
    text = 'password=supersecret token: abc123 Authorization: Bearer xyz'
    out = redact(text)
    assert 'supersecret' not in out
    assert 'abc123' not in out
    assert 'xyz' not in out


def test_state_machine_terminal():
    assert TaskState.RUNNING not in ALLOWED_TRANSITIONS[TaskState.COMPLETED]
    assert TaskState.COMPLETED not in ALLOWED_TRANSITIONS[TaskState.CANCELLED]
    assert TaskState.QUEUED in ALLOWED_TRANSITIONS[TaskState.FAILED]


def test_priority_queue_order():
    async def run():
        q = BoundedPriorityQueue(10)
        q.put_nowait(5, "low")
        q.put_nowait(1, "high")
        q.put_nowait(1, "high2")
        assert (await q.get()).task_id == "high"
        assert (await q.get()).task_id == "high2"
        assert (await q.get()).task_id == "low"
    asyncio.run(run())


def test_priority_queue_capacity():
    async def run():
        q = BoundedPriorityQueue(1)
        q.put_nowait(1, "a")
        with pytest.raises(asyncio.QueueFull):
            q.put_nowait(1, "b")
    asyncio.run(run())
