# P-00 Deliverable E — Database Architecture

## Strategy

SQLite first (single-file, zero-admin, local-first), accessed only through the Core OS data layer (agents never touch the DB directly). **Versioned migrations from the first table (P-01)** so the PostgreSQL migration is a replay, not a rewrite. PostgreSQL trigger points: multi-process writers, multi-machine operation (P-13), or measured SQLite contention. Vector data lives in ChromaDB behind the Memory interface; everything factual lives in SQLite.

## Entities (proposal — purpose · relationships · lifecycle · classification)

| Entity | Purpose & key relationships | Lifecycle | Classification |
|---|---|---|---|
| users | Owner + any operators; owns everything | Permanent | Restricted |
| agents | Registry: role, parent, business, model profile, permissions, budget, status → tasks, runs | Created → Configured → Active → Paused → Reassigned → Terminated (transitions recorded) | Internal |
| agent_capabilities | Tool permissions per agent (checked by Policy Layer) | With agent | Restricted |
| missions | Owner-level objectives → plans | Open → Completed/Closed | Internal |
| plans | Decomposition of a mission → tasks, decision records | Draft → Approved → Executing → Done | Internal |
| agent_tasks | Persistent queue items → tool_executions; survives restart | Queued → Running → Done/Failed/Retrying | Internal |
| tool_executions | Every tool call: agent, tool, inputs hash, result, cost, duration | Append-only | Internal |
| opportunities | Discovery records **with evidence**, score components, risk gate, status | Discovered → Evaluated → Testing/Rejected/Archived (dedup enforced) | Internal |
| business_experiments | Pre-declaration (hypothesis, criteria, budget, duration, min test volume) → outcome vs declaration | Declared → Running → Judged (scale/optimise/pause/close) | Internal |
| businesses | Independent units: director, plan, budget, ledger link, status | Discovered → … → Scaling / Paused / Closed (records preserved on closure) | Internal |
| financial_accounts | Read-only account/wallet connections (no keys stored — references to secure storage only) | Connected → Suspended | **Confidential** |
| transactions | Append-only ledger events: type (expected/booked/invoiced/collected/refunded/expense), amount, currency, source evidence | Immutable — corrections are new compensating entries, never edits | **Confidential** |
| expenses / revenue_records | Classified views over transactions per business | With transactions | Confidential |
| customers | Business-scoped customer records (isolation enforced) | Active → Closed (retention rules apply) | Confidential (PII) |
| products | Per-business catalogue, pricing history | Draft → Live → Retired | Internal |
| projects | Work containers linking plans/tasks/artefacts | Active → Archived | Internal |
| permissions | Role/tool/business permission definitions (governance-owned) | Versioned | Restricted |
| approvals | L2–L4 approval requests + owner decisions + reasons | Pending → Approved/Rejected/Expired | Restricted |
| audit_events | Append-only: actor, action, target, decision, reason, correlation ID | Immutable, retained across closures | Restricted |
| memories | Typed records: fact / assumption / prediction / lesson, with evidence links + confidence | Active → Superseded (never silently rewritten) | Internal |
| system_configurations | Non-secret config; secrets referenced, never stored | Versioned | Restricted |

## Persistence & lifecycle rules

- Financial and audit records are **append-only**; historical events are never overwritten by any agent or service account used by agents.
- Closing a business archives, never deletes: financial records, obligations, customer records under retention, audit logs (Constitution §6.2).
- Backups are filesystem-level, before major upgrades, stored outside git (see `.gitignore`: `backups/`, `data/`, `*.db` excluded).
- SQLite → PostgreSQL migration plan: (1) migrations framework from P-01; (2) no SQLite-specific SQL outside the data layer; (3) types chosen from the portable subset; (4) migration rehearsed on a copy before any production switch (the owner's ClipOS Phase 11 audit proved a full upgrade/downgrade/re-upgrade chain on PostgreSQL — that same rehearsal standard applies here).
