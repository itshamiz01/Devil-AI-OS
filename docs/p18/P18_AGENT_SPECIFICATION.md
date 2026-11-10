# P-18 Agent Specification (§14)

The ten customer-experience roles are **P-04 Agent Factory
templates** (category `experience`), seeded idempotently at
startup by `ExperienceService.seed_agent_templates` — P-18
builds no agent orchestration of its own (§14).

| Role | Type | Capabilities | Boundary |
|---|---|---|---|
| Customer Onboarding Agent | operations | read/write internal, memory read | works only from the configured template and recorded state |
| Fulfillment Monitoring Agent | operations | read-only | reports recorded states with source labels; never claims a shipment |
| Customer Support Agent | support | draft (reasoning + memory read) | answers only from approved KB articles, cites them, escalates the unverifiable; never impersonates a human |
| Ticket Classification Agent | support | read/write internal | declared categories/factors only; breakdown recorded |
| Support Quality Assurance Agent | analysis | read-only | scores documented dimensions from recorded evidence; never presents QA as satisfaction |
| Customer Feedback Analysis Agent | analysis | read-only | recorded feedback only; produces no sentiment estimates |
| Issue Resolution Coordinator | operations | read/write internal | prepares recommendations; may never execute a refund/compensation |
| Customer Success Analyst | analysis | read-only | health from recorded signals with factors/evidence; never a churn prediction |
| Knowledge Base Maintenance Agent | production | draft | drafts stay drafts until the owner approves; never edits approved content silently |
| Service Performance Analyst | analysis | read-only | missing data is reported unavailable, never estimated |

## Hard boundaries (all roles)

- **No external communication capability exists for any role** —
  there is no transport to send through, and the P-04 catalogue
  grant is deliberately withheld.
- **No financial capability** — refunds, credits and compensation
  remain owner-approved, P-07-executed.
- **Service-layer enforcement is independent of roles:** P-18
  writes are owner-gated in-service and customer reads are
  owner/system-only, so an agent principal is refused by the
  service even before role capabilities are considered (pinned
  by `test_p18_security.py`).
- Templates carry the house governance: handlers restricted to
  `core.echo_check` / `core.health_snapshot` / `core.noop`,
  quality criteria requiring evidence for claims, creation
  approval level 0.
