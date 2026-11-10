"""Universal Task Management engine (P-01 §7).

Persistence-first design: the ``tasks`` table IS the bounded queue
(priority-ordered, FIFO within priority). A single async worker loop claims
due tasks up to the configured concurrency, executes them ONLY through the
handler registry, applies retry/backoff, and records every attempt in
``task_executions``. Startup recovery marks RUNNING tasks as interrupted
(-> PAUSED with ``recovery_required``) and never blindly re-executes them.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import time

from ..core.exceptions import (
    InvalidStateTransitionError, NotFoundError, PermissionDeniedError,
    QueueFullError, ResourceBlockedError,
)
from ..core.logging import get_logger
from ..database.models.base import utcnow
from ..database.models.core import Task, TaskExecution
from ..database.repositories.core import AgentRepository, TaskRepository
from ..events.bus import EventBus
from ..events.events import Event, EventType
from ..permissions.engine import PermissionEngine
from ..permissions.models import Permission, Principal
from .handlers import HandlerRegistry
from .models import ErrorKind, TaskExecutionError, TaskStatus, validate_transition
from .queue import QueueStats
from .scheduler import backoff_delay, classify_exception, is_retryable


class TaskManager:
    def __init__(self, session_factory, bus: EventBus, permissions: PermissionEngine,
                 registry: HandlerRegistry | None = None, capacity: int = 100,
                 max_concurrency: int = 4, retry_base_delay: float = 0.5,
                 retry_max_delay: float = 30.0, admission_guard=None, monitor=None):
        self._session_factory = session_factory
        self._bus = bus
        self._permissions = permissions
        self.registry = registry or HandlerRegistry()
        self.queue = QueueStats(session_factory, capacity)
        self.max_concurrency = max_concurrency
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay
        self._admission_guard = admission_guard  # callable(task)->str|None (block reason)
        self._monitor = monitor
        self._accepting = True
        self._worker_task: asyncio.Task | None = None
        self._running: set[asyncio.Task] = set()
        self._log = get_logger("tasks.manager")

    # ------------------------------------------------------------------ util
    def _repo(self):
        session = self._session_factory()
        return session, TaskRepository(session)

    def transition(self, task: Task, target: TaskStatus, repo: TaskRepository) -> Task:
        current = TaskStatus(task.status)
        if not validate_transition(current, target):
            raise InvalidStateTransitionError(
                f"invalid task transition {current.value} -> {target.value}",
                details={"task_id": task.id, "from": current.value, "to": target.value})
        task.status = target.value
        return repo.save(task)

    async def _emit(self, event_type: EventType, task: Task, payload: dict | None = None,
                    severity: str = "info") -> None:
        await self._bus.publish(Event(
            event_type=event_type, source="tasks.manager", task_id=task.id,
            correlation_id=(payload or {}).get("correlation_id"),
            payload={"task_id": task.id, "status": task.status, **(payload or {})},
            severity=severity))

    # --------------------------------------------------------------- submit
    async def submit(self, principal: Principal, *, name: str, handler_name: str,
                     payload: dict | None = None, description: str | None = None,
                     category: str = "general", priority: int = 5, max_retries: int = 0,
                     timeout_seconds: float = 30.0, assigned_agent_id: str | None = None,
                     requires_approval: bool = False, essential: bool = False,
                     idempotency_key: str | None = None,
                     correlation_id: str | None = None) -> Task:
        decision = self._permissions.check(
            principal, Permission.SUBMIT_TASKS.value, resource="tasks", correlation_id=correlation_id)
        if not decision.allowed:
            raise PermissionDeniedError(
                "principal lacks submit_tasks permission", details={"reason": decision.reason})

        session, repo = self._repo()
        try:
            if idempotency_key:
                existing = repo.get_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return existing
            if assigned_agent_id and AgentRepository(session).get(assigned_agent_id) is None:
                raise NotFoundError(f"agent {assigned_agent_id} not found")
        finally:
            session.close()

        if not self._accepting:
            raise QueueFullError("task manager is shutting down and not accepting new tasks")
        if not self.queue.has_capacity():
            raise QueueFullError("task queue capacity reached (backpressure)",
                                 details={"capacity": self.queue.capacity})
        if self._admission_guard is not None and not essential:
            reason = self._admission_guard()
            if reason:
                raise ResourceBlockedError(
                    "nonessential task admission blocked by resource thresholds",
                    details={"reason": reason})

        # Handler + payload validation happens BEFORE queueing (VALIDATING).
        try:
            validated_payload = self.registry.validate_payload(handler_name, payload or {})
        except TaskExecutionError as exc:
            raise PermissionDeniedError(str(exc)) if exc.kind == ErrorKind.PERMISSION_DENIED else \
                _validation_error(exc)

        session, repo = self._repo()
        try:
            task = Task(
                name=name, description=description, category=category,
                handler_name=handler_name, payload=validated_payload, priority=priority,
                status=TaskStatus.CREATED.value, creator_type=principal.type.value,
                creator_id=principal.id, assigned_agent_id=assigned_agent_id,
                max_retries=max_retries, timeout_seconds=timeout_seconds,
                requires_approval=requires_approval, essential=essential,
                idempotency_key=idempotency_key)
            repo.add(task)
            self.transition(task, TaskStatus.VALIDATING, repo)
            if requires_approval:
                self.transition(task, TaskStatus.WAITING_FOR_APPROVAL, repo)
            else:
                self.transition(task, TaskStatus.QUEUED, repo)
                task.next_attempt_at = utcnow()
                repo.save(task)
        finally:
            session.close()
        await self._emit(EventType.TASK_CREATED, task, {"correlation_id": correlation_id})
        if task.status == TaskStatus.QUEUED.value:
            await self._emit(EventType.TASK_QUEUED, task, {"correlation_id": correlation_id})
        return task

    # ---------------------------------------------------------------- reads
    def get(self, task_id: str) -> Task:
        session, repo = self._repo()
        try:
            task = repo.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} not found")
            return task
        finally:
            session.close()

    def list(self, status: str | None = None, limit: int = 50, offset: int = 0):
        session, repo = self._repo()
        try:
            return repo.list(status, limit, offset)
        finally:
            session.close()

    def history(self, task_id: str) -> list[TaskExecution]:
        task = self.get(task_id)
        return list(task.executions)

    # -------------------------------------------------------------- control
    async def cancel(self, principal: Principal, task_id: str,
                     correlation_id: str | None = None) -> Task:
        self._permissions.require(principal, Permission.CANCEL_TASKS.value,
                                  resource="tasks", correlation_id=correlation_id)
        session, repo = self._repo()
        try:
            task = repo.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} not found")
            if TaskStatus(task.status) == TaskStatus.RUNNING:
                task.cancellation_requested = True
                repo.save(task)
                return task
            self.transition(task, TaskStatus.CANCELLED, repo)
            task.completed_at = utcnow()
            repo.save(task)
        finally:
            session.close()
        await self._emit(EventType.TASK_CANCELLED, task, {"correlation_id": correlation_id})
        return task

    async def pause(self, task_id: str) -> Task:
        session, repo = self._repo()
        try:
            task = repo.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} not found")
            return self.transition(task, TaskStatus.PAUSED, repo)
        finally:
            session.close()

    async def resume(self, task_id: str) -> Task:
        session, repo = self._repo()
        try:
            task = repo.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} not found")
            self.transition(task, TaskStatus.QUEUED, repo)
            task.progress = {**task.progress, "recovery_required": False}
            task.next_attempt_at = utcnow()
            return repo.save(task)
        finally:
            session.close()

    async def retry(self, task_id: str) -> Task:
        """Manual retry of a FAILED task (creates a fresh attempt cycle)."""
        session, repo = self._repo()
        try:
            task = repo.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} not found")
            self.transition(task, TaskStatus.RETRY_PENDING, repo)
            task.retry_count = 0
            task.error = None
            task.completed_at = None
            task.next_attempt_at = utcnow()
            self.transition(task, TaskStatus.QUEUED, repo)
            return task
        finally:
            session.close()

    def approve_task(self, task_id: str) -> Task:
        """Move a WAITING_FOR_APPROVAL task to QUEUED (called after an
        approval decision has been verified by the approvals service)."""
        session, repo = self._repo()
        try:
            task = repo.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} not found")
            self.transition(task, TaskStatus.QUEUED, repo)
            task.next_attempt_at = utcnow()
            return repo.save(task)
        finally:
            session.close()

    # -------------------------------------------------------------- worker
    async def start(self) -> None:
        self._accepting = True
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._loop())

    async def stop(self, timeout: float = 10.0) -> None:
        self._accepting = False
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        if self._running:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._running, return_exceptions=True), timeout=timeout)
            except asyncio.TimeoutError:
                for t in self._running:
                    t.cancel()

    async def _loop(self) -> None:
        while True:
            try:
                if self._accepting and len(self._running) < self.max_concurrency:
                    session, repo = self._repo()
                    try:
                        due = repo.due_tasks(utcnow(), limit=self.max_concurrency - len(self._running))
                    finally:
                        session.close()
                    for task in due:
                        run = asyncio.create_task(self._execute(task.id))
                        self._running.add(run)
                        run.add_done_callback(self._running.discard)
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._log.exception("task worker loop error")
                await asyncio.sleep(0.2)

    async def _execute(self, task_id: str) -> None:
        session, repo = self._repo()
        try:
            task = repo.get(task_id)
            if task is None or task.status not in (TaskStatus.QUEUED.value, TaskStatus.RETRY_PENDING.value):
                return
            if task.status == TaskStatus.RETRY_PENDING.value:
                self.transition(task, TaskStatus.QUEUED, repo)
            attempt_number = len(task.executions) + 1
            execution = TaskExecution(task_id=task.id, attempt_number=attempt_number,
                                      status="running", started_at=utcnow())
            repo.add_execution(execution)
            self.transition(task, TaskStatus.RUNNING, repo)
            task.started_at = utcnow()
            repo.save(task)
        finally:
            session.close()
        await self._emit(EventType.TASK_STARTED, task)

        started = time.monotonic()
        context = {"task_id": task_id, "monitor": self._monitor}
        try:
            result = await asyncio.wait_for(
                self.registry.execute(task.handler_name, task.payload, context),
                timeout=task.timeout_seconds)
            kind, error_message = None, None
        except asyncio.TimeoutError:
            result, kind, error_message = None, ErrorKind.TIMEOUT, f"task timed out after {task.timeout_seconds}s"
        except asyncio.CancelledError:
            # The worker itself is being torn down (shutdown/crash). Do NOT
            # write a verdict: the task stays RUNNING in the DB and startup
            # recovery will mark it interrupted/recovery-required (§7.5).
            raise
        except BaseException as exc:  # classified below; never swallowed silently
            result, kind, error_message = None, classify_exception(exc), str(exc)

        duration_ms = (time.monotonic() - started) * 1000.0
        session, repo = self._repo()
        try:
            task = repo.get(task_id)
            execution = next(e for e in task.executions if e.id == execution.id)
            execution.finished_at = utcnow()
            execution.duration_ms = duration_ms
            if kind is None:
                # A cancellation requested while running wins over success.
                if task.cancellation_requested:
                    execution.status = "cancelled"
                    repo.save_execution(execution)
                    self.transition(task, TaskStatus.CANCELLED, repo)
                    task.completed_at = utcnow()
                    repo.save(task)
                    await self._emit(EventType.TASK_CANCELLED, task)
                else:
                    execution.status = "completed"
                    execution.result = result
                    repo.save_execution(execution)
                    self.transition(task, TaskStatus.COMPLETED, repo)
                    task.result = result
                    task.completed_at = utcnow()
                    repo.save(task)
                    await self._emit(EventType.TASK_COMPLETED, task)
            else:
                execution.status = "failed"
                execution.error = {"kind": kind.value, "message": error_message}
                repo.save_execution(execution)
                task.error = {"kind": kind.value, "message": error_message}
                if task.cancellation_requested and kind == ErrorKind.INTERRUPTED:
                    self.transition(task, TaskStatus.CANCELLED, repo)
                    task.completed_at = utcnow()
                    repo.save(task)
                    await self._emit(EventType.TASK_CANCELLED, task)
                elif is_retryable(kind) and task.retry_count < task.max_retries:
                    self.transition(task, TaskStatus.FAILED, repo)
                    self.transition(task, TaskStatus.RETRY_PENDING, repo)
                    task.retry_count += 1
                    delay = backoff_delay(task.retry_count, self.retry_base_delay, self.retry_max_delay)
                    task.next_attempt_at = utcnow() + dt.timedelta(seconds=delay)
                    repo.save(task)
                else:
                    if task.status != TaskStatus.FAILED.value:
                        self.transition(task, TaskStatus.FAILED, repo)
                    task.completed_at = utcnow()
                    repo.save(task)
                    await self._emit(EventType.TASK_FAILED, task,
                                     {"kind": kind.value, "message": error_message}, severity="error")
        finally:
            session.close()

    # ------------------------------------------------------------- recovery
    def recover_interrupted(self) -> list[str]:
        """Startup recovery (P-01 §7.5): RUNNING tasks are marked interrupted
        and moved to PAUSED with recovery_required=True. They are NOT
        re-executed automatically; an operator resumes or cancels them."""
        session, repo = self._repo()
        recovered: list[str] = []
        try:
            for task in repo.by_status([TaskStatus.RUNNING.value]):
                for execution in task.executions:
                    if execution.status == "running":
                        execution.status = "interrupted"
                        execution.finished_at = utcnow()
                        execution.error = {"kind": ErrorKind.INTERRUPTED.value,
                                           "message": "interrupted by application restart"}
                task.status = TaskStatus.PAUSED.value
                task.progress = {**task.progress, "recovery_required": True, "interrupted": True}
                task.error = {"kind": ErrorKind.INTERRUPTED.value,
                              "message": "interrupted by application restart; manual review required"}
                repo.save(task)
                recovered.append(task.id)
            for task in repo.by_status([TaskStatus.VALIDATING.value]):
                task.status = TaskStatus.QUEUED.value  # validation has no side effects; safe to requeue
                task.next_attempt_at = utcnow()
                repo.save(task)
        finally:
            session.close()
        return recovered


def _validation_error(exc: TaskExecutionError):
    from ..core.exceptions import ValidationError

    return ValidationError(str(exc), details={"kind": exc.kind.value})
