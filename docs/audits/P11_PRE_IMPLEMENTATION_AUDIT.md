# P-11 PRE-IMPLEMENTATION AUDIT — Premium Command Center (Stage 1, §3)

**Date:** 9 Nov 2026 · **Scope:** audit of P-01–P-10 as actually implemented in staging
(`~/workspace/projects/autonomus-ai-os`), performed BEFORE any P-11 implementation code,
per P-11 §3 and the phase house pattern. All findings below were verified by direct
inspection and by booting the real application and calling its APIs (probe transcript
notes inline; the probe instance used a throwaway data directory, since removed).

---

## 1. Existing frontend inspection (§3.1) — FINDING: NO FRONTEND EXISTS

Verified three ways:

1. **Repository scan:** no `package.json`, no `*.tsx`/`*.jsx`/`*.vue`, no `vite.config*`,
   no application HTML anywhere in the project tree. The only `.html` files on disk are
   generated business-website artefacts inside `.tmp/` execution workspaces (outputs of
   P-05/P-06 test runs), not an application frontend.
2. **Prior phase audits agree:** the P-09 and P-10 Stage-1 audits both recorded "no
   frontend exists in staging"; the P-10 tracker row states the dashboard (§24) is
   NOT IMPLEMENTED with "no frontend in staging".
3. **Live backend self-report:** `GET /api/v1/business/status` returns
   `"frontend": "none in staging (API-only; P-11 owns the Command Center)"`.

**Consequence (§2 rule 5):** there is no existing frontend to preserve, extend, or
replace. P-11 creates the first frontend. Every §3.1 sub-item (framework, routing,
components, styling, state management, API client, auth flow, charts, error/loading
states) is therefore **absent — to be created**, not audited. Nothing working is
discarded by this phase.

## 2. Backend capability inspection (§3.2) — integration map

The backend is FastAPI (app factory `app.main:create_app`), all routers mounted under
`/api/v1`. **418 routes** across 16 routers (counted from route decorators). Uniform
response envelope: `{success, data, error, correlation_id, meta}`; list endpoints use
`meta = {total, limit, offset}`. Errors are structured
(`error: {code, message, details}`) with correct HTTP statuses — the frontend API
client is built against exactly this envelope.

**Authentication (§2 rule 8 — unchanged):** `POST /api/v1/auth/login {username,
password}` → `{access_token, token_type: "bearer", principal}`; every protected route
resolves `Authorization: Bearer <token>` via P-01 `AuthService` and enforces P-01
permissions through `require_permission(...)` dependencies (`get_principal` →
`PermissionEngine.check`, deny-by-default). The frontend stores the bearer token and
attaches it; it makes **no** authorization decisions.

Key consumed APIs (all verified live against a probe instance on an empty database;
sample shapes recorded during the audit):

| Dashboard need | Existing endpoint(s) | Verified shape (empty staging DB) |
|---|---|---|
| System status | `GET /system/status`, `GET /system/resources` | lifecycle_state, database_healthy, resources{cpu/memory/disk/process_count}, threshold_violations[], queue{capacity,depth,running,by_status} |
| Health | `GET /health/live` (public), `/health/ready`, `/health` | liveness without auth; readiness gated by `read_system_data` |
| Security posture | `GET /security/status` | mode, financial_suspension, active_sessions, active_agents, pending_approvals, open_alerts, recent_security_events, latest_backup, audit_chain{ok, chain_length, unsealed_events} |
| Approvals (unified source) | `GET /approvals?status=`, `GET /approvals/{id}`, `POST /approvals`, `POST /approvals/{id}/decision` | ApprovalOut: id, requesting_principal_{type,id}, action, resource, risk_classification, reason, requested_permissions, **parameters (exact)**, **parameters_hash**, status, approver_id, decision_at, expires_at, created_at. Decision requires `approve_actions`; P-10 service layer enforces role check + non-owner self-approval refusal; `task.execute` approvals re-verify the parameter binding before releasing the task. |
| Tasks | `GET /tasks`, `GET /tasks/{id}`, `POST /tasks`, `.../pause|resume|cancel|retry` | paged list envelope |
| Agents | `GET /agents`, `/agents/{id}` (+ assignments, permissions, health, metrics, events, config-history, memory), `POST /agents/{id}/suspend|resume|retire|assign`, permission request/approve/revoke | paged; lifecycle owned by P-04 |
| Agent factory | `GET /agent-factory/status` (+ requests, resources, scaling, templates) | total_agents, agents_by_status, active_agents, limits, resource_pressure, queue |
| Intelligence | `GET/POST /missions`, `/missions/{id}/plan`, `GET /plans/{id}` (+ approve, execute, explanation), `GET /decisions`, `GET /models/status`, `GET/PUT /models/profiles` | models/status: mode, providers{ollama, cloud}{available, detail, models}, configured_profiles, planner_default (deterministic planner stated honestly) |
| Opportunities | `GET /opportunities/status`, `/opportunities` (+ detail, evidence, research, validation, history, report), `/opportunities/rankings`, `/opportunities/research-queue` | status: opportunities_by_status, total, sources_registered/enabled, scoring_version |
| Execution | `GET /execution/status`, `/execution/requests` (+ detail, audit, evidence), `/execution/workflows`, `/execution/workflow-runs`, `/execution/tools`, `/execution/health-report` | status: requests_by_status (15 states), runs_total, workflow_runs_by_status, ceilings, emergency_stop |
| Businesses | `GET /business/status`, `/business/businesses` (+ detail, lifecycle, blueprint, readiness, assets, assignments, financial-inputs…), transitions via `POST /business/businesses/{id}/transition` etc. | status: businesses count, templates, min_validation_level, explicit no-money-movement / no-publishing honesty strings |
| Finance (P-07, sole authority) | `GET /financial/overview`, `/financial/dashboard`, `/financial/businesses/{id}/summary|available-cash|profitability|cashflow|indicators`, `/financial/revenue`, `/financial/expenses`, `/financial/ledger/*`, `/financial/budgets` (+ utilisation), `/financial/alerts`, `/financial/approvals`, `/financial/spending-requests`, `/financial/reports/*`, `/financial/forecasts` (+ vs-actual) | overview: currency (INR), businesses[], totals{net_collected_minor, expenses_minor, net_profit_minor}, internal_transfers_excluded, §14 consolidation note. dashboard: businesses[] with projected vs collected as **separate columns by design**, open_alerts |
| Survival | `GET /survival/portfolio/overview`, `/survival/businesses/{id}/health` (+ snapshots), decisions, experiments, forecasts, scaling plans/assessments (router prefix `/survival`) | portfolio overview embeds P-07 consolidated figures verbatim, labelled `consolidated_source: p07.financial.consolidated` |
| Memory | `GET /memory/status`, `/memory` (list), `/memory/{id}` (+ sources, history), `/memory/analytics/overview`, `/memory/learning`, `/memory/contradictions/list`, `/memory/review/required`, `/memory/owner/preferences`, `/memory/owner/audit` | status: total_memories, by_layer, learning_records, vector_store{store: "sqlite-local", status, embedder: "local-hash-v1", honest Chroma note}, authority_boundary (Article 0) |
| Security ops | `GET /security/alerts|incidents|audit|audit/verify|auth/sessions|identities|capabilities|policies|secrets (metadata only)|backups|broker/decisions`, `POST /security/emergency/mode`, `POST /security/emergency/financial-suspension`, session revoke, TOTP verify | emergency mode changes are P-10-governed POSTs returning the new confirmed state |
| Events / activity | `GET /events` | persisted critical events only, permission-filtered: event_id, event_type, source, severity, payload, created_at |
| Audit | `GET /security/audit`, P-01 audit via security routes | SHA-256 hash chain (tamper-EVIDENT per P-10) |

## 3. Missing-API classification (§3.3)

| Proposed P-11 feature | Classification | Action |
|---|---|---|
| Overview KPIs, health, activity feed (§6) | **Partially supported** — data exists across ~10 endpoints | Add small scoped aggregation endpoints (`/dashboard/overview`, `/dashboard/system-health`, `/dashboard/activity`, `/dashboard/attention`) composing existing services; no new business data |
| Module summaries (§25 groupings) | **Partially supported** | Add `/dashboard/{agents,businesses,opportunities,execution,finance,security}/summary` thin aggregations over the owning engines' own status/summary calls (finance via P-07 `consolidated()` verbatim) |
| Unified Approval Inbox (§18) | **Fully supported** for P-01 approvals (exact parameters + hash shown, decision endpoint exists); financial approvals and agent-factory requests have their own list endpoints | Inbox reads `GET /approvals?status=pending` (+ counts from financial/agent-factory lists); decisions only via the existing governed endpoints. Aggregation endpoint `/dashboard/approvals/summary` for counts only |
| Notifications (§5.4) | **Backend integration required** — events/alerts/approvals exist, but read/dismiss state does not | Derive notifications server-side from pending approvals, open P-10 alerts, failed tasks, warning/error events; store ONLY per-principal read/dismiss state (dashboard-owned table) |
| Global search (§20) | **Backend integration required** | Add `GET /dashboard/search` querying existing tables (businesses, agents, opportunities, tasks, memory, audit) with per-type limits; backend authorization applies |
| Dashboard preferences (§24/§25) | **Backend integration required** | One dashboard-owned table + `GET/PUT /dashboard/preferences`, scoped to the calling principal |
| Master Intelligence chat (§7) | **Partially supported** — missions/plans/decisions APIs exist; **no streaming exists** | UI submits instructions as missions, shows plans + explanation + decisions. Streaming honestly marked NOT SUPPORTED by backend (no fake typing effect) |
| Real-time updates (§22.2) | **Partially supported** — no WebSocket/SSE infrastructure exists in the backend | Bounded polling of summary endpoints (active view only, paused when hidden), with freshness indicators (§22.4). Introducing WS/SSE is NOT the smallest extension; recorded as a limitation |
| Hardware telemetry (§16.2) | **Partially supported** — `/system/resources` gives CPU/RAM/disk/processes; **no GPU telemetry exists** | Display what exists; GPU shown as an explicit unavailable state, never invented |
| Scheduler view (§16.4) | **Partially supported** — task queue + workflow runs exist; no cron-style scheduler API | Operations view shows queue + workflow runs; recurring-schedule controls honestly marked not supported where no endpoint exists |
| Report export (§19.3) | **Partially supported** — P-07 report endpoints exist; no PDF generator anywhere | CSV/JSON export generated client-side from real API responses with an integrity header (timestamp, period, sources, definitions, actual-vs-forecast labels); **PDF export NOT IMPLEMENTED** (no backend capability; not faked) |
| Agent pause (§8.5, Scenario 9) | **Fully supported** via P-04 lifecycle: suspend/resume endpoints exist (agent "pause" = suspend in the backend's state machine; the UI labels it with the backend's own state names) | Wire controls to the real endpoints; UI updates only from the confirmed response |
| Emergency stop (§15.5, Scenario 10) | **Fully supported** — `POST /security/emergency/mode`, `POST /security/emergency/financial-suspension` | Confirmation dialog → POST → UI shows the state returned by the backend; never optimistic |

## 4. Stack decision (§3.1 consequence + task instruction) — WITH EVIDENCE

Environment evidence (measured during this audit):

- Node **v24.22.1**, npm **10.9.4** at `/usr/bin/node`, `/opt/hatch-image/bin/npm`;
  `npm ping` → PONG 581 ms (registry reachable from this staging host).
- Python 3.12.3 + existing backend `.venv` (FastAPI 0.115+, uvicorn, pytest).
- Disk: 148 GB free on the workspace volume (node_modules is affordable; `/tmp` is
  the constrained resource — 512 MB tmpfs, currently 1% used).
- No headless browser is installed (no Chromium/Chrome/Playwright browsers on disk) —
  responsive verification will be breakpoint/unit-level + served-page checks, and
  the gap reported honestly (see §6 risks).

Candidates considered:

| Candidate | Builds here? | Tests here? | Verdict |
|---|---|---|---|
| **Vite + React + TypeScript** | Yes — Vite 7 supports Node 24; registry reachable | Yes — Vitest + Testing Library + jsdom (pure Node, no browser needed) | **CHOSEN** |
| Vite + vanilla TypeScript | Yes | Yes (Vitest) | Rejected: 14 views + ~25 shared components (§21) in vanilla DOM means hand-rolling component/state machinery — more code, more defects, worse maintainability for the owner's future work |
| Next.js / SSR framework | Yes | Yes | Rejected: SSR server is unjustified weight for a local-first single-owner console on modest hardware (i7-4712HQ, 16 GB, CPU-only); the FastAPI backend already exists — a static SPA served by it is the smaller, honest architecture |
| Python-served templates (Jinja) | Yes | Partial (no component model) | Rejected: cannot meet §21 component library / §22 state separation / §28 interaction-test expectations without rebuilding a JS framework by hand |

**Chosen stack:** Vite + React + TypeScript (strict), Vitest + @testing-library/react
+ jsdom for tests, hand-rolled design-token CSS (custom properties; no utility
framework — the §4 premium dark identity is token-driven and a framework would fight
it), hand-rolled SVG chart components (no chart library is installed anywhere in the
project — §21 permits one consistent library; a tiny in-house chart set keeps the
bundle small on modest hardware and every chart is fed real API series), and a minimal
hash-based router (deep links + back/forward via `hashchange`; zero extra dependency;
works identically when the bundle is later wrapped for Windows desktop). The built
bundle is served by the existing FastAPI app under `/app` (static mount, only when
the build output exists) — local-first, single process, no new server.

State management: React context + a small typed API client with request
cancellation/timeout (§22.1, §22.3 separation: server state fetched per view,
auth state in context, UI state local). No external state library — the data model
is request/response, and adding one is not the smallest honest choice.

## 5. Risks and dependencies

- **R1 — npm install size/time on a shared VM.** Mitigation: minimal dependency set
  (react, react-dom; dev: vite, typescript, vitest, jsdom, testing-library). Install
  once, into `frontend/node_modules` (excluded from the transfer zip).
- **R2 — /tmp exhaustion** by backend pytest (known lesson) and npm caches. Mitigation:
  house pruner method for the final regression run; `df -h /tmp` before/after, reported.
- **R3 — No headless browser:** §28.5 viewport checks cannot be true render tests.
  Mitigation: breakpoint logic + matchMedia hook tests, CSS contains the five
  breakpoint bands, served-page smoke; gap stated in the report, never smoothed.
- **R4 — Aggregation drift:** dashboard totals must equal the owning engines' own
  endpoints. Mitigation: aggregations call the same services (finance via P-07
  `consolidated()` verbatim); backend tests assert dashboard figures equal the
  source endpoints' figures on identical data; the smoke re-checks equality live.
- **R5 — Scope:** §5–§24 describe 14 views. Mitigation: shared component library
  first (§21), views composed from it; every control wired to a real endpoint or
  the feature is visibly marked and reported NOT IMPLEMENTED — no mockup screens.

## 6. What P-11 will NOT do (boundaries)

No new business/financial/agent/memory/security systems; no backend engine redesign;
no constitution changes; no P-12. Financial figures only from P-07. Authorization
only from P-01/P-10. New persistence is limited to two dashboard-owned tables
(preferences; notification read/dismiss state), additive migration from head
`e37d00443d20` (137 → 139 tables).
