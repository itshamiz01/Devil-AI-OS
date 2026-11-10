# P-11 IMPLEMENTATION PLAN — Premium Command Center (§3.4 / §29)

Companion to `P11_PRE_IMPLEMENTATION_AUDIT.md`. Stage order follows §29 exactly.

## Navigation architecture (final)

AppShell: left Sidebar (collapsible) · TopStatusBar (identity, system state, local
time in configured timezone, AI provider status, active agents/tasks, pending
approvals, critical-alert indicator, owner session controls) · main content ·
notification layer · command palette (Ctrl/Cmd-K).

Routes (hash-based): `#/overview` · `#/intelligence` · `#/opportunities` ·
`#/opportunities/:id` · `#/agents` · `#/agents/:id` · `#/execution` · `#/businesses` ·
`#/businesses/:id` · `#/finance` · `#/survival` · `#/memory` · `#/security` ·
`#/approvals` · `#/operations` · `#/reports` · `#/settings`. Detail routes are real
deep links (back/forward via hashchange). Counters (pending approvals, critical
alerts) render only when the count is > 0 / data exists (§5.1).

## Design system (§4, §21)

Tokens (CSS custom properties): charcoal surfaces (`--bg`, `--surface`, `--surface-2`),
warm metallic accent (`--accent` gold/olive), meaning colors `--ok/--warn/--bad/--info/
--neutral`, typography scale, spacing/border/radius/shadow tokens, breakpoints
(1920/1440/1366/tablet/mobile bands), `prefers-reduced-motion` respected, tabular
numerals for money (`font-variant-numeric: tabular-nums`).

Components (shared, `frontend/src/components/`): AppShell, Sidebar, TopStatusBar,
PageHeader, MetricCard, StatusBadge, AlertCard, AgentCard, BusinessCard,
OpportunityCard, TaskCard, ApprovalCard, ActivityFeed, DataTable, FilterBar,
SearchPanel, ChartPanel (+ hand-rolled SVG LineChart/BarChart), EmptyState,
ErrorState, LoadingState, ConfirmationDialog, DetailDrawer, Timeline,
ProgressIndicator, FreshnessBar (last-updated / stale / connection state, §22.4).

## Backend additions (smallest honest set)

New module `app/dashboard/` (service) + `app/api/routes/dashboard.py` +
`app/database/models/dashboard.py` (2 tables) + additive migration from
`e37d00443d20`:

- `GET /dashboard/overview` — operating state, mode, KPI set (each metric: value,
  period, source, measured-at), built from the owning engines' status calls.
- `GET /dashboard/system-health` — per-subsystem checks from real endpoints
  (backend lifecycle, database, AI providers, queue, memory store, browser
  automation, security, workers) — each `ok/degraded/down/unavailable` from evidence.
- `GET /dashboard/activity?limit=` — persisted events feed (source-linked).
- `GET /dashboard/attention` — pending approvals, failed tasks (24h), survival
  warnings, budget alerts, open security incidents/alerts; severity-sorted.
- `GET /dashboard/{agents,businesses,opportunities,execution,finance,security}/summary`
  — thin aggregations over the owning engines (finance via P-07 `consolidated()`).
- `GET /dashboard/notifications`, `POST /dashboard/notifications/{id}/read`,
  `POST /dashboard/notifications/{id}/dismiss` — derived notifications + per-principal
  read/dismiss state (critical security/financial notifications cannot be dismissed,
  §5.4: the dismiss endpoint refuses them with a structured error).
- `GET /dashboard/search?q=` — scoped search across businesses, agents,
  opportunities, tasks, memory records, audit events; per-type cap; backend auth.
- `GET /dashboard/approvals/summary` — pending counts by source (P-01 approvals,
  financial approvals, agent-factory requests).
- `GET/PUT /dashboard/preferences` — principal-scoped dashboard preferences
  (sidebar collapsed, default landing view, timezone, currency display, density).

All dashboard routes require `read_system_data` (preferences: any authenticated
principal, own record only). FastAPI serves the built frontend at `/app` when
`frontend/dist` exists (static mount added in `app/main.py`, no route conflicts:
API stays under `/api/v1`).

## Stage plan (§29)

1. **Audit + foundation** — this audit + plan; design tokens; AppShell; API client
   (envelope-aware, bearer auth, timeout/cancel, typed errors); hash router.
2. **Overview + global** — sidebar/topbar, Overview (state, KPIs, health, activity,
   attention), notifications, backend dashboard aggregations + migration.
3. **Operational** — Intelligence (missions/plans/decisions; no fake streaming),
   Agents (+detail +lifecycle controls), Execution (requests/tasks + controls),
   Opportunities (+detail).
4. **Business + finance** — Businesses (+detail), Finance (P-07 truth layout:
   forecast/invoiced/collected/refunded separated), Survival.
5. **Intelligence + security** — Memory, Security (status/alerts/sessions/audit +
   emergency controls via P-10), unified Approval Inbox.
6. **Operations + analytics** — Operations (system/resources/models/logs-as-events),
   Autonomous Operations (live feed from tasks/execution/approvals), Reports
   (CSV/JSON export with integrity header; PDF honestly not implemented),
   global search + command palette.
7. **Personalization + polish** — Settings (preferences API), responsive bands,
   keyboard accessibility, loading/empty/error/stale states everywhere.
8. **Testing + final audit** — frontend Vitest suite (§28.1–28.4, scenario tests),
   backend dashboard tests + full 575-test regression (pruner method), live smoke
   (uvicorn + served frontend), implementation report (§31), tracker + README.

## Test strategy (§28)

- Frontend (Vitest/jsdom): router/navigation, sidebar collapse, API client envelope
  + failure handling, money formatting (minor units, currency, tabular), Overview
  renders exact API values, empty-state (Scenario 12), disconnect/stale (Scenario 8),
  approval inbox exact parameters (Scenario 5) + decision posts and only confirms
  after backend response (Scenario 6), emergency stop confirmation gating
  (Scenario 10), finance classification separation (Scenario 4), agent suspend
  control calls the real endpoint (Scenario 9), long-running task shown as running,
  never completed (Scenario 14), matchMedia responsive hook (Scenario 11 support),
  unauthenticated → login gate (Scenario 13 frontend half).
- Backend (pytest, house style): dashboard auth required; overview/finance figures
  equal source endpoints on identical fixtures; preferences principal-scoping;
  notification read/dismiss + critical-dismiss refusal; search scoping; migration
  cycle 137→139→137→139; cross-business denial through the existing P-06 endpoints
  remains intact (Scenario 13 backend half).
- Smoke (real uvicorn + built frontend served at /app): login → overview values
  equal API values → create approval (service principal) → appears in inbox data →
  owner decision → emergency mode set via the same endpoint the UI calls → status
  reflects it → frontend HTML/assets served. Evidence to docs/reports/.
