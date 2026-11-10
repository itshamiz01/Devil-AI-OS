"""Built-in task handler registry (P-01 Rule 4).

Tasks execute ONLY through named handlers registered here. A task payload
can never carry code, shell commands or callables — unknown handler names
are rejected at submission time as invalid input. All built-in handlers are
harmless core utilities.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from pydantic import BaseModel, Field, ValidationError

from .models import ErrorKind, TaskExecutionError

HandlerFunc = Callable[[dict, dict], Awaitable[dict]]


class EchoPayload(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    data: dict = Field(default_factory=dict)


class WaitPayload(BaseModel):
    milliseconds: int = Field(ge=0, le=10_000)


class EmptyPayload(BaseModel):
    model_config = {"extra": "allow"}


async def _noop(payload: dict, context: dict) -> dict:
    return {"ok": True, "handler": "core.noop"}


async def _echo_check(payload: dict, context: dict) -> dict:
    try:
        parsed = EchoPayload(**payload)
    except ValidationError as exc:
        raise TaskExecutionError(f"invalid echo payload: {exc.errors()}", ErrorKind.INVALID_INPUT)
    return {"ok": True, "echo": parsed.model_dump()}


async def _health_snapshot(payload: dict, context: dict) -> dict:
    monitor = context.get("monitor")
    if monitor is None:
        raise TaskExecutionError("monitor unavailable", ErrorKind.TRANSIENT)
    return {"ok": True, "resources": monitor.resources(), "db_healthy": monitor.database_healthy()}


async def _wait(payload: dict, context: dict) -> dict:
    """Bounded sleep — exists so timeout/cancellation behaviour is testable
    through the same governed path as every other task."""
    try:
        parsed = WaitPayload(**payload)
    except ValidationError as exc:
        raise TaskExecutionError(f"invalid wait payload: {exc.errors()}", ErrorKind.INVALID_INPUT)
    await asyncio.sleep(parsed.milliseconds / 1000.0)
    return {"ok": True, "waited_ms": parsed.milliseconds}


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, tuple[HandlerFunc, type[BaseModel]]] = {}
        self.register("core.noop", _noop, EmptyPayload)
        self.register("core.echo_check", _echo_check, EchoPayload)
        self.register("core.health_snapshot", _health_snapshot, EmptyPayload)
        self.register("core.wait", _wait, WaitPayload)

    def register(self, name: str, func: HandlerFunc, payload_model: type[BaseModel]) -> None:
        self._handlers[name] = (func, payload_model)

    def names(self) -> list[str]:
        return sorted(self._handlers)

    def has(self, name: str) -> bool:
        return name in self._handlers

    def validate_payload(self, name: str, payload: dict) -> dict:
        if name not in self._handlers:
            raise TaskExecutionError(f"unknown handler '{name}'", ErrorKind.INVALID_INPUT)
        _, model = self._handlers[name]
        try:
            return model(**payload).model_dump()
        except ValidationError as exc:
            raise TaskExecutionError(
                f"invalid payload for handler '{name}': {exc.errors()}", ErrorKind.INVALID_INPUT)

    async def execute(self, name: str, payload: dict, context: dict) -> dict:
        func, _ = self._handlers[name]
        return await func(payload, context)
