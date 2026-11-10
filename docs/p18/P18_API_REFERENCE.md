# P-18 API Reference

Base: `/api/v1/experience`. Permissions mirror the house
pattern (read = `read_business_data`, write =
`modify_business_data`, govern = `approve_actions`); the
service additionally enforces owner-only writes and
owner/system-only reads — routes never widen service rules.
**53 routes** (OpenAPI total 642 paths).

## Engine

| Route | Purpose |
|---|---|
| GET `/experience/status` | engine posture, counts, authorities |
| GET/POST `/experience/settings` | owner governance (autonomy 0–3, communication stop, thresholds, health weights) |
| GET `/experience/integrations` | 8 surfaces, all `not_configured` |
| GET `/experience/agent-roles` | the 10 §14 P-04 templates and their capability posture |
| GET `/experience/overview` | cross-business aggregates (owner/system only) |

## Delivery

| Route | Purpose |
|---|---|
| POST/GET `/experience/businesses/{id}/templates` | lifecycle templates (§3) |
| POST/GET `/experience/businesses/{id}/onboardings` | start (dedupe per customer) / list |
| POST `/experience/onboardings/{id}/steps` | step completion; auto-completes the workflow |
| POST `/experience/onboardings/{id}/status` · `/assistance` | governed updates |
| GET `/experience/businesses/{id}/onboarding-dashboard` | §4 dashboard |
| POST/GET `/experience/businesses/{id}/fulfillments` | create (per-kind flow validated) / list |
| POST `/experience/fulfillments/{id}/transition` · `/milestones` · `/acceptance` | fulfilment lifecycle |
| POST `/experience/businesses/{id}/evaluate` · POST `/experience/evaluate` | deterministic incident detection (idempotent) |
| GET `/experience/businesses/{id}/incidents` · POST `/experience/incidents/{id}/transition` | incident handling |

## Support

| Route | Purpose |
|---|---|
| POST/GET `/experience/businesses/{id}/sla-policies` | owner-configured targets only |
| GET `/experience/businesses/{id}/sla-compliance` | computed, or NOT_AVAILABLE with reason |
| POST/GET `/experience/businesses/{id}/tickets` · GET `/experience/tickets/{id}` | cases with SLA state + messages |
| POST `/experience/tickets/{id}/transition` · `/assign` · `/messages` · `/escalate` | lifecycle; escalate creates a P-12 DRAFT workflow |
| POST/GET `/experience/businesses/{id}/articles` · GET `/kb-health` | knowledge base (§13) |
| POST `/experience/articles/{id}` · `/approve` · `/retire` · `/review` | edit bumps version and un-approves; approval is owner-only |
| POST `/experience/businesses/{id}/support/ask` | grounded answer (verified / partially_verified / insufficient_information / human_review_required) |
| GET `/experience/businesses/{id}/support/answers` | recorded answers |

## Engagement & insight

| Route | Purpose |
|---|---|
| POST/GET `/experience/businesses/{id}/communications` | queue with consent/suppression/dedupe/frequency checks |
| POST `/experience/communications/{id}/dispatch` | honestly blocked dispatch |
| GET `/experience/businesses/{id}/proactive` | computed follow-up candidates |
| POST/GET `/experience/businesses/{id}/feedback` | recorded feedback only |
| GET `/experience/businesses/{id}/metrics` | §16 metrics with sample sizes |
| POST/GET `/experience/businesses/{id}/customers/{cid}/health` · GET `/experience/businesses/{id}/health` | §12 classifications |
| GET `/experience/businesses/{id}/customers/{cid}` | customer 360 (P-07 purchases read live) |
| POST/GET `/experience/businesses/{id}/quality-reviews` · GET `/quality-summary` | §9 QA sampling |
| POST/GET `/experience/businesses/{id}/resolutions` · POST `/experience/resolutions/{id}/approve` · `/execute` · `/verify` | §11 recovery; execution is P-07-only |
| POST/GET `/experience/businesses/{id}/success-tasks` · POST `/experience/success-tasks/{id}/complete` | §12 internal follow-ups |
| GET `/experience/businesses/{id}/insights` · `/overview` | §19 patterns with evidence counts; business rollup |
