from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field, ValidationError

from ..core.exceptions import AppError


class HandlerError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class NoopPayload(BaseModel):
    pass


class EchoPayload(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class WaitPayload(BaseModel):
    duration_ms: int = Field(default=100, ge=0, le=5000)


@dataclass
class ExecutionContext:
    task_id: str
    cancellation: asyncio.Event


@dataclass
class Handler:
    name: str
    payload_model: type[BaseModel]
    essential: bool
    retryable: bool
    execute: Callable[[BaseModel, ExecutionContext], Awaitable[dict[str, Any]]]


async def _noop(payload: BaseModel, ctx: ExecutionContext) -> dict:
    return {"ok": True, "handler": "system.noop"}


async def _echo(payload: EchoPayload, ctx: ExecutionContext) -> dict:
    return {"message": payload.message}


async def _wait(payload: WaitPayload, ctx: ExecutionContext) -> dict:
    remaining = payload.duration_ms
    while remaining > 0:
        if ctx.cancellation.is_set():
            raise asyncio.CancelledError()
        step = min(50, remaining)
        await asyncio.sleep(step / 1000)
        remaining -= step
    if ctx.cancellation.is_set():
        raise asyncio.CancelledError()
    return {"waited_ms": payload.duration_ms}


HANDLERS: dict[str, Handler] = {
    "system.noop": Handler("system.noop", NoopPayload, True, True, _noop),
    "system.echo": Handler("system.echo", EchoPayload, False, True, _echo),
    "system.wait": Handler("system.wait", WaitPayload, False, True, _wait),
}


def validate_payload(handler_name: str, payload: dict) -> dict:
    handler = HANDLERS.get(handler_name)
    if not handler:
        raise AppError("Unknown or disallowed task handler", {"handler": handler_name})
    try:
        validated = handler.payload_model.model_validate(payload)
    except ValidationError as exc:
        raise AppError("Invalid task payload", {"errors": exc.errors()}) from exc
    return validated.model_dump()
