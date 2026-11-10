"""The framework's one reference connector (Expansion Feature 2).

``local_echo`` is genuinely real and deliberately trivial: a local,
no-network connector whose ``echo`` capability validates its input
and returns it with a server timestamp. It exists to prove the
framework end to end — registration, configuration, enablement,
health, broker-authorized invocation, idempotency, rate limiting,
audit — without pretending any external service is connected.

Per the pack's honesty rule, no provider may be claimed supported
until its connector is implemented and tested. This connector
claims nothing beyond itself.
"""
from __future__ import annotations

from ...database.models.base import utcnow
from ..interfaces.base import (
    Capability, ConnectorAdapter, ConnectorContext, ConnectorDescriptor,
    IntegrationHealth,
)

DESCRIPTOR = ConnectorDescriptor(
    key="local_echo",
    name="Local Echo (reference connector)",
    provider="AUTONOMUS (local)",
    version="1.0.0",
    kind="custom",
    description="Local no-network reference connector proving the "
                "framework end to end. Echoes a validated message "
                "back with a server timestamp.",
    requires_credential=False,
    capabilities=(
        Capability(
            name="echo",
            description="Return the supplied message with a server "
                        "timestamp. Local only; no external effect.",
            permission="read_system_data",
            risk_action="read",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "minLength": 1,
                                "maxLength": 500},
                },
                "required": ["message"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "echo": {"type": "string"},
                    "responded_at": {"type": "string"},
                },
                "required": ["echo", "responded_at"],
            }),
    ),
)


class LocalEchoAdapter(ConnectorAdapter):
    descriptor = DESCRIPTOR
    name = "local_echo"

    async def health(self) -> IntegrationHealth:
        return IntegrationHealth(
            name=self.name, available=True,
            detail="local reference connector; no external dependency")

    async def invoke(self, capability: str, payload: dict,
                     context: ConnectorContext) -> dict:
        if capability != "echo":
            raise ValueError(f"local_echo has no capability '{capability}'")
        return {"echo": payload["message"],
                "responded_at": utcnow().isoformat()}

    async def close(self) -> None:
        return None
