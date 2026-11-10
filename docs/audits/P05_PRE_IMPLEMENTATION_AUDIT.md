# P-05 Pre-Implementation Audit — Universal Digital Execution Engine

**Stage 1 of the P-05 prompt (§3), executed before any implementation code.**
Baseline test run recorded first, per the phase discipline of P-02–P-04:
the full existing suite was re-run in this staging workspace before the
audit began — **230/230 passed** (P-01: 76, P-02: 35, P-03: 61, P-04: 58;
one pre-existing Starlette TestClient deprecation warning). Migration head
at audit time: `a694abea811f` (P-04), 35 tables.

**Environment statement (decided in advance, recorded here, not
relitigated):** staging is a **Linux sandbox**, not the owner's Windows
machine (i7-4712HQ / 16 GB / CPU-only — see
`docs/reports/AI_HARDWARE_FEASIBILITY.md`). Per the prompt's own rules
(§30 final rule, §30 rule 22, §32), an adapter that cannot be safely
supported *and tested in this environment* gets its interface implemented,
its limitation documented, and stays **disabled**. Nothing in this audit
claims a Windows capability that was not exercised here.

---

## 1. Existing execution capabilities

There is **no execution engine** in the codebase today. What exists:

| Capability today | Where | Nature |
|---|---|---|
| Governed task handlers `core.noop / core.echo_check / core.health_snapshot / core.wait` | `backend/app/tasks/handlers.py` | In-process, payload-validated, no external effects. `os.system` as a handler name is rejected (P-01). |
| `opportunity.research` handler | `backend/app/opportunities/service.py`, registered in `app/core/application.py` | The one real external-effect path: governed web/RSS/seed research through SSRF-guarded adapters, executed only as a P-01 task. |
| SSRF-guarded HTTP fetch (`HttpTransport`, `assert_url_allowed`, `MockTransport`, robots respect, size cap, TLS never disabled) | `backend/app/opportunities/sources.py` | Proven in P-03 with live fetches and tests. **This is the network heritage P-05 reuses** for its API adapter and browser read path. |
| Agent assignment → P-01 task execution with output contracts | `backend/app/agents/service.py` (`assign`, `refresh_assignment`) | Agents already receive work and return contract-validated results — but only against the in-process handlers above. |
| Shared model router (single instance, bound by reference) | `backend/app/intelligence/router.py`, bound in `app/agents/resources.py` | P-05 needs no model inference of its own; none is added. |

There is **no** filesystem tool an agent can invoke, **no** subprocess/code
execution anywhere, **no** browser automation, **no** desktop automation,
**no** generic HTTP client outside the P-03 research transport. A grep for
`subprocess`, `os.system`, `playwright`, `selenium`, `pywinauto` across
`backend/app/` returns nothing outside comments/tests that assert their
absence.

## 2. Existing components that can be reused (verified in code)

| Component | File | P-05 use |
|---|---|---|
| Task engine (`TaskManager.submit/get/cancel`, bounded queue, idempotency keys, recovery) | `app/tasks/manager.py` | Execution requests may link a real P-01 task (`task_id`); P-05 does **not** build a second task queue. The execution scheduler governs adapter concurrency, not task execution. |
| Permission engine (deny-by-default, explicit deny wins, every check audited) | `app/permissions/engine.py` | All API authorization and the enforcement mirror for capability grants. Unchanged. |
| Hash-bound approvals (`ApprovalService.create/decide/verify_binding`, expiry enforced on read) | `app/permissions/approvals.py` | **The** approval system for Risk-2 execution (§17: no second system). An execution approval binds `action="execution.execute"` + request id + a hash of the exact action parameters — parameter drift fails `verify_binding` and the request cannot execute. |
| Capability catalogue + grant ledger + grant flow (Level 0–3, owner-decided Level-2 approvals, drift detection) | `app/agents/capabilities.py`, `app/agents/constants.py` | The capability validator for execution. P-05 flips `supported` for the capabilities it genuinely backs (§6 below) so they become grantable **through the same flow** — no side door. |
| Factory settings pattern (owner-only JSON in `system_config`, audited updates) | `app/agents/service.py` (`get_settings`/`update_settings`), key `agent_factory.settings` | P-05 mirrors it exactly with key `execution.settings` for execution ceilings and the emergency-stop flag. |
| Agent factory emergency stop (deterministic, owner-only, safe-mode flag + audit + event) | `app/agents/service.py` (`emergency_stop`) | Pattern for the P-05 execution emergency stop (§23.7). P-05's stop is scoped to execution; it does not alter factory state. |
| Agent lifecycle states (`ASSIGNABLE_STATES = {active, idle, busy}`) | `app/agents/lifecycle.py` | Policy check: only assignable agents may execute. |
| Resource monitor + admission guard | `app/monitoring/system_monitor.py` | Scheduler reads host pressure; pressure is always *reported*, blocking follows the same semantics as P-01/P-04. |
| Audit trail (`audit_events`, append-only API) and event bus with persisted critical events | `app/database/models/core.py`, `app/events/` | Execution audit is written to `audit_events` (see §7 decision: **no** `execution_audit_events` table). New execution event types join the bus; security-relevant ones join the persisted-critical set. |
| Auth (owner password/scrypt sessions, service token, dev token; NO agent credential exists) | `app/core/auth.py` | API identity. Consequence (§5 risk): an "agent" cannot authenticate to the API directly — agent-originated execution requests arrive via a principal acting for the agent, and the engine verifies `agent_id` server-side against the registry and the caller's rights (see plan §4). |
| Settings (`AUTONOMUS_` env, redacted logging) | `app/core/config.py` | P-05 adds additive fields only (workspace root, ceilings defaults). |
| Repository + service + route conventions, API envelope (`ok`/`page`), typed errors | `app/database/repositories/`, `app/api/` | Followed exactly by the new `execution` package. |

## 3. Missing execution capabilities (what P-05 must build)

1. Execution request/run/evidence data model (§19 entities) and the
   requested → approved → executed → verified four-fact record (§6).
2. Deterministic execution policy engine: risk classification 0–3 (§8),
   the ten §8.1 checks, standing authorizations (§17).
3. Tool registry (§7) with lifecycle + health, and the adapter manager.
4. Filesystem adapter with managed workspaces and platform-first path
   validation (§9) — including Windows rules enforced on Linux.
5. Code execution adapter with process controls (§10) — honestly labelled.
6. API adapter over the SSRF-guarded transport pattern (§13) + credential
   broker interface (§13.3).
7. Browser session/policy layer (§11) — backend reality decided in §5.
8. Desktop adapter interface (§12) — disabled here (§5).
9. Document/data operations (§14) on stdlib only.
10. Workflow engine: validated definition DATA, persistent runs,
    checkpoints, idempotency, compensation, restart recovery (§§15–16).
11. Execution scheduler with configurable ceilings (§§18/26), execution
    emergency stop (§23.7), startup health report (§27), metrics (§24).

## 4. Existing security controls

Deny-by-default permissions with per-check audit; hash-bound, expiring
approvals; capability Levels 0–3 with Level 3 structurally prohibited (no
approval path exists); per-agent grant ledger mirrored into the permission
engine (explicit deny wins); owner-only governance surfaces (settings,
scoring config, model profiles, factory limits — Article 0); SSRF guard +
robots respect + size caps on the one existing fetch path; loopback-only
default bind; secrets never logged (`Settings.redacted_dict`, log scrubber
seeded with configured secret values); audit append-only by API surface;
mode gates (simulation blocks live fetch in P-03; emergency blocks P-04
creation/assignment). P-05 inherits all of these and adds none that weaken
them.

## 5. Security vulnerabilities, limitations, and the browser decision

- **No OS-level sandbox exists anywhere in this codebase**, and this Linux
  sandbox offers no Windows isolation primitives (Job Objects, restricted
  tokens, Windows Sandbox are Windows-only). The code adapter (§10) can
  therefore only ever be *process controls* here — timeout, process-tree
  kill, scrubbed environment, jailed working directory, size caps. §10.2
  forbids calling that a strong sandbox; P-05 labels it
  `process_controls_only` in the registry, the health report and every doc.
  Policy consequence: the code capability is granted only through the
  owner-approved Level-2 flow, a deterministic dangerous-pattern screen
  (§10.4) escalates flagged code to hash-bound approval, and arbitrary
  untrusted code is never a grantable concept.
- **Browser engine — evidence-based decision (Stage-1 experiment).**
  Playwright 1.64.1's Python package **installed successfully** from PyPI.
  Its Chromium binary (~170 MB from `cdn.playwright.dev`) **did not
  download**: a 280-second `playwright install chromium` attempt through
  the sandbox egress proxy produced no payload (browser cache stayed at
  4 KB) and a direct CDN fetch returned 0 bytes — the sandbox egress
  cannot deliver the browser binary. No system Chromium/Chrome exists.
  The Playwright package was uninstalled again so the environment matches
  `requirements.txt`. **Decision:** a real browser engine is *not*
  runnable in this environment within reasonable effort. Per the brief and
  §32, P-05 implements the full browser session/policy layer (domain
  allowlists, redirect re-validation, auth-challenge state
  `REQUIRES_HUMAN_AUTHENTICATION`, injection containment) with two
  backends: a **fetch backend** (the proven P-03 SSRF-guarded transport)
  that genuinely performs read-only navigation/inspection/extraction and
  is what tests exercise, and an **interactive backend that reports itself
  unavailable** — click/type/submit actions therefore fail truthfully as
  adapter-unavailable in this environment, after passing policy and (for
  Risk-2 interact) approval gates. Live interactive browsing is DISABLED
  here and claimed nowhere.
- **Desktop automation (§12):** Windows UI Automation cannot exist on
  Linux. Interface + **DISABLED**; no `pywinauto`/`pyautogui` is installed
  (installing them here would be theatre — they cannot attach to a
  Windows desktop that does not exist in this sandbox).
- **Identity gap:** agents hold no API credentials (by design, §16.3 of
  P-04). The engine must therefore never trust a client-supplied
  `agent_id`: requests naming an agent require a principal with
  `manage_agents` (owner/service flows acting for the agent) **or** the
  owner; the agent's existence, lifecycle state and grants are verified
  server-side from the registry. This mirrors how P-04 assignments already
  work.
- **Audit is append-only by API, not cryptographically tamper-proof**
  (carried from P-01). The execution interface exposes audit reads only;
  a security test proves no execution endpoint can mutate audit rows.
- **Subprocess risk concentration:** P-05 introduces the codebase's first
  `subprocess` use (code adapter). It is confined to one module, uses an
  argv list (never a shell), an allowed-executable list (the venv's Python
  only), a scrubbed environment and a jailed temp directory.

## 6. Existing agent-to-tool interfaces

Today an agent's "tools" are the P-01 handler registry as seen through
P-02's `ToolRegistryView` (`app/intelligence/tools.py`) and the template
`tool_requirements.handlers` lists (P-04). P-05's tool registry (§7) is a
separate, execution-specific registry — it does not replace the handler
registry, because P-02 plans and P-04 assignments already depend on it.
The junction is the **capability**: P-04 templates may name capabilities;
P-05 tools declare the capabilities they require; the execution policy
checks the requesting agent's live grants through
`CapabilityService.has_capability`. The six catalogue entries P-04 left
`supporte
...[truncated 9119 chars]