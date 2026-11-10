# AUTONOMUS — Post-Completion Expansion Pack: Gate 2 Readiness Review

**Date:** 2026-11-10 · **Scope:** audit only — no production code was
modified and no expansion feature was built. **Method:** every claim
below is backed by an artifact produced during this review or by a
named pre-existing evidence file. Supporting artifacts:
`INVENTORY_EVIDENCE.txt`, `TABLE_INVENTORY.json`,
`BACKUP_RESTORE_EVIDENCE.txt`, `REGRESSION_EVIDENCE.txt`,
`inventory_scan.py`, `backup_restore_drill.py` (all in this folder).

**Gate definitions (pack §5):** Gate 1 = original OS complete, all
existing acceptance tests pass. Gate 2 = architecture map, API
contracts, database inventory, permission model and **backup
verified** before any extension is written.

**Starting state (independently re-verified where marked ✓):**
backend 953 tests, frontend 52 tests, migration head
`218ddd92a0aa`, 224 physical tables, classification READY FOR
CONTROLLED PILOT. Standing open items carried into this review:
DEF-A1 Windows UNVERIFIED, DEF-A2 no real LLM ever exercised,
DEF-A8 no real pilot opportunity yet.

---

## 1. Architecture map

### 1.1 Composition root

One process, one composition object. `app/main.py` builds a FastAPI
app (title "AUTONOMUS Core OS", version `0.1.0`) around a single
`app/core/application.py:Application`, which wires every service at
startup in dependency order:

`engine/session factory → PermissionEngine + ApprovalService (P-01)
→ EventBus → SystemMonitor → TaskManager (P-01) → AuthService →
Intelligence (P-02) → Opportunities (P-03) → AgentFactory (P-04) →
Execution (P-05) → Business (P-06) → Financial (P-07) → Survival
(P-08) → Memory (P-09) → Security (P-10) → Operations (P-12) →
Portfolio (P-13) → Reliability (P-15) → Economy (P-16) → Growth
(P-17) → Experience (P-18)`; the dashboard (P-11) is a read-model
layer over the same services. The P-12 operations scheduler and the
P-15 resource sampler run as asyncio loops inside the same process
(single-process design — a recorded P-12 limitation). Interrupted
tasks and workflows are recovered at boot. The built frontend is
served by the same process at `/app`; the API stays authoritative
under `/api/v1`.

### 1.2 Ownership map (who owns what)

| Concern | Owner | Evidence |
|---|---|---|
| Scheduling / task queue | P-01 `TaskManager`; P-12 operations loop feeds it (not a second scheduler) | `app/tasks/`, `app/operations/` |
| Workflow planning | P-12 planner — dependency DAG, cycle-rejecting, step keys + `depends_on` | `app/operations/planner.py` |
| Memory / learning | P-09 only — ingestion, retrieval, SQLite-backed vector store, `local-hash-v1` embedder | `app/memory/` |
| Finance (sole authority) | P-07 `FinancialService` — double-entry, integer minor units | `app/financial/`, 27 tables |
| Security / permissions | P-10 `SecurityService` + PermissionBroker over the P-01 engine | `app/security/`, `app/permissions/` |
| Approvals | P-01 `ApprovalService` (hash-bound), consumed read-only by later phases | `app/permissions/approvals.py` |
| Customers | P-17 CRM (`crm_customers`); P-18 references it, owns no customer table | schema guard, P-18 tests |
| Events | `app/events/` EventBus — typed events, subscribers, dead-letter table (P-14) | `app/events/bus.py` |
| Execution / tools | P-05 adapter registry: api, browser, code, desktop (disabled), documents, filesystem | `app/execution/adapters/` |
| LLM access | P-02 `ModelProvider` interface — `OllamaProvider`, `FakeProvider`, `CloudProviderStub` | `app/intelligence/providers.py` |
| Monitoring | P-01 psutil metrics + P-15 reliability (sampler, incidents, readiness scorer, benchmarks) | `app/monitoring/`, `app/reliability/` |
| External integrations | **seed only** — one abstract contract, no registry, no concrete connector | `app/integrations/interfaces/base.py` (27 lines) |

Package sizes (backend `app/`, Python): api 42 files / ~10,900 lines;
database 54 / ~16,100 (models + repositories + migrations); financial
14 / ~5,300; execution 18 / ~4,500; growth 9 / ~4,400; operations 10 /
~4,200; survival 12 / ~4,200; experience 8 / ~4,100; business 11 /
~3,800; portfolio 12 / ~3,800; agents 11 / ~3,700; economy 9 / ~3,700;
security 15 / ~3,400; opportunities 13 / ~3,300; memory 10 / ~2,200;
intelligence 10 / ~1,600; reliability 5 / ~1,600; core 8 / ~940;
dashboard 2 / ~780; tasks 6 / ~650; events 4 / ~390; permissions 5 /
~340; monitoring 4 / ~105; integrations 3 / 27.

### 1.3 Frontend

Vite + React 19 + TypeScript SPA (`frontend/src/`): hash router
(`lib/router.ts`), typed API client (`lib/api.ts`), store
(`lib/store.tsx`), shell/cards/ui components, and 24 views — one per
engine (Overview, Agents, Intelligence, Opportunities, Execution,
Businesses, Finance, Survival, Memory, Security, Operations,
Portfolio, Performance, Economy, Growth, Experience, Approvals,
Reports, Settings, Autonomy, Login, …). Presentation only: the
frontend holds no authorization authority (package manifest states
this explicitly).

### 1.4 The seams an expansion feature attaches to

1. **A new service on the `Application` object**, built at startup
   after its dependencies — the pattern every phase P-02→P-18 used.
2. **A new router module** in `app/api/routes/` included under
   `/api/v1`, using `Depends(get_principal)` /
   `Depends(require_permission(...))` from `app/api/dependencies.py`.
3. **Additive tables** in a new `app/database/models/<feature>.py`
   module + one Alembic revision; no edits to existing tables.
4. **Authorization through the P-01 engine / P-10 broker** — never a
   private permission check (see §4).
5. **Events on the EventBus** for anything other modules should
   react to; **approvals via `ApprovalService`** for anything
   governed; **money only via P-07 service calls**.
6. **A Command Center view** following the established pattern,
   reading real endpoints only.

There is no plugin/extension loader: "extension" in this codebase
means a new first-party module composed exactly like a phase. That
is a strength for consistency and a constraint for the Universal
Integration Framework (see §7.2).

---

## 2. API contracts inventory

Source: the application's own OpenAPI schema, generated during this
review (OpenAPI 3.1.0; full per-group table in
`INVENTORY_EVIDENCE.txt`).

- **642 paths, 762 operations, 31 route groups** under `/api/v1`,
  served by 23 router modules. Largest surfaces: `/financial` 71
  paths, `/growth` 64, `/portfolio` 58, `/experience` 53,
  `/security` 50, `/survival` 48, `/economy` 46.
- **Versioning:** prefix-only. Everything lives under `/api/v1`;
  the app info version is `0.1.0` and has never been bumped across
  18 phases; there are no per-route versions, no deprecation or
  sunset headers, and no published changelog contract. Additive
  growth has been the de-facto policy (paths only ever added).
- **Auth model:** a single security scheme, HTTP Bearer. The token
  resolves to a `Principal` (`app/api/dependencies.py:get_principal`
  → `AuthService.resolve_bearer`); authorization is then either
  (a) a named permission via `require_permission(...)`, checked by
  the P-01 engine on every request, or (b) authentication-only at
  the route with policy enforced in the service layer (the P-01-era
  modules: tasks, agents, events, system, health, intelligence,
  agent-factory, opportunities, execution, approvals-via-inline).
- **Only 3 of 762 operations are public:** `GET /health/live`
  (liveness), `POST /auth/login`, and
  `POST /financial/payments/webhooks/{provider}` (inbound payment
  webhook — public by necessity; the provider integration behind it
  is NOT CONFIGURED, so nothing is processed today).
- **Response envelope is uniform:** `{success, data, error{code,
  message, details}, correlation_id, meta}` with a correlation-id
  middleware that also scopes bus events to the request trace.

### Inconsistencies an integration framework will trip over

1. **Two permission-binding conventions.** Business modules bind
   permissions from the `Permission` enum
   (`Permission.READ_BUSINESS_DATA` etc.); system modules bind raw
   string literals (`"read_system_data"`, `"modify_system_config"`
   in dashboard, reliability, security, and inline in approvals).
   The values agree today, but nothing enforces that agreement — a
   typo'd literal would silently create a permission nobody holds
   (deny-by-default fails safe, but the route would be dead). A
   connector framework generating clients from OpenAPI cannot see
   permission names at all: they are not in the schema.
2. **Two authorization depths.** Newer modules gate at the route
   (READ/WRITE/GOVERN tiers); P-01-era modules authenticate at the
   route and authorize inside services. A framework assuming
   route-level metadata describes access will misread the older
   surface.
3. **No machine-readable capability catalogue.** What an external
   system may call is discoverable only by reading route modules;
   the OpenAPI document carries operations and the bearer scheme,
   not permissions, risk levels, or approval requirements (those
   live in P-10 policy code). The Universal Integration Framework
   will have to define this contract layer — it does not exist yet.
4. **Version `0.1.0` since P-01.** Harmless internally; an external
   consumer cannot distinguish the P-18 surface from the P-01 one.

None of these block Gate 2. All four are precisely the class of
issue the Universal Integration Framework feature exists to fix,
and they are recorded here as its starting findings.

---

## 3. Database inventory

Source: SQLAlchemy metadata from the application itself
(`TABLE_INVENTORY.json` — every table with owner module and full
column list), cross-checked against a booted database in the
backup drill (§5).

- **223 metadata tables + `alembic_version` = 224 physical tables**
  in a migrated database ✓ (drill-verified).
- **Migration chain:** 18 Alembic revisions, single head
  `218ddd92a0aa` ✓ (`alembic heads`). Every phase P-06→P-18 added
  exactly one additive revision; cycle tests (upgrade/downgrade)
  are part of the suite.
- **Tables by owning model module:** financial 27 (P-07), portfolio
  19 (P-13), business 18 (P-06), growth 18 (P-17), survival 18
  (P-08), memory 15 (P-09), experience 15 (P-18), security 14
  (P-10), economy 14 (P-16), operations 14 (P-12), opportunities 11
  (P-03), core 10 (P-01), execution 10 (P-05), agents 9 (P-04),
  intelligence 5 (P-02), reliability 4 (P-15), dashboard 2 (P-11).

### Money-column scan (independent, all 223 tables)

Method: every column of every table scanned for money tokens
(`amount, minor, currency, price, balance, revenue, profit,
collected, journal, ledger, charge, fee`) — a broader net than any
single phase's schema-guard test. **50 tables** have at least one
hit; **20 are P-07's own** (`models.financial`). Classifying the
other 30 by inspection of what the column *is*:

- **References into P-07, not money:** `cx_fulfillments.revenue_id`,
  `cx_resolutions.revenue_id` (P-18 stores only the id P-07 returns).
- **Pre-declared caps and ceilings** (the Constitution's
  pre-declaration rule — budgets declared *before* spend, never
  records of spend): experiment/loss caps in P-08/P-16/P-17
  (`approved_budget_minor`, `max_acceptable_loss_minor`,
  `budget_ceiling_minor`), campaign ceilings (P-17), business
  declaration caps (P-06), recovery-plan budgets (P-08).
- **Estimates and proposals** (labelled as such in their names):
  `estimated_cost_minor` (P-08 decisions), `estimated_investment_minor`,
  `estimated_value_minor` (P-17 sales pipeline), allocation and
  scaling *proposals* (P-08/P-13/P-16), research-brief budgets (P-03).
- **Derived attribution:** `internal_cost_allocations.amount_minor`
  (P-13) — cost allocations computed from P-07 figures; an
  analytical record, not a book of account.
- **Descriptive text, not amounts:** `revenue_model`,
  `revenue_scenarios`, `price_assumption`, `fees`,
  `potential_revenue_impact` — labels and model descriptions.

**The decisive structural facts, verified by the scan:**

- **No table outside `models.financial` has a `journal` or `ledger`
  column — NONE.** Double-entry exists only in P-07.
- **No table outside `models.financial` has a `collected` or
  `balance` column — NONE.** Verified collected revenue and cash
  balances of record exist only in P-07 (`revenue_records`,
  `cash_balances`, `tax_records`).

So the accurate Gate 2 statement is: *P-07 is the sole keeper of
books, balances and collected revenue; other modules hold declared
caps, estimates, proposals and references — the pre-declaration
pattern the Constitution mandates — and move money only by calling
P-07.* (The looser slogan "no money columns outside P-07" is not
literally true and should not be used; the invariant that matters —
no second ledger, no second balance of record — holds without
exception.)

---

## 4. Permission model

### 4.1 The stack (three layers, one authority)

1. **P-01 PermissionEngine** (`app/permissions/engine.py`) — the
   single grant authority. Deny-by-default; evaluation order:
   explicit DB deny (principal, then role) → explicit DB allow
   (resource-scoped) → role default → DENY. Fails closed when
   permission data is unavailable. **Every check is written to
   `audit_events`.** Vocabulary: 5 principal types (owner, system,
   service, agent, external) × 12 permissions
   (`app/permissions/models.py`). Role defaults: owner = all;
   system = 7; agent = 5 (read/submit/cancel tasks, execute tools,
   read business data); service = 2; external = none. Three
   permissions additionally flag `requires_approval`:
   `request_financial_operations`, `modify_system_config`,
   `access_sensitive_data` — a grant alone never executes them.
2. **P-10 PermissionBroker** (`app/security/broker.py`) — the
   cross-module entry point for agent/tool authorization. It does
   **not** replace the engine; every broker decision passes through
   it. The broker adds, in order: security-mode gate (normal /
   safe_mode / emergency_stop), agent restriction overlays,
   business-scope enforcement, the engine check, and risk gates —
   Level 2 needs a capability token, Level 3 needs an owner-decided
   **hash-bound approval**. Decisions are recorded in
   `security_broker_decisions`; any internal error returns DENY
   (never raises, never implicitly allows); a Level ≥2 allow that
   cannot be recorded is denied.
3. **ApprovalService** (`app/permissions/approvals.py`) — approvals
   bound to the exact action + resource + parameters by SHA-256
   hash; parameter drift invalidates; single-use state machine
   (pending → approved/rejected/expired/cancelled); expiry;
   service-level enforcement (P-10 hardening) that the decider
   holds `approve_actions` and a non-owner may never approve their
   own request. Capability tokens (`security_capabilities`) are
   scoped, expiring and revocable.

Article 0 surfaces: security policy is versioned
(`security_policy_versions` with rollback); mode changes go through
the versioned policy path only; the audit chain
(`security_audit_chain`) is tamper-evident; secrets are a
metadata-only registry — values live in the owner's environment /
vault and are brokered at the moment of use by P-05's credential
broker, never stored, logged or returned (`app/security/secrets.py`).
The Windows vault/DPAPI backend is an interface whose status is
honestly REQUIRES OWNER CONFIGURATION on this host.

Identity today: owner account with scrypt password hashing, hashed
bearer sessions (`app_sessions`, 12 h expiry), login throttling
(`security_login_attempts`), owner-only session list/revoke
(P-10 `SessionService`), a TOTP verifier wired in the security
service. Carried P-10 limitations: MFA recovery codes NOT
IMPLEMENTED; **no device registry exists** (no device table or
device identity concept anywhere in the schema).

### 4.2 What a new feature must do to inherit this model

1. Take a `Principal` from `get_principal` — never parse tokens or
   invent an identity.
2. Gate routes with `require_permission(Permission.X)` using the
   **enum**, and check governed actions in the service layer too.
3. Route every agent/tool execution through
   `PermissionBroker.authorize(...)` with action, resource,
   business scope and parameters — so mode gates, restrictions,
   risk levels and the decision ledger apply unchanged.
4. For Level 3 / irreversible actions, create an `ApprovalService`
   request and consume it by `verify_binding` against the exact
   parameters at execution time. Never decide approvals in feature
   code.
5. Emit audit through the shared audit facade; emit facts on the
   EventBus rather than calling other modules' internals.
6. Store secrets only as metadata references (`env:NAME` /
   `windows-vault:NAME`); resolve via the credential broker at use
   time.
7. Add tables additively; keep money in P-07, customers in P-17,
   memory in P-09, scheduling in P-01/P-12.
8. Ship tests in the established pattern, including the negative
   ones (non-owner refused, agent refused, mis-bound approval
   refused, Article 0 schema guards where the feature touches a
   guarded invariant).

---

## 5. Backup — VERIFIED by exercise

The Gate 2 criterion is not "a backup feature exists" but "backup
verified". The existing mechanism was therefore exercised end to
end during this review. Full transcript:
`BACKUP_RESTORE_EVIDENCE.txt`; drill script:
`backup_restore_drill.py`. **Result: 18/18 checks passed.**

Mechanism (P-10, `app/security/backup.py`): owner-only
`BackupService.create_backup` takes a consistent copy via the
SQLite backup API, records a SHA-256 manifest + table inventory in
`security_backup_records`; `verify_backup` re-opens the copy
read-only and checks hash, inventory, `PRAGMA integrity_check` and
readability of the security state. Restoration is deliberately not
an in-app overwrite: `SecurityService.restore_preview` (P-14,
closing DEF-A4) requires a verified backup **and** an approved
hash-bound approval for `security.restore_backup`, takes a
pre-restore snapshot, and returns the manual plan
(`executed: false`); the file swap itself is the owner's step with
the app stopped, per `docs/security/INCIDENT_RESPONSE_PLAYBOOK.md`
§5.

The drill executed, against scratch databases under `/tmp`:

1. Booted a source application (production posture, auto-migrate):
   224 physical tables, integrity ok, `alembic_version =
   218ddd92a0aa` ✓.
2. Created backup A (owner): status `created`, 224-table inventory,
   SHA-256 recorded; **verified → `verified`** ✓.
3. Non-owner (agent principal) backup attempt → refused ✓.
4. **Negative control:** appended bytes to backup A's file and
   re-verified → `verify_failed`, "backup file hash does not match
   its manifest" ✓ — the manifest actually detects tampering.
5. Created backup B; ran `restore_preview` with a correctly bound
   approved approval → plan returned, nothing executed, snapshot
   taken ✓; a second approval bound to a *different* backup id was
   **refused** ✓.
6. Performed the documented manual restore: stopped the app, copied
   the live DB aside, copied backup B into place, started a fresh
   application on it → **database healthy, 224 tables, integrity
   ok, at migration head, sentinel row counts identical to the
   backup** (system_config 17, security_policy_versions 1,
   audit_events 3, sessions/permissions/agents/tasks 0) ✓, and an
   **owner login succeeded against the restored database**, resolving
   to the owner principal ✓.

Scope honesty: the drill DB was a freshly booted staging database
(startup-seeded defaults, small row counts), not a populated
production database; the mechanism — SQLite backup API + manifest +
file swap — is identical at any size, and the P-10 suite rehearses
the same cycle (its Scenario 13). What is proven: creation,
verification, tamper detection, the approval guard, and a real
restore boot. What is *not* provided by the current system:
scheduled/incremental backups, off-machine destinations, encryption
of backup files, or an in-app restore execution — those are the
Backup & Disaster Recovery feature's scope (§7.9), not Gate 2
blockers.

Two documentation defects found (documentation only, no code
impact): `backup.py`'s module docstring points at
`docs/security/EMERGENCY_RESPONSE.md` for the restore procedure,
but that document contains no restore procedure — the procedure
lives in `INCIDENT_RESPONSE_PLAYBOOK.md` §5. And `restore_preview`'s
plan cites the playbook correctly, so the stale pointer is confined
to the docstring.

---

## 6. Gate 1 evidence — core acceptance, re-run for this review

The full suites were re-run on the current code during this
review (no production code has changed since P-18 closed; the
review added files under `docs/expansion/` only — running the
suite also regenerated `docs/p14/P14_PERF_MEASUREMENTS.json`,
which the P-14 audit test rewrites on every run by design).

**Backend: 953 passed / 0 failed** — all 73 test files, run in 13
chunks over a C-locale-sorted file list with a per-chunk tmpfs
basetemp deleted after each chunk. `/tmp` was checked before the
run (2% used), monitored throughout (peak ~41%) and ended at 8%;
no disk-full event occurred, so no result needed the
environment-failure diagnosis. Chunk totals: 38 + 102 + 106 + 73 +
77 + 88 + 89 + 86 + 68 + 77 + 70 + 60 + 19 = **953** — exactly the
P-18 verified baseline, i.e. zero drift. Full transcript:
`REGRESSION_EVIDENCE.txt`.

**Frontend: 52 passed / 52 (15 test files)** via `vitest run`,
plus `tsc --noEmit` (the strict TypeScript half of the build)
exiting clean.

Gate 1's scope note: the pack defines Gate 1 as "P-00 to P-16
completed, P-17 per approved scope". The actual state exceeds it:
the full P-01 → P-18 roadmap is built and owner-accepted in
staging; P-00 remains partially open (environment audit and repo
creation are owner-machine items) without blocking any staging
work, per the owner's P-01 decision recorded in the phase tracker.

---

## 7. Per-feature readiness (pack's recommended dependency order)

Labels: **READY** = can start on owner approval with what exists;
**CONDITIONAL** = can start, with a named condition that bounds
what can be proven; **BLOCKED (staging)** = the decisive work
cannot be done or verified from this Linux staging VM at all.

### 7.1 Identity & Device Security — READY

*Reuse:* owner account (scrypt), hashed sessions with owner-only
list/revoke, login throttling, a wired TOTP verifier, the full
P-01/P-10 permission stack (§4), versioned policies, emergency
modes, audit chain. *Missing:* **any device concept** — no device
table, enrolment, trust status or session↔device binding exists
anywhere in the 223 tables; MFA recovery codes (carried P-10 gap);
passkeys/WebAuthn (nothing). *External dependencies:* none for the
core; hardware-bound device signals would need the owner's machine
to verify, and the pack itself warns against spoofable hardware
identifiers. *Risks:* the feature must extend P-10, never grow a
parallel auth path; it will touch the bearer-resolution path, where
the P-17 boot-window login observation (transient refusal of
correct credentials under load, self-healing, never root-caused)
should be re-checked as part of the work.

### 7.2 Universal Integration Framework — READY

*Reuse:* the `IntegrationAdapter` ABC (health/close) present since
P-01; `ModelProvider` as a proven instance of the pattern (3
implementations); P-05 credential broker + P-10 metadata-only
secret registry (env backend working); P-10 network egress guards;
honest NOT CONFIGURED integration surfaces in P-07/P-17/P-18 to
register. *Missing:* everything that makes it a *framework* — a
connector registry (no table, no lifecycle state), a contract
richer than health/close (capability discovery, request/response
validation, rate-limit handling), webhook signature validation,
developer template + test harness, a unified Command Center view.
The §2 findings (permission names invisible in OpenAPI, two
binding conventions, two authorization depths, version frozen at
0.1.0) are this feature's first work items. *Risks:* must not
become a second secret store (P-10 registry is the store) or a
second permission path (the broker is the gate); per the pack, no
provider may be claimed supported until its connector is
implemented and tested — the codebase's existing honesty pattern
already enforces this idiom.

### 7.3 Voice Assistant — CONDITIONAL

*Reuse:* everything downstream of transcription — the text command
path (Intelligence planner → tasks/agents → broker-gated execution
→ verified results), conversation context, approvals for
consequential actions, emergency controls a voice stop must map
to. *Missing:* **all audio.** A full-text search finds no speech,
microphone, wake-word, STT or TTS code anywhere in the backend;
no speech model has been selected or evaluated. *Condition:*
Def-A2 — no real LLM has ever been exercised, so even the text
path's real-model behaviour is unproven; and the owner's hardware
(i7-4712HQ, CPU-only inference, per the P-04 feasibility record)
bounds local speech-model choice. Microphone behaviour cannot be
tested from this VM. *Risks:* voice is a new input channel into
existing authority — it must inherit broker + approvals exactly
(wake word ≠ authentication), and uncertain commands must clarify
rather than execute, reusing the planner's honest unverified
states.

### 7.4 Windows Computer Control — BLOCKED (staging) for build/verify

*Reuse:* P-05's execution engine, adapter registry, policy and
workspace governance; the desktop adapter's defined action
interface (`launch_application`, `focus_window`, `observe_screen`,
`approved_click`, `approved_keyboard`, `close_application`) with a
deliberate no-elevation design (elevation returns
REQUIRES_HUMAN_ACTION); P-10 filesystem/command/download/content
guards; the P-02 verifier pattern for the VERIFY step.
*Missing:* the entire Windows implementation — UI Automation,
screen capture, dialog detection, input injection. The adapter
reports `enabled = False` by design off Windows. *Blocker:*
**DEF-A1 — the owner's Windows machine is a hard dependency.**
Nothing decisive in this feature can be implemented or tested
from this Linux VM; even the browser adapter's interactive
actions are ADAPTER_UNAVAILABLE in staging because no Chromium
binary could be downloaded into this sandbox (recorded P-05
finding). Interface and policy design can proceed; implementation
cannot be evidenced here. *Risks:* highest-risk feature in the
pack; untrusted content (web pages, documents) must never become
commands — P-10 content screening is the seam.

### 7.5 PC & System Management — CONDITIONAL

*Reuse:* psutil resource snapshots (CPU/memory/disk) with
thresholds and admission control (P-01 monitoring); P-15's sampler
history, incident register and resource-intelligence precedent; the
broker-gated action pattern for controls. *Missing:* temperatures,
GPU, process-level detail; **every control** (volume, brightness,
power mode, process termination, startup management, sleep /
restart / shutdown); Windows telemetry (WMI); a PC dashboard (the
Performance view shows the *application's* resources, not the
computer's). *Condition:* most metrics and all controls need the
owner's Windows machine (DEF-A1); hardware-dependent metrics must
be labelled unsupported where absent, as the pack requires.
*Risks:* destructive classes must be mapped onto P-10 risk levels
and the approval path (the pack's A–D classification is a mapping
exercise onto existing machinery, not new machinery); never
terminate critical processes or disable security software — hard
rules to encode as broker policy.

### 7.6 Personal Knowledge & File Intelligence — READY, with conditions

*Reuse:* P-09 wholesale — ingestion (classification, usefulness,
entity extraction over text), retrieval, knowledge records, the
SQLite vector store; P-05's documents/filesystem adapters and
workspace path policy; P-10 filesystem guards, data
classifications and prompt-injection screening. *Missing:*
document-format extraction — the documents adapter handles text
and CSV only; no PDF/DOCX/XLSX/PPTX extraction and no OCR exist;
no folder indexing with incremental refresh; no project-scoped
collections with page/sheet citations; no duplicate/version
comparison. *Conditions:* parsing libraries are local/open-source
(consistent with local-first), but the owner's folders live on his
Windows machine; and retrieval quality is capped by the
`local-hash-v1` embedder — semantic search needs a real embedding
model (DEF-A2 / CPU-only hardware bounds). *Risks:* the pack's
rule — reuse P-09, no competing memory database — makes the design
question "files *into* P-09 records with source references", and
per-folder consent/exclusion maps onto existing P-10
classifications.

### 7.7 Research & Verification Engine — READY, with conditions

*Reuse:* P-03's research heritage (sources, evidence grading,
validation, compliance; `research_briefs` with pre-declared
budgets); the P-02 verifier's tri-state honesty (verified /
failed / unverified — unverified is never reported as verified);
P-16's owner-declared market records with mandatory sources;
SSRF-guarded fetching. *Missing:* the general engine — question
decomposition, a source-evaluation framework, claim-level
verification states, contradiction handling, freshness re-checks —
as a reusable capability rather than opportunity-specific code.
*Conditions:* no search provider is configured, and synthesis
quality depends on a real LLM (DEF-A2); today's research machinery
is deterministic scoring over fetched/declared evidence.
*Risks:* fabricated citations are the core hazard; the codebase's
evidence-table + verifier idiom is the mitigation, and the pack's
own §7 rule applies — external pages are untrusted data, never
instructions.

### 7.8 Testing, Simulation & QA — READY

*Reuse:* the strongest base after Backup — a 953-test backend
suite + 52 frontend tests in a fixed unit/integration/security/
scenario pattern (re-run for this review, §6); P-14's system-wide
audit method and defect register; P-15's benchmark suite,
Production Readiness Scorer and release-gate precedent
(critical-issue withholding); labelled simulation (P-16's
SIMULATION-labelled stress scenarios, `FakeProvider`, fixture
labelling everywhere); migration cycle tests; the smoke-harness
pattern (14 scripts). *Missing:* a *central* QA surface —
orchestrating these as a product capability with a quality
dashboard; a runtime simulation *mode* for arbitrary workflows
(simulation today is labelled fixtures/scenarios, not a sandbox
switch); failure injection; agent-behaviour evaluation.
*Risks:* the pack says integrate P-14/P-15, not rebuild them; a
global simulation switch is dangerous if it can leak into
production paths — the codebase's precedent keeps simulation at
the adapter boundary (FakeProvider), and this feature should too.

### 7.9 Backup & Disaster Recovery — READY

*Reuse:* the mechanism this review exercised in §5 — verified
creation, tamper-evident verification, approval-guarded restore
preview, rehearsed manual restore; P-15's stale-backup detection.
The single-SQLite-file design works in the feature's favour:
database, memory vectors, configuration, workflows and audit all
live in the one file, and — verified by design inspection — a DB
backup contains **no secret values** (the registry stores metadata
only; values live in the owner's environment). *Missing:*
scheduled and incremental backups; destinations beyond the local
`backups/` folder (external drive, network, optional encrypted
cloud); backup-file encryption; coverage of state outside the DB
(logs, built frontend, workspace files); an automated restore
execution; a bootstrap recovery path for when the application
cannot start at all. *Risks:* lowest architectural risk in the
pack; the work is extension of a proven mechanism.

### 7.10 Notification & Approval Center — READY (in-app); delivery CONDITIONAL

*Reuse:* approvals are already the system's single spine —
`ApprovalService`, `/approvals` routes and the Approvals view are
used by every governed flow in 18 phases; P-11's derived
notifications with read/dismiss state
(`dashboard_notification_states`); the `security_alerts`
register; P-15 incidents; the typed EventBus with subscribers and
dead letters to source events from. *Missing:* a unified centre
view (notifications currently live inside the dashboard
derivation); priority classes and quiet-hours policy; delivery —
desktop push, email, mobile. P-17/P-18 communications
queue-but-never-send *by design*: no transport exists.
*Condition:* the pack requires external channels to ride the
Universal Integration Framework with user authorization — so
external delivery is sequenced after §7.2, and desktop
notification needs the owner's Windows machine. *Risks:* the pack
is explicit — do not create a separate approval authority; the
work is presentation, policy and delivery over the existing
service, preserving the codebase's discipline that notification ≠
approval ≠ execution.

### 7.11 Unified Orchestration Enhancement — LAST BY DESIGN

*Reuse:* most of the unified task model already exists — P-01
tasks carry id, objective, source, assignment, state and results;
P-12 adds DAG dependencies, retries, timeouts, cancellation and
approval pauses; P-13 coordinates across businesses; resource
tracking exists in pieces (P-15 sampler, P-05 task cost records).
*Missing:* the cross-feature workflows themselves — they cannot
exist until features 1–10 do (the pack's §9 end-to-end chain needs
Research, Voice/Windows Control and the Notification Center);
system-wide *enforced* resource budgets (P-12's caps are recorded
evidence, not enforced quotas — a carried P-12 limitation).
*Risks:* the pack and the §3 rules are explicit that this is an
integration enhancement, **not a new orchestration engine**; the
failure mode to avoid is rebuilding what P-01/P-12/P-13 already
do. Correctly scoped as contracts, gap-closing and end-to-end
tests — and correctly last.

---

## 8. Verdict

### Gate 1 — PASS
Original OS complete (P-01 → P-18, beyond the pack's P-16/P-17
formulation) and all existing acceptance tests pass, re-verified
today: backend 953/953, frontend 52/52, TypeScript clean.

### Gate 2 — CONDITIONAL PASS

Every criterion the pack names for Gate 2 is evidenced in this
report: architecture map (§1), API contracts (§2), database
inventory (§3), permission model (§4), and **backup verified by
exercise, including a real restore boot** (§5). No architectural
blocker was found: there are no competing authorities to reconcile
(finance, security, memory, scheduling, customers each have
exactly one owner), and every feature has a clean seam to attach
to (§1.4). The pass is conditional on three standing conditions —
none is a code defect, and none blocks starting the first feature:

1. **Windows condition (DEF-A1).** Windows Computer Control
   cannot be implemented or verified from this Linux staging VM
   at all, and PC & System Management's controls and much of its
   telemetry are in the same position. Those features require the
   owner's Windows machine whenever they are started; their
   acceptance evidence can only be produced there.
2. **Real-model condition (DEF-A2).** No real LLM has ever been
   exercised. Voice Assistant and the Research & Verification
   Engine can be built against the existing provider interface,
   but their real-model acceptance evidence requires a model pass
   on the owner's machine (CPU-only hardware bounds the choice).
3. **Process condition (pack §6).** This review authorizes
   nothing by itself: features proceed **one at a time**, each
   with its own owner go-ahead after review of the previous
   feature's evidence. The recommended first feature is
   **Identity & Device Security** (§7.1 — READY).

**Non-blocking findings recorded for the features that own them:**
four API-contract inconsistencies (§2 → Universal Integration
Framework); the corrected money-column invariant (§3 — no second
ledger or balance of record exists; the looser "no money columns
outside P-07" slogan should be retired); two documentation defects
(§5 — a stale restore-procedure pointer in `backup.py`'s
docstring); MFA recovery codes absent (§7.1 scope); the
un-root-caused P-17 boot-window login observation (§7.1
re-check).

### The pack's §7 distinction, carried forward

This verdict concerns the *assistant surface* only. Identity,
voice, desktop control, integrations, file intelligence, research,
QA, backup, notifications and orchestration make AUTONOMUS a
better personal computer assistant; they do not by themselves
make it a reliable money-making system. That question is answered
only by the business engines' real outcomes — verified collected
revenue, real expenses, real profit — measured in P-07, and it
remains open: DEF-A8 stands (no real pilot opportunity has yet
travelled the governed path). Expansion readiness must never be
reported as business readiness.

### Stop rule

This review built nothing. No expansion feature was started.
**Identity & Device Security begins only on the owner's explicit
go-ahead**, as will each feature after it.


