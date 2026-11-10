# P-18 ARCHITECTURE — Customer Experience, Service Delivery & Customer Success Engine

**Stage:** architecture/audit first (the P-14/P-16/P-17 house shape).
This document records what the audit of the existing codebase found,
the gaps P-18 fills, and the conservative minimal design choices
taken where the prompt left discretion. Choices are flagged
**DECISION** so the gate summary can report them.

## 1. What already exists (audit findings)

| Capability the prompt asks for | Existing implementation | P-18 relationship |
|---|---|---|
| Customer records / CRM | P-17 `crm_customers` — one record per customer per business, dedupe by contact, `p07_customer_ref`, consent status, preferences, lifecycle stage | **Reused as the only customer store.** P-18 rows reference `crm_customers.id`. No second customer table (§2.3 rule 7; build brief lock). |
| Purchase facts | P-07 revenue records carry `customer_ref`; read live via `financial.revenue.list_revenue` | Read live by the customer's `p07_customer_ref`. P-18 stores no purchase facts. |
| Refunds | P-07 `RevenueService.create_refund` — verified collected revenue only, capped at the original amount, posts the reversal journal entry | P-18 prepares recommendations; execution calls P-07. P-18 moves no money. |
| Goodwill / compensation spend | P-07 `BudgetService.request_spend` → owner approval → expense records | P-18 prepares the request through P-07; the amount lives in P-07's `SpendingRequest` row, never in a P-18 table. |
| Marketing communications | P-17 `communication_templates` / `communication_messages` (queue, never send; dispatch honestly `dispatch_blocked`) | P-17 keeps marketing comms. P-18 §8 *operational/service* comms are a separate domain and get their own record (the §20 entity list names `CommunicationRecord` for P-18), following the identical queue-never-send discipline. |
| Suppression / consent | P-17 `lead_suppressions` per business by dedupe key; `CrmCustomer.consent_status`, `preferences.communication_opt_in` | P-18 checks both before queueing any service communication. |
| Workflows / scheduled follow-ups | P-12 `OperationsService.create_workflow` (structured steps, idempotency keys); P-13 precedent: sibling engines create P-12 workflows from their services | Escalations and follow-ups create P-12 workflows in DRAFT. No new scheduler (§2.3 rule 6). |
| Timers / condition evaluation | P-15 reliability evaluates conditions on demand (`evaluate_incidents`) beside the P-12 loop | P-18 SLA/fulfillment evaluation is a deterministic on-demand pass in the same pattern. No new loop, no new scheduler. |
| Approvals | P-01 hash-bound approvals (`ApprovalService`, `verify_binding`) | Reused on the P-08/P-16/P-17 pattern for sensitive P-18 decisions (recovery execution, policy-sensitive KB approval stays owner-gated in-service). |
| Memory / learning | P-09 `memory.ingestion.ingest` | Resolved-issue patterns and verified service findings fed best-effort (the P-14 I6 posture: a feed failure never changes the P-18 result). |
| Agent factory | P-04 templates seeded idempotently by name (P-17 precedent) | The ten §14 roles are seeded as P-04 templates with catalogue capabilities only. |
| Business identity/lifecycle | P-06 `BusinessService` | Referenced, never copied. Every P-18 row carries `business_id` and is validated against P-06. |
| Profitability gate | P-16 `EconomyService.engine_status` | Untouched and unconsulted-by-default: P-18 is a service layer, not an expansion layer. It neither rebuilds nor bypasses the gate. |
| Financial authority | P-07 | Untouched. **No P-18 table carries a money column** (schema-asserted by test, the P-17 discipline). |
| Frontend | P-11 Command Center (Vite + React 19 + TS), one view per engine (P-16/P-17 pattern) | One new `Experience` view + nav item on real `/experience/*` endpoints. |

## 2. Gaps P-18 fills (nothing else builds these)

1. Post-purchase lifecycle state per customer (§3): onboarding,
   fulfillment, support, satisfaction, success — P-17 ends at
   conversion; nothing tracked delivery or service afterwards.
2. Configurable lifecycle templates by business model (§3).
3. Onboarding workflows with stall detection (§4).
4. Fulfillment records for physical / digital / service models with
   delay & failure detection that raises actionable incidents (§5).
5. Support tickets with explainable priority, lifecycle, SLA
   tracking against *owner-configured* policies (§7).
6. A knowledge-grounded support assistant that answers **only** from
   approved knowledge articles, classifies its confidence, and
   escalates instead of inventing policy (§6).
7. Operational customer communications under consent, with the
   queue-never-send honesty of P-17 (§8).
8. QA sampling reviews with documented scoring (§9), feedback
   collection and experience metrics with insufficient-data
   discipline (§10).
9. Issue resolution / service recovery that prepares P-07 actions
   but never executes money itself (§11).
10. Customer health classification from recorded signals only —
    explicitly not a churn prediction (§12).
11. A versioned, approval-gated knowledge base (§13).

## 3. Design decisions (conservative minimal options)

- **DECISION D1 — package shape.** New package `app/experience/`
  with `ExperienceService` composed over the assembled `Application`
  from mixins (`delivery`, `support`, `engage`, `insight`), pure
  scoring in `scoring.py`, vocabularies in `constants.py` — the
  exact P-16/P-17 shape. Models in
  `app/database/models/experience.py`, all classes prefixed `Cx`
  (the P-06 schema guard owns the `Business*` namespace; P-16 hit
  that collision and the guard stays untouched).
- **DECISION D2 — no money columns, no stored amounts.** Refund and
  compensation recommendations store *references and basis only*
  (P-07 revenue id, basis full/partial, reason). The amount is
  supplied by the owner in the execution request and passes straight
  into P-07 (`create_refund` / `request_spend`); P-18 stores only
  the ids P-07 returns. This is stricter than the P-13/P-16
  labelled-proposal precedent and matches the build brief's lock.
- **DECISION D3 — SLA policies are owner-configured or absent.**
  No seeded defaults: a business without a policy gets
  `sla: not_configured` on its tickets and `NOT_AVAILABLE`
  compliance metrics. The system never invents a contractual SLA
  (§7). Evaluation is computed from recorded timestamps on demand.
- **DECISION D4 — the support assistant is deterministic and
  extractive.** No LLM has ever been exercised in this system
  (DEF-A2) and none is faked here. The assistant retrieves approved
  KB articles by keyword overlap, answers by quoting the approved
  article (with article id + version citation), classifies
  confidence (`verified` / `partially_verified` /
  `insufficient_information` / `human_review_required`), and on
  insufficient information creates/escalates a ticket instead of
  answering. Policy invention is therefore impossible by
  construction and is covered by a refusal test.
- **DECISION D5 — health is a service-health classification, not
  churn.** Deterministic rules over recorded signals (onboarding
  state, open/critical tickets, reopens, fulfillment problems,
  recorded feedback). Every snapshot persists factors, evidence,
  confidence and a recommended next action (§12). No signal →
  `insufficient_data`, never a guessed classification.
- **DECISION D6 — metrics never compute from missing data.** CSAT /
  NPS / effort / complaint rate / repeat-issue rate /
  first-contact resolution each return `computed` with a sample
  size or `INSUFFICIENT_DATA` / `NOT_AVAILABLE` (§10). Feedback
  rows carry `source` (`recorded` | `owner_declared`) and
  `is_fixture`; AI-estimated sentiment does not exist in P-18.
- **DECISION D7 — autonomy posture.** Settings carry the §18
  levels 0–3, default **1 (recommendations)**. Writes are
  owner-gated in-service (the P-13/P-16/P-17 posture); reads are
  owner/system-only because customer data is restricted.
  Evaluation passes (delay/SLA detection, escalation workflow
  creation) are internal, idempotent and audited; customer-facing
  sends do not exist (no transport), so Level-3 bounded actions
  can never reach a customer unapproved.
- **DECISION D8 — escalation transport.** An escalation creates a
  P-12 workflow in DRAFT (structured steps, idempotency key
  `p18-escalation:<ticket_id>:<level>`) on the P-13 precedent, and
  records its id on the ticket. P-18 builds no queue of its own.

## 4. New tables (15, all additive, migration on head `afe062122eb5`)

`cx_lifecycle_templates`, `cx_onboardings`, `cx_fulfillments`,
`cx_tickets`, `cx_ticket_messages`, `cx_knowledge_articles`,
`cx_support_answers`, `cx_communications`, `cx_feedback`,
`cx_health_snapshots`, `cx_incidents`, `cx_resolutions`,
`cx_sla_policies`, `cx_quality_reviews`, `cx_success_tasks`.

Every table: `business_id` indexed, `created_by`, timestamps;
customer-scoped tables reference `crm_customers.id` (plain string
reference, the house pattern — cross-module FKs are not used
between engine tables). No money column exists in any of them.

## 5. What P-18 deliberately does not do

- No customer store, no order store: purchases are P-07 facts read
  live; a fulfillment references the P-07 revenue record / external
  order reference it fulfils.
- No sending: no support channel is connected (all integrations
  report `not_configured` / REQUIRES OWNER CONFIGURATION).
- No shipment fabrication: fulfillment tracking fields carry a
  `source` label (`manual` | `owner_declared` | `integration`);
  unverified stays unverified.
- No retention campaigns: P-17 owns commercial retention; P-18
  supplies verified service intelligence to it (§16 contract,
  documented in P18_INTEGRATION_REPORT.md).
- No modification of P-01/P-10 auth (the P-17 boot-window
  observation is carried, not chased).
