# P-18 Customer Lifecycle (§3)

Thirteen business models have labelled **system-default**
lifecycles (`experience/constants.py: DEFAULT_LIFECYCLES`):
physical_product, digital_product, subscription, saas,
education, content_publishing, consulting, freelance, agency,
local_service, ai_product, membership, other. Every default
shares an opening (purchase completed → request received →
onboarding initiated → information verified) and a closing
(customer notified → assistance available → satisfaction
evaluated → success monitored), with a model-specific
preparation/fulfilment/delivery middle (e.g. saas provisions an
account, education enrols, local_service schedules an
appointment, physical_product prepares and delivers).

## Rules

- A business's own template (marked default for the model)
  **wins** over the system default; the source used is recorded
  on every onboarding (`business_template` | `system_default`) —
  never silently.
- Onboarding steps are the template stages of kind purchase,
  onboarding and verification; later stages are served by
  fulfilment records, tickets and communications.
- One active onboarding per customer per business: a second
  start returns the existing record with `already_existed`.
- Step completion drives state: first completed step starts the
  workflow; all steps completed/skipped completes it (timestamp
  recorded); a deterministic evaluation pass marks stale
  in-progress onboardings `stalled` and raises an
  `onboarding_stalled` incident.
- The onboarding dashboard reports totals by status, assistance
  queue, average completion hours (only from records with both
  timestamps) and success rate (completed / decided) — averages
  are never computed from partial data without saying so.
