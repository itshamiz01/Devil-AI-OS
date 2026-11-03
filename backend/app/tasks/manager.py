from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from ..core.config import Settings
from ..core.exceptions import ConflictError, InvalidTransitionError, QueueFullError, ResourceProtectedError, NotFoundError
from ..database.connection import Database
from ..database.models import Task, utcnow
from ..database.repositories import AuditRepo, ExecutionRepo, TaskRepo
from ..events.bus import EventBus
from .handlers import HANDLERS, ExecutionContext, HandlerError, validate_payload
from .models import ALLOWED_TRANSITIONS, TaskState, TaskSubmitRequest
from .queue import BoundedPriorityQueue
from .scheduler import RetryScheduler

logger = logging.getLogger(__name__)
TERMINAL = {TaskState.COMPLETED, TaskState.CANCELLED}


class TaskManager:
    def __init__(self, settings: Settings, db: Database, bus: EventBus, monitor):
        self.settings = settings
        self.db = db
        self.bus = bus
        self.monitor = monitor
        self.queue = BoundedPriorityQueue(settings.task_queue_capacity)
        self.accepting = False
        self._workers: list[asyncio.Task] = []
        self._running: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()
        self.scheduler = RetryScheduler(self, settings.scheduler_poll_interval)
        self.worker_id = str(uuid4())

    async def start(self) -> None:
        await self.recover_interrupted()
        self.accepting = True
        self._workers = [asyncio.create_task(self._worker(i), name=f"task-worker-{i}") for i in range(self.settings.task_max_concurrency)]
        await self.scheduler.start()

    async def _transition(self, task: Task, new_state: TaskState) -> None:
        current = TaskState(task.status)
        if new_state not in ALLOWED_TRANSITIONS[current]:
            raise InvalidTransitionError(f"Invalid task transition {current.value} -> {new_state.value}")
        task.status = new_state.value
        task.updated_at = utcnow()
        if new_state == TaskState.RUNNING and task.started_at is None:
            task.started_at = utcnow()
        if new_state in TERMINAL or new_state == TaskState.FAILED:
            task.completed_at = utcnow()

    async def submit(self, principal_id: str, request: TaskSubmitRequest, correlation_id: str | None = None) -> Task:
        if not self.accepting:
            raise ConflictError("Task manager is not accepting submissions")
        handler = HANDLERS[request.handler]
        payload = validate_payload(request.handler, request.payload)
        pressure = self.monitor.resource_pressure()
        if pressure and not handler.essential:
            await self.bus.publish_new("ResourceThresholdExceeded", "monitoring", {"reasons": pressure}, severity="warning", correlation_id=correlation_id)
            raise ResourceProtectedError("Resource thresholds prevent nonessential task admission")
        async with self._lock:
            async with self.db.session_factory() as session:
                repo = TaskRepo(session)
                if request.idempotency_key:
                    existing = await repo.by_idempotency(request.idempotency_key)
                    if existing:
                        if existing.payload != payload or existing.handler != request.handler:
                            raise ConflictError("Idempotency key reused with different payload")
                        return existing
                if await repo.count_active() >= self.settings.task_queue_capacity:
                    raise QueueFullError("Task queue capacity reached")
                task = await repo.create(
                    name=request.name, description=request.description, category="system", handler=request.handler,
                    priority=request.priority, status=TaskState.CREATED.value, creator_id=principal_id,
                    idempotency_key=request.idempotency_key, payload=payload, max_retries=request.max_retries,
                    timeout_seconds=request.timeout_seconds, deadline=request.deadline,
                    approval_required=request.approval_required, essential=handler.essential,
                )
                await self._transition(task, TaskState.VALIDATING)
                if request.approval_required:
                    await self._transition(task, TaskState.WAITING_FOR_APPROVAL)
                else:
                    await self._transition(task, TaskState.QUEUED)
                await AuditRepo(session).record("task.created", "allowed", principal_id=principal_id, resource=task.id, action="submit", correlation_id=correlation_id, payload={"handler": request.handler})
                await session.commit()
                task_id = task.id
                priority = task.priority
                status = task.status
        await self.bus.publish_new("TaskCreated", "tasks", {"handler": request.handler}, task_id=task_id, correlation_id=correlation_id)
        if status == TaskState.QUEUED.value:
            self.queue.put_nowait(priority, task_id)
            await self.bus.publish_new("TaskQueued", "tasks", {}, task_id=task_id, correlation_id=correlation_id)
        async with self.db.session_factory() as session:
            return await TaskRepo(session).get(task_id)

    async def _worker(self, index: int) -> None:
        while self.accepting:
            item = await self.queue.get()
            try:
                await self._execute(item.task_id)
            except Exception:
                logger.exception("Worker failed", extra={"component": "tasks", "task_id": item.task_id})
            finally:
                self.queue.task_done()

    async def _execute(self, task_id: str) -> None:
        async with self.db.session_factory() as session:
            repo = TaskRepo(session)
            task = await repo.get(task_id)
            if not task or task.status != TaskState.QUEUED.value:
                return
            await self._transition(task, TaskState.RUNNING)
            execution = await ExecutionRepo(session).create(task.id, task.retry_count + 1, self.worker_id)
            await session.commit()
            handler_name = task.handler
            payload = dict(task.payload)
            timeout = task.timeout_seconds
            execution_id = execution.id
        cancellation = asyncio.Event()
        self._running[task_id] = cancellation
        await self.bus.publish_new("TaskStarted", "tasks", {}, task_id=task_id)
        error = None
        result = None
        cancelled = False
        try:
            handler = HANDLERS[handler_name]
            validated = handler.payload_model.model_validate(payload)
            result = await asyncio.wait_for(handler.execute(validated, ExecutionContext(task_id, cancellation)), timeout=timeout)
        except asyncio.CancelledError:
            cancelled = True
            error = {"code": "CANCELLED", "message": "Task cancellation requested"}
        except asyncio.TimeoutError:
            error = {"code": "TIMEOUT", "message": "Task execution timed out", "retryable": True}
        except HandlerError as exc:
            error = {"code": "HANDLER_ERROR", "message": str(exc), "retryable": exc.retryable}
        except Exception as exc:
            logger.exception("Unexpected handler failure", extra={"component": "tasks", "task_id": task_id})
            error = {"code": "UNEXPECTED_ERROR", "message": "Handler failed", "retryable": False}
        finally:
            self._running.pop(task_id, None)
        async with self.db.session_factory() as session:
            repo = TaskRepo(session)
            task = await repo.get(task_id)
            if not task:
                return
            if cancelled or task.cancellation_requested:
                await self._transition(task, TaskState.CANCELLED)
                await ExecutionRepo(session).finish(execution_id, "CANCELLED", error)
                await self.bus.publish_new("TaskCancelled", "tasks", {}, task_id=task_id)
            elif error:
                retryable = bool(error.get("retryable")) and HANDLERS[handler_name].retryable
                if retryable and task.retry_count < task.max_retries:
                    task.retry_count += 1
                    delay = min(self.settings.retry_max_delay, self.settings.retry_base_delay * (2 ** (task.retry_count - 1)))
                    task.next_retry_at = utcnow() + timedelta(seconds=delay)
                    await self._transition(task, TaskState.RETRY_PENDING)
                    await ExecutionRepo(session).finish(execution_id, "RETRY_PENDING", error)
                else:
                    task.error_details = error
                    await self._transition(task, TaskState.FAILED)
                    await ExecutionRepo(session).finish(execution_id, "FAILED", error)
                    await self.bus.publish_new("TaskFailed", "tasks", error, task_id=task_id, severity="error")
            else:
                task.result = result
                task.error_details = None
                await self._transition(task, TaskState.COMPLETED)
                await ExecutionRepo(session).finish(execution_id, "COMPLETED", None)
                await self.bus.publish_new("TaskCompleted", "tasks", result or {}, task_id=task_id)
            task.error_details = error if error and task.status == TaskState.FAILED.value else task.error_details
            await session.commit()

    async def cancel(self, principal_id: str, task_id: str, correlation_id: str | None = None) -> Task:
        async with self.db.session_factory() as session:
            task = await TaskRepo(session).get(task_id)
            if not task:
                raise NotFoundError("Task not found")
            state = TaskState(task.status)
            if state in TERMINAL or state == TaskState.FAILED:
                raise ConflictError(f"Cannot cancel task in state {state.value}")
            if state == TaskState.RUNNING:
                task.cancellation_requested = True
                event = self._running.get(task_id)
                if event: event.set()
            else:
                await self._transition(task, TaskState.CANCELLED)
            await AuditRepo(session).record("task.cancelled", "allowed", principal_id=principal_id, resource=task_id, action="cancel", correlation_id=correlation_id)
            await session.commit()
        await self.bus.publish_new("TaskCancelled", "tasks", {}, task_id=task_id, correlation_id=correlation_id)
        return await self.get(task_id)

    async def pause(self, principal_id: str, task_id: str) -> Task:
        async with self.db.session_factory() as session:
            task = await TaskRepo(session).get(task_id)
            if not task: raise NotFoundError("Task not found")
            if TaskState(task.status) not in {TaskState.QUEUED, TaskState.RETRY_PENDING}:
                raise ConflictError("Only queued or retry-pending tasks can be paused")
            await self._transition(task, TaskState.PAUSED)
            await AuditRepo(session).record("task.paused", "allowed", principal_id=principal_id, resource=task_id, action="pause")
            await session.commit()
        return await self.get(task_id)

    async def resume(self, principal_id: str, task_id: str) -> Task:
        async with self.db.session_factory() as session:
            task = await TaskRepo(session).get(task_id)
            if not task: raise NotFoundError("Task not found")
            if TaskState(task.status) != TaskState.PAUSED:
                raise ConflictError("Only paused tasks can be resumed")
            await self._transition(task, TaskState.QUEUED)
            await AuditRepo(session).record("task.resumed", "allowed", principal_id=principal_id, resource=task_id, action="resume")
            await session.commit()
            priority, tid = task.priority, task.id
        self.queue.put_nowait(priority, tid)
        return await self.get(task_id)

    async def retry(self, principal_id: str, task_id: str) -> Task:
        async with self.db.session_factory() as session:
            task = await TaskRepo(session).get(task_id)
            if not task: raise NotFoundError("Task not found")
            if TaskState(task.status) != TaskState.FAILED:
                raise ConflictError("Only failed tasks can be retried")
            if task.retry_count >= task.max_retries:
                raise ConflictError("Maximum retries exceeded")
            task.error_details = None
            task.completed_at = None
            await self._transition(task, TaskState.QUEUED)
            await AuditRepo(session).record("task.retried", "allowed", principal_id=principal_id, resource=task_id, action="retry")
            await session.commit()
            priority, tid = task.priority, task.id
        self.queue.put_nowait(priority, tid)
        return await self.get(task_id)

    async def get(self, task_id: str) -> Task:
        async with self.db.session_factory() as session:
            task = await TaskRepo(session).get(task_id)
            if not task: raise NotFoundError("Task not found")
            return task

    async def promote_due_retries(self) -> None:
        async with self.db.session_factory() as session:
            due = await TaskRepo(session).due_retries()
            promoted = []
            for task in due:
                await self._transition(task, TaskState.QUEUED)
                promoted.append((task.priority, task.id))
            await session.commit()
        for priority, task_id in promoted:
            self.queue.put_nowait(priority, task_id)

    async def recover_interrupted(self) -> None:
        async with self.db.session_factory() as session:
            repo = TaskRepo(session)
            interrupted = await repo.by_status([TaskState.RUNNING.value, TaskState.VALIDATING.value])
            for task in interrupted:
                task.status = TaskState.FAILED.value
                task.error_details = {"code": "INTERRUPTED", "message": "Application restarted before task completed", "retryable": True}
                task.completed_at = utcnow()
                await AuditRepo(session).record("task.interrupted", "recovery", resource=task.id, action="recover")
            queued = await repo.by_status([TaskState.QUEUED.value])
            await session.commit()
            items = [(t.priority, t.id) for t in queued]
        for priority, task_id in items:
            self.queue.put_nowait(priority, task_id)
        await self.promote_due_retries()

    async def health(self) -> dict:
        async with self.db.session_factory() as session:
            active = await TaskRepo(session).count_active()
        return {"accepting": self.accepting, "queue_size": self.queue.qsize(), "active_tasks": active, "running_tasks": len(self._running), "workers": len(self._workers)}

    async def shutdown(self) -> None:
        self.accepting = False
        await self.scheduler.stop()
        for event in self._running.values():
            event.set()
        if self._workers:
            done, pending = await asyncio.wait(self._workers, timeout=self.settings.shutdown_timeout)
            if pending:
                async with self.db.session_factory() as session:
                    running = await TaskRepo(session).by_status([TaskState.RUNNING.value])
                    for task in running:
                        task.status = TaskState.FAILED.value
                        task.error_details = {"code": "INTERRUPTED", "message": "Shutdown timeout", "retryable": True}
                        task.completed_at = utcnow()
                    await session.commit()
                for worker in pending:
                    worker.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
        self._workers.clear()
