# P-18 Data Model

Migration `218ddd92a0aa` (revises P-17 head `afe062122eb5`) adds
fifteen tables, all prefixed `cx_`, all additive; no earlier
table is altered. Physical schema: **224 tables** (223 metadata
+ `alembic_version`). Upgrade/downgrade cycle verified:
209 → 224 → 209 → 224.

## Tables

| Table | Purpose | Key references |
|---|---|---|
| `cx_lifecycle_templates` | §3 per-business lifecycle templates (stages JSON) | business_id |
| `cx_onboardings` | §4 onboarding workflows; steps mirror template stages | customer_id → `crm_customers.id`, template_id |
| `cx_fulfillments` | §5 fulfilment records (physical/digital/service) with status source labels | customer_id, revenue_id → P-07 (reference only) |
| `cx_sla_policies` | §7 owner-configured SLA targets per category (or `*`) | business_id |
| `cx_tickets` | §7 support cases with explainable priority breakdown | customer_id (nullable) |
| `cx_ticket_messages` | §7 case conversation history (internal notes flagged) | ticket_id |
| `cx_knowledge_articles` | §13 KB articles; versioned; approval workflow | business_id |
| `cx_support_answers` | §6 grounded answers with pinned article citations | ticket_id, customer_id |
| `cx_communications` | §8 queued operational communications (never sent) | customer_id, approval_id → P-01 |
| `cx_feedback` | §10 recorded feedback with source labels | customer_id |
| `cx_health_snapshots` | §12 health classifications with factors + evidence | customer_id |
| `cx_incidents` | §5/§7/§11 detected service incidents (idempotent per kind+record) | related record ids |
| `cx_resolutions` | §11 resolution/recovery cases | revenue_id → P-07, p07_refund_id, p07_spending_request_id, approval_id → P-01 |
| `cx_quality_reviews` | §9 QA sample reviews of tickets | ticket_id |
| `cx_success_tasks` | §12 proactive success tasks | customer_id, related_ref (may hold a P-12 workflow id) |

## Discipline

- **No money columns.** A named test asserts no `cx_` column is
  an amount/minor/currency/price/balance/cost/fee/charge column
  (`revenue_id` is a reference, not money). Refund/goodwill
  amounts are supplied by the owner at execution time and pass
  straight into P-07; P-18 stores only the ids P-07 returns.
- **No customer store.** Every customer-scoped row references
  `crm_customers.id` (P-17). A schema-guard test asserts no `cx_`
  table is a customer table.
- **No execution state.** Approvals are P-01 records (id only),
  escalations/follow-ups are P-12 workflows (id only), memory is
  P-09's (fed via ingestion), scheduling is P-01/P-12's.
- **Labelled evidence.** Feedback rows carry `source`
  (recorded | owner_declared) and `is_fixture`; fulfilment
  statuses carry `status_source` (manual | owner_declared |
  integration); health snapshots persist factors, evidence and
  confidence; domain-event timestamps are ISO strings (house
  pattern).
