# P-18 Integration Report

P-18 is a coordinating layer; every integration is an existing
engine consumed through its governed surface. Nothing was
rebuilt, forked or bypassed.

| Authority | How P-18 integrates | Proof |
|---|---|---|
| P-17 customers | `crm_customers` referenced by id everywhere; customer 360 embeds the P-17 record; suppressions read from P-17's `lead_suppressions`; consent/preferences read from the P-17 record | integration + security tests; schema guard (no cx customer table) |
| P-07 money | purchases read live by `p07_customer_ref`; refunds via `RevenueService.create_refund` (verified revenue, P-07 cap); goodwill via `BudgetService.request_spend` in P-07's approval flow; P-18 write flows leave P-07 records solely P-07-shaped | refund/goodwill integration tests; smoke §8 |
| P-16 profitability gate | untouched and not consulted by P-18 decisions (service recovery is not expansion); no gate code modified | full regression (P-16 suites green) |
| P-12 workflows | escalations and success-task follow-ups are P-12 DRAFT workflows via `OperationsService.create_workflow`, idempotency-keyed per ticket+level / per task | integration tests assert workflow status DRAFT |
| P-01 tasks/approvals | SLA timers are *not* a new scheduler: detection is an on-demand deterministic pass (P-15 pattern); approvals are hash-bound P-01 records via the P-08/P-16/P-17 pattern | security tests (agent approval refused) |
| P-09 memory | verified resolution patterns fed best-effort through `memory.ingestion.ingest`; feed failure never changes an experience result | verify-resolution path |
| P-04 agents | the 10 §14 roles seeded as factory templates; validation failures would be reported, not hidden | agent-roles endpoint; smoke §2 |
| P-10 security | no new auth/permission/audit system; P-18 reuses `AuditRepository`, P-01 approvals, P-10 posture (owner-gated writes, restricted reads) | security suite |
| P-13 portfolio | cross-business overview follows P-13's owner/system-only aggregate posture | portfolio overview test |
| P-06 businesses | businesses resolved through `BusinessService`; unknown business → 404 on every surface | all suites |

## External integrations

None connected — by design and by owner constraint. The
catalogue (support inbox, website chat, messaging, logistics
tracking, digital delivery, appointment scheduling, survey
delivery, communication transport) reports `not_configured` /
REQUIRES OWNER CONFIGURATION on every surface, and dispatch is
attempted-and-blocked honestly rather than simulated as sent.
