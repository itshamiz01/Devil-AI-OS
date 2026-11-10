"""Connector test harness (Expansion Feature 2, pack §5/§7).

``MockConnectorAdapter`` is the framework's test double: a real
``ConnectorAdapter`` whose behaviour is configured per test —
success, authentication failure, timeout, generic adapter error —
so connector consumers and the framework itself can be tested
against the failure modes the pack names (authentication failures,
expired/revoked credentials, API timeouts, rate limits, duplicate
requests) without any external service.

It is never seeded into the production registry; tests register it
with a framework service instance directly.
"""
from __future__ import annotations

import asyncio

from .interfaces.base import (
    Capability, ConnectorAdapter, ConnectorContext, ConnectorDescriptor,
    IntegrationHealth,
)


class MockAuthError(Exception):
    """Simulates a provider rejecting the presented credential."""


class MockConnectorAdapter(ConnectorAdapter):
    """Configurable behaviours: ``ok`` (default), ``auth_error``,
    ``timeout``, ``error``, ``unhealthy`` (health reports
    unavailable). ``calls`` records every invocation for assertions
    (payloads only — a credential value is never recorded)."""

    def __init__(self, *, key: str = "mock_connector",
                 behaviour: str = "ok", requires_credential: bool = False,
                 rate_limit_per_minute: int | None = None):
        self.behaviour = behaviour
        self.calls: list[dict] = []
        self.descriptor = ConnectorDescriptor(
            key=key, name=f"Mock connector ({key})", provider="Test harness",
            version="0.0.0", kind="custom",
            description="Framework test double — never a production connector.",
            requires_credential=requires_credential,
            capabilities=(
                Capability(
                    name="ping",
                    description="Mock capability used by framework tests.",
                    permission="execute_tools",
                    risk_action="network.fetch",
                    input_schema={"type": "object",
                                  "properties": {"value": {"type": "string"}},
                                  "additionalProperties": True},
                    output_schema={"type": "object"},
                    rate_limit_per_minute=rate_limit_per_minute),
            ))
        self.name = key

    async def health(self) -> IntegrationHealth:
        if self.behaviour == "unhealthy":
            return IntegrationHealth(name=self.name, available=False,
                                     detail="mock reports unavailable")
        return IntegrationHealth(name=self.name, available=True,
                                 detail="mock healthy")

    async def invoke(self, capability: str, payload: dict,
                     context: ConnectorContext) -> dict:
        self.calls.append({"capability": capability,
                           "credential_present": context.credential_value is not None})
        if self.behaviour == "auth_error":
            raise MockAuthError("mock provider rejected the credential (401)")
        if self.behaviour == "timeout":
            await asyncio.sleep(30)
        if self.behaviour == "error":
            raise RuntimeError("mock provider failure (500)")
        return {"pong": payload.get("value"), "capability": capability}

    async def close(self) -> None:
        return None
