"""Universal Integration Framework vocabulary (Expansion Feature 2).

Two axes, deliberately separate:

- **Lifecycle** — what the registry has done with a connector:
  ``registered`` (a descriptor exists) → ``configured`` (the owner
  attached configuration: a credential secret NAME and/or non-secret
  settings) → ``enabled`` (available for invocation) ⇄ ``disabled``.
- **Reported state** — the ONE state vocabulary every framework
  surface uses, replacing the per-engine ad-hoc states (P-07's
  ``interface_only``, P-17/P-18's response-time stamps) wherever
  those surfaces are presented through the framework:
  ``configured`` / ``not_configured`` /
  ``requires_owner_configuration`` / ``error``.
"""
from __future__ import annotations

# ------------------------------------------------------------- lifecycle
LIFECYCLE_REGISTERED = "registered"
LIFECYCLE_CONFIGURED = "configured"
LIFECYCLE_ENABLED = "enabled"
LIFECYCLE_DISABLED = "disabled"
LIFECYCLES = (LIFECYCLE_REGISTERED, LIFECYCLE_CONFIGURED,
              LIFECYCLE_ENABLED, LIFECYCLE_DISABLED)

# -------------------------------------------------------- reported state
STATE_CONFIGURED = "configured"
STATE_NOT_CONFIGURED = "not_configured"
STATE_REQUIRES_OWNER_CONFIGURATION = "requires_owner_configuration"
STATE_ERROR = "error"
STATES = (STATE_CONFIGURED, STATE_NOT_CONFIGURED,
          STATE_REQUIRES_OWNER_CONFIGURATION, STATE_ERROR)

# Legacy per-engine labels and how they read in the framework
# vocabulary (documentation mapping — the engines' own endpoints are
# unchanged; this is how their states are understood here).
LEGACY_STATE_MAP = {
    "interface_only": STATE_REQUIRES_OWNER_CONFIGURATION,
    "not_configured": STATE_NOT_CONFIGURED,
    "NOT CONFIGURED": STATE_NOT_CONFIGURED,
    "REQUIRES OWNER CONFIGURATION": STATE_REQUIRES_OWNER_CONFIGURATION,
}

# ------------------------------------------------------------ kinds
# The pack §2 integration types. A kind is a design claim about the
# connector's shape, never a claim that a provider works — that is
# proven only by an implemented, tested adapter.
KINDS = (
    "rest_api", "webhook", "oauth", "local_app", "browser", "database",
    "filesystem", "email_calendar", "productivity", "ecommerce",
    "payment", "trading", "custom",
)

# --------------------------------------------------------- outcomes
OUTCOME_SUCCESS = "success"
OUTCOME_ERROR = "error"
OUTCOME_DENIED = "denied"
OUTCOME_NOT_CONFIGURED = "not_configured"
OUTCOME_REQUIRES_OWNER_CONFIGURATION = "requires_owner_configuration"
OUTCOME_RATE_LIMITED = "rate_limited"
OUTCOME_INVALID_REQUEST = "invalid_request"
OUTCOME_DUPLICATE = "duplicate"
OUTCOMES = (OUTCOME_SUCCESS, OUTCOME_ERROR, OUTCOME_DENIED,
            OUTCOME_NOT_CONFIGURED, OUTCOME_REQUIRES_OWNER_CONFIGURATION,
            OUTCOME_RATE_LIMITED, OUTCOME_INVALID_REQUEST, OUTCOME_DUPLICATE)
