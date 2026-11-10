# P-12 API Reference — `/api/v1/operations`

All routes use the standard envelope `{success, data, error,
correlation_id, meta}` and P-01 authentication. READ =
`read_business_data`, WRITE = `modify_business_data`, GOVERN =
`approve_actions` (the service enforces finer owner-only rules for
settings, autonomy policies, dead-letter resolution and emergency
resume regardless of the route gate).

## Engine

| Route | Gate | Notes |
|---|---|---|
| `GET /operations/status` | READ | Engine status: loop running, settings version. |
| `GET /operations/settings` | READ | Owner-governed engine settings. |
| `PATCH /operations/settings` | GOVERN | Owner-only in service; bounds validated (tick ≥ 5s, levels 0–4, ceilings ≥ 1). |
| `GET /operations/overview` | READ | Workflow/task counts, pending approvals, dead letters, engine state. |
| `GET /operations/safety` | READ | P-10 security mode, Constitution mode, financial suspension, paused businesses, policy rows. |
| `POST /operations/scheduler/tick` | GOVERN | One scheduler pass (approvals, triggers, starts, resumes). Idempotent. |

## Workflows

| Route | Gate | Notes |
|---|---|---|
| `GET /operations/workflows` | READ | Filters: `business_id`, `status`, `origin`, `limit`, `offset`. Agents see only their business/own. |
| `POST /operations/workflows` | WRITE | 201. Body: definition, or `template`, or `source_plan_id` (P-02 import). Agent-created workflows are scoped to the agent's business. |
| `GET /operations/workflows/{id}` | READ | Detail: tasks, checkpoints, history. |
| `PATCH /operations/workflows/{id}` | WRITE | DRAFT-only definition/objective edits; new version row. |
| `DELETE /operations/workflows/{id}` | WRITE | DRAFT/INVALID/CANCELLED only. |
| `POST /operations/workflows/{id}/validate` | WRITE | → READY or INVALID with the problem list. |
| `POST /operations/workflows/{id}/start` | WRITE | Start + drive. |
| `POST /operations/workflows/{id}/pause` | WRITE | Agents: own workflows only. |
| `POST /operations/workflows/{id}/resume` | WRITE | Resume + drive (pipeline re-runs). |
| `POST /operations/workflows/{id}/cancel` | WRITE | Agents: own workflows only. |
| `POST /operations/workflows/{id}/reassign` | WRITE | Body `{task_id, agent_id}` — eligibility re-validated. |
| `GET /operations/workflows/{id}/decisions` | READ | The workflow's decision records. |
| `GET /operations/templates` | READ | The deterministic template catalogue. |

## Approvals, autonomy, triggers

| Route | Gate | Notes |
|---|---|---|
| `GET /operations/approvals` | READ | Links into the P-01 store with live approval states. Decisions are made via P-01's approval routes / the P-11 Approvals view. |
| `POST /operations/approvals/check` | GOVERN | Resolve links: verify bindings, complete spends via P-07, drive released workflows. |
| `GET /operations/autonomy/policies` | READ | All policy rows. |
| `POST /operations/autonomy/policies` | GOVERN | Owner-only in service. Body: `scope_type`, `scope_ref`, `agent_ref`, `max_level`, `action_caps`, `reason`. |
| `POST /operations/autonomy/resolve` | READ | Resolution preview with the full ceiling trace. |
| `GET /operations/triggers` | READ | Trigger list. |
| `POST /operations/triggers` | WRITE | Agent-created triggers start workflows as DRAFT only. |
| `PATCH /operations/triggers/{id}` | WRITE | Status/schedule updates. |
| `DELETE /operations/triggers/{id}` | WRITE | |

## Operations views and safety

| Route | Gate | Notes |
|---|---|---|
| `GET /operations/businesses/{business_id}` | READ | Per-business operations view (workflows, budget state via P-07, recent decisions). |
| `GET /operations/agents` | READ | Agent operations: assignments, completions, failures, success rates, autonomy rows. |
| `GET /operations/decisions` | READ | Decision records across workflows (filters: workflow, business). |
| `GET /operations/recovery` | READ | Dead letters, recovery records, circuit breakers, checkpoint count. |
| `POST /operations/recovery/dead-letter/{id}/resolve` | GOVERN | Owner-only in service. Body `{resolution}`. |
| `POST /operations/emergency/stop` | GOVERN | Body `{scope: global\|financial\|business\|agent, scope_ref}`. Composes P-10/P-08/P-04/P-05. |
| `POST /operations/emergency/resume` | GOVERN | Owner-only in service. Same body shape. |
| `GET /operations/reports` | READ | Generated operational reports. |
| `POST /operations/reports` | WRITE | Generate from live data (`operations_summary`). |
