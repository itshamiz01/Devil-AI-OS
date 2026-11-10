# Agent Factory Operations (P-04)

Day-to-day operation of the Dynamic Agent Factory. All endpoints are
under `/api/v1` and require authentication (owner session, dev token,
or service token as in P-01).

## Routine checks

| Check | Call |
|---|---|
| Fleet overview | `GET /agent-factory/status` — totals by status, safe mode, creation/assignment switches, pending approvals |
| Resource pressure | `GET /agent-factory/resources` — host snapshot, pressure level, violations, `blocking_enabled`, ladder actions, shared-inference bindings |
| One agent | `GET /agents/{id}` (+ `/permissions`, `/health`, `/metrics`, `/assignments`, `/events`, `/config-history`) |
| Creation decisions | `GET /agent-factory/requests?decision=REQUEST_OWNER_APPROVAL` |
| Dry-run a requirement | `POST /agent-factory/evaluate` (decision only, nothing persisted as an agent) |

## Common operations

- **Create an agent:** `POST /agent-factory/create {role}` (or
  `POST /agents`). Expect `CREATE_AGENT`, `REUSE_EXISTING_AGENT` or
  `ASSIGN_TO_EXISTING_AGENT` as healthy outcomes; `QUEUE_FOR_LATER`
  means a limit/pressure gate held it; `REQUEST_OWNER_APPROVAL` means
  a Level-2 capability, an intensive budget, or a non-owner requester.
- **Approve a creation:** `POST /agent-factory/requests/{id}/approve
  {approve: true}` — owner only. If the template changed since the
  request, approval fails closed (`approval parameters no longer
  match`): re-issue the creation request.
- **Grant a capability:** `POST /agents/{id}/permissions/request
  {capability}` then, for Level 2, `POST /agents/{id}/permissions/approve
  {approval_id, approve}` — owner only.
- **Revoke:** `POST /agents/{id}/permissions/revoke {capability}` —
  immediate; writes a deny rule into the permission engine.
- **Suspend / resume / retire:** `POST /agents/{id}/suspend|resume|retire`.
  Retirement is one-way and preserves all history.
- **Maintenance:** `POST /agent-factory/maintenance` — sweeps expired
  grants, suspends idle agents, reconciles degraded agents, recovers
  failed agents within the initialization cap.
- **Emergency stop:** `POST /agent-factory/emergency-stop
  {scope: "agent"|"all", agent_id?, reason}` — owner only, fully
  deterministic, no LLM. Fleet scope sets safe mode (creation +
  assignment blocked), suspends agents, cancels eligible tasks,
  revokes grants (single-agent scope). `POST
  /agent-factory/resume-operations` lifts safe mode; suspended agents
  are **not** auto-resumed.

## Factory settings (owner/governance only)

`GET|PATCH /agent-factory/settings`. Keys: `max_total_agents` (12),
`max_active_agents` (8), `max_agents_per_business` (4),
`max_child_agents_per_parent` (3), `max_delegation_depth` (3),
`max_concurrent_tasks_per_agent` (2), `max_concurrent_inference_requests`
(1 — CPU-only hardware), `creation_rate_limit_per_hour` (10),
`max_initialization_failures_per_template` (3),
`idle_suspend_seconds` (3600), `creation_enabled`, `assignments_enabled`,
`safe_mode`. Non-owner writes are refused and audited.

## Windows setup

The factory ships inside the existing backend — no new services, no
new dependencies.

1. Use the P-01 Windows setup (`scripts/` PowerShell starters,
   `docs/reports/P01_IMPLEMENTATION_REPORT.md`): Python 3.12 venv,
   `pip install -r requirements.txt`, environment via `AUTONOMUS_*`
   variables (notably `AUTONOMUS_ADMIN_PASSWORD`).
2. Start the backend (`scripts/start_backend.ps1`); startup runs
   Alembic migrations automatically (`auto_migrate`), including
   `a694abea811f` (P-04), and seeds the capability catalogue + 10
   templates idempotently.
3. Sign in as owner and check `GET /agent-factory/status` — expect
   `total_agents: 0`, `safe_mode: false`, 10 published templates at
   `GET /agent-templates`.
4. Hardware note: on the owner's machine (i7-4712HQ / 16 GB / CPU-only
   inference) keep `max_concurrent_inference_requests = 1` and the
   default fleet ceilings; install Ollama separately for P-02's first
   real-model verification (carried item, not a P-04 dependency).

## Troubleshooting

- *Every creation returns QUEUE_FOR_LATER with "resource pressure"* —
  the host is genuinely over a monitor threshold and admission
  blocking is enabled (production default). Check
  `GET /agent-factory/resources`; free memory/CPU or, if deliberate,
  set `AUTONOMUS_BLOCK_NONESSENTIAL_ON_THRESHOLD=false` (the P-01
  switch) — pressure remains visible either way.
- *Approval returns "parameters no longer match"* — the template was
  re-published or the capability set changed after the request; the
  hash-bound approval is stale by design. Re-issue the request.
- *Agent stuck FAILED after creation* — read the initialization
  failure in the creation request; after 3 failures for a role the
  factory refuses further attempts until the template/config is fixed
  (Scenario F protection).
