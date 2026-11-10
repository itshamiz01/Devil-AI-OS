"""Integration adapter contract (P-01 §3, SYSTEM_ARCHITECTURE integration
strategy). Later phases plug external systems in behind this interface —
dedicated APIs first, browser automation second, desktop control last.
No concrete integrations are implemented in P-01.

Expansion Feature 2 (Universal Integration Framework) extends this
contract ADDITIVELY — the P-01 surface above (``IntegrationHealth``,
``IntegrationAdapter.health/close``) is unchanged, and its existing
consumer (P-02's ``ModelProvider``) is untouched. The framework adds:

- :class:`Capability` — one declared connector action: the P-01
  permission a caller must hold, the P-10 risk action its execution
  classifies under (risk classification stays P-10's authority),
  JSON input/output schemas, an optional rate limit.
- :class:`ConnectorDescriptor` — the static declaration of a
  connector: identity, provider, kind, capabilities, whether a
  credential is required. A descriptor is a *declaration*, never
  evidence that a working connector exists — only a registered
  adapter class is that.
- :class:`ConnectorAdapter` — the executable contract: descriptor,
  health, invoke, close, and an optional webhook-signature hook.
- :class:`ConnectorContext` — what the framework hands an adapter
  at invocation time. A credential VALUE appears here only when the
  framework resolved it through P-10's brokered secret service for
  this single call; adapters must never persist, log or return it.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class IntegrationHealth:
    name: str
    available: bool
    detail: str = ""


class IntegrationAdapter(abc.ABC):
    name: str = "unnamed"

    @abc.abstractmethod
    async def health(self) -> IntegrationHealth:
        raise NotImplementedError

    @abc.abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


# ------------------------------------------------- Expansion Feature 2
@dataclass(frozen=True)
class Capability:
    """One declared connector action (F02 capability contract)."""

    name: str
    description: str = ""
    permission: str = "read_system_data"   # a P-01 Permission value
    risk_action: str = "read"              # a key of P-10's ACTION_RISK
    input_schema: dict = field(default_factory=lambda: {"type": "object"})
    output_schema: dict = field(default_factory=lambda: {"type": "object"})
    rate_limit_per_minute: int | None = None
    is_sync: bool = False                  # success advances last_sync_at

    def to_dict(self) -> dict:
        return {
            "name": self.name, "description": self.description,
            "permission": self.permission, "risk_action": self.risk_action,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "is_sync": self.is_sync,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Capability":
        return cls(
            name=data["name"], description=data.get("description", ""),
            permission=data.get("permission", "read_system_data"),
            risk_action=data.get("risk_action", "read"),
            input_schema=data.get("input_schema") or {"type": "object"},
            output_schema=data.get("output_schema") or {"type": "object"},
            rate_limit_per_minute=data.get("rate_limit_per_minute"),
            is_sync=bool(data.get("is_sync", False)))


@dataclass(frozen=True)
class ConnectorDescriptor:
    """The static declaration of one connector (F02)."""

    key: str
    name: str
    provider: str
    version: str = "1.0.0"
    kind: str = "custom"
    description: str = ""
    capabilities: tuple = ()               # tuple[Capability, ...]
    requires_credential: bool = False

    @property
    def required_permissions(self) -> list[str]:
        return sorted({c.permission for c in self.capabilities})

    def capability(self, name: str) -> Capability | None:
        for cap in self.capabilities:
            if cap.name == name:
                return cap
        return None

    def to_dict(self) -> dict:
        return {
            "key": self.key, "name": self.name, "provider": self.provider,
            "version": self.version, "kind": self.kind,
            "description": self.description,
            "requires_credential": self.requires_credential,
            "required_permissions": self.required_permissions,
            "capabilities": [c.to_dict() for c in self.capabilities],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConnectorDescriptor":
        return cls(
            key=data["key"], name=data["name"], provider=data["provider"],
            version=data.get("version", "1.0.0"),
            kind=data.get("kind", "custom"),
            description=data.get("description", ""),
            capabilities=tuple(
                Capability.from_dict(c) for c in data.get("capabilities", [])),
            requires_credential=bool(data.get("requires_credential", False)))


@dataclass
class ConnectorContext:
    """Invocation-time context handed to an adapter by the framework.

    ``credential_value`` is populated ONLY inside P-10's brokered
    ``execute_with_secret`` callback for this one call. Adapters
    must use it in-flight and never persist, log or return it."""

    connector_key: str
    capability: str
    principal: str = ""                    # "type:id" of the caller
    correlation_id: str | None = None
    credential_value: str | None = None
    settings: dict = field(default_factory=dict)


class ConnectorAdapter(IntegrationAdapter):
    """The executable connector contract (F02). Concrete connectors
    subclass this, set ``descriptor``, and implement ``invoke``."""

    descriptor: ConnectorDescriptor

    @abc.abstractmethod
    async def invoke(self, capability: str, payload: dict,
                     context: ConnectorContext) -> dict:
        """Execute one declared capability. Must raise on failure —
        the framework records the error honestly; an adapter must
        never fabricate a success result."""
        raise NotImplementedError

    def verify_webhook_signature(self, secret_value: str, body: bytes,
                                 headers: dict) -> bool:
        """Optional webhook signature check (pack §4 security).
        Default: unsupported — a connector that receives webhooks
        overrides this with its provider's scheme. The framework
        supplies ``secret_value`` through the P-10 broker only."""
        raise NotImplementedError(
            "this connector does not verify webhook signatures")
