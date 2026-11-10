# P-17 ARCHITECTURE AND INTEGRATION REPORT

**Phase:** P-17 — Customer Acquisition, Marketing & Revenue Growth Engine
**Stage:** §26 Phase 1 (existing architecture audit) + §30 Steps 1–8
**Date:** 2026-11-10 (staging)
**Starting state (verified at P-16 close):** backend 873 passed / 0
failed, frontend 46/46 with clean strict build, live smoke 28/28,
migration head `ccd744b29e54`, 190 metadata / 191 physical tables,
classification READY FOR CONTROLLED PILOT (DEF-A1 Windows UNVERIFIED
and DEF-A2 no real LLM exercised — both stand, neither is faked here).

---

## 1. What already exists (audit of P-01–P-16)

| Need in P-17 | Existing owner | P-17 posture |
|---|---|---|
| Business identity + lifecycle | P-06 `BusinessCreationService` (`list_businesses`, `get_business`) | Referenced by id, never copied |
| Money: revenue, expenses, budgets, spend approvals | P-07 `FinancialService` (`revenue.metrics`, `expenses.totals/list_expenses`, `budgets.request_spend/approve_spend`, `p08_indicators`) | Read live; spend exists only as P-07 records (see §3) |
| Business-idea opportunities | P-03 `OpportunityService` | Untouched; P-17 sales opportunities are deal-level records, a different concept (§4) |
| Experiments with stop-loss | P-08 `SurvivalService.experiments` (pre-declaration §9.2, P-07 budget binding) | Marketing/A-B experiments hand off exactly like P-16 proposals do |
| Memory / learning | P-09 `MemoryService` | Verified outcomes fed best-effort, as in P-16 |
| Security, approvals, audit | P-10 + P-01 (`ApprovalService` hash-bound approvals, `AuditEvent`, permission engine) | Reused; P-17 adds no auth/approval/audit system |
| Command Center | P-11 SPA + per-phase views (P-13/P-15/P-16 patterns) | One new view on real `/growth/*` endpoints |
| Portfolio coordination | P-13 `PortfolioService` | Read for business context; P-17 keeps per-business separation (§20) |
| Reliability/readiness | P-15 | Untouched |
| Economy strategy + **profitability gate** | P-16 `EconomyService` (`engine_status().profitability_gate`, pure `economy.scoring.profitability_gate`) | **Consumed live** — P-17 expansion work is gated by it (§5) |
| Agents | P-04 Agent Factory (`agents.templates`) | The 17 §12 marketing roles are seeded as P-04 templates (§6) |
| Customer segments (declared) | P-16 `customer_segments` (market-level expansion records) | Not duplicated: P-17 personas/ICPs are per-business acquisition research; P-16 segments stay the market-expansion record |
| CRM | ClipOS had one; **AUTONOMUS has none** (P-06 owns business creation, P-07 owns customer_ref as a revenue field only) | P-17 builds the CRM layer the prompt's §11 conditional requires ("do not create a duplicate CRM *if one is already present*" — none is) |

## 2. What P-17 owns (new state)

One new package `app/growth/`, one models module
`app/database/models/growth.py`, one additive migration, one router
`app/api/routes/growth.py` under `/api/v1/growth`, one Command Center
view. Eighteen new tables, all P-17-owned commercial-growth state:

brand profiles (§6), customer personas (§4.1), ideal customer
profiles (§4.2), channel evaluations (§4.3), marketing strategies
(§5), campaigns (§7), content items (§6), leads (§8), lead
suppressions (§8), sales opportunities (§10), CRM customers (§11),
interactions (§8/§11), funnel events (§13), growth experiments
(§14), SEO records (§15), communication templates + messages (§16),
partnerships (§18).

**No ledger, balance or account columns exist in any P-17 table.**
Amount fields are one of: a budget *ceiling* (proposal data), an
*estimated* deal value (labelled ESTIMATE), or terms text. A named
test proves P-07's consolidated output is byte-equal before and
after every P-17 write flow (the P-16 pattern).

## 3. How money ties back (P-07 authority, §21/§22)

* **Actual campaign spend** is read from P-07 expense records with
  `category ∈ {marketing, advertising}` and
  `project_ref = "p17-campaign:<campaign_id>"`. P-17 never creates an
  expense directly. Its one spend path prepares a P-07
  **spending request** (`budgets.request_spend`, with the campaign
  `project_ref` attached) — the request then lives and dies entirely
  inside P-07's approval/execution workflow. The campaign stores
  only the returned request ids.
* **Attributed revenue** is read from P-07
  `revenue.metrics(...)["by_channel_minor"]`. Each campaign carries
  an `attribution_channel` tag (`p17-<code>`); revenue the owner
  records in P-07 under that channel is reported as *attributed
  verified collected revenue* — always labelled ATTRIBUTED, never
  "caused", never blended with accounting totals (§22: attribution
  is not causation; §21: attribution is not accounting revenue).
* **CAC** = eligible P-07 marketing-category paid expenses ÷ new
  CRM customers in the period; **INSUFFICIENT_DATA** when either
  side is missing. **LTV** separates *actual* collected per customer
  (P-07 revenue by `customer_ref`, a fact) from *projected* LTV
  (contribution-margin estimate, labelled ESTIMATE with its
  methodology — §17: revenue-based LTV is not profit-based LTV).

## 4. Name collisions avoided

`SalesOpportunity` (deal-level, §10) is distinct from P-03
`Opportunity` (business ideas) and P-16 `EconomicOpportunity`
(economy pipeline); the API and docs state the distinction wherever
the word appears. P-17 defines no class in the `Business*` namespace
(the P-06 schema guard, hit during P-16, is untouched).

## 5. The P-16 profitability gate in P-17 (§20/§24 + owner priority)

The gate is consumed live from P-16 (`engine_status` →
`profitability_gate`, computed from P-07 verified figures):

* Campaigns carry a `purpose` (`retention | conversion |
  acquisition | expansion`). **Expansion-purpose campaign approval
  is refused while the gate is closed**, unless the owner records a
  per-item override with a mandatory reason on the campaign itself
  (the P-16 mechanism; no global off-switch exists).
* Growth recommendations are ordered improve → diversify → capital
  efficiency → expansion (the owner's mechanical ordering), and
  expansion items are marked `gate_blocked` while the gate is
  closed.
* Strategy approval for expansion-kind strategies follows the same
  rule.

## 6. Agents (§12)

The 17 suggested roles are seeded as **P-04 agent templates**
through the existing factory (`agents.templates.create` + publish,
SYSTEM principal, idempotent by name) with per-role capability
scopes drawn only from the existing P-04 capability catalogue
(research roles read-only; content roles draft-only; the outreach
role receives **no** external-send capability because none exists in
the catalogue — documented, not simulated). P-17 builds no agent
orchestration of its own. Template configurations are built locally
in `app/growth/constants.py` in the P-04 shape (P-04's role taxonomy
is not modified).

## 7. Honest external states (no fake integrations)

No marketing platform, ad network, email transport, search console
or social platform is connected. `GET /growth/integrations` reports
every external surface as `not_configured` /
`REQUIRES OWNER CONFIGURATION`. Consequences, by design:

* Content can be drafted, reviewed and approved; "release" records
  an owner-attested external reference — the system posts nothing.
* Communications can be templated, approved and queued (consent,
  suppression and frequency checks all enforced at queue time);
  dispatch honestly returns `dispatch_blocked` — no message is ever
  recorded as sent or delivered.
* SEO "monitoring" is over owner-imported/declared records with
  mandatory source labels; there is no crawler and no search data
  feed.
* Paid-channel evaluations are decision support only; no ad account
  exists to spend through, and all spend still routes via P-07.

## 8. §30 Step 9 handling (approval before structural changes)

Per the owner's standing one-by-one instruction, the prompt's
internal wait-for-approval steps are handled P-14-style: this audit
and architecture came first, the conservative minimal options were
chosen (one additive migration; no changes to any earlier engine;
no new scheduler/CRM-duplication/agent platform; gate consumed, not
rebuilt), and every choice is reported in the gate summary. The
build did not stop mid-flight to wait.

## 9. Files created / modified

Created: `app/growth/{__init__,constants,scoring,service,
intelligence,campaigns,pipeline,engagement,analytics}.py`,
`app/database/models/growth.py`,
`app/database/migrations/versions/<new>_p17_customer_acquisition_marketing_revenue_growth.py`,
`app/api/routes/growth.py`, `tests/{p17_support,test_p17_unit,
test_p17_integration,test_p17_security,test_p17_scenarios}.py`,
`scripts/p17_smoke.py`, `frontend/src/views/Growth.tsx`,
`frontend/src/views/Growth.test.tsx`, `docs/p17/*.md` (22 documents).

Modified: `app/database/models/__init__.py` (register growth
models), `app/core/application.py` (construct + seed GrowthService
after P-16), `app/main.py` (router), `frontend/src/App.tsx` (route),
`frontend/src/components/shell.tsx` (nav), `docs/PHASE_TRACKER.md`
(P-17 row), and — only where P-15/P-16 precedent requires, each with
a P-17 disclosure comment — earlier tests pinning the exact physical
table count / metadata count / alembic head.
