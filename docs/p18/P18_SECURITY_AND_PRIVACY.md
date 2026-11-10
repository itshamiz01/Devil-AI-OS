# P-18 Security & Privacy (§15/§21)

## Authority posture

- **Writes are owner-only, in-service** (`_require_owner`):
  onboarding, fulfilment, tickets, KB publication, communications,
  feedback, health computation, quality reviews, resolutions and
  settings all refuse agent/service/external principals with a
  denial audit event where the surface is read-gated.
- **Customer reads are owner/system-only** (`_require_reader`):
  customer data is restricted; violations are audited as
  `experience.isolation_violation` before refusal.
- **Cross-business isolation:** a customer, template, ticket,
  incident or article of business A is indistinguishable from
  missing when addressed under business B (NotFound, never a
  leak). Cross-business aggregates are owner/system-only (P-13
  posture) and computed live per business.

## Financial safety

- P-18 tables carry **no money columns** (schema-guard test).
- Refunds execute only via P-07 `create_refund` against a
  verified collected revenue record, capped by P-07 at the
  original payment; goodwill only as a P-07 spending request in
  P-07's own approval workflow. Both require a prior
  hash-bound P-01 owner approval of the resolution
  recommendation; P-18 stores only returned ids.
- There is **no refund-promise communication kind**: a message
  can never commit the business financially.

## Privacy & consent

- Communications require, in order: communications not stopped
  → consent `granted`/`not_required` on the P-17 record
  (withdrawn blocks everything) → P-17 suppression list
  (dedupe key / email identity) → per-record opt-out of
  non-essential kinds → dedupe → 30-day frequency cap. Sensitive
  kinds additionally require a P-01 owner approval.
- Feedback is recorded or owner-declared only; AI-estimated
  sentiment does not exist. Health classifications persist
  factors and evidence and are labelled service-health signals,
  never churn predictions.
- The support assistant is extractive over approved knowledge:
  it cannot invent policy, and high-impact topics (refund,
  legal, chargeback…) force human review even when grounded.

## Article 0

P-18 modifies no governance, safety or financial-authority
rule; Constitution/ADRs were not touched; approvals are
single-use hash-bound P-01 records consumed by P-07 paths as
before. Audit events are written for creations, transitions,
escalations, approvals, executions, dispatches and settings
changes.
