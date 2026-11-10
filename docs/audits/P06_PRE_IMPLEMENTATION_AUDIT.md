# P-06 Pre-Implementation Audit — Business Creation Engine

**Date:** 2026-11-09 · **Author:** AUTONOMUS build (staging) · **Status:** Stage 1 of
P-06 §32, completed before any P-06 implementation code was written.
**Governing documents:** `docs/prompts/P06_PROMPT.md` (§§1–36) and the design
baseline `docs/reports/P06_PREPARATION.md`. Where the two disagree, the prompt
governs (§1 of this audit records the reconciliation).

**Baseline test result recorded before implementation:** the full suite was
re-run from `backend/` (`.venv/bin/python -m pytest tests -q`):

```
300 passed, 1 warning in 102.88s
```

The single warning is the pre-existing Starlette TestClient/httpx deprecation
warning, unchanged since P-01. Baseline: **300/300 green**.

---

## 1. Authority order and prep-pack reconciliation

Authority (unchanged since P-02): Article 0 (Supreme Principle) → official
Constitution v1.0 → P-06 prompt → P-06 preparation pack. The prep pack was
written against the real P-01–P-05 code and parent-verified; this audit
re-checked its claims against the code (see §3).

**Agreements (prep pack and prompt coincide — adopted as-is):**

1. A business template **is** a `WorkflowEngine` definition whose steps are
   P-05 execution requests; a step that cannot be expressed with a registered
   tool/action rejects the template at validation. No new execution path.
2. Templates are versioned data, never code; businesses pin a template
   version.
3. Pre-declaration is a hard gate, judged against the declaration, never
   against checklist completion.
4. Platform gates are design: KDP publish ⇒ prepared package +
   `REQUIRES_HUMAN_ACTION`; publish defaults to draft/prepared.
5. Financial boundary shut: pricing is data; no money path; P-07 owns truth.
6. Per-business isolated workspace; cross-unit access is a named security
   test with a persisted critical violation event.
7. Deterministic-first acceptance: no LLM, no live platform, no interactive
   browser engine required.
8. No outreach / no auto-posting: `external_communication` stays
   ungrantable; acquisition output is plans and drafts only.
9. First seed template: digital product / ebook (the existing KDP track).

**Prompt overrides / refinements (prompt wins):**

1. **Minimum creation validation level.** The prep pack proposed "Level 3+
   as a locked default". The prompt (§6) requires the minimum to be an
   explicit eligibility criterion with the level computed by P-03. Adopted:
   the minimum lives in **owner-governed `system_config`**
   (`business.settings.min_validation_level`, default **3**), mirroring the
   P-03 scoring-config and P-04/P-05 settings pattern — never hardcoded,
   never agent-editable. The prep pack's substance (3+) stands; the
   mechanism follows the prompt's configurability requirement.
2. **Readiness outcomes.** The prep pack spoke loosely of "READY".
   §20 defines five results — `READY`, `READY_WITH_WARNINGS`, `NOT_READY`,
   `BLOCKED`, `OWNER_REVIEW_REQUIRED` — adopted exactly.
3. **Lifecycle.** The prep pack sketched a short happy path. §19's full
   state set and transition discipline is implemented exactly (see §7).
4. **Fixture rule sharpened.** The prompt's honesty test is stronger than
   the prep pack: fixture levels must be **computed by P-03's machinery
   from evidence stored through P-03's own API**, never asserted. Adopted
   verbatim (see §4).

**Gaps found in the prep pack (closed by the prompt or by this audit):**

1. The prep pack did not address §21 (agent conflicts: an agent never
   approves its own critical deliverables). Closed: approvals are the P-01
   hash-bound service and P-06 additionally requires the launch/creation
   approver to be an **owner principal** who is not the requesting agent.
2. The prep pack did not specify the declaration's approval mechanics.
   Closed in §5 below (P-01 `ApprovalService`, action `business.declaration`).
3. The prep pack did not flag the P-05 workspace-authorisation caveat in
   §6 below. P-06 enforces per-business isolation in its own service layer.

---

## 2. P-01 Core OS — reusable systems (verified in code)

| Capability | Home | P-06 use |
|---|---|---|
| Hash-bound approvals | `app/permissions/approvals.py` `ApprovalService.create/decide/verify_binding` (SHA-256 over canonical {action, resource, parameters}) | Creation approval, declaration approval, blueprint approval, launch approval — **no `business_approvals` table** (see §5) |
| Permissions (deny-by-default, audited) | `app/permissions/engine.py`; business permissions already exist in the catalogue: `read_business_data`, `modify_business_data`, `approve_actions`, `manage_agents`, `request_financial_operations` | Route guards + service checks |
| Audit trail | `app/database/models/core.py` `AuditEvent`; every prior service audits allow/deny | Every P-06 decision audited |
| Events | `app/events/events.py` `EventType` + `CRITICAL_EVENT_TYPES` persisted to `system_events` by `app/events/subscribers.py` | New business event types; isolation-violation and publish-refused events join the critical set |
| Owner-governed config | `system_config` via `ConfigRepository` (P-03 scoring, P-04/P-05 settings pattern) | `business.settings` (minimum validation level, defaults) |
| Modes | `Settings.mode` ∈ simulation/supervised/controlled/emergency, enforced by P-05 policy | P-06 checks mode for creation (emergency ⇒ halted; simulation ⇒ drafts only) |
| Task engine | P-01 tasks, registered handlers only | Traceability for research runs of fixtures (P-03 handler) |

## 3. P-02 Master Intelligence — reusable systems

- `missions` / `decision_records` give traceability: P-03 opportunities may
  carry a `mission_id`; P-06 records creation/readiness decisions through
  the same decision-record pattern used by P-03 (via the intelligence
  service's record path where a mission exists) and always through audit +
  lifecycle events. No planner changes: P-06 is deterministic and does not
  ask the planner to invent business steps — templates are data (§7 of the
  prompt: "business instructions must become structured data").
- Model profiles are **not** used: no LLM exists in this environment and
  P-06 generation is deterministic templating from stored data, labelled as
  such (§22 compliance).

## 4. P-03 Opportunity Discovery — the only input source

Verified in `app/opportunities/`:

- `OpportunityService.validate()` **computes** the level from stored
  evidence (`validation.assess_level`), stores a `ValidationRecord`, and
  refuses claimed levels above the justified level with 422. P-06 calls
  this — the level is never asserted by P-06.
- `score()` stores dimensions, evidence quality, risk classification and
  `hard_rejection` (prohibited models, fake reviews/testimonials,
  deceptive claims, prohibited products, budget incompatibility at
  discovery). P-06 eligibility reads the latest score.
- `run_commercial_analysis()` stores startup/recurring/variable costs,
  price, fees and budget compatibility — the §6 "estimated startup
  requirements" input and the §9 financial-input source.
- `report()` aggregates opportunity + evidence + analyses + score +
  validation — used by eligibility and by blueprint generation.
- Research runs only as P-01 tasks via the `opportunity.research` handler —
  fixture construction uses exactly this path (evidence stored through
  `add_evidence`, research through the task engine, analyses through the
  service).

**Honesty fact (load-bearing):** the three real staging investigations
(e-book, planner, India GST tool) concluded at **Validation Level 1 —
REQUIRES MORE RESEARCH**. With the default minimum of 3, the §6 gate must
block all of them. Scenario D demonstrates this first; fixture opportunities
(clearly labelled, evidence through P-03 machinery) carry the acceptance
scenarios that need a qualifying opportunity.

## 5. Approvals reuse decision (§23's conditional table)

§23 lists `business_approvals` *only if* the central service cannot carry
business references. Audit finding: **it can.** `ApprovalService` binds
`action` + `resource` + arbitrary `parameters` by SHA-256; P-05 already
carries execution approvals this way (action `execution.request`,
resource = tool name), and P-04 carries creation approvals. Business
approvals use actions `business.create`, `business.declaration`,
`business.blueprint`, `business.launch` with `resource = business_id`
(or opportunity id pre-creation) and parameters binding the exact
opportunity/template-version/declaration/readiness-review ids. Drift
(changed template version, changed declaration, newer readiness review)
changes the hash and fails verification closed — the same property P-04/
P-05 rely on. **No `business_approvals` table is created.** P-06 adds one
guard the central service does not itself impose: for creation and launch,
the recorded approver must be an **owner principal** (checked from the
approval row's `approver_id` prefix and the deciding call's principal), so
an agent can never approve its own business (§21/§28.6).

## 6. P-05 Execution Engine — the only execution path, and one caveat

Verified in `app/execution/`:

- `ExecutionService.submit / submit_and_execute / execute` run the full
  gate chain (capability, workspace authorisation, mode, policy, hash-bound
  approval for risk ≥ 2) — P-06 creation steps inherit all of it.
- `WorkflowEngine` definitions are validated data (≤ 50 steps, unique ids,
  tool+action must resolve in the registry, `{{input.key}}` substitution is
  data-only). Template validation reuses `validate_definition` semantics by
  resolving every step against `ToolRegistry.action_spec`.
- Workspaces: `WorkspaceManager` roots live under
  `<data_dir>/execution_workspaces`; managed kinds include `businesses`.
  P-06 provisions one `ExecutionWorkspace` row per business
  (`business:<id>`, kind `businesses`, root `businesses/<id>/`) with the
  §18 subdirectories created by workflow `mkdir` steps.
- Adapter truth (carried, not hidden): filesystem/documents/code/API are
  OPERATIONAL (code isolation = `process_controls_only`); browser
  interactive actions return `ADAPTER_UNAVAILABLE`; desktop is DISABLED.
  Templates may therefore only use filesystem/documents (and, for the SaaS
  template, `code_python.run`) — validation rejects steps naming disabled
  or unavailable-interactive actions.

**Caveat (recorded honestly):** P-05's generic workspace authorisation for
kind `businesses`/`projects` accepts *any* non-empty `business_ref` for
writes and allows reads broadly. That is **not** per-business isolation.
P-06 therefore enforces isolation in its own service layer: before any
execution for a business, the acting agent must hold an active
`business_agent_assignments` row for *that* business, the workspace name is
pinned server-side to `business:<id>`, and cross-business attempts are
denied with a persisted critical `BusinessIsolationViolation` event
(Scenario G). P-05 is not modified; the stricter rule lives where the
business boundary is known.

## 7. Lifecycle, readiness, eligibility — prompt-exact semantics

- §19 states and transitions are implemented as data + a guard table in
  `app/business/lifecycle.py`; every transition writes
  `business_lifecycle_events` (actor, from/to, reason, approval reference).
  Guards: `BLUEPRINT_READY` requires a stored blueprint; `READY_FOR_LAUNCH`
  requires a latest readiness review of `READY`/`READY_WITH_WARNINGS`;
  `LAUNCHING` requires a verified owner launch approval; `OPERATIONAL`
  additionally requires the declaration to exist and the launch record to
  carry the staging truth fields (`deployment_state=local_package_only`,
  `public_availability=false`, `revenue_asserted=false`).
- §20 readiness: eight deterministic dimension evaluators (A–H) producing
  pass/warning/blocker findings with evidence references; hard blockers
  override any score; result precedence `BLOCKED` > `NOT_READY` >
  `OWNER_REVIEW_REQUIRED` > `READY_WITH_WARNINGS` > `READY`. The review
  carries the §20 disclaimer that legal/regulatory readiness is **not**
  independently certified.
- §6 eligibility: a pure evaluation over the P-03 report (status, computed
  level, hard rejection, evidence presence, customer/problem completeness,
  commercial analysis, compliance flags, budget compatibility, owner
  approval state) returning one of the six §6 decisions with per-check
  reasons; evaluations are persisted (`business_eligibility_evaluations`)
  and creation is impossible unless the fresh evaluation is
  `ELIGIBLE_FOR_CREATION` or `ELIGIBLE_WITH_CONDITIONS` **and** a verified
  owner creation approval is bound.

## 8. Financial boundary design (§9/§27)

- Financial figures exist only as **financial values**: {amount or range,
  currency, source, classification `estimate|verified`, confidence, date,
  assumptions}. The only permitted `verified` classifications are for
  *cost-side facts the owner recorded* (e.g. a domain price the owner
  paid); **revenue and profit can never be recorded as verified/collected
  by any P-06 path** — the schema has no such fields, the financial
  interface builder rejects them, and security test 11 proves it.
- All arithmetic (startup totals, break-even reuse) is deterministic code
  in `app/business/financial.py`; P-03's commercial analysis remains the
  source of estimates.
- The P-07 interface payload (per-business financial inputs) is buildable
  and validated, but nothing is *sent* anywhere — P-07 does not exist yet.

## 9. Security posture inherited and extended

Inherited: deny-by-default permissions, hash-bound approvals, secret-value
rejection in execution parameters (`reject_secret_values`), SSRF-guarded
transports (unused by P-06 — no outbound calls), workspace path safety,
append-only-by-API audit. Extended by P-06: per-business isolation (§6
above), generated-content secret redaction + scan, injection-bearing
opportunity text treated as data (gates unchanged), template validation
denylist (no money-moving constructs, no disabled tools, no
`external_communication`), mode checks (simulation ⇒ draft-only steps are
still refused side effects by P-05 policy; emergency ⇒ creation halted at
the P-06 gate too).

## 10. Risks and unknowns recorded before building

1. **RAM pressure on this VM** (>90% host RAM observed in P-04/P-05):
   agent creation may queue under the P-01 admission guard. Tests use the
   established `AUTONOMUS_BLOCK_NONESSENTIAL_ON_THRESHOLD=false` test
   setting (threshold machinery itself is tested separately in P-01/P-04).
2. **Playwright/Chromium unavailable** (P-05 finding): no template may
   depend on interactive browsing; website "verification" is local file
   verification via execution reads, never a browser claim.
3. **No LLM**: blueprint/asset text is deterministic templating from stored
   opportunity/template data and is labelled as generated-from-data; it is
   never independent evidence (§22).
4. **Windows unverified** (carried since P-01): all P-06 paths are
   platform-neutral (pathlib via P-05 workspaces); the operations guide
   documents the Windows setup honestly as untested.
5. **Fixture realism**: fixtures prove machinery, not market truth — the
   gate report will say so in those words.

**Audit conclusion:** reuse is sufficient for every cross-cutting concern;
P-06 adds one package (`app/business/`), one models module, one repository
module, one API router, new event types, one additive migration, and seed
template data. No existing table is altered; no existing service's contract
changes.
