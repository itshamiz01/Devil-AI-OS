"""Connector development template (Expansion Feature 2, pack §5).

Copy this file, rename the class, and implement the three methods.
A connector becomes real only when ALL of the following hold:

1. Its ``DESCRIPTOR`` is valid — every capability names a real P-01
   permission and a risk action P-10 has classified (the framework
   refuses anything else at registration).
2. The class is registered in ``app/integrations/registry.py``
   (``ADAPTER_FACTORIES``) — until then the registry record has no
   adapter and reports ``requires_owner_configuration`` honestly.
3. Credentials are declared (``requires_credential=True``) and read
   ONLY from ``context.credential_value`` inside ``invoke`` — the
   framework resolves them through P-10's brokered secret service
   for that one call. Never store, log or return the value.
4. ``invoke`` raises on failure. The framework records errors
   honestly; fabricating a success result is the one unforgivable
   connector bug.
5. It ships with tests using ``app/integrations/testing.py``
   (auth failure, timeout, rate limiting, revoked access) and its
   acceptance evidence is recorded in the feature's docs.

This template is NEVER registered: importing it changes nothing.
"""
from __future__ import annotations

from ..interfaces.base import (
    Capability, ConnectorAdapter, ConnectorContext, ConnectorDescriptor,
    IntegrationHealth,
)

DESCRIPTOR = ConnectorDescriptor(
    key="template_connector",
    name="Template Connector",
    provider="Example Provider",
    version="0.1.0",
    kind="rest_api",
    description="Skeleton — replace with a real description.",
    requires_credential=True,
    capabilities=(
        Capability(
            name="example_action",
            description="What this action does, in one sentence.",
            permission="execute_tools",
            risk_action="network.fetch",   # must exist in P-10 ACTION_RISK
            input_schema={"type": "object", "properties": {},
                          "additionalProperties": False},
            output_schema={"type": "object"}),
    ),
)


class TemplateConnectorAdapter(ConnectorAdapter):
    descriptor = DESCRIPTOR
    name = "template_connector"

    async def health(self) -> IntegrationHealth:
        raise NotImplementedError("template — implement a real health check")

    async def invoke(self, capability: str, payload: dict,
                     context: ConnectorContext) -> dict:
        raise NotImplementedError("template — implement the real call")

    async def close(self) -> None:
        return None
