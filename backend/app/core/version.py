"""The API version — one source of truth (Expansion Feature 2).

The version sat frozen at ``0.1.0`` from P-01 through P-18 and two
expansion features (Gate 2 review §2, finding 4): an external
consumer could not distinguish the P-01 surface from the P-18 one.
From F02 the rule is:

- **1.0.0** — the completed P-01 → P-18 roadmap baseline.
- **Minor** increments per expansion feature (F01 = 1.1.0,
  F02 = 1.2.0, F03 = 1.3.0, …). Minors follow the order features
  are BUILT: F06 was approved to proceed ahead of the deferred
  F04/F05 (owner decision, they need his Windows machine), so
  F06 = 1.4.0.
- **Patch** increments for fixes that add no surface.

``app/main.py`` (the FastAPI ``version=``) and the integration
framework's status surface both read this constant, and the route
prefix remains ``/api/v1`` — the version describes the surface,
the prefix stays stable for existing clients.
"""
from __future__ import annotations

APP_VERSION = "1.4.0"
