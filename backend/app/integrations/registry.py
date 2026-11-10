"""The connector registry's code side (Expansion Feature 2).

Two distinct things live here:

- ``ADAPTER_FACTORIES`` — the in-code adapters that actually
  exist. A registry row whose ``adapter_key`` is absent from this
  mapping has **no implementation** and can never be invoked,
  however it is configured. This is the pack's honesty rule made
  structural: support for a provider exists only when a connector
  has been implemented and tested.
- ``builtin_descriptors()`` — the catalogue seeded into the
  registry at startup: the framework's reference connector, plus
  the external surfaces the engines already report ad hoc (P-07's
  Stripe, P-17's marketing platforms, P-18's support channels),
  imported from those engines' own constants so the registry can
  never drift from what the engines declare. The external entries
  carry **no adapter** — they are registry records awaiting a real
  connector and owner configuration, and the framework reports
  them ``requires_owner_configuration``.
"""
from __future__ import annotations

from .adapters.local_echo import DESCRIPTOR as LOCAL_ECHO_DESCRIPTOR
from .adapters.local_echo import LocalEchoAdapter
from .interfaces.base import Capability, ConnectorDescriptor

ADAPTER_FACTORIES = {
    "local_echo": LocalEchoAdapter,
}


def _stripe_descriptor() -> ConnectorDescriptor:
    """P-07's Stripe surface (``app/financial/payments.py``:
    ``StripeAdapter``, status ``interface_only`` — an event-mapping
    interface never tested against Stripe's real API). Capability
    keys mirror that adapter's declared capability map; the
    framework registers the surface, it does not make it live."""
    def cap(name, permission, risk_action, description):
        return Capability(name=name, permission=permission,
                          risk_action=risk_action, description=description)
    return ConnectorDescriptor(
        key="stripe", name="Stripe payments", provider="Stripe",
        version="1.0.0", kind="payment",
        description="P-07 payment-provider interface (event mapping "
                    "only). REQUIRES OWNER CONFIGURATION before any "
                    "live use; never tested against Stripe's real "
                    "interface in staging.",
        requires_credential=True,
        capabilities=(
            cap("payment_events", "read_business_data", "network.fetch",
                "Receive/normalise payment events (via P-07's webhook)."),
            cap("verification", "read_business_data", "network.fetch",
                "Verify webhook signatures (P-07 holds the scheme)."),
            cap("settlements", "read_business_data", "network.fetch",
                "Settlement event mapping."),
            cap("refunds", "request_financial_operations", "financial.transfer",
                "Refund event mapping — financial authority stays P-07."),
            cap("disputes", "read_business_data", "network.fetch",
                "Dispute event mapping."),
            cap("balances", "read_business_data", "financial.view",
                "Balance reporting."),
            cap("payouts", "read_business_data", "financial.view",
                "Payout reporting."),
        ))


# Kind assignments for the engines' declared surfaces (a design
# classification of the surface's shape — never a support claim).
_GROWTH_KINDS = {
    "email_transport": "email_calendar", "search_ads": "rest_api",
    "social_ads": "rest_api", "social_publishing": "rest_api",
    "search_console": "rest_api", "web_analytics": "rest_api",
    "video_platform": "rest_api", "affiliate_network": "ecommerce",
}
_EXPERIENCE_KINDS = {
    "support_email": "email_calendar", "website_chat": "custom",
    "messaging_platforms": "rest_api", "logistics_tracking": "rest_api",
    "digital_delivery": "rest_api", "appointment_scheduling": "productivity",
    "survey_delivery": "rest_api", "communication_transport": "email_calendar",
}


def builtin_descriptors() -> list[tuple[ConnectorDescriptor, str, str | None]]:
    """(descriptor, source, adapter_key) triples seeded at startup."""
    entries: list[tuple[ConnectorDescriptor, str, str | None]] = [
        (LOCAL_ECHO_DESCRIPTOR, "framework", "local_echo"),
        (_stripe_descriptor(), "p07", None),
    ]
    from ..experience import constants as cx_constants
    from ..growth import constants as growth_constants
    for item in growth_constants.INTEGRATIONS:
        entries.append((ConnectorDescriptor(
            key=f"growth_{item['key']}", name=item["label"],
            provider="External platform (undeclared)", kind=_GROWTH_KINDS.get(
                item["key"], "rest_api"),
            description=f"P-17 growth surface — needed for: "
                        f"{item.get('needed_for', 'growth operations')}. "
                        f"No connector implemented; nothing is connected "
                        f"or simulated.",
            requires_credential=True), "p17", None))
    for item in cx_constants.INTEGRATIONS:
        entries.append((ConnectorDescriptor(
            key=f"experience_{item['key']}", name=item["label"],
            provider="External platform (undeclared)", kind=_EXPERIENCE_KINDS.get(
                item["key"], "rest_api"),
            description=f"P-18 experience surface — {item.get('note', '')}",
            requires_credential=True), "p18", None))
    return entries
